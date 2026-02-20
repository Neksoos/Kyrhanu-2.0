from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from db import get_pool
from routers.auth import get_tg_id


router = APIRouter(prefix="/api/gathering/professions", tags=["gathering"])


# ───────────────────────────────────────
# mapping profession.code -> source_type
# ───────────────────────────────────────
SourceType = Literal["herb", "ore", "stone"]

_PROF_CODE_TO_SOURCE: Dict[str, SourceType] = {
    "herbalist": "herb",
    "miner": "ore",
    "stonemason": "stone",
}


def _source_type_for_prof_code(code: str) -> SourceType:
    c = (code or "").strip().lower()
    st = _PROF_CODE_TO_SOURCE.get(c)
    if not st:
        raise HTTPException(status_code=400, detail=f"UNSUPPORTED_GATHERING_PROFESSION:{c}")
    return st


# ───────────────────────────────────────
# DTO
# ───────────────────────────────────────
UIMode = Literal["auto", "choose", "none"]


class GatheringProfessionButtonDTO(BaseModel):
    profession_id: int
    code: str
    label: str
    source_type: SourceType
    emoji: Optional[str] = None


class GatheringProfessionsUIResponse(BaseModel):
    ok: bool = True
    mode: UIMode
    title: Optional[str] = None
    message: Optional[str] = None
    auto_profession: Optional[GatheringProfessionButtonDTO] = None
    buttons: List[GatheringProfessionButtonDTO] = []


# ───────────────────────────────────────
# helpers
# ───────────────────────────────────────
async def _get_player_id_by_tg(tg_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM players WHERE tg_id = $1", tg_id)
    if not row:
        raise HTTPException(status_code=404, detail="Player not found")
    return int(row["id"])


async def _get_player_gathering_professions(player_id: int) -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                pr.id   AS profession_id,
                pr.code AS code,
                pr.name AS name,
                pr.icon AS icon
            FROM player_professions pp
            JOIN professions pr ON pr.id = pp.profession_id
            WHERE pp.player_id = $1
              AND pr.kind = 'gathering'
            ORDER BY pr.min_level, pr.id
            """,
            player_id,
        )
    return [dict(r) for r in rows]


# ───────────────────────────────────────
# endpoint
# ───────────────────────────────────────
@router.get("/ui", response_model=GatheringProfessionsUIResponse)
async def gathering_professions_ui(
    tg_id: int = Depends(get_tg_id),
):
    player_id = await _get_player_id_by_tg(tg_id)

    profs = await _get_player_gathering_professions(player_id)

    if not profs:
        return GatheringProfessionsUIResponse(
            ok=True,
            mode="none",
            message="Немає збиральницьких професій",
            buttons=[],
        )

    buttons: List[GatheringProfessionButtonDTO] = []
    for p in profs:
        code = str(p["code"])
        buttons.append(
            GatheringProfessionButtonDTO(
                profession_id=int(p["profession_id"]),
                code=code,
                label=str(p["name"]),
                source_type=_source_type_for_prof_code(code),
                emoji=p.get("icon"),
            )
        )

    if len(buttons) == 1:
        return GatheringProfessionsUIResponse(
            ok=True,
            mode="auto",
            auto_profession=buttons[0],
            buttons=[],
        )

    return GatheringProfessionsUIResponse(
        ok=True,
        mode="choose",
        title="Обери, за чим вирушити",
        buttons=buttons,
    )