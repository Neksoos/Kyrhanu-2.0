"""
Core game mechanics: tapping, energy, daily rolls, choices.
"""
import random
import hashlib
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.sql import func

from database import get_db
from models import User, DailyRoll
from config import settings
from services.anti_cheat import anti_cheat, TapValidationResult
from services.analytics import analytics, TrackedEvent
from services.live_ops import live_ops
from content.ethno_content import (
    HERO_NAMES, ARCHETYPES, AMULETS, MOUND_STORIES, CHOICES, get_random_phrase
)
from routers.auth import get_current_user
from schemas import TapRequest, DailyChoiceRequest

router = APIRouter()


class DailyGenerator:
    """Deterministic daily content generator."""
    
    def __init__(self, user_id: int, day: date):
        seed_str = f"{user_id}:{day.isoformat()}:cursed_mounds_v2"
        self.seed = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16)
        self.rng = random.Random(self.seed)
        self.day = day
    
    def generate_hero(self):
        name = self.rng.choice(HERO_NAMES)
        archetype_key = self.rng.choice(list(ARCHETYPES.keys()))
        archetype = ARCHETYPES[archetype_key]
        
        stats = {
            "strength": self.rng.randint(1, 10),
            "cunning": self.rng.randint(1, 10),
            "endurance": self.rng.randint(1, 10),
            "fate": self.rng.randint(1, 10)
        }
        stats[archetype["stat_bonus"]] = min(10, stats[archetype["stat_bonus"]] + self.rng.randint(1, 2))
        
        return {
            "name": name,
            "archetype": archetype_key,
            "archetype_name": archetype["name"],
            "archetype_description": archetype["description"],
            "emoji": archetype["emoji"],
            "stats": stats
        }
    
    def generate_amulet(self):
        amulet = self.rng.choice(AMULETS)
        return {
            "name": amulet["name"],
            "description": amulet["description"],
            "power": amulet["power"],
            "rarity": amulet["rarity"]
        }
    
    def generate_mound_story(self):
        return {"text": self.rng.choice(MOUND_STORIES)}
    
    def calculate_outcome(self, choice: str):
        choice_data = CHOICES[choice]
        glory = self.rng.randint(*choice_data["glory_range"])
        chervontsi = self.rng.randint(*choice_data["chervontsi_range"])
        
        # Apply day modifier
        day_mod = (self.day.day % 7) - 3
        if choice == "accept":
            glory += day_mod * 2
        
        return {"glory": glory, "chervontsi": chervontsi}


@router.post("/tap")
async def tap(
    payload: TapRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Process a tap (digging action).
    Protected by anti-cheat validation.
    """
    # Check cooldown
    on_cooldown, cooldown_sec = await anti_cheat.is_under_cooldown(current_user.id)
    if on_cooldown:
        raise HTTPException(
            status_code=429,
            detail=f"Cooldown active: {cooldown_sec}s remaining"
        )
    
    # Validate energy
    if current_user.energy <= 0:
        await analytics.track(TrackedEvent(
            name="energy_depleted",
            user_id=current_user.id,
            session_id=None,
            properties={"kleynodu_balance": current_user.kleynodu}
        ))
        raise HTTPException(status_code=403, detail="Energy depleted")
    
    # Anti-cheat validation
    validation = await anti_cheat.validate_tap(
        user_id=current_user.id,
        client_timestamp=payload.client_timestamp,
        sequence_number=payload.sequence_number,
        nonce=payload.nonce,
        current_anomaly_score=current_user.anomaly_score
    )
    
    if not validation.is_valid:
        # Apply sanctions
        sanctions = await anti_cheat.apply_sanctions(
            current_user.id,
            validation.new_anomaly_score
        )
        
        current_user.anomaly_score = validation.new_anomaly_score
        await db.commit()
        
        raise HTTPException(
            status_code=403,
            detail={
                "error": validation.reason,
                "sanctions": sanctions,
                "anomaly_score": validation.new_anomaly_score
            }
        )
    
    # Update anomaly score even for valid taps
    current_user.anomaly_score = max(0, validation.new_anomaly_score - 0.5)  # Decay
    current_user.last_tap_at = datetime.utcnow()
    
    # Calculate rewards
    multipliers = await live_ops.get_active_multipliers()
    
    base_chervontsi = random.randint(1, 5)
    base_glory = random.randint(0, 2)
    
    # Apply multipliers
    chervontsi_earned = int(base_chervontsi * multipliers["chervontsi"])
    glory_earned = int(base_glory * multipliers["glory"])
    
    # Check for rare drops
    drop_chance = 0.05 * multipliers["drop_chance"]  # 5% base
    drop = None
    
    if random.random() < drop_chance:
        drop = random.choice(AMULETS)
        glory_earned += drop["power"] // 5
    
    # Shadow nerf check
    is_nerfed, nerf_level = await anti_cheat.is_shadow_nerfed(current_user.id)
    if is_nerfed:
        chervontsi_earned = int(chervontsi_earned * 0.5)
        glory_earned = int(glory_earned * 0.5)
    
    # Apply
    current_user.chervontsi += chervontsi_earned
    current_user.glory += glory_earned
    current_user.energy -= 1
    current_user.experience += 1
    
    # Level up check
    old_level = current_user.level
    new_level = current_user.level
    while current_user.experience >= current_user.level * 100:
        current_user.experience -= current_user.level * 100
        current_user.level += 1
        new_level = current_user.level
        current_user.max_energy += 5
        current_user.energy = current_user.max_energy
    
    await db.commit()
    
    # Track
    await analytics.track(TrackedEvent(
        name="tap",
        user_id=current_user.id,
        session_id=None,
        properties={
            "chervontsi_earned": chervontsi_earned,
            "glory_earned": glory_earned,
            "energy_left": current_user.energy,
            "had_drop": drop is not None
        }
    ))
    
    response = {
        "success": True,
        "chervontsi_earned": chervontsi_earned,
        "total_chervontsi": current_user.chervontsi,
        "glory_earned": glory_earned,
        "total_glory": current_user.glory,
        "energy_left": current_user.energy,
        "max_energy": current_user.max_energy,
        "level_up": current_user.level > old_level,
        "current_level": current_user.level,
        "total_kleynodu": current_user.kleynodu,
        "drop": drop,
        "message": get_random_phrase("rare_drop") if drop else None,
        "multipliers_active": multipliers if any(m != 1.0 for m in multipliers.values()) else None
    }

    if is_nerfed:
        response["warning"] = "Підозріла активність виявлена. Нагороди зменшено."
    
    return response


@router.get("/daily")
async def get_daily(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get or create daily roll."""
    today = date.today()
    
    result = await db.execute(
        select(DailyRoll).where(
            and_(
                DailyRoll.user_id == current_user.id,
                DailyRoll.day_date == today
            )
        )
    )
    roll = result.scalar_one_or_none()
    
    if not roll:
        # Generate new
        generator = DailyGenerator(current_user.id, today)
        hero = generator.generate_hero()
        amulet = generator.generate_amulet()
        story = generator.generate_mound_story()
        
        roll = DailyRoll(
            user_id=current_user.id,
            day_date=today,
            hero_name=hero["name"],
            hero_archetype=hero["archetype"],
            hero_stats=hero["stats"],
            hero_level=current_user.level,
            mound_story=story["text"],
            amulet_name=amulet["name"],
            amulet_power=amulet["power"]
        )
        db.add(roll)
        await db.commit()
        await db.refresh(roll)
        
        await analytics.track(TrackedEvent(
            name="daily_claim",
            user_id=current_user.id,
            session_id=None,
            properties={"hero": hero["name"], "archetype": hero["archetype"]}
        ))
    
    return {
        "id": roll.id,
        "hero": {
            "name": roll.hero_name,
            "archetype": roll.hero_archetype,
            "archetype_name": ARCHETYPES[roll.hero_archetype]["name"],
            "archetype_description": ARCHETYPES[roll.hero_archetype]["description"],
            "emoji": ARCHETYPES[roll.hero_archetype]["emoji"],
            "stats": roll.hero_stats,
            "level": roll.hero_level
        },
        "amulet": {
            "name": roll.amulet_name,
            "power": roll.amulet_power
        },
        "mound_story": roll.mound_story,
        "choices": {
            k: {
                "name": v["name"],
                "description": v["description"],
                "risk": v["risk_level"]
            }
            for k, v in CHOICES.items()
        },
        "completed": roll.choice_made is not None,
        "choice_made": roll.choice_made,
        "result": {
            "glory_delta": roll.glory_delta,
            "chervontsi_earned": roll.chervontsi_earned,
            "text": roll.result_text
        } if roll.choice_made else None
    }


@router.post("/daily/choice")
async def make_choice(
    payload: DailyChoiceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Make choice for daily roll."""
    choice = payload.choice
    if choice not in CHOICES:
        raise HTTPException(status_code=400, detail="Invalid choice")
    
    today = date.today()
    
    result = await db.execute(
        select(DailyRoll).where(
            and_(
                DailyRoll.user_id == current_user.id,
                DailyRoll.day_date == today
            )
        )
    )
    roll = result.scalar_one_or_none()
    
    if not roll:
        raise HTTPException(status_code=404, detail="Daily roll not found")
    
    if roll.choice_made:
        raise HTTPException(status_code=400, detail="Choice already made")
    
    # Generate outcome
    generator = DailyGenerator(current_user.id, today)
    outcome = generator.calculate_outcome(choice)
    
    # Apply multipliers
    multipliers = await live_ops.get_active_multipliers()
    glory_delta = int(outcome["glory"] * multipliers["glory"])
    chervontsi_earned = int(outcome["chervontsi"] * multipliers["chervontsi"])
    
    # Update
    roll.choice_made = choice
    roll.glory_delta = glory_delta
    roll.chervontsi_earned = chervontsi_earned
    roll.result_text = f"Ти обрав: {CHOICES[choice]['name']}. Доля відповіла."
    roll.completed_at = datetime.utcnow()
    
    current_user.glory += glory_delta
    current_user.chervontsi += chervontsi_earned
    
    await db.commit()
    
    # Track
    await analytics.track(TrackedEvent(
        name="choice_made",
        user_id=current_user.id,
        session_id=None,
        properties={
            "choice": choice,
            "glory_delta": glory_delta,
            "chervontsi": chervontsi_earned
        }
    ))
    
    return {
        "success": True,
        "choice": choice,
        "glory_delta": glory_delta,
        "chervontsi_earned": chervontsi_earned,
        "total_glory": current_user.glory,
        "total_chervontsi": current_user.chervontsi,
        "result_text": roll.result_text
    }


@router.get("/energy")
async def get_energy_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get current energy status and refill info."""
    now = datetime.utcnow()
    
    # Calculate natural refill
    if current_user.energy < current_user.max_energy:
        minutes_since_refill = (now - current_user.energy_last_refill).total_seconds() / 60
        refill_amount = int(minutes_since_refill / 3)  # 1 energy per 3 minutes
        
        if refill_amount > 0:
            current_user.energy = min(
                current_user.max_energy,
                current_user.energy + refill_amount
            )
            current_user.energy_last_refill = now
    
    next_refill_in = 180 - int((now - current_user.energy_last_refill).total_seconds()) % 180

    await db.commit()

    return {
        "energy": current_user.energy,
        "max_energy": current_user.max_energy,
        "next_refill_in_seconds": next_refill_in if current_user.energy < current_user.max_energy else 0,
        "refill_rate": "1 per 3 minutes"
    }