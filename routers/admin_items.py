from __future__ import annotations

from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from routers.admin_guard import require_admin
from db import get_pool

router = APIRouter(prefix="/admin/items", tags=["admin-items"])


class ItemDTO(BaseModel):
    """Data transfer object for creating a new item.

    Many of the fields are optional so that items with minimal
    information can still be created; however, ``code`` and
    ``name`` are required because they uniquely identify and label
    the item.  Additional stats such as attack, defense, HP, and
    MP are supported for equipment items.
    """

    code: str
    name: str
    emoji: Optional[str] = None
    category: Optional[str] = None
    rarity: Optional[str] = None
    description: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None
    base_value: Optional[int] = None
    sell_price: Optional[int] = None
    slot: Optional[str] = None
    atk: Optional[int] = None
    defense: Optional[int] = None
    hp: Optional[int] = None
    mp: Optional[int] = None
    level_req: Optional[int] = None
    class_req: Optional[str] = None
    is_active: Optional[bool] = True
    stackable: Optional[bool] = None


class ItemUpdateDTO(BaseModel):
    """Data transfer object for updating an existing item.

    All fields are optional; only the provided values will overwrite
    existing ones.
    """

    name: Optional[str] = None
    emoji: Optional[str] = None
    category: Optional[str] = None
    rarity: Optional[str] = None
    description: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None
    base_value: Optional[int] = None
    sell_price: Optional[int] = None
    slot: Optional[str] = None
    atk: Optional[int] = None
    defense: Optional[int] = None
    hp: Optional[int] = None
    mp: Optional[int] = None
    level_req: Optional[int] = None
    class_req: Optional[str] = None
    is_active: Optional[bool] = None
    stackable: Optional[bool] = None


@router.get("")
async def list_items(
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _admin=Depends(require_admin),
):
    """List items with optional search on code/name.

    Parameters
    ----------
    q: str | None
        Optional search query to filter by ``code`` or ``name`` (case-insensitive).
    limit: int
        Maximum number of items to return.
    offset: int
        Number of items to skip before starting the page.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        if q and q.strip():
            qq = f"%{q.strip()}%"
            rows = await conn.fetch(
                """
                SELECT *
                FROM items
                WHERE code ILIKE $1 OR name ILIKE $1
                ORDER BY code ASC
                LIMIT $2 OFFSET $3
                """,
                qq,
                limit,
                offset,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT *
                FROM items
                ORDER BY code ASC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
    return {"ok": True, "items": [dict(r) for r in rows]}


@router.get("/{code}")
async def get_item(code: str, _admin=Depends(require_admin)):
    """Retrieve a single item by its code."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM items WHERE code = $1", code)
    if not row:
        raise HTTPException(status_code=404, detail={"error": "ITEM_NOT_FOUND"})
    return {"ok": True, "item": dict(row)}


@router.post("")
async def create_item(dto: ItemDTO, _admin=Depends(require_admin)):
    """Create a new item in the database."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                """
                INSERT INTO items (
                    code, name, emoji, category, rarity, description, stats,
                    base_value, sell_price, slot, atk, defense, hp, mp,
                    level_req, class_req, is_active, stackable
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7,
                    $8, $9, $10, $11, $12, $13, $14,
                    $15, $16, $17, $18
                )
                """,
                dto.code,
                dto.name,
                dto.emoji,
                dto.category,
                dto.rarity,
                dto.description,
                dto.stats,
                dto.base_value,
                dto.sell_price,
                dto.slot,
                dto.atk,
                dto.defense,
                dto.hp,
                dto.mp,
                dto.level_req,
                dto.class_req,
                dto.is_active,
                dto.stackable,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail={"error": str(e)})
    return {"ok": True}


@router.put("/{code}")
async def update_item(code: str, dto: ItemUpdateDTO, _admin=Depends(require_admin)):
    """Update an existing item.  Only provided fields will be updated."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM items WHERE code = $1", code)
        if not row:
            raise HTTPException(status_code=404, detail={"error": "ITEM_NOT_FOUND"})
        data = dict(row)
        # merge provided fields into existing data
        for field, value in dto.dict(exclude_unset=True).items():
            data[field] = value
        await conn.execute(
            """
            UPDATE items
            SET name=$2, emoji=$3, category=$4, rarity=$5, description=$6,
                stats=$7, base_value=$8, sell_price=$9, slot=$10,
                atk=$11, defense=$12, hp=$13, mp=$14,
                level_req=$15, class_req=$16, is_active=$17, stackable=$18,
                updated_at=NOW()
            WHERE code=$1
            """,
            code,
            data.get("name"),
            data.get("emoji"),
            data.get("category"),
            data.get("rarity"),
            data.get("description"),
            data.get("stats"),
            data.get("base_value"),
            data.get("sell_price"),
            data.get("slot"),
            data.get("atk"),
            data.get("defense"),
            data.get("hp"),
            data.get("mp"),
            data.get("level_req"),
            data.get("class_req"),
            data.get("is_active"),
            data.get("stackable"),
        )
    return {"ok": True}


@router.delete("/{code}")
async def delete_item(code: str, _admin=Depends(require_admin)):
    """Soft-delete an item by marking it as inactive."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # mark the item inactive rather than physically deleting
        await conn.execute("UPDATE items SET is_active = FALSE WHERE code = $1", code)
    return {"ok": True}
