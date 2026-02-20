from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Tuple, Optional

from loguru import logger

from db import get_pool


# ──────────────────────────────────────────────────────────────
# Energy / "наснага"
#
# У БД вже є колонки players.energy та players.energy_max.
# ВАЖЛИВО: energy_max трактуємо як КАП (макс. запас), а не як
# "скільки видаємо на добу". Добова видача рахується окремо.
# Це потрібно для premium+ (перенос залишку), щоб не було
# нескінченного накопичення.
# ──────────────────────────────────────────────────────────────

# База (free)
BASE_DAILY_ENERGY = 240
BASE_CAP = 240

# Жива вода (premium)
WATER_DAILY_BONUS = 60
WATER_DAILY = BASE_DAILY_ENERGY + WATER_DAILY_BONUS  # 300
WATER_CAP = 360

# Благословення мольфара (premium+)
# Мольфар включає бонуси Живої води + перенос
MOLFAR_DAILY = WATER_DAILY
MOLFAR_CAP = 480
MOLFAR_CARRY_LIMIT = BASE_DAILY_ENERGY  # переносимо максимум "базову добу"


def _is_active(until: Optional[datetime], now: datetime) -> bool:
    try:
        return bool(until and until > now)
    except Exception:
        return False


def _tier_and_limits(
    *,
    now: datetime,
    water_until: Optional[datetime],
    molfar_until: Optional[datetime],
) -> tuple[str, int, int, int]:
    """Return (tier, daily, cap, carry_limit)."""
    if _is_active(molfar_until, now):
        return ("molfar", MOLFAR_DAILY, MOLFAR_CAP, MOLFAR_CARRY_LIMIT)
    if _is_active(water_until, now):
        return ("water", WATER_DAILY, WATER_CAP, 0)
    return ("none", BASE_DAILY_ENERGY, BASE_CAP, 0)


async def _fetch_energy_row(conn, tg_id: int):
    """Читаємо максимум полів, але переживаємо старі БД без колонок."""
    # 1) Найновіший варіант
    try:
        return await conn.fetchrow(
            """
            SELECT
              energy,
              energy_max,
              energy_last_reset,
              last_login,
              premium_water_until,
              premium_molfar_until
            FROM players
            WHERE tg_id = $1
            """,
            tg_id,
        )
    except Exception:
        pass

    # 2) Якщо немає premium_* колонок
    try:
        return await conn.fetchrow(
            """
            SELECT energy, energy_max, energy_last_reset, last_login
            FROM players
            WHERE tg_id = $1
            """,
            tg_id,
        )
    except Exception:
        pass

    # 3) Якщо немає навіть last_login
    return await conn.fetchrow(
        """
        SELECT energy, energy_max, energy_last_reset
        FROM players
        WHERE tg_id = $1
        """,
        tg_id,
    )


async def _normalize_player_energy(conn, tg_id: int) -> Tuple[int, int]:
    """
    Приватна утиліта.
    Викликається перед кожною операцією з наснагою.
    Дає (energy, energy_max) після daily reset.
    """

    today = date.today()
    now = datetime.now(timezone.utc)

    row = await _fetch_energy_row(conn, tg_id)
    if not row:
        # player missing — не валимо ендпоінт, але й не створюємо тут запис
        return BASE_DAILY_ENERGY, BASE_CAP

    energy_db = row.get("energy")
    cap_db = row.get("energy_max")
    last_reset = row.get("energy_last_reset")
    last_login = row.get("last_login")
    water_until = row.get("premium_water_until")
    molfar_until = row.get("premium_molfar_until")

    tier, daily, cap, carry_limit = _tier_and_limits(
        now=now,
        water_until=water_until,
        molfar_until=molfar_until,
    )

    # Поточні значення з БД
    energy = int(energy_db) if energy_db is not None else min(daily, cap)
    energy_max = int(cap_db) if cap_db is not None else cap

    # Підтягуємо cap до актуального (premium on/off)
    if energy_max <= 0:
        energy_max = cap

    if energy_max != cap:
        try:
            await conn.execute(
                "UPDATE players SET energy_max=$2 WHERE tg_id=$1",
                tg_id,
                cap,
            )
        except Exception as e:
            logger.warning(f"energy: update cap failed tg_id={tg_id}: {e}")
        energy_max = cap

    # --- Daily reset ---
    if last_reset is None or last_reset < today:
        leftover = max(0, int(energy))
        carry = 0

        if tier == "molfar" and carry_limit > 0:
            try:
                yday = today - timedelta(days=1)
                if last_login == yday:
                    carry = min(leftover, carry_limit)
            except Exception:
                carry = 0

        new_energy = min(energy_max, daily + carry)

        await conn.execute(
            """
            UPDATE players
               SET energy = $2,
                   energy_max = $3,
                   energy_last_reset = $4
             WHERE tg_id = $1
            """,
            tg_id,
            int(new_energy),
            int(energy_max),
            today,
        )
        energy = int(new_energy)

    # --- Санітарна нормалізація ---
    if energy < 0 or energy > energy_max:
        energy = max(0, min(int(energy), int(energy_max)))
        await conn.execute(
            "UPDATE players SET energy = $2 WHERE tg_id = $1",
            tg_id,
            energy,
        )

    return energy, energy_max


async def get_energy(tg_id: int) -> Tuple[int, int]:
    """Повертає (energy, energy_max) після нормалізації."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await _normalize_player_energy(conn, tg_id)


async def spend_energy(tg_id: int, amount: int) -> Tuple[int, int]:
    """
    Знімає amount наснаги.
    Якщо не вистачає — кидає ValueError.
    Повертає (energy_after, energy_max).
    """
    if amount <= 0:
        raise ValueError("ENERGY_AMOUNT_INVALID")

    pool = await get_pool()
    async with pool.acquire() as conn:
        energy, energy_max = await _normalize_player_energy(conn, tg_id)

        if energy < amount:
            raise ValueError("NO_ENERGY")

        new_energy = energy - amount
        await conn.execute(
            "UPDATE players SET energy = $2 WHERE tg_id = $1",
            tg_id,
            new_energy,
        )

        return new_energy, energy_max
