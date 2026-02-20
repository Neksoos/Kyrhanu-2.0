# services/inventory/service.py
from __future__ import annotations

from fastapi import HTTPException
from typing import Any, Dict, Optional
import json

from db import get_pool

from services.inventory.models import InventoryItem, InventoryListResponse
from services.inventory.repo import (
    consume_repo,
    equip_repo,
    get_item_row,
    give_item_to_player_repo,
    list_inventory_rows,
    unequip_repo,
    unequip_slot_repo,
)
from services.inventory.utils import (
    merge_display_stats,
    normalize_slot,
    normalize_stats,
    pick_emoji,
)


def _norm_stats(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8")
            return json.loads(raw)
        except Exception:
            return {}
    try:
        return dict(raw)  # type: ignore
    except Exception:
        return {}


async def _load_item_meta(item_code: str) -> Optional[Dict[str, Any]]:
    code = (item_code or "").strip()
    if not code:
        return None
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT code, name, rarity, description, stats, emoji, slot, category
            FROM items
            WHERE code = $1
            LIMIT 1
            """,
            code,
        )
    return dict(row) if row else None


async def _enrich_kwargs_from_items(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Якщо фронт/роутер дав мінімум даних (або description/stats=None),
    підтягнути missing поля з таблиці items.
    """
    item_code = (kwargs.get("item_code") or kwargs.get("code") or "").strip()
    if not item_code:
        return kwargs

    meta = await _load_item_meta(item_code)
    if not meta:
        # якщо такого item_code нема в items — нехай repo обробляє як раніше
        return kwargs

    # Заповнюємо лише те, що не передали або передали як None/""
    def _is_missing(v: Any) -> bool:
        return v is None or (isinstance(v, str) and not v.strip())

    if _is_missing(kwargs.get("name")):
        kwargs["name"] = meta.get("name") or item_code

    if _is_missing(kwargs.get("rarity")):
        kwargs["rarity"] = meta.get("rarity")

    if _is_missing(kwargs.get("description")):
        kwargs["description"] = meta.get("description")

    if _is_missing(kwargs.get("emoji")):
        kwargs["emoji"] = meta.get("emoji")

    if _is_missing(kwargs.get("slot")):
        kwargs["slot"] = meta.get("slot")

    if _is_missing(kwargs.get("category")):
        kwargs["category"] = meta.get("category")

    # stats: якщо None — підтягуємо
    if kwargs.get("stats") is None:
        kwargs["stats"] = _norm_stats(meta.get("stats"))

    return kwargs


# ✅ FIX: приймаємо tg_id позиційно + решту як kwargs, і прокидуємо в repo
async def give_item_to_player(tg_id: int, **kwargs) -> None:
    # ✅ головний фікс: автопідтягування мети предмета
    kwargs = await _enrich_kwargs_from_items(dict(kwargs))
    await give_item_to_player_repo(tg_id=tg_id, **kwargs)


async def list_inventory(tg_id: int) -> InventoryListResponse:
    rows = await list_inventory_rows(tg_id)

    items: list[InventoryItem] = []
    for r in rows:
        merged_stats = merge_display_stats(
            base_stats=normalize_stats(r["stats"]),
            atk=int(r["atk"] or 0),
            defense=int(r["defense"] or 0),
            hp=int(r["hp"] or 0),
            mp=int(r["mp"] or 0),
            weight=int(r["weight"] or 0),
        )

        slot_val = normalize_slot(r["item_slot"] or r["inv_slot"])

        items.append(
            InventoryItem(
                id=r["inv_id"],
                item_id=r["item_id"],
                item_code=r["item_code"],
                emoji=pick_emoji(r["category"], r["emoji"], slot_val),
                name=r["name"],
                description=r["description"],
                rarity=r["rarity"],
                slot=slot_val,
                stats=merged_stats,
                qty=int(r["qty"] or 1),
                is_equipped=bool(r["is_equipped"]),
            )
        )

    return InventoryListResponse(items=items)


async def get_item(inv_id: int, tg_id: int) -> InventoryItem:
    r = await get_item_row(inv_id, tg_id)
    if not r:
        raise HTTPException(404, "ITEM_NOT_FOUND")

    merged_stats = merge_display_stats(
        base_stats=normalize_stats(r["stats"]),
        atk=int(r["atk"] or 0),
        defense=int(r["defense"] or 0),
        hp=int(r["hp"] or 0),
        mp=int(r["mp"] or 0),
        weight=int(r["weight"] or 0),
    )

    slot_val = normalize_slot(r["item_slot"] or r["inv_slot"])

    return InventoryItem(
        id=r["inv_id"],
        item_id=r["item_id"],
        item_code=r["item_code"],
        emoji=pick_emoji(r["category"], r["emoji"], slot_val),
        name=r["name"],
        description=r["description"],
        rarity=r["rarity"],
        slot=slot_val,
        stats=merged_stats,
        qty=int(r["qty"] or 1),
        is_equipped=bool(r["is_equipped"]),
    )


async def equip(inv_id: int, tg_id: int) -> None:
    await equip_repo(inv_id, tg_id)


async def unequip(inv_id: int, tg_id: int) -> None:
    await unequip_repo(inv_id, tg_id)


async def unequip_slot(slot: str, tg_id: int) -> None:
    await unequip_slot_repo(slot, tg_id)


async def consume(inv_id: int, tg_id: int, qty: int) -> dict:
    data = await consume_repo(inv_id, tg_id, qty)
    return {"ok": True, **data}