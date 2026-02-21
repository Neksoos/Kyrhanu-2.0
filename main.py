# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.db import engine
from app.core.init_db import ensure_schema

# SQLAlchemy-based app routers (залишаємо)
from app.api.routes_auth import router as auth_router
from app.api.routes_daily import router as daily_router
from app.api.routes_achievements import router as ach_router
from app.api.routes_me import router as me_router
from app.api.routes_runs import router as runs_router
from app.api.routes_inventory import router as inv_router
from app.api.routes_shop import router as shop_router
from app.api.routes_tutorial import router as tutorial_router

# Existing craft/profession routers (залишаємо)
from routers.professions import router as professions_router
from routers.alchemy import router as alchemy_router
from routers.blacksmith import router as blacksmith_router
from routers.craft import router as craft_router
from routers.items import router as items_router, router_public as items_router_public
from routers.craft_materials import router as craft_materials_router, router_public as craft_materials_router_public

# ✅ REAL Telegram Mini App routers (ОЦЕ ВАЖЛИВО)
from routers.auth import router as tg_auth_router
from routers.profile import router as tg_profile_router
from routers.city_entry import router as tg_city_entry_router
from routers.registration import router as tg_registration_router
from routers.npc_router import router as tg_npc_router

from db import ensure_min_schema  # asyncpg schema for players


app = FastAPI(title=settings.APP_NAME)

origins = [o.strip() for o in settings.CORS_ALLOW_ORIGINS.split(",") if o.strip()]

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

# --- SQLAlchemy app routers ---
app.include_router(auth_router)
app.include_router(daily_router)
app.include_router(ach_router)
app.include_router(me_router)
app.include_router(runs_router)
app.include_router(inv_router)
app.include_router(shop_router)
app.include_router(tutorial_router)

# --- craft/professions routers ---
app.include_router(professions_router)
app.include_router(alchemy_router)
app.include_router(blacksmith_router)
app.include_router(craft_router)
app.include_router(items_router)
app.include_router(items_router_public)
app.include_router(craft_materials_router)
app.include_router(craft_materials_router_public)

# ✅ Telegram Mini App real endpoints
app.include_router(tg_auth_router)         # /api/auth/*
app.include_router(tg_profile_router)      # /api/profile
app.include_router(tg_city_entry_router)   # /api/city-entry
app.include_router(tg_registration_router) # /api/registration/*
app.include_router(tg_npc_router)          # /api/npc/*

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
    # SQLAlchemy schema (users/wallet/etc)
    await ensure_schema()
    # asyncpg schema (players table)
    await ensure_min_schema()
