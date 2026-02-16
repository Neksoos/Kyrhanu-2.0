import os, hashlib, secrets
from datetime import datetime, timedelta, timezone
from jose import jwt
from passlib.context import CryptContext
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(pw: str) -> str:
    return pwd_context.hash(pw)

def verify_password(pw: str, pw_hash: str) -> bool:
    return pwd_context.verify(pw, pw_hash)

def create_access_token(sub: str) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES)
    payload = {"sub": sub, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)

def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def refresh_cookie_params() -> dict:
    # HttpOnly cookie
    max_age = settings.REFRESH_TOKEN_DAYS * 24 * 60 * 60
    return dict(
        httponly=True,
        secure=True,         # set False only in local dev if needed
        samesite="lax",
        max_age=max_age,
        path="/",
    )