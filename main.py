from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.db import engine

# ✅ V2 API
from app.api.routes_auth import router as v2_auth_router
from app.api.routes_daily import router as v2_daily_router
from app.api.routes_achievements import router as v2_ach_router

# ✅ LEGACY game API (це кличе фронт)
from routers.auth import router as legacy_auth_router
from routers.profile import router as legacy_profile_router
from routers.city_entry import router as legacy_city_entry_router
from routers.npc_router import router as legacy_npc_router

app = FastAPI(title=getattr(settings, "APP_NAME", "Kyrhanu API"))

origins_raw = (getattr(settings, "CORS_ALLOW_ORIGINS", "") or "").strip()
origins = [o.strip() for o in origins_raw.split(",") if o.strip()]

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

# ✅ LEGACY endpoints (прибирає 404)
app.include_router(legacy_auth_router)
app.include_router(legacy_profile_router)
app.include_router(legacy_city_entry_router)
app.include_router(legacy_npc_router)

# ✅ V2 endpoints
app.include_router(v2_auth_router)
app.include_router(v2_daily_router)
app.include_router(v2_ach_router)


@app.get("/healthz")
async def healthz():
    db_ok = True
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {"ok": True, "dbOk": db_ok}