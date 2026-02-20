# core/tg_auth.py
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException


def _bot_token() -> str:
    """Read BOT_TOKEN lazily so the module can be imported even if env is missing."""
    return (os.getenv("BOT_TOKEN") or "").strip()


def _parse_qs(qs: str) -> Dict[str, str]:
    pairs = parse_qsl(qs, keep_blank_values=True, strict_parsing=False)
    return {k: v for k, v in pairs}


def verify_webapp_init_data(init_data: str, *, max_age_days: int = 7) -> Dict[str, str]:
    """Verify Telegram Mini App initData (WebAppData)."""
    token = _bot_token()
    if not token:
        raise HTTPException(status_code=500, detail="BOT_TOKEN not configured")

    data = _parse_qs(init_data or "")

    hash_received = (data.get("hash") or "").strip()
    if not hash_received:
        raise HTTPException(status_code=401, detail="initData hash missing")

    # auth_date expiry
    auth_date_raw = data.get("auth_date")
    if auth_date_raw:
        try:
            auth_date = int(auth_date_raw)
        except Exception:
            raise HTTPException(status_code=401, detail="initData auth_date invalid")

        if int(time.time()) - auth_date > 86400 * int(max_age_days):
            raise HTTPException(status_code=401, detail="initData expired")

    check_pairs = [f"{k}={v}" for k, v in sorted(data.items()) if k != "hash"]
    data_check_string = "\n".join(check_pairs)

    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    hash_calculated = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(hash_calculated, hash_received):
        raise HTTPException(status_code=401, detail="initData hash invalid")

    return data


def extract_webapp_user(verified: Dict[str, str]) -> Dict[str, Any]:
    user_raw = verified.get("user")
    if not user_raw:
        raise HTTPException(status_code=401, detail="initData user missing")
    try:
        user = json.loads(user_raw)
    except Exception:
        raise HTTPException(status_code=401, detail="initData user invalid json")

    if not isinstance(user, dict) or user.get("id") is None:
        raise HTTPException(status_code=401, detail="initData user.id missing")

    return user


def verify_login_widget(payload: Dict[str, Any], *, max_age_days: int = 7) -> Dict[str, Any]:
    """Verify Telegram Login Widget auth payload.

    Docs: https://core.telegram.org/widgets/login

    The payload is usually a dict with fields like:
      id, first_name, username, photo_url, auth_date, hash, ...
    """
    token = _bot_token()
    if not token:
        raise HTTPException(status_code=500, detail="BOT_TOKEN not configured")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be an object")

    hash_received = str(payload.get("hash") or "").strip()
    if not hash_received:
        raise HTTPException(status_code=401, detail="hash missing")

    auth_date_raw = payload.get("auth_date")
    if auth_date_raw is not None:
        try:
            auth_date = int(auth_date_raw)
        except Exception:
            raise HTTPException(status_code=401, detail="auth_date invalid")

        if int(time.time()) - auth_date > 86400 * int(max_age_days):
            raise HTTPException(status_code=401, detail="login widget payload expired")

    # Build data_check_string
    items: list[tuple[str, str]] = []
    for k, v in payload.items():
        if k == "hash" or v is None:
            continue
        # Telegram sends only flat scalars for widget; keep as string.
        items.append((str(k), str(v)))

    items.sort(key=lambda x: x[0])
    data_check_string = "\n".join([f"{k}={v}" for k, v in items])

    secret_key = hashlib.sha256(token.encode("utf-8")).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(calc_hash, hash_received):
        raise HTTPException(status_code=401, detail="hash invalid")

    return payload


# ─────────────────────────────────────────────
# FastAPI dependencies
# ─────────────────────────────────────────────

async def get_verified_initdata(
    x_init_data: str | None = Header(default=None, alias="X-Init-Data"),
) -> Dict[str, str]:
    if not x_init_data or not x_init_data.strip():
        raise HTTPException(status_code=401, detail="X-Init-Data header missing")
    return verify_webapp_init_data(x_init_data)


async def get_tg_user(
    x_init_data: str | None = Header(default=None, alias="X-Init-Data"),
) -> Dict[str, Any]:
    """Return Telegram user from verified Mini App initData."""
    if not x_init_data or not x_init_data.strip():
        raise HTTPException(status_code=401, detail="X-Init-Data header missing")
    data = verify_webapp_init_data(x_init_data)
    return extract_webapp_user(data)


async def optional_verified_initdata(
    x_init_data: str | None = Header(default=None, alias="X-Init-Data"),
) -> Dict[str, str] | None:
    if not x_init_data or not x_init_data.strip():
        return None
    return verify_webapp_init_data(x_init_data)


async def optional_tg_user(
    x_init_data: str | None = Header(default=None, alias="X-Init-Data"),
) -> Dict[str, Any] | None:
    if not x_init_data or not x_init_data.strip():
        return None
    verified = verify_webapp_init_data(x_init_data)
    return extract_webapp_user(verified)
