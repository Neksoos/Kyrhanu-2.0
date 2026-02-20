from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Optional, Tuple

from db import get_pool


SpiritState = str  # "calm" | "restless" | "hostile"


def _today_utc() -> dt.date:
    return dt.datetime.utcnow().date()


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def normalize_source_type(source_type: Optional[str]) -> str:
    """
    Normalize incoming source types to canonical: herb | ore | ks.

    Важливо: не маскуємо помилки "тихим" переходом у herb,
    інакше будь-який баг у фронті/беку виглядає як "трави падають всюди".
    """
    s = (source_type or "").strip().lower()
    if not s:
        return "herb"

    # stone / stonemason / ks
    if s in (
        "ks",
        "stone",
        "stones",
        "stonemason",
        "камінь",
        "каміння",
        "камені",
        "каменяр",
        "каменярство",
    ):
        return "ks"

    # herb / herbalist
    if s in ("herb", "herbalist", "трава", "трави", "травник", "травництво"):
        return "herb"

    # ore / miner
    if s in ("ore", "miner", "руда", "руди", "рудокоп", "рудокопство"):
        return "ore"

    raise ValueError(f"INVALID_SOURCE_TYPE: {source_type!r}")


def _impact_for_risk(risk: Optional[str]) -> Tuple[str, int]:
    """risk -> (impact, intensity).

    - low/careful/safe   -> stabilize(1)
    - medium/normal      -> deplete(1)
    - high/risky         -> corrupt(2)
    - extreme            -> corrupt(3)
    """
    r = (risk or "medium").strip().lower()
    if r in ("low", "careful", "safe"):
        return ("stabilize", 1)
    if r in ("high", "risky"):
        return ("corrupt", 2)
    if r in ("extreme",):
        return ("corrupt", 3)
    return ("deplete", 1)


async def ensure_spot(area_key: str, source_type: str) -> int:
    """Ensure spot + state exist and return spot_id."""
    area = str(area_key).strip()
    st = normalize_source_type(source_type)

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO gathering_spots(area_key, source_type)
            VALUES ($1, $2)
            ON CONFLICT(area_key, source_type) DO UPDATE
              SET area_key = EXCLUDED.area_key
            RETURNING id
            """,
            area,
            st,
        )
        spot_id = int(row["id"])

        await conn.execute(
            """
            INSERT INTO gathering_spot_state(spot_id)
            VALUES ($1)
            ON CONFLICT(spot_id) DO NOTHING
            """,
            spot_id,
        )

    return spot_id


async def get_spot_snapshot(area_key: str, source_type: str, log_limit: int = 5) -> Dict[str, Any]:
    st = normalize_source_type(source_type)
    spot_id = await ensure_spot(area_key, st)

    pool = await get_pool()
    async with pool.acquire() as conn:
        state = await conn.fetchrow(
            """
            SELECT local_stock, quality_bias, danger_level, spirit_state, updated_at
            FROM gathering_spot_state
            WHERE spot_id = $1
            """,
            spot_id,
        )
        logs = await conn.fetch(
            """
            SELECT action, impact, intensity, created_at
            FROM gathering_spot_log
            WHERE spot_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            spot_id,
            log_limit,
        )

    return {
        "spot_id": spot_id,
        "area_key": area_key,
        "source_type": st,
        "local_stock": int(state["local_stock"]) if state else 100,
        "quality_bias": int(state["quality_bias"]) if state else 0,
        "danger_level": int(state["danger_level"]) if state else 0,
        "spirit_state": str(state["spirit_state"]) if state else "calm",
        "last_actions": [dict(r) for r in logs],
    }


async def get_global_pool(source_type: str) -> Dict[str, Any]:
    st = normalize_source_type(source_type)
    day = _today_utc()

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO gathering_global_pool(day, source_type, global_stock)
            VALUES ($1, $2, 100)
            ON CONFLICT(day, source_type) DO UPDATE
              SET day = EXCLUDED.day
            RETURNING global_stock
            """,
            day,
            st,
        )

    return {"day": str(day), "source_type": st, "global_stock": int(row["global_stock"])}


async def apply_start(
    *,
    area_key: str,
    source_type: str,
    risk: Optional[str],
    duration_min: int,
) -> Dict[str, Any]:
    """Start impact:
    - reduce GLOBAL pool (race)
    - write anonymous spot log (start)
    """
    st = normalize_source_type(source_type)
    spot_id = await ensure_spot(area_key, st)
    impact, intensity = _impact_for_risk(risk)

    # Global cost: depends on duration and intensity
    d = max(1, int(duration_min or 10))
    cost = _clamp((d // 10) + (intensity - 1), 1, 5)

    day = _today_utc()

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO gathering_global_pool(day, source_type, global_stock)
            VALUES ($1, $2, 100)
            ON CONFLICT(day, source_type) DO NOTHING
            """,
            day,
            st,
        )

        row = await conn.fetchrow(
            "SELECT global_stock FROM gathering_global_pool WHERE day=$1 AND source_type=$2",
            day,
            st,
        )
        g = int(row["global_stock"]) if row else 100
        g2 = _clamp(g - cost, 0, 100)

        await conn.execute(
            """
            UPDATE gathering_global_pool
            SET global_stock=$3, updated_at=NOW()
            WHERE day=$1 AND source_type=$2
            """,
            day,
            st,
            g2,
        )

        await conn.execute(
            """
            INSERT INTO gathering_spot_log(spot_id, action, impact, intensity)
            VALUES ($1, 'start', $2, $3)
            """,
            spot_id,
            impact,
            intensity,
        )

    return {"global_stock": g2, "cost": cost, "impact": impact, "intensity": intensity}


async def apply_finish(
    *,
    area_key: str,
    source_type: str,
    outcome: str,  # "complete"|"escape"|"fight_win"|"fight_lose"
    risk: Optional[str],
) -> Dict[str, Any]:
    """Finish impact:
    - reduce LOCAL stock (place competition)
    - update spirits/quality/danger
    - write anonymous spot log (complete/escape)
    """
    st = normalize_source_type(source_type)
    spot_id = await ensure_spot(area_key, st)
    impact, intensity = _impact_for_risk(risk)

    action = "complete" if outcome in ("complete", "fight_win") else "escape"
    deplete = (3 * intensity) if action == "complete" else (1 * intensity)

    pool = await get_pool()
    async with pool.acquire() as conn:
        state = await conn.fetchrow(
            """
            SELECT local_stock, quality_bias, danger_level, spirit_state
            FROM gathering_spot_state
            WHERE spot_id=$1
            """,
            spot_id,
        )

        local_stock = int(state["local_stock"]) if state else 100
        quality_bias = int(state["quality_bias"]) if state else 0
        danger_level = int(state["danger_level"]) if state else 0
        spirit_state: SpiritState = str(state["spirit_state"]) if state else "calm"

        local2 = _clamp(local_stock - deplete, 0, 100)

        if impact == "stabilize":
            danger_level = _clamp(danger_level - 1, 0, 5)
            quality_bias = _clamp(quality_bias + 1, -2, 2)
            spirit_state = "calm"
        elif impact == "deplete":
            if local2 <= 30:
                spirit_state = "restless"
            if local2 <= 20:
                danger_level = _clamp(danger_level + 1, 0, 5)
        else:  # corrupt
            spirit_state = "hostile"
            danger_level = _clamp(danger_level + 1, 0, 5)

        await conn.execute(
            """
            UPDATE gathering_spot_state
            SET local_stock=$2, quality_bias=$3, danger_level=$4, spirit_state=$5, updated_at=NOW()
            WHERE spot_id=$1
            """,
            spot_id,
            local2,
            quality_bias,
            danger_level,
            spirit_state,
        )

        await conn.execute(
            """
            INSERT INTO gathering_spot_log(spot_id, action, impact, intensity)
            VALUES ($1, $2, $3, $4)
            """,
            spot_id,
            action,
            impact,
            intensity,
        )

    return {
        "local_stock": local2,
        "quality_bias": quality_bias,
        "danger_level": danger_level,
        "spirit_state": spirit_state,
        "impact": impact,
        "intensity": intensity,
    }