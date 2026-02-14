"""
LiveOps system for Cursed Mounds.
Manages events, seasons, weekly cycles, and dynamic content.
"""
import yaml
import json
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path

from config import settings
from redis_client import get_redis, cache_get, cache_set, publish_event


@dataclass
class LiveEvent:
    id: str
    event_type: str
    name: str
    description: str
    starts_at: datetime
    ends_at: datetime
    config: Dict[str, Any]
    is_active: bool = True
    
    def to_dict(self) -> dict:
        return {
            **asdict(self),
            'starts_at': self.starts_at.isoformat(),
            'ends_at': self.ends_at.isoformat()
        }


class LiveOpsEngine:
    """
    Central engine for all live operations.
    - Weekly cycle management
    - Event scheduling and activation
    - Season progression
    - Dynamic content injection
    """
    
    WEEKLY_CYCLE = {
        0: {  # Monday
            "event_type": "guild_war_start",
            "name": "Початок Війни Громад",
            "weight": 1.0
        },
        2: {  # Wednesday
            "event_type": "mid_week_boost",
            "name": "Середа — День Сили",
            "weight": 1.0
        },
        4: {  # Friday
            "event_type": "new_banner",
            "name": "П'ятничний Баннер",
            "weight": 1.0
        },
        6: {  # Sunday
            "event_type": "leaderboard_reset",
            "name": "Неділя — Підсумки Тижня",
            "weight": 1.0
        }
    }
    
    SEASONAL_TEMPLATES = {
        "kupala": {
            "name": "Купала 2024",
            "theme": "summer_solstice",
            "events": [
                {"type": "double_drop", "name": "Ніч на Івана Купала", "duration_hours": 12},
                {"type": "boss_rush", "name": "Половико
                {"type": "boss_rush", "name": "Половикова Ніч", "duration_hours": 6},
            ],
            "special_drops": ["amulet_fern_flower", "skin_kupala_wreath"],
            "bp_theme": "kupala"
        },
        "harvest": {
            "name": "Зажинки",
            "theme": "autumn_harvest",
            "events": [
                {"type": "resource_rush", "name": "Жнива", "duration_hours": 24},
                {"type": "guild_competition", "name": "Змагання Громад", "duration_hours": 48},
            ],
            "special_drops": ["amulet_golden_sheaf", "skin_reaper"],
            "bp_theme": "harvest"
        },
        "winter": {
            "name": "Маланка",
            "theme": "winter_solstice",
            "events": [
                {"type": "winter_boss", "name": "Морозко", "duration_hours": 12},
                {"type": "gift_exchange", "name": "Колядування", "duration_hours": 48},
            ],
            "special_drops": ["amulet_frost_star", "skin_mummer"],
            "bp_theme": "winter"
        }
    }
    
    def __init__(self):
        self.redis = get_redis()
        self._load_config()
    
    def _load_config(self):
        """Load event configuration from YAML or use defaults."""
        config_path = Path(settings.EVENT_CONFIG_PATH)
        if config_path.exists():
            with open(config_path) as f:
                self.config = yaml.safe_load(f)
        else:
            self.config = self._default_config()
    
    def _default_config(self) -> dict:
        """Default LiveOps configuration."""
        return {
            "weekly_cycle": self.WEEKLY_CYCLE,
            "seasonal_templates": self.SEASONAL_TEMPLATES,
            "event_weights": {
                "double_drop": 0.3,
                "boss_rush": 0.2,
                "lucky_hour": 0.25,
                "guild_war": 0.15,
                "special": 0.1
            }
        }
    
    async def get_current_events(self) -> List[LiveEvent]:
        """Get all currently active events."""
        now = datetime.utcnow()
        
        # Check cache first
        cached = await cache_get("liveops:current_events")
        if cached:
            return [LiveEvent(**e) for e in cached]
        
        # Get from Redis active set
        event_keys = await self.redis.smembers("liveops:active_events")
        events = []
        
        for key in event_keys:
            event_data = await self.redis.hgetall(key)
            if event_data:
                event = LiveEvent(
                    id=event_data.get('id', key.split(':')[-1]),
                    event_type=event_data['event_type'],
                    name=event_data['name'],
                    description=event_data.get('description', ''),
                    starts_at=datetime.fromisoformat(event_data['starts_at']),
                    ends_at=datetime.fromisoformat(event_data['ends_at']),
                    config=json.loads(event_data.get('config', '{}')),
                    is_active=event_data.get('is_active', 'true') == 'true'
                )
                
                # Auto-expire if past end time
                if now > event.ends_at:
                    await self._deactivate_event(key)
                    continue
                    
                events.append(event)
        
        # Cache for 60 seconds
        await cache_set("liveops:current_events", [e.to_dict() for e in events], expire=60)
        return events
    
    async def get_active_multipliers(self) -> Dict[str, float]:
        """Get current multipliers from active events."""
        events = await self.get_current_events()
        multipliers = {
            "chervontsi": 1.0,
            "glory": 1.0,
            "drop_chance": 1.0,
            "energy_regen": 1.0,
            "boss_damage": 1.0
        }
        
        for event in events:
            config = event.config
            if "multiplier" in config:
                target = config.get("applies_to", "all")
                mult = config["multiplier"]
                
                if target == "all" or target == "chervontsi":
                    multipliers["chervontsi"] *= mult
                if target == "all" or target == "glory":
                    multipliers["glory"] *= mult
                if target == "drop_chance":
                    multipliers["drop_chance"] *= mult
                if target == "energy_regen":
                    multipliers["energy_regen"] *= mult
                if target == "boss_damage":
                    multipliers["boss_damage"] *= mult
        
        return multipliers
    
    async def schedule_event(
        self,
        event_type: str,
        name: str,
        description: str,
        duration_hours: int,
        config: Dict[str, Any],
        start_at: Optional[datetime] = None
    ) -> LiveEvent:
        """Schedule a new event."""
        if start_at is None:
            start_at = datetime.utcnow()
        
        ends_at = start_at + timedelta(hours=duration_hours)
        event_id = f"evt_{start_at.strftime('%Y%m%d%H%M%S')}_{random.randint(1000, 9999)}"
        
        event = LiveEvent(
            id=event_id,
            event_type=event_type,
            name=name,
            description=description,
            starts_at=start_at,
            ends_at=ends_at,
            config=config
        )
        
        # Store in Redis
        key = f"liveops:event:{event_id}"
        await self.redis.hset(key, mapping={
            'id': event_id,
            'event_type': event_type,
            'name': name,
            'description': description,
            'starts_at': start_at.isoformat(),
            'ends_at': ends_at.isoformat(),
            'config': json.dumps(config),
            'is_active': 'true'
        })
        
        await self.redis.sadd("liveops:active_events", key)
        await self.redis.expireat(key, int(ends_at.timestamp()) + 3600)  # Cleanup 1h after
        
        # Publish notification
        await publish_event("liveops:new_event", {
            "event": event.to_dict(),
            "message": f"Нова подія: {name}!"
        })
        
        # Invalidate cache
        await cache_delete("liveops:current_events")
        
        return event
    
    async def _deactivate_event(self, key: str):
        """Deactivate expired event."""
        await self.redis.hset(key, "is_active", "false")
        await self.redis.srem("liveops:active_events", key)
    
    async def process_weekly_cycle(self):
        """Process weekly scheduled events."""
        now = datetime.utcnow()
        weekday = now.weekday()
        
        # Check if already processed today
        last_run = await self.redis.get("liveops:last_weekly_run")
        today_str = now.strftime("%Y-%m-%d")
        
        if last_run == today_str:
            return  # Already ran today
        
        cycle_config = self.WEEKLY_CYCLE.get(weekday)
        if not cycle_config:
            return
        
        # Schedule appropriate event
        if weekday == 0:  # Monday - Guild War
            await self.schedule_event(
                "guild_war",
                "Війна Громад",
                "Твоя громада проти ворожої! Бийся за славу і території!",
                48,  # 2 days
                {"war_points_multiplier": 2, "territory_control": True}
            )
        
        elif weekday == 2:  # Wednesday - Mid-week boost
            boost_type = random.choice(["double_drop", "lucky_hour", "energy_rush"])
            if boost_type == "double_drop":
                await self.schedule_event(
                    "double_drop",
                    "Середа Сили",
                    "Подвійні нагороди з курганів!",
                    12,
                    {"multiplier": 2, "applies_to": "all"}
                )
            elif boost_type == "lucky_hour":
                await self.schedule_event(
                    "lucky_hour",
                    "Щаслива Година",
                    "Шанс на легендарний дроп збільшено втричі!",
                    1,
                    {"legendary_chance_multiplier": 3}
                )
        
        elif weekday == 4:  # Friday - New banner/content
            await self.schedule_event(
                "special",
                "П'ятничний Баннер",
                "Нові унікальні предмети доступні обмежений час!",
                72,  # Weekend long
                {"special_shop_rotation": True, "exclusive_items": 3}
            )
        
        elif weekday == 6:  # Sunday - Leaderboard reset
            await self._process_leaderboard_reset()
            await self.schedule_event(
                "leaderboard_reset",
                "Підсумки Тижня",
                "Нагороди за лідерство! Новий сезон починається!",
                2,
                {"celebration_mode": True}
            )
        
        await self.redis.set("liveops:last_weekly_run", today_str)
    
    async def _process_leaderboard_reset(self):
        """Process weekly leaderboard rewards."""
        # Get top 100 from Redis
        top_players = await self.redis.zrevrange(
            "leaderboard:weekly", 0, 99, withscores=True
        )
        
        rewards = []
        for rank, (player_id, score) in enumerate(top_players):
            kleynodu = 0
            chervontsi = 0
            
            if rank == 0:
                kleynodu, chervontsi = 500, 50000
            elif rank < 3:
                kleynodu, chervontsi = 300, 30000
            elif rank < 10:
                kleynodu, chervontsi = 150, 15000
            elif rank < 50:
                kleynodu, chervontsi = 50, 5000
            else:
                kleynodu, chervontsi = 25, 2500
            
            rewards.append({
                "user_id": player_id,
                "rank": rank + 1,
                "kleynodu": kleynodu,
                "chervontsi": chervontsi
            })
        
        # Store rewards for distribution
        await self.redis.setex(
            "leaderboard:weekly_rewards",
            604800,  # 7 days
            json.dumps(rewards)
        )
        
        # Reset weekly leaderboard
        await self.redis.delete("leaderboard:weekly")
        
        # Publish
        await publish_event("liveops:leaderboard_reset", {
            "top_10": rewards[:10],
            "total_rewards": len(rewards)
        })
    
    async def start_season(self, season_key: str) -> Dict[str, Any]:
        """Start a new seasonal event."""
        template = self.SEASONAL_TEMPLATES.get(season_key)
        if not template:
            raise ValueError(f"Unknown season: {season_key}")
        
        now = datetime.utcnow()
        
        # Schedule season events
        scheduled = []
        for evt in template["events"]:
            event = await self.schedule_event(
                evt["type"],
                evt["name"],
                f"Сезонна подія: {evt['name']}",
                evt["duration_hours"],
                {"season": season_key, "special": True}
            )
            scheduled.append(event.to_dict())
        
        # Set active season
        season_data = {
            "key": season_key,
            "name": template["name"],
            "theme": template["theme"],
            "started_at": now.isoformat(),
            "ends_at": (now + timedelta(days=90)).isoformat(),
            "special_drops": template["special_drops"],
            "bp_theme": template["bp_theme"]
        }
        
        await self.redis.setex(
            "liveops:current_season",
            7776000,  # 90 days
            json.dumps(season_data)
        )
        
        return {
            "season": season_data,
            "events_scheduled": scheduled
        }
    
    async def get_current_season(self) -> Optional[Dict[str, Any]]:
        """Get currently active season."""
        data = await self.redis.get("liveops:current_season")
        if data:
            return json.loads(data)
        return None
    
    async def get_player_event_status(self, user_id: int) -> Dict[str, Any]:
        """Get personalized event status for player."""
        events = await self.get_current_events()
        season = await self.get_current_season()
        multipliers = await self.get_active_multipliers()
        
        # Check for unclaimed rewards
        unclaimed = await self.redis.get(f"rewards:pending:{user_id}")
        
        return {
            "active_events": [e.to_dict() for e in events],
            "current_season": season,
            "multipliers": multipliers,
            "unclaimed_rewards": json.loads(unclaimed) if unclaimed else [],
            "next_reset": self._get_next_reset_time()
        }
    
    def _get_next_reset_time(self) -> str:
        """Get next scheduled reset time."""
        now = datetime.utcnow()
        # Next Sunday midnight UTC
        days_until_sunday = (6 - now.weekday()) % 7
        if days_until_sunday == 0 and now.hour >= 0:
            days_until_sunday = 7
        
        next_reset = now + timedelta(days=days_until_sunday)
        next_reset = next_reset.replace(hour=0, minute=0, second=0, microsecond=0)
        return next_reset.isoformat()


# Global instance
live_ops = LiveOpsEngine()