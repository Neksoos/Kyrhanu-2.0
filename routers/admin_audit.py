from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from routers.admin_guard import require_admin
from db import get_pool

router = APIRouter(prefix="/admin/audit", tags=["admin-audit"])


@router.get("")
async def list_actions(
    tg_id: Optional[int] = Query(default=None, description="Filter by player tg_id"),
    action_type: Optional[str] = Query(default=None, description="Filter by action type code"),
    actor_type: Optional[str] = Query(default=None, description="Filter by actor (player/admin/system)"),
    start_date: Optional[datetime] = Query(default=None, description="Inclusive start of date filter"),
    end_date: Optional[datetime] = Query(default=None, description="Inclusive end of date filter"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _admin=Depends(require_admin),
):
    """Retrieve audit log entries with flexible filtering.

    This endpoint exposes the contents of the ``player_actions`` table.
    Administrators can filter by player id, action type, actor type, and
    creation timestamps.  Results are ordered from newest to oldest.
    """
    # Dynamically build WHERE clause based on provided filters.
    clauses: list[str] = []
    params: list = []
    if tg_id is not None:
        clauses.append(f"tg_id = ${len(params) + 1}")
        params.append(tg_id)
    if action_type:
        clauses.append(f"action_type = ${len(params) + 1}")
        params.append(action_type)
    if actor_type:
        clauses.append(f"actor_type = ${len(params) + 1}")
        params.append(actor_type)
    if start_date:
        clauses.append(f"created_at >= ${len(params) + 1}")
        params.append(start_date)
    if end_date:
        clauses.append(f"created_at <= ${len(params) + 1}")
        params.append(end_date)

    where_clause = " AND ".join(clauses) if clauses else "TRUE"
    # Append limit and offset after all filtering params
    params.append(limit)
    params.append(offset)

    sql = f"SELECT * FROM player_actions WHERE {where_clause} ORDER BY created_at DESC LIMIT ${len(params)-1} OFFSET ${len(params)}"

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return {"ok": True, "items": [dict(r) for r in rows]}
