import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user_id

router = APIRouter(prefix="/shop", tags=["shop"])


@router.get("")
async def shop_list(db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            text(
                """
                SELECT s.id AS offer_id,
                       (s.data->>'item_id') AS item_id,
                       COALESCE((s.data->'price'->>'chervontsi')::int, 0) AS price_chervontsi,
                       COALESCE((s.data->>'stock')::int, 0) AS stock,
                       COALESCE(s.data->>'tag', '') AS tag,
                       i.data->>'name' AS name,
                       COALESCE(i.data->>'slot', '') AS slot,
                       COALESCE(i.data->>'rarity', '') AS rarity,
                       COALESCE(i.data->'stats', '{}'::jsonb) AS stats
                FROM shop s
                JOIN items i ON i.id = (s.data->>'item_id')
                ORDER BY tag, offer_id
                """
            )
        )
    ).mappings().all()
    return {"ok": True, "offers": [dict(r) for r in rows]}


@router.post("/buy")
async def shop_buy(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    offer_id = (body or {}).get("offer_id") or (body or {}).get("id")
    if not offer_id:
        raise HTTPException(status_code=400, detail="Missing offer_id")

    offer = (
        await db.execute(
            text(
                """
                SELECT s.id AS offer_id,
                       (s.data->>'item_id') AS item_id,
                       COALESCE((s.data->'price'->>'chervontsi')::int, 0) AS price_chervontsi
                FROM shop s
                WHERE s.id = :oid
                """
            ),
            {"oid": offer_id},
        )
    ).mappings().first()

    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    price = int(offer["price_chervontsi"] or 0)

    # Wallet check + deduct
    w = (
        await db.execute(
            text("SELECT chervontsi FROM wallet WHERE user_id = :uid FOR UPDATE"),
            {"uid": user_id},
        )
    ).first()
    if not w:
        raise HTTPException(status_code=400, detail="Wallet not found")

    balance = int(w[0] or 0)
    if balance < price:
        raise HTTPException(status_code=400, detail="Not enough chervontsi")

    await db.execute(
        text("UPDATE wallet SET chervontsi = chervontsi - :p WHERE user_id = :uid"),
        {"p": price, "uid": user_id},
    )

    # Create item instance + add to inventory
    inst_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    await db.execute(
        text(
            """
            INSERT INTO item_instances (id, user_id, item_id, rarity, affixes, created_at)
            VALUES (:iid, :uid, :item_id, 'common', '{}'::jsonb, :now)
            """
        ),
        {"iid": str(inst_id), "uid": user_id, "item_id": offer["item_id"], "now": now},
    )

    await db.execute(
        text(
            """
            INSERT INTO inventory (user_id, item_instance_id, qty)
            VALUES (:uid, :iid, 1)
            ON CONFLICT (user_id, item_instance_id)
            DO UPDATE SET qty = inventory.qty + 1
            """
        ),
        {"uid": user_id, "iid": str(inst_id)},
    )

    await db.commit()

    return {
        "ok": True,
        "bought": {
            "item_instance_id": str(inst_id),
            "item_id": offer["item_id"],
            "price_chervontsi": price,
        },
    }
