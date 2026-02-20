# app/main.py
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.core.db import engine
from app.core.init_db import ensure_schema

# ✅ V2 (JWT) routers — НЕ ламаємо, але ховаємо під /v2 щоб не конфліктували з LEGACY /api/*
from app.api.routes_auth import router as v2_auth_router
from app.api.routes_daily import router as v2_daily_router
from app.api.routes_achievements import router as v2_ach_router
from app.api.routes_me import router as v2_me_router
from app.api.routes_runs import router as v2_runs_router
from app.api.routes_inventory import router as v2_inv_router
from app.api.routes_shop import router as v2_shop_router
from app.api.routes_tutorial import router as v2_tutorial_router

app = FastAPI(title=getattr(settings, "APP_NAME", "Kyrhanu"))

# ✅ CORS: Telegram WebView + браузер
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

# ✅ щоб не було {"detail":"Not Found"} на /
@app.get("/", tags=["default"])
def root():
    return {"ok": True, "service": "kyrhanu-backend"}

# ✅ простий пінг (для перевірки що деплой взяв код)
@app.get("/_ping", tags=["default"])
def ping():
    return {"ok": True}

# ─────────────────────────────────────────────────────────────
# ✅ LEGACY /api/* — головне для твого фронта
# Підключаємо “routers/*” (Telegram initData / X-Init-Data)
# ─────────────────────────────────────────────────────────────
_legacy_import_error = None

try:
    # Основні legacy endpoints
    from routers.auth import router as legacy_auth_router
    from routers.profile import router as legacy_profile_router
    from routers.city_entry import router as legacy_city_entry_router
    from routers.npc_router import router as legacy_npc_router

    from routers.professions import router as legacy_professions_router
    from routers.materials import router as legacy_materials_router
    from routers.inventory import router as legacy_inventory_router

    # Існуючі системи крафту
    from routers.alchemy import router as legacy_alchemy_router
    from routers.blacksmith import router as legacy_blacksmith_router

    # Якщо ти вже додав craft hub (як ми планували)
    try:
        from routers.craft import router as legacy_craft_router
    except Exception:
        legacy_craft_router = None  # type: ignore

    # Підключаємо все як є: ці routers вже мають свої prefix (/api/...)
    app.include_router(legacy_auth_router)
    app.include_router(legacy_profile_router)
    app.include_router(legacy_city_entry_router)
    app.include_router(legacy_npc_router)

    app.include_router(legacy_professions_router)
    app.include_router(legacy_materials_router)
    app.include_router(legacy_inventory_router)

    app.include_router(legacy_alchemy_router)
    app.include_router(legacy_blacksmith_router)

    if legacy_craft_router is not None:
        app.include_router(legacy_craft_router)

except Exception as e:
    # Не валимо сервіс, щоб було видно причину через endpoint нижче
    _legacy_import_error = str(e)


@app.get("/__legacy_error", tags=["debug"])
def legacy_error():
    """
    Якщо тут ok=false — значить в контейнері не підтягуються legacy routers
    (наприклад, немає папки routers/ або конфлікт імпортів).
    """
    return {"ok": _legacy_import_error is None, "error": _legacy_import_error}


# ─────────────────────────────────────────────────────────────
# ✅ V2 API (JWT) — під /v2 щоб не конфліктувати з /api/*
# ─────────────────────────────────────────────────────────────
app.include_router(v2_auth_router, prefix="/v2")
app.include_router(v2_daily_router, prefix="/v2")
app.include_router(v2_ach_router, prefix="/v2")
app.include_router(v2_me_router, prefix="/v2")
app.include_router(v2_runs_router, prefix="/v2")
app.include_router(v2_inv_router, prefix="/v2")
app.include_router(v2_shop_router, prefix="/v2")
app.include_router(v2_tutorial_router, prefix="/v2")


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