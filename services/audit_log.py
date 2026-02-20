from __future__ import annotations

import json
from typing import Any, Dict, Optional

from loguru import logger

from db import get_pool


async def log_player_action(
    tg_id: int,
    action_type: str,
    *,
    actor_type: str = "player",
    context: Optional[Dict[str, Any]] = None,
    conn=None,
) -> None:
    """Write one row into player_actions.

    - tg_id: Telegram user id of the player.
    - action_type: short code (e.g. "battle.attack"), or a route-based string
      like "POST /api/gathering/quick".
    - actor_type: "player" | "admin" | "system".
    - context: arbitrary JSON-serializable dict.

    This function is intentionally "best-effort": it must never break gameplay.
    """
    try:
        tg_id_int = int(tg_id)
    except Exception:
        return

    if tg_id_int <= 0:
        return

    action = (action_type or "").strip()
    if not action:
        return

    actor = (actor_type or "player").strip() or "player"
    ctx = context or {}

    ctx_json = json.dumps(ctx, ensure_ascii=False, default=str)

    sql = (
        "INSERT INTO player_actions (tg_id, action_type, actor_type, context) "
        "VALUES ($1, $2, $3, $4::jsonb)"
    )

    try:
        if conn is not None:
            await conn.execute(sql, tg_id_int, action, actor, ctx_json)
            return

        pool = await get_pool()
        async with pool.acquire() as c:
            await c.execute(sql, tg_id_int, action, actor, ctx_json)
    except Exception as e:
        logger.debug(f"audit_log insert failed: {e}")