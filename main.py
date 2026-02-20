# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.db import engine
from app.core.init_db import ensure_schema

from app.api.routes_auth import router as auth_router
from app.api.routes_daily import router as daily_router
from app.api.routes_achievements import router as ach_router
from app.api.routes_me import router as me_router
from app.api.routes_runs import router as runs_router
from app.api.routes_inventory import router as inv_router
from app.api.routes_shop import router as shop_router
from app.api.routes_tutorial import router as tutorial_router

# ✅ NPC router (travelling NPC spawn/encounter)
from routers.npc_router import router as npc_router


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

# ✅ add NPC endpoints: /api/npc/spawn, /api/npc/{npc_key}/encounter, etc.
app.include_router(npc_router)


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