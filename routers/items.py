"""Item API router for Kyrhanu.

This router exposes a single endpoint, ``/items/brief``, which returns
a combined list of item and craft material names.  The backend stores
equipment, consumables, resources and other objects in the ``items``
table, while profession ingredients live in ``craft_materials``.  UI
clients such as the blacksmith page use this endpoint to populate
dropdowns and labels without needing to issue two separate requests.

The implementation uses the existing asyncpg connection pool via
``db.get_pool`` and executes simple SELECT queries.  Results are
merged into a single list with consistent key names.  Optional query
parameter ``q`` allows filtering by code or name (case-insensitive).

Example response:

```
{
  "items": [
    {"code": "sword_0001", "name": "Залізний меч"},
    {"code": "herb_polin_0003", "name": "Нетрицький полин"},
    {"code": "smith_ingot_zalizna", "name": "Залізний чушок"},
    ...
  ]
}
```
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any

from fastapi import APIRouter

from db import get_pool


router = APIRouter(prefix="/items", tags=["items"])


@router.get("/brief")
async def items_brief(q: Optional[str] = None) -> Dict[str, List[Dict[str, str]]]:
    """Return a list of all items and craft materials with their codes and names.

    Parameters
    ----------
    q: str | None
        Optional search query to filter by ``code`` or ``name`` (case-insensitive).

    Returns
    -------
    dict
        A dictionary with a single key ``items`` whose value is a list of objects
        having ``code`` and ``name`` fields.

    This endpoint is used by the client UI (e.g. the blacksmith page) to
    populate recipe names.  It combines the ``items`` and ``craft_materials``
    tables, ensuring that profession-specific ingredients such as
    ``smith_*`` appear alongside regular equipment and resources.
    """
    pool = await get_pool()
    items: List[Dict[str, str]] = []

    # Prepare the filter clause and parameters if a search query is provided
    filter_clause = ""
    params: List[Any] = []
    if q and q.strip():
        qq = f"%{q.strip()}%"
        filter_clause = "WHERE code ILIKE $1 OR name ILIKE $1"
        params.append(qq)

    async with pool.acquire() as conn:
        # Fetch from items table
        if filter_clause:
            rows_items = await conn.fetch(
                f"""
                SELECT code, name
                FROM items
                {filter_clause}
                ORDER BY id ASC
                """,
                *params,
            )
        else:
            rows_items = await conn.fetch(
                """
                SELECT code, name
                FROM items
                ORDER BY id ASC
                """
            )

        for r in rows_items:
            items.append({"code": str(r["code"]), "name": r["name"]})

        # Fetch from craft_materials table
        if filter_clause:
            rows_mats = await conn.fetch(
                f"""
                SELECT code, name
                FROM craft_materials
                {filter_clause}
                ORDER BY id ASC
                """,
                *params,
            )
        else:
            rows_mats = await conn.fetch(
                """
                SELECT code, name
                FROM craft_materials
                ORDER BY id ASC
                """
            )
        for r in rows_mats:
            items.append({"code": str(r["code"]), "name": r["name"]})

    return {"items": items}
