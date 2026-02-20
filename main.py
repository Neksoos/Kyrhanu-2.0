# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.db import engine
from app.core.init_db import ensure_schema

# ✅ V2 API (JWT) — як є зараз у тебе в Swagger
from app.api.routes_auth import router as v2_auth_router
from app.api.routes_daily import router as v2_daily_router
from app.api.routes_achievements import router as v2_ach_router
from app.api.routes_me import router as v2_me_router
from app.api.routes_runs import router as v2_runs_router
from app.api.routes_inventory import router as v2_inv_router
from app.api.routes_shop import router as v2_shop_router
from app.api.routes_tutorial import router as v2_tutorial_router

# ✅ LEGACY game API (фронт кличе саме /api/...)
from routers.auth import router as legacy_auth_router
from routers.profile import router as legacy_profile_router
from routers.city_entry import router as legacy_city_entry_router
from routers.npc_router import router as legacy_npc_router

app = FastAPI(title=getattr(settings, "APP_NAME", "Cursed Kurgans"))

# ✅ CORS для Telegram WebView/браузера
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

# ✅ щоб не бачити Not Found на /
@app.get("/")
async def root():
    return {"ok": True, "service": "cursed-kurgans-backend"}

# ─────────────────────────────────────────────────────────────
# ✅ LEGACY endpoints (те, що потрібно фронту)
# /api/profile
# /api/city-entry
# /api/npc/spawn
# ─────────────────────────────────────────────────────────────
app.include_router(legacy_auth_router)
app.include_router(legacy_profile_router)
app.include_router(legacy_city_entry_router)
app.include_router(legacy_npc_router)

# ─────────────────────────────────────────────────────────────
# ✅ V2 endpoints (JWT) — як було
# ─────────────────────────────────────────────────────────────
app.include_router(v2_auth_router)
app.include_router(v2_daily_router)
app.include_router(v2_ach_router)
app.include_router(v2_me_router)
app.include_router(v2_runs_router)
app.include_router(v2_inv_router)
app.include_router(v2_shop_router)
app.include_router(v2_tutorial_router)


@app.on_event("startup")
async def on_startup():
    # v2 schema init (не заважає legacy)
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