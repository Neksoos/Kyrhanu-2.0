# app/main.py
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.db import engine
from app.core.init_db import ensure_schema

# ✅ V2 API
from app.api.routes_auth import router as v2_auth_router
from app.api.routes_daily import router as v2_daily_router
from app.api.routes_achievements import router as v2_ach_router
from app.api.routes_me import router as v2_me_router
from app.api.routes_runs import router as v2_runs_router
from app.api.routes_inventory import router as v2_inv_router
from app.api.routes_shop import router as v2_shop_router
from app.api.routes_tutorial import router as v2_tutorial_router

app = FastAPI(title=getattr(settings, "APP_NAME", "Cursed Kurgans"))

# ✅ CORS
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

@app.get("/")
async def root():
    return {"ok": True, "service": "cursed-kurgans-backend"}

# ✅ Діагностика: покаже, чи Railway реально взяв новий код/коміт
@app.get("/__version")
async def version():
    return {
        "ok": True,
        "service": "cursed-kurgans-backend",
        "railway_revision": os.getenv("RAILWAY_GIT_COMMIT_SHA")
            or os.getenv("RAILWAY_GIT_COMMIT")
            or os.getenv("GIT_COMMIT")
            or "unknown",
        "app_module": os.getenv("APP_MODULE", "not_set"),
        "has_legacy_expected": "routers" in os.listdir("/app") if os.path.exists("/app") else False,
    }

# ─────────────────────────────
# ✅ Спроба підключити legacy routers
# (якщо папка routers є в контейнері)
# ─────────────────────────────
try:
    from routers.auth import router as legacy_auth_router
    from routers.profile import router as legacy_profile_router
    from routers.city_entry import router as legacy_city_entry_router
    from routers.npc_router import router as legacy_npc_router

    app.include_router(legacy_auth_router)
    app.include_router(legacy_profile_router)
    app.include_router(legacy_city_entry_router)
    app.include_router(legacy_npc_router)
except Exception as e:
    # якщо routers нема в image — не валимо сервіс, але це видно в /__version (і по відсутності шляхів)
    @app.get("/__legacy_error")
    async def legacy_error():
        return {"ok": False, "error": str(e)}

# ✅ V2 routes (як було)
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