from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import engine
from app.core.init_db import ensure_schema

from app.api.deps import get_db, get_current_user_id
from app.models.user import User
from app.models.wallet import Wallet

# Optional/legacy endpoints used by older frontends
from routers.npc_router import router as npc_router

from app.api.routes_auth import router as auth_router
from app.api.routes_daily import router as daily_router
from app.api.routes_achievements import router as ach_router
from app.api.routes_me import router as me_router
from app.api.routes_runs import router as runs_router
from app.api.routes_inventory import router as inv_router
from app.api.routes_shop import router as shop_router
from app.api.routes_tutorial import router as tutorial_router


app = FastAPI(title=settings.APP_NAME)

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

app.include_router(auth_router)
app.include_router(daily_router)
app.include_router(ach_router)
app.include_router(me_router)
app.include_router(runs_router)
app.include_router(inv_router)
app.include_router(shop_router)
app.include_router(tutorial_router)

# --- Legacy /api/* compatibility layer ---
# Some clients call /api/profile, /api/city-entry, /api/npc/spawn
app.include_router(npc_router, prefix="/api/npc", tags=["npc"])


@app.get("/", tags=["default"])
def root():
    return {"ok": True, "service": "cursed-kurgans"}


@app.get("/_ping", tags=["default"])
def ping():
    return {"ok": True}


@app.get("/api/profile", tags=["legacy"])
async def legacy_profile(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Compatibility alias for older frontend builds."""
    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    w = await db.get(Wallet, user_id)
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
async def legacy_city_entry(user_id: str = Depends(get_current_user_id)):
    """Stop-gap endpoint to prevent 404s for older clients.

    Update the frontend to use the newer endpoints (e.g. /tutorial, /runs/*).
    """
    return {"ok": True, "user_id": str(user_id)}


@app.on_event("startup")
async def on_startup():
    await ensure_schema()


@app.get("/healthz")
async def healthz():
    db_ok = True
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {"ok": True, "dbOk": db_ok}