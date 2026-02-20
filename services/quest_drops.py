from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import random
import json

from db import get_pool

QUEST_DROP_CHANCE_MOB = 0.18       # шанс на квест-предмет з моба
QUEST_DROP_CHANCE_GATHER = 0.14    # шанс на квест-предмет зі збору

# cache:
# {
#   "mob":   { area_key: [ {"code","name","qty","drop_weight"}, ... ] },
#   "gather":{ (area_key, source_type): [ ... ] }
# }
_QUEST_DROP_CACHE: Optional[Dict[str, Any]] = None


def _norm_area(a: Optional[str]) -> str:
    return (a or "").strip().lower()


def _norm_source_type(st: Optional[str]) -> str:
    v = (st or "").strip().lower()
    if v in ("herb", "herbalist"):
        return "herb"
    if v in ("ore", "miner"):
        return "ore"
    if v in ("ks", "stone", "stonemason", "камінь", "камені", "каменяр"):
        return "ks"
    return v or ""


def _normalize_stats(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (str, bytes)):
        try:
            return json.loads(raw)
        except Exception:
            return {}
    try:
        return dict(raw)  # type: ignore
    except Exception:
        return {}


def _extract_sources(stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Очікуємо в stats:
      sources: {
         "mob": ["slums","suburbs"],
         "gather": {"herb": ["swamp"], "ore": ["quarry"]}
      }
    """
    src = stats.get("sources")
    if isinstance(src, dict):
        return src
    return {}


def _extract_weight(stats: Dict[str, Any]) -> int:
    w = stats.get("drop_weight", None)
    if w is None:
        w = stats.get("loot_weight", 1)

    try:
        w = int(w)
    except Exception:
        w = 1

    return max(0, w)


async def _load_cache() -> Dict[str, Any]:
    global _QUEST_DROP_CACHE
    if _QUEST_DROP_CACHE is not None:
        return _QUEST_DROP_CACHE

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT code, name, stats
            FROM items
            WHERE COALESCE(is_archived,false) = false
              AND COALESCE(stats->>'quest_item','false') = 'true'
              AND COALESCE(stats->>'kind','') = 'require'
            """
        )

    mob_map: Dict[str, List[Dict[str, Any]]] = {}
    gather_map: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}

    for r in rows:
        code = str(r["code"])
        name = str(r["name"] or code)
        stats = _normalize_stats(r["stats"])
        sources = _extract_sources(stats)
        weight = _extract_weight(stats)
        if weight <= 0:
            continue

        item_dict = {
            "code": code,
            "name": name,
            "qty": 1,
            "drop_weight": weight,
        }

        mob_areas = sources.get("mob")
        if isinstance(mob_areas, list):
            for a in mob_areas:
                if isinstance(a, str):
                    ak = _norm_area(a)
                    if ak:
                        mob_map.setdefault(ak, []).append(item_dict)

        g = sources.get("gather")
        if isinstance(g, dict):
            for st, areas in g.items():
                st_norm = _norm_source_type(st)
                if not st_norm:
                    continue
                if isinstance(areas, list):
                    for a in areas:
                        if isinstance(a, str):
                            ak = _norm_area(a)
                            if ak:
                                gather_map.setdefault((ak, st_norm), []).append(item_dict)

    _QUEST_DROP_CACHE = {"mob": mob_map, "gather": gather_map}
    return _QUEST_DROP_CACHE


def invalidate_quest_drop_cache() -> None:
    global _QUEST_DROP_CACHE
    _QUEST_DROP_CACHE = None


def _weighted_choice(items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not items:
        return None
    weights = [max(1, int(it.get("drop_weight", 1))) for it in items]
    return random.choices(items, weights=weights, k=1)[0]


async def quest_drop_from_mob(area_key: Optional[str]) -> List[Dict[str, Any]]:
    """
    Повертає 0..1 квест-предмет з моба, якщо він дозволений в цій зоні.
    """
    if random.random() > QUEST_DROP_CHANCE_MOB:
        return []

    a = _norm_area(area_key)
    if not a:
        return []

    data = await _load_cache()
    pool = data["mob"].get(a, []) or []
    pick = _weighted_choice(pool)
    return [pick] if pick else []


async def quest_drop_from_gather(area_key: Optional[str], source_type: str) -> List[Dict[str, Any]]:
    """
    Повертає 0..1 квест-предмет зі збору (herb/ore/ks), якщо дозволений в цій зоні.
    """
    if random.random() > QUEST_DROP_CHANCE_GATHER:
        return []

    a = _norm_area(area_key)
    st = _norm_source_type(source_type)
    if not a or not st:
        return []

    data = await _load_cache()
    pool = data["gather"].get((a, st), []) or []
    pick = _weighted_choice(pool)
    return [pick] if pick else []


# ─────────────────────────────────────────────────────────────────────
# ✅ Backward compatibility: old code imports roll_quest_drops
# ─────────────────────────────────────────────────────────────────────
async def roll_quest_drops(
    *,
    area_key: Optional[str],
    source: str,
    mob_code: Optional[str] = None,
    source_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Сумісність зі старим інтерфейсом.
    Використовується в:
      - services/battle/rewards.py  (source=\"mob\")
      - routers/gathering.py        (source=\"gather\")

    mob_code зараз не використовується (залишено для майбутнього).
    """
    s = (source or "").strip().lower()

    if s == "mob":
        return await quest_drop_from_mob(area_key)

    if s in ("gather", "gathering"):
        return await quest_drop_from_gather(area_key, source_type or "")

    return []