"""Authentication router.

Supports:
- Telegram Mini App auth (WebApp initData)
- Telegram Login Widget auth (browser)
- Email/password auth (optional)

All POST endpoints accept JSON bodies (matches the Next.js frontend).
"""

import json
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models import AuthProvider, User
from services.telegram_auth import (
    TelegramAuthError,
    verify_telegram_init_data,
    verify_telegram_login_widget,
)


router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


class EmailRegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    age_confirm: bool = False


class EmailLoginRequest(BaseModel):
    username: str
    password: str


class TelegramInitDataRequest(BaseModel):
    init_data: str


class TelegramWidgetAuthRequest(BaseModel):
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: Optional[int] = None
    hash: str


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _serialize_user(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username or "",
        "display_name": u.display_name or u.username or "",
        "avatar_url": u.avatar_url,
        "chervontsi": u.chervontsi,
        "kleynodu": u.kleynodu,
        "level": u.level,
        "experience": u.experience,
        "glory": u.glory,
        "energy": u.energy,
        "max_energy": u.max_energy,
        "referral_code": u.referral_code,
    }


async def _ensure_unique_username(db: AsyncSession, base: str) -> str:
    """Return a username that's unique in DB (adds suffix if needed)."""
    base = (base or "").strip()
    if not base:
        return "player"

    candidate = base
    i = 0
    while True:
        q = await db.execute(select(User).where(User.username == candidate))
        exists = q.scalar_one_or_none()
        if not exists:
            return candidate
        i += 1
        candidate = f"{base}_{i}"


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(status_code=401, detail="Could not validate credentials")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id: Optional[int] = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await db.get(User, int(user_id))
    if not user:
        raise credentials_exception
    if user.banned_at:
        raise HTTPException(status_code=403, detail="User is banned")
    return user


@router.post("/register")
async def register_email(payload: EmailRegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check existing
    existing = await db.execute(
        select(User).where(or_(User.username == payload.username, User.email == payload.email))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username or email already exists")

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=_hash_password(payload.password),
        auth_provider=AuthProvider.EMAIL,
        provider_id=None,
        display_name=payload.username,
        age_verified=payload.age_confirm,
        accepted_tos=True,
        accepted_privacy=True,
        referral_code=secrets.token_urlsafe(8)[:10],
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token({"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer", "user": _serialize_user(user), "is_new": True}


@router.post("/login")
async def login_email(payload: EmailLoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == payload.username))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not _verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer", "user": _serialize_user(user), "is_new": False}


@router.post("/telegram")
async def telegram_miniapp_auth(payload: TelegramInitDataRequest, db: AsyncSession = Depends(get_db)):
    try:
        parsed = verify_telegram_init_data(payload.init_data)
    except TelegramAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))

    if not parsed or "user" not in parsed:
        raise HTTPException(status_code=401, detail="Invalid Telegram initData")

    try:
        tg_user = json.loads(parsed["user"]) if isinstance(parsed["user"], str) else parsed["user"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Telegram user payload")

    tg_id = tg_user.get("id")
    if not tg_id:
        raise HTTPException(status_code=401, detail="Telegram user id missing")

    provider_id = str(tg_id)
    res = await db.execute(
        select(User).where(and_(User.auth_provider == AuthProvider.TELEGRAM, User.provider_id == provider_id))
    )
    user = res.scalar_one_or_none()
    is_new = False

    username = tg_user.get("username")
    display_name = " ".join(filter(None, [tg_user.get("first_name"), tg_user.get("last_name")])).strip() or username

    if not user:
        is_new = True
        unique_username = None
        if username:
            unique_username = await _ensure_unique_username(db, username)

        user = User(
            username=unique_username,
            email=None,
            password_hash=None,
            auth_provider=AuthProvider.TELEGRAM,
            provider_id=provider_id,
            display_name=display_name,
            avatar_url=tg_user.get("photo_url"),
            age_verified=True,
            accepted_tos=True,
            accepted_privacy=True,
            referral_code=secrets.token_urlsafe(8)[:10],
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        # Keep profile in sync
        changed = False
        if not user.username and username:
            user.username = await _ensure_unique_username(db, username)
            changed = True
        if display_name and user.display_name != display_name:
            user.display_name = display_name
            changed = True
        if tg_user.get("photo_url") and user.avatar_url != tg_user.get("photo_url"):
            user.avatar_url = tg_user.get("photo_url")
            changed = True
        if changed:
            await db.commit()

    access_token = create_access_token({"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer", "user": _serialize_user(user), "is_new": is_new}


@router.post("/telegram-widget")
async def telegram_widget_auth(payload: TelegramWidgetAuthRequest, db: AsyncSession = Depends(get_db)):
    data = payload.model_dump()
    # Verify
    if not verify_telegram_login_widget(data):
        raise HTTPException(status_code=401, detail="Invalid Telegram widget data")

    tg_id = payload.id
    provider_id = str(tg_id)
    res = await db.execute(
        select(User).where(and_(User.auth_provider == AuthProvider.TELEGRAM, User.provider_id == provider_id))
    )
    user = res.scalar_one_or_none()
    is_new = False

    username = payload.username
    display_name = " ".join(filter(None, [payload.first_name, payload.last_name])).strip() or username

    if not user:
        is_new = True
        unique_username = None
        if username:
            unique_username = await _ensure_unique_username(db, username)
        user = User(
            username=unique_username,
            email=None,
            password_hash=None,
            auth_provider=AuthProvider.TELEGRAM,
            provider_id=provider_id,
            display_name=display_name,
            avatar_url=payload.photo_url,
            age_verified=True,
            accepted_tos=True,
            accepted_privacy=True,
            referral_code=secrets.token_urlsafe(8)[:10],
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        changed = False
        if not user.username and username:
            user.username = await _ensure_unique_username(db, username)
            changed = True
        if display_name and user.display_name != display_name:
            user.display_name = display_name
            changed = True
        if payload.photo_url and user.avatar_url != payload.photo_url:
            user.avatar_url = payload.photo_url
            changed = True
        if changed:
            await db.commit()

    access_token = create_access_token({"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer", "user": _serialize_user(user), "is_new": is_new}


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return {"user": _serialize_user(current_user)}
