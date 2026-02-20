# routers/profile.py

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from loguru import logger

from db import get_pool
from services.progress import xp_required_for, _ensure_player_progress_schema
from services.char_stats import get_full_stats_for_player
from services.energy import get_energy

from models.player import PlayerDTO
from routers.auth import get_player

router = APIRouter(prefix="/api", tags=["profile"])


# ────────────────────────────────────────────────────────────────────
# ✅ ENSURE: вага + qty (щоб не падало на старих БД)
# ────────────────────────────────────────────────────────────────────
async def _ensure_inventory_weight_schema() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""ALTER TABLE items ADD COLUMN IF NOT EXISTS weight INTEGER DEFAULT 0;""")
        # ✅ DEFAULT 1, щоб нові записи не прилітали з NULL
        await conn.execute("""ALTER TABLE player_inventory ADD COLUMN IF NOT EXISTS qty INTEGER DEFAULT 1;""")
        await conn.execute("""UPDATE player_inventory SET qty = 1 WHERE qty IS NULL OR qty = 0;""")


# ────────────────────────────────────────────────────────────────────
# ✅ ENSURE: premium cosmetics (frames + name styles + avatars)
# ────────────────────────────────────────────────────────────────────
async def _ensure_premium_cosmetics_schema() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""ALTER TABLE players ADD COLUMN IF NOT EXISTS equipped_frame_sku TEXT;""")
        await conn.execute("""ALTER TABLE players ADD COLUMN IF NOT EXISTS equipped_name_sku TEXT;""")
        await conn.execute("""ALTER TABLE players ADD COLUMN IF NOT EXISTS equipped_avatar_sku TEXT;""")


# ────────────────────────────────────────────────────────────────────
# ✅ ENSURE: premium subs ("Жива вода" / "Благословення мольфара")
# ────────────────────────────────────────────────────────────────────
async def _ensure_premium_subs_schema() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""ALTER TABLE players ADD COLUMN IF NOT EXISTS premium_water_until timestamptz;""")
        await conn.execute("""ALTER TABLE players ADD COLUMN IF NOT EXISTS premium_molfar_until timestamptz;""")


# ────────────────────────────────────────────────────────────────────
# DTO
# ────────────────────────────────────────────────────────────────────
class ProfileDTOOut(BaseModel):
    tg_id: int
    name: str

    level: int
    xp: int
    xp_needed: int

    race_key: Optional[str] = None
    class_key: Optional[str] = None
    gender: Optional[str] = None

    # поточні значення
    hp: int
    mp: int
    energy: int
    energy_max: int

    # максимальні стати
    hp_max: int
    mp_max: int
    atk: int
    defense: int

    chervontsi: int
    kleynody: int

    # ✅ ВАГА
    carry_weight: int
    carry_capacity: int

    # ✅ PREMIUM (рамка + стиль імені + аватар)
    equipped_frame_sku: Optional[str] = None
    equipped_name_sku: Optional[str] = None
    equipped_avatar_sku: Optional[str] = None

    # ✅ PREMIUM SUBS
    premium_water_until: Optional[str] = None
    premium_molfar_until: Optional[str] = None
    active_premium_tier: Optional[str] = None


class EntryState(BaseModel):
    """Залишаємо для сумісності, але поки не використовуємо."""
    regen_hp: int
    regen_mp: int
    regen_energy: int


class ProfileResponse(BaseModel):
    ok: bool
    player: ProfileDTOOut
    entry: Optional[EntryState] = None


# ────────────────────────────────────────────────────────────────────
# API: tg_id з initData (X-Init-Data) через get_player
# ────────────────────────────────────────────────────────────────────
@router.get("/profile", response_model=ProfileResponse)
async def get_profile(player: PlayerDTO = Depends(get_player)) -> ProfileResponse:
    tg_id = int(player.tg_id)
    pool = await get_pool()

    # щоб були level/xp у players
    await _ensure_player_progress_schema()

    # ✅ щоб була вага/qty
    await _ensure_inventory_weight_schema()

    # ✅ щоб були поля під рамки/імена/аватар
    await _ensure_premium_cosmetics_schema()

    # ✅ premium subs
    await _ensure_premium_subs_schema()

    # 1️⃣ ЧИТАЄМО ГРАВЦЯ
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                tg_id,
                name,
                COALESCE(level, 1)      AS level,
                COALESCE(xp, 0)         AS xp,
                COALESCE(chervontsi, 0) AS chervontsi,
                COALESCE(kleynody, 0)   AS kleynody,
                race_key,
                class_key,
                gender,
                hp,
                mp,
                equipped_frame_sku,
                equipped_name_sku,
                equipped_avatar_sku,
                premium_water_until,
                premium_molfar_until
            FROM players
            WHERE tg_id = $1
            """,
            tg_id,
        )

        # ✅ Вага інвентаря
        carry_weight = await conn.fetchval(
            """
            SELECT COALESCE(SUM(COALESCE(pi.qty,1) * COALESCE(i.weight,0)), 0) AS carry_weight
            FROM player_inventory pi
            JOIN items i ON i.id = pi.item_id
            WHERE pi.tg_id = $1
            """,
            tg_id,
        )

    if not row:
        raise HTTPException(status_code=403, detail="Player not found")

    level = int(row["level"])
    xp = int(row["xp"])
    xp_needed = xp_required_for(level)

    # 2️⃣ ПОВНІ СТАТИ (МАКСИ)
    try:
        stats = await get_full_stats_for_player(tg_id)
        hp_max = int(stats.get("hp_max", 1))
        mp_max = int(stats.get("mp_max", 0))
        atk = int(stats.get("atk", 1))
        defense = int(stats.get("def", 0))
    except Exception as e:
        logger.warning(f"profile: get_full_stats_for_player fail tg_id={tg_id}: {e}")
        hp_max = 1
        mp_max = 0
        atk = 1
        defense = 0

    # 3️⃣ ПОТОЧНІ HP/MP (обмежуємо max)
    hp_row = row["hp"]
    mp_row = row["mp"]

    if hp_row is None or hp_row <= 0:
        hp_current = hp_max
    else:
        hp_current = min(int(hp_row), hp_max)

    if mp_row is None:
        mp_current = mp_max
    else:
        mp_current = min(int(mp_row), mp_max)

    # 4️⃣ НАСНАГА
    try:
        energy_current, energy_max = await get_energy(tg_id)
    except Exception as e:
        logger.warning(f"profile: get_energy fail tg_id={tg_id}: {e}")
        energy_current, energy_max = 0, 0

    # ✅ Максимальна вантажопідйомність (поки формула)
    carry_capacity = 50 + 5 * max(level - 1, 0)

    # ✅ Premium subs status
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    water_until = row.get("premium_water_until")
    molfar_until = row.get("premium_molfar_until")
    if molfar_until and molfar_until > now:
        active_tier = "molfar"
    elif water_until and water_until > now:
        active_tier = "water"
    else:
        active_tier = "none"

    dto = ProfileDTOOut(
        tg_id=int(row["tg_id"]),
        name=row["name"] or "",
        level=level,
        xp=xp,
        xp_needed=xp_needed,
        race_key=row["race_key"],
        class_key=row["class_key"],
        gender=row["gender"],
        hp=hp_current,
        mp=mp_current,
        energy=energy_current,
        energy_max=energy_max,
        hp_max=hp_max,
        mp_max=mp_max,
        atk=atk,
        defense=defense,
        chervontsi=int(row["chervontsi"]),
        kleynody=int(row["kleynody"]),
        carry_weight=int(carry_weight or 0),
        carry_capacity=int(carry_capacity),
        equipped_frame_sku=row["equipped_frame_sku"],
        equipped_name_sku=row["equipped_name_sku"],
        equipped_avatar_sku=row["equipped_avatar_sku"],

        premium_water_until=water_until.isoformat() if water_until else None,
        premium_molfar_until=molfar_until.isoformat() if molfar_until else None,
        active_premium_tier=active_tier,
    )

    return ProfileResponse(ok=True, player=dto, entry=None)