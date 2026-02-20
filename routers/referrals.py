# routers/referrals.py
from __future__ import annotations

import os
import re
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from loguru import logger

try:
    from db import get_pool  # type: ignore
except Exception:
    async def get_pool():  # type: ignore
        return None

from routers.auth import get_tg_id  # type: ignore

router = APIRouter(prefix="/api/referrals", tags=["referrals"])

BOT_USERNAME = os.getenv("BOT_USERNAME")  # наприклад: proklyati_kurgany_bot (без @)
WEBAPP_SHORTNAME = os.getenv("WEBAPP_SHORTNAME")  # якщо мініап відкривається як t.me/bot/<shortname>

_DEEPLINK_RE = re.compile(
    r"(?ix)"
    r"(?:^(?:ref|r|u)\s*[:=]?\s*([0-9]{4,})$)"
    r"|"
    r"(?:([0-9]{4,})$)"
)

def _parse_inviter(payload: Optional[str]) -> Optional[int]:
    if not payload:
        return None
    m = _DEEPLINK_RE.search(payload.strip())
    if not m:
        return None
    g = m.group(1) or m.group(2)
    try:
        v = int(g)  # type: ignore[arg-type]
        return v if v > 0 else None
    except Exception:
        return None

def _require_bot_username() -> str:
    # краще впасти і одразу показати проблему конфігурації,
    # ніж тихо віддавати "your_bot" і плодити биті лінки
    if not BOT_USERNAME:
        raise HTTPException(500, "BOT_USERNAME is not configured")
    return BOT_USERNAME

def _build_link(username: str, inviter_id: int) -> str:
    # Mini App referral: startapp=...
    payload = f"ref{inviter_id}"
    if WEBAPP_SHORTNAME:
        return f"https://t.me/{username}/{WEBAPP_SHORTNAME}?startapp={payload}"
    return f"https://t.me/{username}?startapp={payload}"

async def _ensure_schema() -> bool:
    pool = await get_pool()
    if not pool:
        return False
    async with pool.acquire() as c:
        await c.execute(
            """
            CREATE TABLE IF NOT EXISTS referrals (
                id           BIGSERIAL PRIMARY KEY,
                invitee_id   BIGINT UNIQUE NOT NULL,
                inviter_id   BIGINT NOT NULL,
                reward_paid  BOOLEAN NOT NULL DEFAULT FALSE,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        await c.execute(
            "CREATE INDEX IF NOT EXISTS idx_ref_inviter ON referrals(inviter_id);"
        )
    return True

async def _stats(uid: int) -> Tuple[int, int]:
    pool = await get_pool()
    if not pool:
        return (0, 0)
    async with pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT COUNT(*)::int AS c, "
            "COALESCE(SUM(CASE WHEN reward_paid THEN 1 ELSE 0 END),0)::int AS p "
            "FROM referrals WHERE inviter_id=$1",
            uid,
        )
        return (int(row["c"]), int(row["p"])) if row else (0, 0)

class BindRequest(BaseModel):
    payload: Optional[str] = None
    inviter_id: Optional[int] = None

@router.get("/link")
async def get_link(me: int = Depends(get_tg_id)):
    username = _require_bot_username()
    link = _build_link(username, me)
    total, paid = await _stats(me)
    return {"ok": True, "username": username, "link": link, "stats": {"invited": total, "paid": paid}}

@router.post("/bind")
async def bind_ref(req: BindRequest, me: int = Depends(get_tg_id)):
    ok_schema = await _ensure_schema()
    if not ok_schema:
        raise HTTPException(500, "DB unavailable")

    inviter = req.inviter_id or _parse_inviter(req.payload)
    if not inviter or inviter == me:
        return {"ok": False, "bound": False, "reason": "invalid_inviter"}

    pool = await get_pool()
    if not pool:
        raise HTTPException(500, "DB unavailable")

    async with pool.acquire() as c:
        res = await c.execute(
            """
            INSERT INTO referrals(invitee_id, inviter_id)
            VALUES ($1,$2)
            ON CONFLICT (invitee_id) DO NOTHING
            """,
            me, inviter
        )

    if res.endswith("0"):
        return {"ok": True, "bound": False, "reason": "already_linked"}

    logger.info(f"[ref] linked invitee={me} <- inviter={inviter}")
    return {"ok": True, "bound": True}

@router.get("/stats")
async def my_stats(me: int = Depends(get_tg_id)):
    total, paid = await _stats(me)
    return {"ok": True, "invited": total, "paid": paid}

@router.get("")
async def combined(me: int = Depends(get_tg_id)):
    username = _require_bot_username()
    link = _build_link(username, me)
    total, paid = await _stats(me)
    return {"ok": True, "username": username, "link": link, "stats": {"invited": total, "paid": paid}}