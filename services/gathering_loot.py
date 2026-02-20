
# services/gathering_loot.py
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import asyncpg

from db import get_pool


# ──────────────────────────────────────────────
# DTO
# ──────────────────────────────────────────────

@dataclass
class ItemDrop:
    code: str
    name: str
    qty: int = 1
    rarity: Optional[str] = None
    category: Optional[str] = None  # ✅ важливо: щоб не ламати інвентар категоріями "винахідника"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "qty": self.qty,
            "rarity": self.rarity,
            "category": self.category,
        }


# ──────────────────────────────────────────────
# profession.code -> source bucket
# ──────────────────────────────────────────────
#
# ✅ В твоїй БД "камені" для каменяра лежать в items з code 'ore_%' (глина/пісок/граніт/вапняк...),
#   а не в category='ks'. Категорія 'ks' у тебе — це самоцвіти/камінці (кварц/рубін/опал...).
#
# Тому:
# - miner      -> ore_metal   (ore_metal_%)
# - stonemason -> ore_stone   (ore_% але НЕ ore_metal_%)
# - herbalist  -> herb        (як було)
#
PROFESSION_TO_SOURCE: Dict[str, str] = {
    "herbalist": "herb",
    "herbalis": "herb",  # alias/опечатка, щоб не ламати виклики
    "miner": "ore_metal",
    "stonemason": "ore_stone",
    # aliases
    "herb": "herb",
    "ore": "ore_metal",
    "metal": "ore_metal",
    "stone": "ore_stone",
    "stonе": "ore_stone",  # на випадок кривої латиниці
    "ks": "ore_stone",     # якщо фронт все ще шле ks — трактуємо як каменяр (каміння)
}


# ──────────────────────────────────────────────
# items.use_professions (TEXT[])
# ──────────────────────────────────────────────
#
# Колонка use_professions у вас описує, хто «використовує» предмет (здебільшого крафтові профи).
# В міграціях:
# - трави -> alchemist
# - руда/каміння (ore_*) -> blacksmith
# - самоцвіти (ks / ore_gem_*) -> jeweler
#
# Щоб не зламати лут, фільтр робимо м’яким:
# - use_professions порожній/NULL -> предмет може випадати (беккомпат)
# - інакше -> має бути перетин з дозволеним набором для джерела

SOURCE_ALLOWED_PROFESSIONS: Dict[str, List[str]] = {
    "herb": ["alchemist", "herbalist", "herbalis"],
    "ore_metal": ["blacksmith", "miner"],
    "ore_stone": ["blacksmith", "jeweler", "stonemason"],
}


# risk -> tier weights (впливає на rarity поля, не на SQL фільтр)
RISK_WEIGHTS = {
    "low": {"common": 80, "uncommon": 18, "rare": 2, "epic": 0},
    "medium": {"common": 70, "uncommon": 23, "rare": 6, "epic": 1},
    "high": {"common": 55, "uncommon": 28, "rare": 14, "epic": 3},
}


def _pick_tier(risk: str) -> str:
    w = RISK_WEIGHTS.get((risk or "").lower(), RISK_WEIGHTS["medium"])
    roll = random.randint(1, sum(w.values()))
    cur = 0
    for k, v in w.items():
        cur += v
        if roll <= cur:
            return k
    return "common"


def _normalize_source(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    s = v.strip().lower()
    return PROFESSION_TO_SOURCE.get(s, s)


async def _fetch_items_for_source(source: str, tier: str, limit: int = 300) -> List[Dict[str, Any]]:
    """
    ✅ Головна логіка під твою таблицю items:

    - ore_metal:  code LIKE 'ore_metal_%'          (рудокоп)
    - ore_stone:  code LIKE 'ore_%' AND NOT metal  (каменяр: каміння/порода/пісок/глина/вапняк...)
    - herb:       category IN ('herb', 'herb_tier') (як у тебе було)

    tier тут використовується лише як fallback для rarity, або якщо у herb реально є tier-розбиття.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        st = (source or "").strip().lower()
        allowed = SOURCE_ALLOWED_PROFESSIONS.get(st, [])
        use_prof_filter = bool(allowed)

        if st == "ore_metal":
            if use_prof_filter:
                try:
                    rows = await conn.fetch(
                        """
                        SELECT code, name, rarity, category
                        FROM items
                        WHERE code LIKE 'ore_metal_%'
                          AND (COALESCE(cardinality(use_professions), 0) = 0 OR use_professions && $1::text[])
                        LIMIT $2
                        """,
                        allowed,
                        limit,
                    )
                    return [dict(r) for r in rows]
                except asyncpg.UndefinedColumnError:
                    # якщо міграція ще не застосована на якомусь середовищі
                    pass

            rows = await conn.fetch(
                """
                SELECT code, name, rarity, category
                FROM items
                WHERE code LIKE 'ore_metal_%'
                LIMIT $1
                """,
                limit,
            )
            return [dict(r) for r in rows]

        if st == "ore_stone":
            if use_prof_filter:
                try:
                    rows = await conn.fetch(
                        """
                        SELECT code, name, rarity, category
                        FROM items
                        WHERE code LIKE 'ore_%'
                          AND code NOT LIKE 'ore_metal_%'
                          AND (COALESCE(cardinality(use_professions), 0) = 0 OR use_professions && $1::text[])
                        LIMIT $2
                        """,
                        allowed,
                        limit,
                    )
                    return [dict(r) for r in rows]
                except asyncpg.UndefinedColumnError:
                    pass

            rows = await conn.fetch(
                """
                SELECT code, name, rarity, category
                FROM items
                WHERE code LIKE 'ore_%'
                  AND code NOT LIKE 'ore_metal_%'
                LIMIT $1
                """,
                limit,
            )
            return [dict(r) for r in rows]

        # default: herb
        t = (tier or "common").strip().lower()
        cats = ["herb", f"herb_{t}"]
        if use_prof_filter:
            try:
                rows = await conn.fetch(
                    """
                    SELECT code, name, rarity, category
                    FROM items
                    WHERE category = ANY($1::text[])
                      AND (COALESCE(cardinality(use_professions), 0) = 0 OR use_professions && $2::text[])
                    LIMIT $3
                    """,
                    cats,
                    allowed,
                    limit,
                )
                return [dict(r) for r in rows]
            except asyncpg.UndefinedColumnError:
                pass

        rows = await conn.fetch(
            """
            SELECT code, name, rarity, category
            FROM items
            WHERE category = ANY($1::text[])
            LIMIT $2
            """,
            cats,
            limit,
        )
        return [dict(r) for r in rows]


async def _get_player_profession_key(tg_id: int) -> Optional[str]:
    """
    Витягує активну gathering-профу: herbalist/miner/stonemason.
    Сумісно з різними схемами players (з id або без).
    """
    if tg_id <= 0:
        return None

    pool = await get_pool()
    async with pool.acquire() as conn:
        # 1) players(id, tg_id, ...)
        try:
            row = await conn.fetchrow(
                """
                SELECT pr.code
                FROM players pl
                JOIN player_professions pp ON pp.player_id = pl.id
                JOIN professions pr ON pr.id = pp.profession_id
                WHERE pl.tg_id = $1
                  AND pr.kind = 'gathering'
                ORDER BY pp.updated_at DESC NULLS LAST, pp.created_at DESC NULLS LAST
                LIMIT 1
                """,
                tg_id,
            )
            if row:
                return str(row["code"])
        except asyncpg.UndefinedColumnError:
            pass

        # 2) fallback: players(tg_id PK), pp.player_id == tg_id
        try:
            row = await conn.fetchrow(
                """
                SELECT pr.code
                FROM players pl
                JOIN player_professions pp ON pp.player_id = pl.tg_id
                JOIN professions pr ON pr.id = pp.profession_id
                WHERE pl.tg_id = $1
                  AND pr.kind = 'gathering'
                ORDER BY pp.updated_at DESC NULLS LAST, pp.created_at DESC NULLS LAST
                LIMIT 1
                """,
                tg_id,
            )
            if row:
                return str(row["code"])
        except Exception:
            return None

    return None


def _resolve_source_type(explicit: Optional[str], profession_key: Optional[str]) -> str:
    """
    Якщо source_type прийшов з кнопки (explicit) — використовуємо ТІЛЬКИ його.
    Інакше беремо з активної професії.
    """
    exp = _normalize_source(explicit)
    if exp:
        return exp

    prof = _normalize_source(profession_key)
    if prof:
        return prof

    return "herb"


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

async def roll_gathering_loot(
    tg_id: int,
    area_key: str,
    source_type: Optional[str],
    risk: str = "medium",
) -> List[ItemDrop]:
    """
    Повертає лут як items з таблиці items.

    ✅ Не плутає професії:
    - miner/ore -> ore_metal (тільки ore_metal_%)
    - stonemason/stone/ks -> ore_stone (ore_% але НЕ ore_metal_%)
    - herbalist/herb -> herb (category herb/herb_tier)
    """
    profession_key = await _get_player_profession_key(tg_id)
    chosen_source = _resolve_source_type(source_type, profession_key)

    tier = _pick_tier(risk)

    items = await _fetch_items_for_source(chosen_source, tier=tier, limit=300)
    if not items:
        return []

    n = random.randint(1, 3)
    picks = random.sample(items, k=min(n, len(items)))

    out: List[ItemDrop] = []
    for it in picks:
        out.append(
            ItemDrop(
                code=str(it["code"]),
                name=str(it.get("name") or it["code"]),
                qty=random.randint(1, 2),
                rarity=str(it.get("rarity") or tier),
                category=str(it.get("category") or None),
            )
        )
    return out
