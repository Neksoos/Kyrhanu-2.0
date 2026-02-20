# routers/admin_guard.py
from __future__ import annotations

from fastapi import Header, HTTPException
from config import settings


def _extract_token(
    x_admin_token: str | None,
    authorization: str | None,
) -> str | None:
    # 1) X-Admin-Token
    if x_admin_token and x_admin_token.strip():
        return x_admin_token.strip()

    # 2) Authorization: Bearer <token>
    if authorization and authorization.strip():
        a = authorization.strip()
        if a.lower().startswith("bearer "):
            t = a[7:].strip()
            return t if t else None

    return None


async def require_admin(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    """
    Глобальний guard адмінки.
    Підтримує:
      - X-Admin-Token: <token>
      - Authorization: Bearer <token>
    """
    token = _extract_token(x_admin_token, authorization)
    if not token or token != settings.ADMIN_SECRET:
        raise HTTPException(status_code=401, detail={"error": "ADMIN_UNAUTHORIZED"})
    return {"ok": True}