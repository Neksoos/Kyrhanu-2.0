from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

MAX_PROF_LEVEL = 20
BASE_XP = 100
XP_STEP = 75


@dataclass
class ProfessionProgress:
    level: int
    xp: int
    xp_to_next: int | None


def xp_to_next(level: int) -> int:
    lvl = max(1, int(level or 1))
    return BASE_XP + (lvl - 1) * XP_STEP


def calc_level_up(level: int, xp: int) -> ProfessionProgress:
    lvl = max(1, int(level or 1))
    rest_xp = max(0, int(xp or 0))

    while lvl < MAX_PROF_LEVEL and rest_xp >= xp_to_next(lvl):
        rest_xp -= xp_to_next(lvl)
        lvl += 1

    return ProfessionProgress(
        level=lvl,
        xp=rest_xp,
        xp_to_next=None if lvl >= MAX_PROF_LEVEL else xp_to_next(lvl),
    )


async def get_prof_level(conn: Any, tg_id: int, code: str) -> ProfessionProgress:
    row = await conn.fetchrow(
        """
        SELECT pp.level, pp.xp
        FROM player_professions pp
        JOIN professions p ON p.id = pp.profession_id
        JOIN players pl ON pl.id = pp.player_id
        WHERE pl.tg_id = $1 AND p.code = $2
        """,
        int(tg_id),
        code,
    )
    if not row:
        raise HTTPException(status_code=400, detail=f"Profession '{code}' not learned")

    cur = calc_level_up(int(row["level"] or 1), int(row["xp"] or 0))

    # Normalize stale rows if needed
    if cur.level != int(row["level"] or 1) or cur.xp != int(row["xp"] or 0):
        await conn.execute(
            """
            UPDATE player_professions pp
            SET level = $1, xp = $2, updated_at = NOW()
            FROM players pl, professions p
            WHERE pp.player_id = pl.id
              AND pp.profession_id = p.id
              AND pl.tg_id = $3
              AND p.code = $4
            """,
            cur.level,
            cur.xp,
            int(tg_id),
            code,
        )

    return cur


async def add_prof_xp(conn: Any, tg_id: int, code: str, gained_xp: int) -> ProfessionProgress:
    gain = max(0, int(gained_xp or 0))
    if gain == 0:
        return await get_prof_level(conn, tg_id, code)

    row = await conn.fetchrow(
        """
        SELECT pp.level, pp.xp
        FROM player_professions pp
        JOIN professions p ON p.id = pp.profession_id
        JOIN players pl ON pl.id = pp.player_id
        WHERE pl.tg_id = $1 AND p.code = $2
        FOR UPDATE
        """,
        int(tg_id),
        code,
    )
    if not row:
        raise HTTPException(status_code=400, detail=f"Profession '{code}' not learned")

    next_state = calc_level_up(int(row["level"] or 1), int(row["xp"] or 0) + gain)

    await conn.execute(
        """
        UPDATE player_professions pp
        SET level = $1, xp = $2, updated_at = NOW()
        FROM players pl, professions p
        WHERE pp.player_id = pl.id
          AND pp.profession_id = p.id
          AND pl.tg_id = $3
          AND p.code = $4
        """,
        next_state.level,
        next_state.xp,
        int(tg_id),
        code,
    )

    return next_state
