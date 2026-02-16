from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    hash_password, verify_password, create_access_token,
    new_refresh_token, sha256
)
from app.core.telegram import verify_telegram_webapp_initdata, verify_telegram_login_widget
from app.models.user import User
from app.models.auth import AuthSession
from app.models.wallet import Wallet

async def _ensure_wallet(session: AsyncSession, user_id):
    w = await session.get(Wallet, user_id)
    if not w:
        session.add(Wallet(user_id=user_id, chervontsi=300, kleidony=0))  # старт
    return

def _user_out(u: User) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "telegram_id": u.telegram_id,
        "telegram_username": u.telegram_username,
    }

async def register_email(session: AsyncSession, email: str, password: str, ua: str | None, ip: str | None):
    existing = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        raise ValueError("Email already registered")

    now = datetime.now(timezone.utc)
    u = User(email=email, password_hash=hash_password(password), created_at=now, is_active=True)
    session.add(u)
    await session.flush()
    await _ensure_wallet(session, u.id)

    refresh = new_refresh_token()
    session.add(AuthSession(
        user_id=u.id, refresh_hash=sha256(refresh),
        user_agent=ua, ip=ip, created_at=now
    ))
    access = create_access_token(str(u.id))
    return _user_out(u), access, refresh

async def login_email(session: AsyncSession, email: str, password: str, ua: str | None, ip: str | None):
    u = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if not u or not u.password_hash or not verify_password(password, u.password_hash):
        raise ValueError("Bad credentials")

    now = datetime.now(timezone.utc)
    refresh = new_refresh_token()
    session.add(AuthSession(
        user_id=u.id, refresh_hash=sha256(refresh),
        user_agent=ua, ip=ip, created_at=now
    ))
    access = create_access_token(str(u.id))
    return _user_out(u), access, refresh

async def login_telegram_initdata(session: AsyncSession, init_data: str, ua: str | None, ip: str | None):
    data = verify_telegram_webapp_initdata(init_data)
    # Telegram sends user as JSON string in "user"
    import json
    user_json = json.loads(data.get("user", "{}"))
    tg_id = int(user_json["id"])
    tg_username = user_json.get("username")

    u = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if not u:
        u = User(telegram_id=tg_id, telegram_username=tg_username, created_at=now, is_active=True)
        session.add(u)
        await session.flush()
        await _ensure_wallet(session, u.id)
    else:
        if tg_username and u.telegram_username != tg_username:
            u.telegram_username = tg_username

    refresh = new_refresh_token()
    session.add(AuthSession(
        user_id=u.id, refresh_hash=sha256(refresh),
        user_agent=ua, ip=ip, created_at=now
    ))
    access = create_access_token(str(u.id))
    return _user_out(u), access, refresh

async def login_telegram_widget(session: AsyncSession, payload: dict, ua: str | None, ip: str | None):
    data = verify_telegram_login_widget(payload)
    tg_id = int(data["id"])
    tg_username = data.get("username")

    u = (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if not u:
        u = User(telegram_id=tg_id, telegram_username=tg_username, created_at=now, is_active=True)
        session.add(u)
        await session.flush()
        await _ensure_wallet(session, u.id)
    else:
        if tg_username and u.telegram_username != tg_username:
            u.telegram_username = tg_username

    refresh = new_refresh_token()
    session.add(AuthSession(
        user_id=u.id, refresh_hash=sha256(refresh),
        user_agent=ua, ip=ip, created_at=now
    ))
    access = create_access_token(str(u.id))
    return _user_out(u), access, refresh

async def rotate_refresh(session: AsyncSession, refresh_token: str, ua: str | None, ip: str | None):
    rh = sha256(refresh_token)
    row = (await session.execute(
        select(AuthSession).where(AuthSession.refresh_hash == rh, AuthSession.revoked_at.is_(None))
    )).scalar_one_or_none()
    if not row:
        raise ValueError("Invalid refresh")

    now = datetime.now(timezone.utc)
    # rotate: revoke old (set rotated_at) + issue new session
    row.rotated_at = now
    new_r = new_refresh_token()
    session.add(AuthSession(
        user_id=row.user_id, refresh_hash=sha256(new_r),
        user_agent=ua, ip=ip, created_at=now
    ))
    access = create_access_token(str(row.user_id))
    return access, new_r

async def logout_refresh(session: AsyncSession, refresh_token: str):
    rh = sha256(refresh_token)
    row = (await session.execute(select(AuthSession).where(AuthSession.refresh_hash == rh))).scalar_one_or_none()
    if row and row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
    return True