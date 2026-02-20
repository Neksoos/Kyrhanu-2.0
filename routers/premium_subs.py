from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from db import get_pool
from models.player import PlayerDTO
from routers.auth import get_player
from services.energy import (
    BASE_DAILY_ENERGY,
    BASE_CAP,
    WATER_DAILY,
    WATER_CAP,
    MOLFAR_DAILY,
    MOLFAR_CAP,
    MOLFAR_CARRY_LIMIT,
    _normalize_player_energy,
)


router = APIRouter(prefix="/api", tags=["premium_subs"])


# ──────────────────────────────────────────────────────────────
# Catalog
#
# Ціни — орієнтовні. Можеш підкрутити під свою економіку.
# Якщо хочеш, винесемо в .env.
# ──────────────────────────────────────────────────────────────

SUBS_CATALOG: Dict[str, Dict[str, Any]] = {
    # Жива вода
    "sub_water_1d": {
        "kind": "sub",
        "tier": "water",
        "days": 1,
        "title": "Жива вода — 1 день",
        "price_kleynody": 12,
        "effects": {"daily": WATER_DAILY, "cap": WATER_CAP},
    },
    "sub_water_7d": {
        "kind": "sub",
        "tier": "water",
        "days": 7,
        "title": "Жива вода — 7 днів",
        "price_kleynody": 60,
        "effects": {"daily": WATER_DAILY, "cap": WATER_CAP},
    },
    "sub_water_30d": {
        "kind": "sub",
        "tier": "water",
        "days": 30,
        "title": "Жива вода — 30 днів",
        "price_kleynody": 200,
        "effects": {"daily": WATER_DAILY, "cap": WATER_CAP},
    },

    # Благословення мольфара
    "sub_molfar_1d": {
        "kind": "sub",
        "tier": "molfar",
        "days": 1,
        "title": "Благословення мольфара — 1 день",
        "price_kleynody": 18,
        "effects": {"daily": MOLFAR_DAILY, "cap": MOLFAR_CAP, "carry_limit": MOLFAR_CARRY_LIMIT},
    },
    "sub_molfar_7d": {
        "kind": "sub",
        "tier": "molfar",
        "days": 7,
        "title": "Благословення мольфара — 7 днів",
        "price_kleynody": 90,
        "effects": {"daily": MOLFAR_DAILY, "cap": MOLFAR_CAP, "carry_limit": MOLFAR_CARRY_LIMIT},
    },
    "sub_molfar_30d": {
        "kind": "sub",
        "tier": "molfar",
        "days": 30,
        "title": "Благословення мольфара — 30 днів",
        "price_kleynody": 300,
        "effects": {"daily": MOLFAR_DAILY, "cap": MOLFAR_CAP, "carry_limit": MOLFAR_CARRY_LIMIT},
    },
}


async def _ensure_schema() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            ALTER TABLE players
              ADD COLUMN IF NOT EXISTS premium_water_until  timestamptz,
              ADD COLUMN IF NOT EXISTS premium_molfar_until timestamptz;
            """
        )


def _active_tier(
    *,
    now: datetime,
    water_until: Optional[datetime],
    molfar_until: Optional[datetime],
) -> str:
    if molfar_until and molfar_until > now:
        return "molfar"
    if water_until and water_until > now:
        return "water"
    return "none"


class PurchaseSubIn(BaseModel):
    sku: str


@router.get("/premium/subs/catalog")
async def premium_subs_catalog(player: PlayerDTO = Depends(get_player)):
    """Каталог підписок + поточний статус гравця."""
    await _ensure_schema()
    tg_id = int(player.tg_id)
    now = datetime.now(timezone.utc)

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT premium_water_until, premium_molfar_until
            FROM players
            WHERE tg_id=$1
            """,
            tg_id,
        )

    water_until = row["premium_water_until"] if row else None
    molfar_until = row["premium_molfar_until"] if row else None

    tier = _active_tier(now=now, water_until=water_until, molfar_until=molfar_until)

    # Пояснення ефектів (щоб фронт міг показати текст)
    effects = {
        "none": {"daily": BASE_DAILY_ENERGY, "cap": BASE_CAP},
        "water": {"daily": WATER_DAILY, "cap": WATER_CAP},
        "molfar": {"daily": MOLFAR_DAILY, "cap": MOLFAR_CAP, "carry_limit": MOLFAR_CARRY_LIMIT},
    }

    return {
        "ok": True,
        "now": now.isoformat(),
        "active_tier": tier,
        "premium_water_until": water_until.isoformat() if water_until else None,
        "premium_molfar_until": molfar_until.isoformat() if molfar_until else None,
        "current_effects": effects.get(tier, effects["none"]),
        "catalog": {sku: jsonable_encoder(item) for sku, item in SUBS_CATALOG.items()},
    }


@router.post("/premium/subs/purchase")
async def premium_subs_purchase(body: PurchaseSubIn, player: PlayerDTO = Depends(get_player)):
    """Покупка підписки за клейноди (пак 1/7/30 днів)."""
    await _ensure_schema()
    tg_id = int(player.tg_id)
    now = datetime.now(timezone.utc)
    today = date.today()

    sku = (body.sku or "").strip()
    if not sku:
        raise HTTPException(400, {"code": "BAD_REQUEST", "reason": "missing sku"})

    item = SUBS_CATALOG.get(sku)
    if not item:
        raise HTTPException(404, {"code": "UNKNOWN_SKU"})

    price = int(item.get("price_kleynody") or 0)
    if price <= 0:
        raise HTTPException(400, {"code": "BAD_PRICE"})

    tier = str(item.get("tier") or "")
    days = int(item.get("days") or 0)
    if tier not in ("water", "molfar") or days <= 0:
        raise HTTPException(400, {"code": "BAD_ITEM"})

    col = "premium_water_until" if tier == "water" else "premium_molfar_until"

    # Повернемо оновлені значення, щоб фронт міг одразу перемалюватись.
    energy_after: Optional[int] = None
    energy_max_after: Optional[int] = None

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT
                  kleynody,
                  premium_water_until,
                  premium_molfar_until,
                  energy,
                  energy_max,
                  energy_last_reset,
                  last_login
                FROM players
                WHERE tg_id=$1
                FOR UPDATE
                """,
                tg_id,
            )
            if not row:
                raise HTTPException(409, {"code": "NEED_REGISTER"})

            bal = int(row["kleynody"] or 0)
            if bal < price:
                raise HTTPException(400, {"code": "NOT_ENOUGH_KLEYNODY"})

            water_until: Optional[datetime] = row.get("premium_water_until")
            molfar_until: Optional[datetime] = row.get("premium_molfar_until")
            old_tier = _active_tier(now=now, water_until=water_until, molfar_until=molfar_until)

            cur_until = row.get(col)
            base = cur_until if (cur_until and cur_until > now) else now
            new_until = base + timedelta(days=days)

            await conn.execute(
                "UPDATE players SET kleynody=kleynody-$1 WHERE tg_id=$2",
                price,
                tg_id,
            )
            await conn.execute(
                f"UPDATE players SET {col}=$1 WHERE tg_id=$2",
                new_until,
                tg_id,
            )

            # Оновлюємо локальні until для визначення нового тиру
            if tier == "water":
                water_until = new_until
            else:
                molfar_until = new_until

            new_tier = _active_tier(now=now, water_until=water_until, molfar_until=molfar_until)

            # 1) Нормалізуємо наснагу/кап (підтягує energy_max під активний premium)
            energy_now, cap_now = await _normalize_player_energy(conn, tg_id)

            # 2) UX-фікс: якщо гравець купив premium посеред дня, кап оновився,
            #    але добова видача вже була (240). Даємо разовий "додаток" за цей день.
            #    Важливо: лише при переході з none -> water/molfar, щоб не було
            #    безкінечного донарахування при продовженні підписки.
            if old_tier == "none" and new_tier in ("water", "molfar"):
                bonus = int((WATER_DAILY - BASE_DAILY_ENERGY) if new_tier == "water" else (MOLFAR_DAILY - BASE_DAILY_ENERGY))
                if bonus > 0:
                    # Якщо daily reset для сьогодні вже відбувся (energy_last_reset==today)
                    # — додаємо тільки бонус (наприклад +60), а не ставимо на 300,
                    # щоб це не стало платною "заливкою до фула".
                    try:
                        last_reset = row.get("energy_last_reset")
                        if last_reset == today and energy_now <= BASE_DAILY_ENERGY:
                            topped = min(int(cap_now), int(energy_now) + bonus)
                            if topped != energy_now:
                                await conn.execute(
                                    "UPDATE players SET energy=$2 WHERE tg_id=$1",
                                    tg_id,
                                    int(topped),
                                )
                                energy_now = int(topped)
                    except Exception:
                        # якщо щось піде не так — просто не топаємо
                        pass

            energy_after = int(energy_now)
            energy_max_after = int(cap_now)

    return {
        "ok": True,
        "sku": sku,
        "tier": tier,
        "days": days,
        "price_kleynody": price,
        "until": new_until.isoformat(),
        "purchased_at": now.isoformat(),
        "energy": energy_after,
        "energy_max": energy_max_after,
    }
