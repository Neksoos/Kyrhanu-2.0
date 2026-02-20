from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

# ✅ Правильні імпорти:
from routers.auth import get_player
from models.player import PlayerDTO
from db import get_pool

# ✅ Правильні назви каталогів:
from routers.premium_frames import FRAMES_CATALOG
from routers.premium_names import NAMES_CATALOG
from routers.premium_avatars import AVATARS_CATALOG, AVATAR_VARIANT_TO_BASE

router = APIRouter(prefix="/api", tags=["premium"])

# Об’єднаний каталог: sku -> item
CATALOG: Dict[str, Dict[str, Any]] = {
    **FRAMES_CATALOG,
    **NAMES_CATALOG,
    **AVATARS_CATALOG,
}

# Щоб не виконувати DDL на кожен запит
_SCHEMA_READY = False


def _normalize_sku(sku_in: str) -> str:
    """Для аватарів: avatar_xxx_m/f -> avatar_xxx"""
    sku = (sku_in or "").strip()
    return AVATAR_VARIANT_TO_BASE.get(sku, sku)


async def _ensure_premium_schema() -> None:
    """Створює потрібні таблиці та колонки, CHECK має включати avatar."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        # 1) Таблиця + індекс (avatar включено)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS player_premium_owned (
              tg_id BIGINT NOT NULL,
              sku TEXT NOT NULL,
              kind TEXT NOT NULL CHECK (kind IN ('frame','name','avatar')),
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              PRIMARY KEY (tg_id, sku)
            );

            CREATE INDEX IF NOT EXISTS idx_player_premium_owned_tg
              ON player_premium_owned (tg_id);
            """
        )

        # 2) Якщо таблиця була створена раніше без updated_at — додамо (щоб INSERT не падав)
        await conn.execute(
            """
            ALTER TABLE player_premium_owned
              ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();

            ALTER TABLE player_premium_owned
              ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
            """
        )

        # 3) Слоти у players
        await conn.execute(
            """
            ALTER TABLE players
              ADD COLUMN IF NOT EXISTS equipped_frame_sku  TEXT;

            ALTER TABLE players
              ADD COLUMN IF NOT EXISTS equipped_name_sku   TEXT;

            ALTER TABLE players
              ADD COLUMN IF NOT EXISTS equipped_avatar_sku TEXT;
            """
        )

        # 4) Оновлюємо constraint (якщо він старий і без avatar)
        await conn.execute(
            """
            ALTER TABLE player_premium_owned
              DROP CONSTRAINT IF EXISTS player_premium_owned_kind_check;

            ALTER TABLE player_premium_owned
              ADD CONSTRAINT player_premium_owned_kind_check
              CHECK (kind IN ('frame','name','avatar'));
            """
        )

    _SCHEMA_READY = True


async def _owned_skus(tg_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT sku FROM player_premium_owned WHERE tg_id=$1", tg_id)
    return [r["sku"] for r in rows]


async def _equip_get(tg_id: int) -> Dict[str, Any]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT equipped_frame_sku, equipped_name_sku, equipped_avatar_sku FROM players WHERE tg_id=$1",
            tg_id,
        )
    return {
        "frame_sku": row["equipped_frame_sku"] if row else None,
        "name_sku": row["equipped_name_sku"] if row else None,
        "avatar_sku": row["equipped_avatar_sku"] if row else None,
    }


class PurchaseIn(BaseModel):
    sku: str


class EquipIn(BaseModel):
    sku: str


_EQUIP_COL_BY_KIND = {
    "frame": "equipped_frame_sku",
    "name": "equipped_name_sku",
    "avatar": "equipped_avatar_sku",
}


@router.get("/premium/catalog")
async def premium_catalog(player: PlayerDTO = Depends(get_player)):
    """Повертає каталог і придбані/активовані предмети."""
    await _ensure_premium_schema()
    tg_id = int(player.tg_id)

    owned = await _owned_skus(tg_id)
    equipped = await _equip_get(tg_id)

    return {
        "ok": True,
        "catalog": {sku: jsonable_encoder(item) for sku, item in CATALOG.items()},
        "owned_skus": owned,
        "equipped": equipped,
    }


@router.post("/premium/purchase")
async def premium_purchase(body: PurchaseIn, player: PlayerDTO = Depends(get_player)):
    """Покупка предмета за клейноди."""
    await _ensure_premium_schema()
    tg_id = int(player.tg_id)

    sku_in = str(body.sku or "").strip()
    if not sku_in:
        raise HTTPException(400, {"code": "BAD_REQUEST", "reason": "missing sku"})

    sku = _normalize_sku(sku_in)
    item = CATALOG.get(sku)
    if not item:
        raise HTTPException(404, {"code": "UNKNOWN_SKU"})

    price = int(item.get("price_kleynody") or 0)
    if price <= 0:
        raise HTTPException(400, {"code": "BAD_PRICE"})

    kind = str(item.get("kind") or "").strip()
    if kind not in ("frame", "name", "avatar"):
        raise HTTPException(400, {"code": "BAD_KIND"})

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # ✅ Захист від подвійного кліку: якщо вже є — не списуємо вдруге
            already = await conn.fetchval(
                "SELECT 1 FROM player_premium_owned WHERE tg_id=$1 AND sku=$2",
                tg_id, sku
            )
            if already:
                return {
                    "ok": True,
                    "sku": sku,
                    "kind": kind,
                    "price_kleynody": price,
                    "already_owned": True,
                }

            bal = await conn.fetchval(
                "SELECT kleynody FROM players WHERE tg_id=$1 FOR UPDATE",
                tg_id
            )
            if bal is None:
                raise HTTPException(409, {"code": "NEED_REGISTER"})
            if int(bal) < price:
                raise HTTPException(400, {"code": "NOT_ENOUGH_KLEYNODY"})

            await conn.execute(
                "UPDATE players SET kleynody=kleynody-$1 WHERE tg_id=$2",
                price, tg_id
            )

            await conn.execute(
                """
                INSERT INTO player_premium_owned (tg_id, sku, kind, created_at, updated_at)
                VALUES ($1, $2, $3, now(), now())
                ON CONFLICT (tg_id, sku)
                DO UPDATE SET kind=EXCLUDED.kind, updated_at=now()
                """,
                tg_id, sku, kind
            )

            # ✅ Авто-еквіп, якщо слот порожній
            auto_equipped = False
            slot_col = _EQUIP_COL_BY_KIND.get(kind)
            if slot_col:
                cur = await conn.fetchval(f"SELECT {slot_col} FROM players WHERE tg_id=$1", tg_id)
                if cur in (None, ""):
                    await conn.execute(
                        f"UPDATE players SET {slot_col}=$1 WHERE tg_id=$2",
                        sku, tg_id
                    )
                    auto_equipped = True

    return {
        "ok": True,
        "sku": sku,
        "kind": kind,
        "price_kleynody": price,
        "already_owned": False,
        "auto_equipped": auto_equipped,
        "purchased_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/premium/equip")
async def premium_equip(body: EquipIn, player: PlayerDTO = Depends(get_player)):
    """Активує предмет (frame / name / avatar)."""
    await _ensure_premium_schema()
    tg_id = int(player.tg_id)

    sku_in = str(body.sku or "").strip()
    if not sku_in:
        raise HTTPException(400, {"code": "BAD_REQUEST", "reason": "missing sku"})

    sku = _normalize_sku(sku_in)
    item = CATALOG.get(sku)
    if not item:
        raise HTTPException(404, {"code": "UNKNOWN_SKU"})

    kind = str(item.get("kind") or "").strip()
    if kind not in ("frame", "name", "avatar"):
        raise HTTPException(400, {"code": "BAD_KIND"})

    slot_col = _EQUIP_COL_BY_KIND.get(kind)
    if not slot_col:
        raise HTTPException(400, {"code": "BAD_KIND"})

    pool = await get_pool()
    async with pool.acquire() as conn:
        owned = await conn.fetchval(
            "SELECT 1 FROM player_premium_owned WHERE tg_id=$1 AND sku=$2",
            tg_id, sku
        )
        if not owned:
            raise HTTPException(403, {"code": "NOT_OWNED"})

        await conn.execute(
            f"UPDATE players SET {slot_col}=$1 WHERE tg_id=$2",
            sku, tg_id
        )

    return {"ok": True, "sku": sku, "kind": kind, "equipped_at": datetime.now(timezone.utc).isoformat()}