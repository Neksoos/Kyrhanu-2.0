"""Main entry point for the Kyhranu backend.

Production notes (P0):
- Auth must support BOTH Telegram Mini App (initData) and Browser (Telegram Login Widget)
  and resolve to ONE player account.
- Migrations must NOT be re-applied on every start (many SQL files are not idempotent).

This file wires routers, CORS, auth context middleware, and startup tasks.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from core.session import SESSION_COOKIE_NAME, create_session, resolve_session_tg_id
from core.tg_auth import extract_webapp_user, verify_webapp_init_data
from db import ensure_min_schema, fetch_player_by_telegram_id, get_pool, run_migrations

# ───────── ROUTERS ─────────
from routers.admin_auth import router as admin_auth_router
from routers.admin_notify import router as admin_notify_router
from routers.admin_players import router as admin_players_router

from routers.areas import router as areas_router
from routers.auth import router as auth_router
from routers.battle import router as battle_router
from routers.city import router as city_router
from routers.city_entry import router as city_entry_router
from routers.daily_login_router import router as daily_login_router
from routers.forum import router as forum_router

from routers.gathering import router as gathering_router
from routers.gathering_professions_ui import router as gathering_professions_ui_router

from routers.inventory import router as inventory_router
from routers.materials import router as materials_router
from routers.alchemy import router as alchemy_router
from routers.blacksmith import router as blacksmith_router

from routers.craft_materials import router as craft_materials_router
from routers.achievements import router as achievements_router

from routers.mail import router as mail_router
from routers.night_watch_api import router as night_watch_router
from routers.npc_router import router as npc_router
from routers.items import router as items_router
from routers.perun import router as perun_router
from routers.profile import router as profile_router
from routers.professions import router as professions_router
from routers.quests import router as quests_router
from routers.ratings import router as ratings_router
from routers.redis_manager import close_redis, get_redis
from routers.referrals import router as referrals_router
from routers.registration import router as registration_router
from routers.tavern import router as tavern_router
from routers.tavern_chat import router as tavern_chat_router
from routers.zastava import router as zastava_router
from routers.zastavy_chat import router as zastavy_chat_router

from routers.stars_shop import router as stars_shop_router
from routers.telegram_webhook import router as telegram_webhook_router

from routers.premium import router as premium_router
from routers.premium_subs import router as premium_subs_router
from routers.players_mini import router as players_mini_router

from seed_craft_materials import seed_craft_materials
from seed_equipment import seed_equipment_items
from seed_gathering_resources import seed_gathering_resources
from seed_junk_loot import seed_junk_loot

APP_VERSION = os.getenv("APP_VERSION", "dev")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN")

app = FastAPI(title="Kyhranu API", version=APP_VERSION)

# ─────────────────────────────────────────────
# CORS
# ─────────────────────────────────────────────
allowed_origins = {
    "http://localhost:3000",
    "https://web.telegram.org",
    "https://telegram.org",
    "https://t.me",
    "https://kyrhanu-frontend-production.up.railway.app",
}
if FRONTEND_ORIGIN:
    allowed_origins.add(FRONTEND_ORIGIN)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(allowed_origins),
    allow_origin_regex=r"^https:\/\/([a-z0-9-]+\.)*(railway\.app|telegram\.org|t\.me)$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Init-Data",
        # Telegram webhook
        "X-Telegram-Bot-Api-Secret-Token",
    ],
)


# ─────────────────────────────────────────────
# ✅ AUTH CONTEXT MIDDLEWARE
# ─────────────────────────────────────────────

def _tg_id_from_query(request: Request) -> Optional[int]:
    raw = request.query_params.get("tg_id")
    if not raw:
        return None
    try:
        n = int(raw)
        return n if n > 0 else None
    except Exception:
        return None


class AuthContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1) Session cookie → internal tg_id
        try:
            sid_tg = await resolve_session_tg_id(request)
            if sid_tg:
                request.state.tg_id = int(sid_tg)
        except Exception:
            # don't crash on redis hiccups
            pass

        # 2) Telegram Mini App initData → telegram_id → player.tg_id
        if not getattr(request.state, "tg_id", None):
            init_data = request.headers.get("X-Init-Data")
            if init_data:
                try:
                    verified = verify_webapp_init_data(init_data)
                    user = extract_webapp_user(verified)
                    telegram_id = int(user["id"])
                    request.state.telegram_id = telegram_id
                    request.state.locale = (
                        user.get("language_code")
                        or verified.get("language_code")
                        or "uk"
                    )

                    player = await fetch_player_by_telegram_id(telegram_id)
                    if player:
                        request.state.tg_id = int(player["tg_id"])
                    else:
                        request.state.need_register = True
                except Exception:
                    # invalid/expired initData → treat as unauthenticated
                    pass

        # 3) Legacy query guard: if tg_id is present, it MUST match authenticated user.
        q_tg = _tg_id_from_query(request)
        st_tg = getattr(request.state, "tg_id", None)
        if q_tg and st_tg and int(q_tg) != int(st_tg):
            return JSONResponse(403, {"detail": "tg_id mismatch"})

        response = await call_next(request)

        # 4) Convenience: if authenticated via initData and no session cookie yet,
        # create one so browser flow can reuse cookies and avoid repeated initData.
        try:
            st_tg = getattr(request.state, "tg_id", None)
            if st_tg and not request.cookies.get(SESSION_COOKIE_NAME):
                await create_session(response, int(st_tg))
        except Exception:
            pass

        return response


app.add_middleware(AuthContextMiddleware)


# ─────────────────────────────────────────────
# ChatLevelGuard
# ─────────────────────────────────────────────
MIN_CHAT_LEVEL = 3


class ChatLevelGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        is_chat_write = request.method in ("POST", "PUT", "PATCH") and (
            path.startswith("/chat/tavern") or path.startswith("/api/zastavy/chat")
        )
        if not is_chat_write:
            return await call_next(request)

        tg_id = getattr(request.state, "tg_id", None)
        if not tg_id:
            return JSONResponse(401, {"detail": "Missing auth"})

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COALESCE(level,1) AS level FROM players WHERE tg_id=$1",
                int(tg_id),
            )

        if (row["level"] if row else 1) < MIN_CHAT_LEVEL:
            return JSONResponse(403, {"error": f"💬 Чат доступний з {MIN_CHAT_LEVEL} рівня"})

        return await call_next(request)


app.add_middleware(ChatLevelGuard)


# ─────────────────────────────────────────────
# STARTUP / SHUTDOWN
# ─────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    await get_redis()

    # Ensure base schema before migrations (fresh DB safety)
    try:
        await ensure_min_schema()
    except Exception as e:
        logger.warning(f"ensure_min_schema failed: {e}")

    await run_migrations()

    for fn in (
        seed_gathering_resources,
        seed_craft_materials,
        seed_equipment_items,
        seed_junk_loot,
    ):
        try:
            await fn()
        except Exception as e:
            logger.warning(e)


@app.on_event("shutdown")
async def shutdown_event():
    await close_redis()


@app.get("/health")
async def health():
    return {"ok": True, "version": APP_VERSION}


# ─────────────────────────────────────────────
# ROUTERS
# ─────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(city_router)
app.include_router(city_entry_router)
app.include_router(daily_login_router)
app.include_router(registration_router)
app.include_router(zastava_router)
app.include_router(profile_router)

app.include_router(players_mini_router)
app.include_router(premium_router)
app.include_router(premium_subs_router)

app.include_router(battle_router, prefix="/api")
app.include_router(professions_router)

app.include_router(gathering_router)
app.include_router(gathering_professions_ui_router)

app.include_router(inventory_router)
app.include_router(materials_router)
app.include_router(alchemy_router)
app.include_router(blacksmith_router)

app.include_router(achievements_router)
app.include_router(craft_materials_router, prefix="/api")

app.include_router(areas_router)
app.include_router(mail_router)
app.include_router(npc_router)
app.include_router(perun_router)
app.include_router(referrals_router)
app.include_router(tavern_chat_router)
app.include_router(zastavy_chat_router)
app.include_router(tavern_router)
app.include_router(ratings_router)
app.include_router(night_watch_router)

# Admin
app.include_router(admin_auth_router)
app.include_router(admin_notify_router)
app.include_router(admin_players_router)

# Stars + webhook
app.include_router(stars_shop_router)
app.include_router(telegram_webhook_router)

# Forum (browser-friendly)
app.include_router(forum_router)

# Items
app.include_router(items_router)

# Quests
app.include_router(quests_router)
