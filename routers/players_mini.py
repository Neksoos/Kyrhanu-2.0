# routers/players_mini.py
from __future__ import annotations

from typing import List, Optional, Dict

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from loguru import logger

from db import get_pool
from routers.auth import get_player
from models.player import PlayerDTO

router = APIRouter(prefix="/api", tags=["players"])


class PlayerMini(BaseModel):
    tg_id: int
    name: str

    # ✅ щоб фронт міг показати стандартний аватар раси
    race_key: Optional[str] = None
    gender: Optional[str] = None

    # ✅ premium cosmetics
    equipped_frame_sku: Optional[str] = None
    equipped_name_sku: Optional[str] = None
    equipped_avatar_sku: Optional[str] = None


class PlayersMiniResponse(BaseModel):
    ok: bool
    players: List[PlayerMini]


def _parse_ids(raw: str) -> List[int]:
    ids: List[int] = []
    if not raw:
        return ids

    for part in raw.split(","):
        p = (part or "").strip()
        if not p:
            continue
        try:
            n = int(p)
            if n > 0:
                ids.append(n)
        except Exception:
            continue

    # unique збереженням порядку
    seen = set()
    uniq: List[int] = []
    for n in ids:
        if n in seen:
            continue
        seen.add(n)
        uniq.append(n)

    return uniq[:200]


@router.get("/players/mini", response_model=PlayersMiniResponse)
async def players_mini(
    tg_ids: Optional[str] = Query(None, description="comma-separated tg_ids"),
    ids: Optional[str] = Query(None, description="alias for tg_ids (backward compatibility)"),
    _: PlayerDTO = Depends(get_player),
) -> PlayersMiniResponse:
    """
    GET /api/players/mini?tg_ids=1,2,3
    (також підтримує ?ids=1,2,3 для сумісності)
    """
    raw = (tg_ids or ids or "").strip()
    parsed = _parse_ids(raw)

    if not parsed:
        return PlayersMiniResponse(ok=True, players=[])

    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    tg_id,
                    COALESCE(name,'') AS name,
                    race_key,
                    gender,
                    equipped_frame_sku,
                    equipped_name_sku,
                    equipped_avatar_sku
                FROM players
                WHERE tg_id = ANY($1)
                """,
                parsed,
            )

        by_id: Dict[int, PlayerMini] = {}
        for r in rows:
            tid = int(r["tg_id"])
            by_id[tid] = PlayerMini(
                tg_id=tid,
                name=r["name"] or "",
                race_key=r["race_key"],
                gender=r["gender"],
                equipped_frame_sku=r["equipped_frame_sku"],
                equipped_name_sku=r["equipped_name_sku"],
                equipped_avatar_sku=r["equipped_avatar_sku"],
            )

        # у тому ж порядку що parsed
        players = [by_id[i] for i in parsed if i in by_id]
        return PlayersMiniResponse(ok=True, players=players)

    except Exception as e:
        logger.exception(f"players_mini failed: {e}")
        # не валимо фронт — просто віддаємо порожньо
        return PlayersMiniResponse(ok=True, players=[])