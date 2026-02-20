# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

# ✅ Legacy game API (те, що зараз кличе фронт: /api/...)
from routers.auth import router as legacy_auth_router
from routers.profile import router as legacy_profile_router
from routers.city_entry import router as legacy_city_entry_router
from routers.npc_router import router as legacy_npc_router

# ✅ V2 API (JWT) — щоб не зміішувати з legacy, відносимо на /v2/...
from app.api.routes_auth import router as v2_auth_router
from app.api.routes_daily import router as v2_daily_router
from app.api.routes_achievements import router as v2_ach_router
from app.api.routes_me import router as v2_me_router
from app.api.routes_runs import router as v2_runs_router
from app.api.routes_inventory import router as v2_inv_router
from app.api.routes_shop import router as v2_shop_router
from app.api.routes_tutorial import router as v2_tutorial_router

app = FastAPI(title=getattr(settings, "APP_NAME", "Kyrhanu API"))

# ✅ CORS: Telegram WebView + браузер
origins_raw = getattr(settings, "CORS_ALLOW_ORIGINS", "") or ""
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

# ─────────────────────────────────────────────────────────────
# ✅ LEGACY API (саме це потрібно для гри зараз)
#    /api/profile
#    /api/city-entry
#    /api/npc/spawn
# ─────────────────────────────────────────────────────────────
app.include_router(legacy_auth_router)
app.include_router(legacy_profile_router)
app.include_router(legacy_city_entry_router)
app.include_router(legacy_npc_router)

# ─────────────────────────────────────────────────────────────
# ✅ V2 API (JWT) — із префіксом /v2
# ─────────────────────────────────────────────────────────────
app.include_router(v2_auth_router, prefix="/v2")
app.include_router(v2_daily_router, prefix="/v2")
app.include_router(v2_ach_router, prefix="/v2")
app.include_router(v2_me_router, prefix="/v2")
app.include_router(v2_runs_router, prefix="/v2")
app.include_router(v2_inv_router, prefix="/v2")
app.include_router(v2_shop_router, prefix="/v2")
app.include_router(v2_tutorial_router, prefix="/v2")


@app.get("/healthz")
async def healthz():
    return {"ok": True}