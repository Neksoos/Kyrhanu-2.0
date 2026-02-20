from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import engine
from app.core.init_db import ensure_schema

from app.api.deps import get_db
from jose import JWTError, jwt
from app.models.user import User
from app.models.wallet import Wallet

from app.api.routes_auth import router as auth_router
from app.api.routes_daily import router as daily_router
from app.api.routes_achievements import router as ach_router
from app.api.routes_me import router as me_router
from app.api.routes_runs import router as runs_router
from app.api.routes_inventory import router as inv_router
from app.api.routes_shop import router as shop_router
from app.api.routes_tutorial import router as tutorial_router

from routers.professions import router as professions_router
from routers.alchemy import router as alchemy_router
from routers.blacksmith import router as blacksmith_router
from routers.craft import router as craft_router
from routers.items import router as items_router, router_public as items_router_public
from routers.craft_materials import router as craft_materials_router, router_public as craft_materials_router_public


app = FastAPI(title=settings.APP_NAME)


def get_optional_user_id(request: Request) -> str | None:
    """Best-effort user extraction for legacy compatibility routes.

    Older web clients may call `/api/profile`, `/api/city-entry`, `/api/npc/spawn`
    without Authorization headers while bootstrapping. Returning 401 in this phase
    creates noisy logs and breaks initial loading. For those compatibility routes we
    decode bearer JWT if present, otherwise continue as anonymous.
    """
    auth = (request.headers.get("authorization") or "").strip()
    if not auth.lower().startswith("bearer "):
        return None

    token = auth.split(" ", 1)[1].strip()
    if not token:
        return None

    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        sub = payload.get("sub")
        return str(sub) if sub else None
    except JWTError:
        return None

origins = [o.strip() for o in settings.CORS_ALLOW_ORIGINS.split(",") if o.strip()]

# If CORS_ALLOW_ORIGINS is empty or "*", allow any origin (Telegram WebView + Railway previews).
if not origins or origins == ["*"]:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# --- Main routers ---
app.include_router(auth_router)
app.include_router(daily_router)
app.include_router(ach_router)
app.include_router(me_router)
app.include_router(runs_router)
app.include_router(inv_router)
app.include_router(shop_router)
app.include_router(tutorial_router)

# --- Profession/craft routers (legacy + mini-app) ---
app.include_router(professions_router)
app.include_router(alchemy_router)
app.include_router(blacksmith_router)
app.include_router(craft_router)
app.include_router(items_router)
app.include_router(items_router_public)
app.include_router(craft_materials_router)
app.include_router(craft_materials_router_public)

# ------------------------------
# Default / health
# ------------------------------
@app.get("/", tags=["default"])
def root():
    return {"ok": True, "service": "cursed-kurgans"}


@app.get("/_ping", tags=["default"])
def ping():
    return {"ok": True}


@app.get("/healthz", tags=["default"])
async def healthz():
    db_ok = True
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {"ok": True, "dbOk": db_ok}


@app.on_event("startup")
async def on_startup():
    await ensure_schema()


# ------------------------------
# Legacy /api/* compatibility
# (старі фронти: /api/profile, /api/city-entry, /api/npc/spawn)
# ------------------------------
@app.get("/api/profile", tags=["legacy"])
async def legacy_profile(
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Depends(get_optional_user_id),
):
    """
    Compatibility alias for older frontend builds.
    Expected by: /api/proxy/api/profile
    """
    if user_id:
        u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        w = await db.get(Wallet, user_id)
    else:
        u = None
        w = None

    return {
        "ok": True,
        "user": {
            "id": str(getattr(u, "id", user_id)),
            "email": getattr(u, "email", None),
            "telegram_id": getattr(u, "telegram_id", None),
            "telegram_username": getattr(u, "telegram_username", None),
        },
        "wallet": {
            "chervontsi": int(getattr(w, "chervontsi", 0) or 0),
            "kleidony": int(getattr(w, "kleidony", 0) or 0),
        },
    }


@app.get("/api/city-entry", tags=["legacy"])
async def legacy_city_entry(
    user_id: str | None = Depends(get_optional_user_id),
):
    """
    Stop-gap endpoint to prevent 404/401 for older clients.
    Expected by: /api/proxy/api/city-entry
    """
    return {"ok": True, "user_id": str(user_id) if user_id else None}


@app.post("/api/npc/spawn", tags=["legacy"])
async def legacy_npc_spawn(user_id: str | None = Depends(get_optional_user_id)):
    """
    Старий фронт викликає POST /api/npc/spawn (через /api/proxy).
    Тут мінімальний "заглушковий" респонс, щоб не валити гру 404-кою.

    IMPORTANT:
    - Ми повертаємо валідний JSON з ok=true.
    - Формат робимо максимально нейтральним: список NPC може бути пустим.
    """
    return {
        "ok": True,
        "user_id": str(user_id) if user_id else None,
        "npcs": [],  # можна наповнити пізніше, зараз головне прибрати 404
    }
