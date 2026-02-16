from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.auth import (
    AuthRegisterIn, AuthLoginIn, AuthTelegramInitDataIn, AuthTelegramWidgetIn, AuthOut
)
from app.services import auth_service
from app.core.security import refresh_cookie_params
from app.core.rate_limit import rate_limiter
from app.core.config import settings
from app.api.deps import get_db, get_ip

router = APIRouter(prefix="/auth", tags=["auth"])

def _rl_or_429(key: str, limit: int, per_sec: int):
    if not rate_limiter.allow(key, limit, per_sec):
        raise HTTPException(status_code=429, detail="Too many requests")

@router.post("/register", response_model=AuthOut)
async def register(body: AuthRegisterIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    _rl_or_429(f"auth:register:{get_ip(request)}", settings.RATE_LIMIT_AUTH_PER_MIN, 60)
    try:
        user, access, refresh = await auth_service.register_email(
            db, body.email, body.password, request.headers.get("user-agent"), get_ip(request)
        )
        await db.commit()
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    response.set_cookie("refresh_token", refresh, **refresh_cookie_params())
    return {"ok": True, "user": user, "accessToken": access}

@router.post("/login", response_model=AuthOut)
async def login(body: AuthLoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    _rl_or_429(f"auth:login:{get_ip(request)}", settings.RATE_LIMIT_AUTH_PER_MIN, 60)
    try:
        user, access, refresh = await auth_service.login_email(
            db, body.email, body.password, request.headers.get("user-agent"), get_ip(request)
        )
        await db.commit()
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    response.set_cookie("refresh_token", refresh, **refresh_cookie_params())
    return {"ok": True, "user": user, "accessToken": access}

@router.post("/telegram/initdata", response_model=AuthOut)
async def telegram_initdata(body: AuthTelegramInitDataIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    _rl_or_429(f"auth:tg_init:{get_ip(request)}", settings.RATE_LIMIT_AUTH_PER_MIN, 60)
    try:
        user, access, refresh = await auth_service.login_telegram_initdata(
            db, body.initData, request.headers.get("user-agent"), get_ip(request)
        )
        await db.commit()
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    response.set_cookie("refresh_token", refresh, **refresh_cookie_params())
    return {"ok": True, "user": user, "accessToken": access}

@router.post("/telegram/widget", response_model=AuthOut)
async def telegram_widget(body: AuthTelegramWidgetIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    _rl_or_429(f"auth:tg_widget:{get_ip(request)}", settings.RATE_LIMIT_AUTH_PER_MIN, 60)
    try:
        user, access, refresh = await auth_service.login_telegram_widget(
            db, body.payload, request.headers.get("user-agent"), get_ip(request)
        )
        await db.commit()
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    response.set_cookie("refresh_token", refresh, **refresh_cookie_params())
    return {"ok": True, "user": user, "accessToken": access}

@router.post("/refresh")
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    _rl_or_429(f"auth:refresh:{get_ip(request)}", settings.RATE_LIMIT_AUTH_PER_MIN, 60)
    rt = request.cookies.get("refresh_token")
    if not rt:
        raise HTTPException(status_code=401, detail="Missing refresh_token")
    try:
        access, new_rt = await auth_service.rotate_refresh(db, rt, request.headers.get("user-agent"), get_ip(request))
        await db.commit()
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=401, detail=str(e))

    response.set_cookie("refresh_token", new_rt, **refresh_cookie_params())
    return {"ok": True, "accessToken": access}

@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    rt = request.cookies.get("refresh_token")
    if rt:
        await auth_service.logout_refresh(db, rt)
        await db.commit()
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}