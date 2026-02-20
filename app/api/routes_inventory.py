import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user_id

router = APIRouter(prefix="/inventory", tags=["inventory"])


async def _ensure_equipment(db: AsyncSession, user_id: str) -> None:
    await db.execute(
        text(
            """
            INSERT INTO equipment (user_id, slots)
            VALUES (:uid, '{}'::jsonb)
            ON CONFLICT (user_id) DO NOTHING
            """
        ),
        {"uid": user_id},
    )


@router.get("")
async def inventory_get(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    await _ensure_equipment(db, user_id)

    equip = (
        await db.execute(
            text("SELECT slots FROM equipment WHERE user_id = :uid"),
            {"uid": user_id},
        )
    ).first()
    slots = equip[0] if equip else {}

    items = (
        await db.execute(
            text(
                """
                SELECT inv.item_instance_id,
                       inv.qty,
                       ii.item_id,
                       i.data->>'name' AS name,
                       COALESCE(i.data->>'slot', '') AS slot,
                       COALESCE(i.data->>'rarity', '') AS rarity,
                       COALESCE(i.data->'stats', '{}'::jsonb) AS stats,
                       ii.created_at
                FROM inventory inv
                JOIN item_instances ii ON ii.id = inv.item_instance_id
                JOIN items i ON i.id = ii.item_id
                WHERE inv.user_id = :uid
                ORDER BY ii.created_at DESC
                """
            ),
            {"uid": user_id},
        )
    ).mappings().all()

    return {"ok": True, "equipment": slots, "items": [dict(r) for r in items]}


@router.post("/equip")
async def inventory_equip(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    item_instance_id = (body or {}).get("item_instance_id")
    if not item_instance_id:
        raise HTTPException(status_code=400, detail="Missing item_instance_id")

    await _ensure_equipment(db, user_id)

    # Validate ownership + get slot
    row = (
        await db.execute(
            text(
                """
                SELECT ii.id, i.data->>'slot' AS slot
                FROM item_instances ii
                JOIN items i ON i.id = ii.item_id
                WHERE ii.id = :iid AND ii.user_id = :uid
                """
            ),
            {"iid": item_instance_id, "uid": user_id},
        )
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Item not found")

    slot = row["slot"] or "misc"

    equip = (
        await db.execute(
            text("SELECT slots FROM equipment WHERE user_id = :uid FOR UPDATE"),
            {"uid": user_id},
        )
    ).first()
    slots = equip[0] if equip else {}

    if isinstance(slots, str):
        slots = json.loads(slots)

    slots = dict(slots or {})
    slots[slot] = str(item_instance_id)

    # NOTE: SQLAlchemy's text() parser intentionally avoids bind params directly followed by ':'
    # (to not confuse with PostgreSQL '::' casts). Use CAST(:param AS jsonb) instead of :param::jsonb.
    await db.execute(
        text("UPDATE equipment SET slots = CAST(:slots AS jsonb) WHERE user_id = :uid"),
        {"slots": json.dumps(slots), "uid": user_id},
    )
    await db.commit()

    return {"ok": True, "equipment": slots}


@router.post("/unequip")
async def inventory_unequip(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    slot = (body or {}).get("slot")
    if not slot:
        raise HTTPException(status_code=400, detail="Missing slot")

    await _ensure_equipment(db, user_id)

    equip = (
        await db.execute(
            text("SELECT slots FROM equipment WHERE user_id = :uid FOR UPDATE"),
            {"uid": user_id},
        )
    ).first()
    slots = equip[0] if equip else {}

    if isinstance(slots, str):
        slots = json.loads(slots)

    slots = dict(slots or {})
    if slot in slots:
        slots.pop(slot)

    await db.execute(
        text("UPDATE equipment SET slots = CAST(:slots AS jsonb) WHERE user_id = :uid"),
        {"slots": json.dumps(slots), "uid": user_id},
    )
    await db.commit()

    return {"ok": True, "equipment": slots}
