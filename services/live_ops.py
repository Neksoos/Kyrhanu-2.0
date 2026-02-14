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
    start_time: datetime
    end_time: datetime
    config: Dict[str, Any]
    is_active: bool = True
    
    def to_dict(self):
        data = asdict(self)
        data['start_time'] = self.start_time.isoformat()
        data['end_time'] = self.end_time.isoformat()
        return data


class LiveOpsEngine:
    """
    Main LiveOps engine. Handles:
    - Event scheduling and activation
    - Weekly cycles
    - Seasonal content
    - Dynamic configuration updates
    """
    
    # Default events configuration
    DEFAULT_WEEKLY_EVENTS = {
        "monday": {
            "event_type": "double_xp",
            "name": "Понеділок — Подвійний Досвід",
            "duration_hours": 24,
            "weight": 1.0
        },
        "wednesday": {
            "event_type": "resource_rush",
            "name": "Середа — Шалені Знахідки",
            "duration_hours": 24,
            "weight": 1.0
        },
        "friday": {
            "event_type": "boss_spawn",
            "name": "П’ятниця — Прокляті Боси",
            "duration_hours": 24,
            "weight": 1.0
        },
        "sunday": {
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
            "special_drops": ["amulet_wheat_spirit", "skin_harvester"],
            "bp_theme": "harvest"
        },
        "winter": {
            "name": "Зимове Сонцестояння",
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
        # NOTE: Redis is initialized asynchronously in app startup.
        # Do NOT call get_redis() at import time.
        self._redis = None
        self._load_config()

    @property
    def redis(self):
        """Lazy Redis client (available after init_redis())."""
        if self._redis is None:
            self._redis = get_redis()
        return self._redis
    
    def _load_config(self):
        """Load event configuration from YAML or use defaults."""
        config_path = Path(settings.EVENT_CONFIG_PATH)
        if config_path.exists():
            with open(config_path) as f:
                self.config = yaml.safe_load(f)
        else:
            self.config = self._default_config()
    
    def _default_config(self) -> Dict[str, Any]:
        """Default configuration if no YAML file."""
        return {
            "weekly_events": self.DEFAULT_WEEKLY_EVENTS,
            "special_events": [],
            "seasonal_templates": self.SEASONAL_TEMPLATES,
            "event_weights": {
                "double_xp": 1.0,
                "resource_rush": 1.0,
                "boss_spawn": 1.0,
                "double_drop": 0.5,
                "guild_competition": 0.3
            }
        }
    
    async def get_active_events(self) -> List[LiveEvent]:
        """Get currently active events."""
        events_data = await cache_get("liveops:active_events")
        if not events_data:
            return []
        
        events = []
        for event_dict in events_data:
            # Convert datetime strings back
            event_dict['start_time'] = datetime.fromisoformat(event_dict['start_time'])
            event_dict['end_time'] = datetime.fromisoformat(event_dict['end_time'])
            events.append(LiveEvent(**event_dict))
        
        # Filter expired
        now = datetime.utcnow()
        active_events = [e for e in events if e.end_time > now and e.is_active]
        
        # Update cache if needed
        if len(active_events) != len(events):
            await cache_set("liveops:active_events", [e.to_dict() for e in active_events])
        
        return active_events
    
    async def schedule_event(
        self,
        event_type: str,
        name: str,
        description: str,
        duration_hours: int,
        config: Optional[Dict[str, Any]] = None,
        start_time: Optional[datetime] = None
    ) -> LiveEvent:
        """Schedule a new live event."""
        start = start_time or datetime.utcnow()
        end = start + timedelta(hours=duration_hours)
        
        event = LiveEvent(
            id=f"{event_type}_{int(start.timestamp())}",
            event_type=event_type,
            name=name,
            description=description,
            start_time=start,
            end_time=end,
            config=config or {}
        )
        
        # Add to active events
        active = await self.get_active_events()
        active.append(event)
        
        await cache_set("liveops:active_events", [e.to_dict() for e in active])
        
        # Publish event started
        await publish_event("live_event_started", event.to_dict())
        
        return event
    
    async def end_event(self, event_id: str) -> bool:
        """Manually end an event."""
        active = await self.get_active_events()
        
        # Find and deactivate
        for event in active:
            if event.id == event_id:
                event.is_active = False
                event.end_time = datetime.utcnow()
                
                await cache_set("liveops:active_events", [e.to_dict() for e in active])
                await publish_event("live_event_ended", {"event_id": event_id})
                return True
        
        return False
    
    async def process_weekly_cycle(self):
        """
        Process weekly cycle:
        - Schedule daily/weekly events
        - Reset leaderboards on Sunday
        - Process seasonal transitions
        """
        now = datetime.utcnow()
        day_name = now.strftime("%A").lower()
        
        # Check if already processed today
        last_processed = await cache_get("liveops:last_processed_date")
        today = now.date().isoformat()
        
        if last_processed == today:
            return
        
        # Schedule daily event if configured
        weekly_events = self.config.get("weekly_events", {})
        if day_name in weekly_events:
            event_config = weekly_events[day_name]
            
            if event_config["event_type"] == "leaderboard_reset":
                await self._process_leaderboard_reset()
            else:
                await self.schedule_event(
                    event_type=event_config["event_type"],
                    name=event_config["name"],
                    description=event_config.get("description", ""),
                    duration_hours=event_config.get("duration_hours", 24),
                    config=event_config.get("config", {})
                )
        
        # Process seasonal
        await self._process_seasonal_content()
        
        # Mark processed
        await cache_set("liveops:last_processed_date", today)
    
    async def _process_leaderboard_reset(self):
        """Reset leaderboards and distribute rewards."""
        # Publish leaderboard reset event
        await publish_event("leaderboard_reset", {
            "timestamp": datetime.utcnow().isoformat(),
            "type": "weekly"
        })
        
        # Could implement reward distribution here
        # For now, just reset signal
    
    async def _process_seasonal_content(self):
        """Check and activate seasonal events."""
        now = datetime.utcnow()
        month = now.month
        
        # Simple seasonal mapping
        season_map = {
            6: "kupala",    # June
            9: "harvest",   # September
            12: "winter"    # December
        }
        
        if month in season_map:
            template_key = season_map[month]
            
            # Check if seasonal already active this month
            seasonal_key = f"liveops:seasonal:{template_key}:{now.year}"
            already_active = await cache_get(seasonal_key)
            
            if not already_active:
                await self._activate_seasonal_template(template_key)
                await cache_set(seasonal_key, True)
    
    async def _activate_seasonal_template(self, template_key: str):
        """Activate a seasonal template and schedule its events."""
        template = self.config.get("seasonal_templates", {}).get(template_key)
        if not template:
            return
        
        # Schedule template events
        for event_config in template.get("events", []):
            await self.schedule_event(
                event_type=event_config["type"],
                name=event_config["name"],
                description=f"Seasonal event: {template['name']}",
                duration_hours=event_config["duration_hours"],
                config={
                    "seasonal_template": template_key,
                    "special_drops": template.get("special_drops", []),
                    "theme": template.get("theme")
                }
            )
        
        # Publish seasonal start
        await publish_event("seasonal_activated", {
            "template": template_key,
            "name": template["name"],
            "special_drops": template.get("special_drops", [])
        })
    
    async def get_dynamic_config(self) -> Dict[str, Any]:
        """Get current dynamic configuration for client."""
        active_events = await self.get_active_events()
        
        # Build config based on active events
        dynamic = {
            "active_events": [e.to_dict() for e in active_events],
            "modifiers": {},
            "special_drops": []
        }
        
        # Apply event modifiers
        for event in active_events:
            if event.event_type == "double_xp":
                dynamic["modifiers"]["xp_multiplier"] = 2.0
            elif event.event_type == "resource_rush":
                dynamic["modifiers"]["drop_multiplier"] = 1.5
            elif event.event_type == "double_drop":
                dynamic["modifiers"]["rare_drop_chance"] = 2.0
            
            # Collect special drops
            if "special_drops" in event.config:
                dynamic["special_drops"].extend(event.config["special_drops"])
        
        return dynamic
    
    async def force_refresh_config(self):
        """Reload config from file and update."""
        self._load_config()
        await publish_event("liveops_config_updated", {
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def get_next_weekly_reset(self) -> str:
        """Get timestamp of next weekly reset (Sunday midnight UTC)."""
        now = datetime.utcnow()
        
        # Calculate next Sunday midnight UTC
        days_until_sunday = (6 - now.weekday()) % 7
        if days_until_sunday == 0 and now.hour >= 0:
            days_until_sunday = 7
        
        next_reset = now + timedelta(days=days_until_sunday)
        next_reset = next_reset.replace(hour=0, minute=0, second=0, microsecond=0)
        return next_reset.isoformat()


# Global instance
live_ops = LiveOpsEngine()