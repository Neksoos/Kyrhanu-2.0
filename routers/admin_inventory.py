from __future__ import annotations

from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers.admin_guard import require_admin
from services.inventory.service import (
    list_inventory as svc_list_inventory,
    give_item_to_player as svc_give_item,
    get_item as svc_get_item,
    consume as svc_consume,
)

router = APIRouter(prefix="/admin/inventory", tags=["admin-inventory"])


class GiveItemDTO(BaseModel):
    """Parameters for granting an item to a player.

    Only ``item_code`` and ``qty`` are strictly required.  Additional
    optional fields allow the admin to override default metadata stored
    in the ``items`` table when giving the item (for example, a custom
    name or rarity).  These values will be passed through to the
    underlying inventory service.
    """

    item_code: str
    qty: int = 1
    name: Optional[str] = None
    rarity: Optional[str] = None
    description: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None
    emoji: Optional[str] = None
    slot: Optional[str] = None
    category: Optional[str] = None


@router.get("/{tg_id}")
async def get_inventory(tg_id: int, _admin=Depends(require_admin)):
    """Return the full inventory for a given player (by tg_id)."""
    data = await svc_list_inventory(tg_id)
    # Pydantic models have a ``dict`` method; convert each item
    return {"ok": True, "items": [item.dict() for item in data.items]}


@router.post("/{tg_id}/give")
async def give_item(tg_id: int, dto: GiveItemDTO, _admin=Depends(require_admin)):
    """Grant an item to the specified player.

    This endpoint uses the underlying inventory service which will
    normalize missing metadata based on the ``items`` table.  If a
    requested item code does not exist in the base table, the
    inventory service will still create an entry with the provided
    metadata.
    """
    await svc_give_item(
        tg_id,
        item_code=dto.item_code,
        qty=dto.qty,
        name=dto.name,
        rarity=dto.rarity,
        description=dto.description,
        stats=dto.stats,
        emoji=dto.emoji,
        slot=dto.slot,
        category=dto.category,
    )
    return {"ok": True}


@router.delete("/{tg_id}/{inv_id}")
async def remove_item(tg_id: int, inv_id: int, _admin=Depends(require_admin)):
    """Remove an entire stack of an inventory item from a player.

    This operation consumes all units of the specified inventory record.
    If the inventory entry is not found, a 404 error will be raised.
    """
    item = await svc_get_item(inv_id, tg_id)
    qty = item.qty
    # Use the consume service to remove the stack.  This will handle
    # quantity decrement and deletion of the record when quantity hits zero.
    await svc_consume(inv_id, tg_id, qty)
    return {"ok": True}
