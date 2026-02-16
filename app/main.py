from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.core.config import settings
from app.core.db import engine

from app.api.routes_auth import router as auth_router
from app.api.routes_daily import router as daily_router
from app.api.routes_achievements import router as ach_router

app = FastAPI(title=settings.APP_NAME)

origins = [o.strip() for o in settings.CORS_ALLOW_ORIGINS.split(",") if o.strip()]
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

@app.get("/healthz")
async def healthz():
    db_ok = True
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {"ok": True, "dbOk": db_ok}