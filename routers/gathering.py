from __future__ import annotations

import json
from typing import Optional, List, Dict, Any
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel
from loguru import logger

from services.gathering_tasks import (
    GatheringTask,
    GatheringAlreadyInProgress,
    GatheringTaskNotFound,
    GatheringNotReady,
    get_active_task,
    start_gathering_task,
    complete_gathering_task,
)

# ✅ якщо ти перейшов на новий rewards-сервіс
from services.rewards import distribute_drops

# ✅ для /api/gathering/state (story-flow у Redis)
from routers.redis_manager import get_redis

# ✅ потрібно для quick gather
from services.gathering_loot import roll_gathering_loot
from routers.inventory import give_item_to_player

# ✅ квестові дропи (мікс)
from services.quest_drops import roll_quest_drops

router = APIRouter(prefix="/api/gathering", tags=["gathering"])

# ─────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────

def _tg_id_from_init_data(x_init_data: str | None) -> int:
    """Витягує tg_id з підписаного Telegram initData"""
    if not x_init_data or not x_init_data.strip():
        raise HTTPException(status_code=401, detail="Missing X-Init-Data")
    try:
        qs = parse_qs(x_init_data, keep_blank_values=True)
        user_raw = (qs.get("user") or [None])[0]
        if not user_raw:
            raise ValueError("user missing")
        user = json.loads(user_raw)
        return int(user.get("id"))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid X-Init-Data")

def _story_key(tg_id: int) -> str:
    return f"gather_story:{tg_id}"

# мапінг slug→ключ БД для quick gather
_SLUG_TO_DB: Dict[str, str] = {
    "slums": "netrytsia",
    "suburbs": "peredmistia",
    "peredmistya": "peredmistia",
    "swamp": "bolota",
    "ruins": "forpost",
    "quarry": "karjer",
    "ridge": "hrebet",
    "crown": "kryzhana",
}

def _normalize_area_key(v: str) -> str:
    """Повертає валідний ключ локації для БД. Дозволяє slug."""
    k = (v or "").strip().lower()
    return _SLUG_TO_DB.get(k, k)

# DTO класи для FastAPI
class GatheringTaskDTO(BaseModel):
    id: int
    tg_id: int
    area_key: str
    source_type: str
    started_at: str
    finishes_at: str
    seconds_left: int
    resolved: bool
    finished: bool
    result: Optional[Dict[str, Any]] = None

class GatheringStatusResponse(BaseModel):
    ok: bool
    task: Optional[GatheringTaskDTO] = None

class GatheringStartRequest(BaseModel):
    area_key: str
    source_type: str  # "herb" | "ore" | "ks"
    duration_minutes: Optional[int] = None
    risk: Optional[str] = None  # "low"|"medium"|"high"|"extreme"

class GatheringStartResponse(BaseModel):
    ok: bool
    task: GatheringTaskDTO

class GatheringCompleteResponse(BaseModel):
    ok: bool
    task: GatheringTaskDTO
    drops: List[Dict[str, Any]]

class GatheringStateResponse(BaseModel):
    ok: bool = True
    active: bool
    story: Optional[Dict[str, Any]] = None
    area_key: Optional[str] = None
    profession_code: Optional[str] = None
    eta_seconds: Optional[int] = None

# DTO для швидкої збірки
class QuickGatherRequest(BaseModel):
    area_key: str
    source_type: str  # herb|ore|ks або herbalist/miner/stonemason
    risk: Optional[str] = "low"

class QuickGatherDropDTO(BaseModel):
    code: str
    name: str
    qty: int
    rarity: Optional[str] = None

class QuickGatherResponse(BaseModel):
    ok: bool = True
    drops: List[QuickGatherDropDTO]

def _to_dto(task: GatheringTask) -> GatheringTaskDTO:
    return GatheringTaskDTO(
        id=task.id,
        tg_id=task.tg_id,
        area_key=task.area_key,
        source_type=task.source_type,
        started_at=task.started_at.isoformat(),
        finishes_at=task.finishes_at.isoformat(),
        seconds_left=task.seconds_left,
        resolved=task.resolved,
        finished=task.is_finished,
        result=task.result_json,
    )

# ─────────────────────────────────────────────
# Quick gather helpers
# ─────────────────────────────────────────────
_RARITY_TIER_MAP = {
    "звичайний": "common",
    "добротний": "uncommon",
    "рідкісний": "rare",
    "вибраний": "epic",
    "обереговий": "legendary",
    "божественний": "mythic",
    "common": "common",
    "uncommon": "uncommon",
    "rare": "rare",
    "epic": "epic",
    "legendary": "legendary",
    "mythic": "mythic",
}

def _normalize_source_type(v: str) -> str:
    v = (v or "").strip().lower()
    if v in ("herb", "herbalist"):
        return "herb"
    if v in ("ore", "miner"):
        return "ore"
    if v in ("ks", "stone", "stonemason", "камінь", "камені", "каменяр"):
        return "ks"
    raise HTTPException(status_code=400, detail="INVALID_SOURCE_TYPE")

def _category_for_drop(source_type: str, rarity: Optional[str]) -> str:
    base = (source_type or "").strip().lower()
    if base == "ks":
        return "ks"
    r = (rarity or "").strip().lower()
    tier = _RARITY_TIER_MAP.get(r, "common")
    if base not in ("herb", "ore"):
        base = "herb"
    return f"{base}_{tier}"

def _scale_qty(qty: int, risk: str) -> int:
    r = (risk or "low").lower()
    if r == "high":
        mult = 1.15
    elif r == "medium":
        mult = 1.05
    else:
        mult = 0.95
    out = int(round(max(1, qty) * mult))
    return max(1, out)

async def _grant_drops_as_items(
    tg_id: int,
    source_type: str,
    drops: List[Dict[str, Any]],
    risk: str,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if tg_id <= 0 or not drops:
        return out
    for d in drops:
        code = str(d.get("code") or d.get("item_code") or "").strip()
        if not code:
            continue
        name = str(d.get("name") or code)
        rarity = d.get("rarity")
        qty_raw = int(d.get("qty") or d.get("amount") or 1)
        qty = _scale_qty(qty_raw, risk)
        category = _category_for_drop(source_type, rarity)
        await give_item_to_player(
            tg_id,
            item_code=code,
            name=name,
            category=category,
            emoji=None,
            rarity=rarity,
            description=None,
            stats=None,
            amount=qty,
            slot=None,
        )
        out.append({"code": code, "name": name, "qty": qty, "rarity": rarity})
    return out

async def _grant_quest_items_direct(
    tg_id: int,
    quest_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Квестові предмети ми кладемо в інвентар напряму.
    На відміну від ресурсів, тут:
      - qty завжди 1
      - category ставимо "quest" (щоб не змішувалось з herb_common і т.д.)
    """
    out: List[Dict[str, Any]] = []
    if tg_id <= 0 or not quest_items:
        return out

    for it in quest_items:
        code = str(it.get("code") or "").strip()
        if not code:
            continue
        name = str(it.get("name") or code)
        rarity = it.get("rarity")
        desc = it.get("description")
        stats = it.get("stats")
        emoji = it.get("emoji")
        slot = it.get("slot")

        await give_item_to_player(
            tg_id,
            item_code=code,
            name=name,
            category="quest",
            emoji=emoji,
            rarity=rarity,
            description=desc,
            stats=stats,
            amount=1,
            slot=slot,
        )
        out.append({"code": code, "name": name, "qty": 1, "rarity": rarity})

    return out

# ─────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────

@router.get("/status", response_model=GatheringStatusResponse)
async def gathering_status(
    x_init_data: str | None = Header(default=None, alias="X-Init-Data"),
) -> GatheringStatusResponse:
    tg_id = _tg_id_from_init_data(x_init_data)
    task = await get_active_task(tg_id)
    return GatheringStatusResponse(ok=True, task=_to_dto(task) if task else None)

@router.get("/state", response_model=GatheringStateResponse)
async def gathering_state(
    x_init_data: str | None = Header(default=None, alias="X-Init-Data"),
    tg_id: Optional[int] = Query(default=None, description="(optional legacy) Telegram user id"),
) -> GatheringStateResponse:
    if x_init_data and x_init_data.strip():
        real_tg_id = _tg_id_from_init_data(x_init_data)
    else:
        if tg_id is None:
            raise HTTPException(status_code=401, detail="Missing X-Init-Data")
        real_tg_id = int(tg_id)
    redis = await get_redis()
    raw = await redis.get(_story_key(real_tg_id))
    if not raw:
        return GatheringStateResponse(active=False, story=None)
    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        story = json.loads(raw)
    except Exception:
        await redis.delete(_story_key(real_tg_id))
        return GatheringStateResponse(active=False, story=None)
    if story.get("finished"):
        return GatheringStateResponse(active=False, story=None)
    return GatheringStateResponse(
        active=True,
        story=story,
        area_key=story.get("area_key"),
        profession_code=story.get("profession_code") or story.get("source_type"),
        eta_seconds=story.get("eta_seconds"),
    )

@router.post("/start", response_model=GatheringStartResponse)
async def gathering_start(
    payload: GatheringStartRequest,
    x_init_data: str | None = Header(default=None, alias="X-Init-Data"),
) -> GatheringStartResponse:
    tg_id = _tg_id_from_init_data(x_init_data)
    area_key = _normalize_area_key(payload.area_key)
    source_type = payload.source_type
    duration = payload.duration_minutes or 10
    risk = payload.risk
    try:
        task = await start_gathering_task(
            tg_id=tg_id,
            area_key=area_key,
            source_type=source_type,
            duration_minutes=duration,
            risk=risk,
        )
    except GatheringAlreadyInProgress as e:
        logger.warning(f"gathering_start: already in progress tg_id={tg_id}: {e}")
        raise HTTPException(
            status_code=409,
            detail={
                "error": "ALREADY_IN_PROGRESS",
                "message": "У героя вже є активний похід на збір.",
            },
        )
    return GatheringStartResponse(ok=True, task=_to_dto(task))

@router.post("/complete", response_model=GatheringCompleteResponse)
async def gathering_complete(
    x_init_data: str | None = Header(default=None, alias="X-Init-Data"),
) -> GatheringCompleteResponse:
    tg_id = _tg_id_from_init_data(x_init_data)
    try:
        task, drops = await complete_gathering_task(tg_id)
    except GatheringTaskNotFound:
        raise HTTPException(
            status_code=404,
            detail={"error": "NO_ACTIVE_TASK", "message": "У героя немає активного походу на збір."},
        )
    except GatheringNotReady as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "NOT_READY", "message": str(e)},
        )

    try:
        drops_payload: List[Dict[str, Any]] = [
            d.as_dict() if hasattr(d, "as_dict") else d
            for d in (drops or [])
        ]

        # ✅ МІКС: додаємо шанс квестового предмета і на complete теж
        # (якщо не хочеш тут — прибери цей блок)
        try:
            quest_items = await roll_quest_drops(
                area_key=getattr(task, "area_key", None),
                source="gather",
                mob_code=None,
            )
            if quest_items:
                drops_payload.extend(quest_items)
        except Exception as e:
            logger.error(f"gathering_complete: quest roll failed tg_id={tg_id}: {e}")

        await distribute_drops(tg_id, drops_payload)
        drops = drops_payload
    except Exception as e:
        logger.error(f"gathering_complete: distribute_drops failed tg_id={tg_id}: {e}")

    return GatheringCompleteResponse(ok=True, task=_to_dto(task), drops=drops or [])

# ✅ Швидка знахідка ресурсів під час мандрів
@router.post("/quick", response_model=QuickGatherResponse)
async def gathering_quick(
    payload: QuickGatherRequest,
    tg_id: int = Depends(get_tg_id),
) -> QuickGatherResponse:
    # нормалізація area_key: приймаємо slug або ключ БД
    area_key_norm = _normalize_area_key(payload.area_key)
    if not area_key_norm:
        raise HTTPException(status_code=400, detail="INVALID_AREA_KEY")

    # нормалізація типу ресурсу (herb/ore/ks)
    source_type = _normalize_source_type(payload.source_type)

    risk = (payload.risk or "low").lower()
    if risk not in ("low", "medium", "high"):
        risk = "low"

    # виклик луту без story-стану
    try:
        drops_raw = await roll_gathering_loot(
            tg_id=tg_id,
            area_key=area_key_norm,
            source_type=source_type,
            risk=risk,
        )
    except Exception as e:
        logger.error(f"gathering_quick: roll_gathering_loot failed tg_id={tg_id}: {e}")
        raise HTTPException(status_code=500, detail="LOOT_ROLL_FAILED")

    drops_dicts: List[Dict[str, Any]] = []
    for d in (drops_raw or []):
        if hasattr(d, "as_dict"):
            drops_dicts.append(d.as_dict())
        elif isinstance(d, dict):
            drops_dicts.append(d)

    # 1) звичайні ресурси -> в інвентар
    granted = await _grant_drops_as_items(tg_id, source_type, drops_dicts, risk=risk)

    # 2) ✅ МІКС: квестові предмети (kind=require) -> теж в інвентар
    quest_granted: List[Dict[str, Any]] = []
    try:
        quest_items = await roll_quest_drops(
            area_key=area_key_norm,
            source="gather",
            mob_code=None,
        )
        if quest_items:
            quest_granted = await _grant_quest_items_direct(tg_id, quest_items)
    except Exception as e:
        logger.error(f"gathering_quick: quest roll failed tg_id={tg_id}: {e}")

    merged = []
    merged.extend(granted)
    merged.extend(quest_granted)

    return QuickGatherResponse(
        ok=True,
        drops=[QuickGatherDropDTO(**d) for d in merged],
    )