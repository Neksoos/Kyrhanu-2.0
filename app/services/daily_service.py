import hashlib
from datetime import date, datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.daily import DailyRoll

RARITIES = ["Common","Rare","Epic","Legendary","Mythic"]

BASE_THRESHOLDS = [
    ("Common", 0.65),
    ("Rare", 0.90),
    ("Epic", 0.985),
    ("Legendary", 0.999),
    ("Mythic", 1.0),
]

ARCHETYPES = [
    "Kharakternyk","Molfar","Berehynia","Lisovyk",
    "Vovkulak","Rusalka","Pysar","Honchar","Znakhар","OtamanGhost"
]

def _seed_int(user_id: str, day_key: str, salt: str = "") -> int:
    h = hashlib.sha256(f"{user_id}:{day_key}:{salt}".encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big", signed=False)

def _rand01(seed_int: int) -> float:
    # deterministic float in [0,1)
    return (seed_int % 10_000_000) / 10_000_000.0

def _apply_pity(thresholds: list[tuple[str,float]], pity_epic: int, pity_leg: int) -> list[tuple[str,float]]:
    # Convert thresholds to probabilities by adjusting cutoffs.
    # Simple: if pity_epic>=7 => Epic share +0.06; if pity_leg>=30 => Legendary share becomes 0.03
    # We rebuild probabilities then cumulative thresholds.
    p = {"Common":0.65,"Rare":0.25,"Epic":0.085,"Legendary":0.014,"Mythic":0.001}
    if pity_epic >= 7:
        bump = 0.06
        p["Epic"] += bump
        p["Common"] -= bump
    if pity_leg >= 30:
        # set Legendary to 0.03 by stealing from Common+Rare
        target = 0.03
        delta = target - p["Legendary"]
        if delta > 0:
            take_c = min(p["Common"] - 0.40, delta * 0.6) if p["Common"] > 0.40 else 0
            take_r = delta - take_c
            p["Common"] -= take_c
            p["Rare"] -= take_r
            p["Legendary"] = target

    # normalize tiny drift
    s = sum(p.values())
    for k in p:
        p[k] /= s

    cum = 0.0
    out = []
    for r in ["Common","Rare","Epic","Legendary","Mythic"]:
        cum += p[r]
        out.append((r, cum))
    out[-1] = ("Mythic", 1.0)
    return out

def _pick_rarity(r: float, thresholds: list[tuple[str,float]]) -> str:
    for name, t in thresholds:
        if r < t:
            return name
    return "Mythic"

def _pick_archetype(r: float) -> str:
    idx = int(r * len(ARCHETYPES)) % len(ARCHETYPES)
    return ARCHETYPES[idx]

def _generate_loadout(archetype: str, rarity: str, r: float) -> list[dict]:
    # placeholder deterministic loadout; in prod: pull from content tables
    base_weapon = {"slot":"Weapon","item_id":f"wpn_{archetype.lower()}_01","rarity":min(rarity,"Epic")}
    trinket = {"slot":"Trinket1","item_id":"trn_obereg_redthread","rarity":"Common"}
    armor = {"slot":"Body","item_id":"arm_rushnyk_vest","rarity":"Rare" if rarity in ("Epic","Legendary","Mythic") else "Common"}
    return [base_weapon, armor, trinket]

def _story_line(archetype: str, rarity: str, r: float) -> str:
    lines = [
        "Доля сьогодні усміхнулась… але з підтекстом.",
        "Курган пам’ятає тебе. І трохи сміється.",
        "Не сперечайся з насипом. Він у більшості.",
        "Сьогодні ти інший. Відповідальність — та сама.",
    ]
    return lines[int(r*len(lines)) % len(lines)]

async def ensure_daily(session: AsyncSession, user_id: str, day: date) -> DailyRoll:
    row = await session.get(DailyRoll, {"user_id": user_id, "day_key": day})
    if row:
        return row
    # create with inherited pity (read yesterday)
    yesterday = day.fromordinal(day.toordinal()-1)
    prev = await session.get(DailyRoll, {"user_id": user_id, "day_key": yesterday})
    pity_epic = prev.pity_epic if prev else 0
    pity_leg = prev.pity_legendary if prev else 0
    row = DailyRoll(user_id=user_id, day_key=day, pity_epic=pity_epic, pity_legendary=pity_leg, roll_json={})
    session.add(row)
    await session.flush()
    return row

async def roll_variants(session: AsyncSession, user_id: str, day: date) -> dict:
    dr = await ensure_daily(session, user_id, day)
    day_key = day.isoformat()

    thresholds = _apply_pity(BASE_THRESHOLDS, dr.pity_epic, dr.pity_legendary)

    variants = {}
    for salt in ["A","B","C"]:
        s = _seed_int(user_id, day_key, salt)
        r1 = _rand01(s)
        r2 = _rand01(s ^ 0x9E3779B97F4A7C15)
        r3 = _rand01(s ^ 0xC2B2AE3D27D4EB4F)

        rarity = _pick_rarity(r1, thresholds)
        archetype = _pick_archetype(r2)
        loadout = _generate_loadout(archetype, rarity, r3)
        variants[salt] = {
            "day_key": day_key,
            "hero": {"archetype": archetype, "rarity": rarity, "perks": ["obereg_ward","redthread_luck"]},
            "loadout": loadout,
            "rebirth_story_line": _story_line(archetype, rarity, r3),
        }
    return variants

async def select_and_claim(session: AsyncSession, user_id: str, day: date, variant: str) -> dict:
    dr = await ensure_daily(session, user_id, day)
    variants = await roll_variants(session, user_id, day)
    if variant not in variants:
        raise ValueError("Bad variant")
    chosen = variants[variant]

    # update pity counters for next day based on chosen rarity
    rarity = chosen["hero"]["rarity"]
    if rarity in ("Epic","Legendary","Mythic"):
        dr.pity_epic = 0
    else:
        dr.pity_epic += 1
    if rarity in ("Legendary","Mythic"):
        dr.pity_legendary = 0
    else:
        dr.pity_legendary += 1

    dr.selected_variant = variant
    dr.roll_json = chosen
    dr.claimed_at = datetime.now(timezone.utc)

    return chosen