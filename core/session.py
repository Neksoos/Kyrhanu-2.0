from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import Request
from starlette.responses import Response

from routers.redis_manager import get_redis


SESSION_COOKIE_NAME = (os.getenv("SESSION_COOKIE_NAME") or "sid").strip() or "sid"
SESSION_TTL_DAYS = int((os.getenv("SESSION_TTL_DAYS") or "14").strip() or "14")
COOKIE_SECURE = (os.getenv("COOKIE_SECURE") or "0").strip() == "1"
COOKIE_SAMESITE = (os.getenv("COOKIE_SAMESITE") or "lax").strip().lower()  # lax/none/strict
COOKIE_DOMAIN = (os.getenv("COOKIE_DOMAIN") or "").strip() or None


def _ttl_seconds() -> int:
    return max(3600, SESSION_TTL_DAYS * 86400)


def _new_sid() -> str:
    # URL-safe random token
    return secrets.token_urlsafe(32)


def _cookie_kwargs() -> dict:
    kwargs = {
        "httponly": True,
        "secure": COOKIE_SECURE,
        "samesite": COOKIE_SAMESITE,
        "path": "/",
        "max_age": _ttl_seconds(),
    }
    if COOKIE_DOMAIN:
        kwargs["domain"] = COOKIE_DOMAIN
    return kwargs


async def create_session(response: Response, tg_id: int) -> str:
    redis = await get_redis()
    sid = _new_sid()
    await redis.setex(f"sid:{sid}", _ttl_seconds(), str(int(tg_id)))
    response.set_cookie(SESSION_COOKIE_NAME, sid, **_cookie_kwargs())
    return sid


async def resolve_session_tg_id(request: Request) -> Optional[int]:
    sid = request.cookies.get(SESSION_COOKIE_NAME)
    if not sid:
        return None

    redis = await get_redis()
    v = await redis.get(f"sid:{sid}")
    if not v:
        return None

    try:
        return int(v)
    except Exception:
        return None


async def destroy_session(request: Request, response: Response) -> None:
    sid = request.cookies.get(SESSION_COOKIE_NAME)
    if sid:
        redis = await get_redis()
        try:
            await redis.delete(f"sid:{sid}")
        except Exception:
            pass

    response.delete_cookie(SESSION_COOKIE_NAME, path="/", domain=COOKIE_DOMAIN)
