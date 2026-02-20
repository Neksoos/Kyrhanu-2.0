# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.db import engine
from app.core.init_db import ensure_schema

# ✅ V2 API (JWT)
from app.api.routes_auth import router as auth_router
from app.api.routes_daily import router as daily_router
from app.api.routes_achievements import router as ach_router
from app.api.routes_me import router as me_router
from app.api.routes_runs import router as runs_router
from app.api.routes_inventory import router as inv_router
from app.api.routes_shop import router as shop_router
from app.api.routes_tutorial import router as tutorial_router

# ✅ LEGACY game API (це кличе фронт: /api/profile, /api/city-entry, /api/npc/spawn)
from routers.auth import router as legacy_auth_router
from routers.profile import router as legacy_profile_router
from routers.city_entry import router as legacy_city_entry_router
from routers.npc_router import router as legacy_npc_router

app = FastAPI(title=getattr(settings, "APP_NAME", "Kyrhanu API"))

origins = [o.strip() for o in (getattr(settings, "CORS_ALLOW_ORIGINS", "") or "").split(",") if o.strip()]

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

# ✅ root для швидкої перевірки в браузері (щоб не бачити Not Found на головній)
@app.get("/")
async def root():
    return {"ok": True, "service": "kyrhanu-backend"}

# ✅ підключаємо LEGACY (фікс 404)
app.include_router(legacy_auth_router)
app.include_router(legacy_profile_router)
app.include_router(legacy_city_entry_router)
app.include_router(legacy_npc_router)

# ✅ V2 як було
app.include_router(auth_router)
app.include_router(daily_router)
app.include_router(ach_router)
app.include_router(me_router)
app.include_router(runs_router)
app.include_router(inv_router)
app.include_router(shop_router)
app.include_router(tutorial_router)

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