"""
Analytics and A/B testing system for Cursed Mounds.
Tracks events, manages experiments, and provides insights.
"""
import json
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict

from config import settings
from redis_client import get_redis, cache_get, cache_set
from database import async_session_maker
from models import AnalyticsEvent, ABTestAssignment


@dataclass
class TrackedEvent:
    name: str
    user_id: Optional[int]
    session_id: Optional[str]
    properties: Dict[str, Any]
    client_timestamp: Optional[datetime] = None
    ab_test_group: Optional[str] = None
    ab_test_id: Optional[str] = None


class AnalyticsService:
    """
    Event tracking and analytics.
    Batches events for efficient database writes.
    """
    
    EVENT_BUFFER_KEY = "analytics:event_buffer"
    BUFFER_SIZE = 100
    FLUSH_INTERVAL = 60  # seconds
    
    CORE_EVENTS = {
        "tap", "energy_depleted", "purchase_start", "purchase_complete",
        "guild_join", "referral_used", "ad_watched", "reward_claimed",
        "level_up", "boss_attack", "daily_claim", "choice_made",
        "shop_open", "inventory_open", "leaderboard_view"
    }
    
    def __init__(self):
        self.redis = get_redis()
    
    async def track(self, event: TrackedEvent):
        """
        Track an analytics event.
        Stores in Redis buffer, flushes to DB periodically.
        """
        # Add timestamp if not provided
        if event.client_timestamp is None:
            event.client_timestamp = datetime.utcnow()
        
        event_data = {
            "event_name": event.name,
            "user_id": event.user_id,
            "session_id": event.session_id,
            "properties": json.dumps(event.properties),
            "client_timestamp": event.client_timestamp.isoformat() if event.client_timestamp else None,
            "ab_test_group": event.ab_test_group,
            "ab_test_id": event.ab_test_id,
            "server_timestamp": datetime.utcnow().isoformat()
        }
        
        # Add to buffer
        await self.redis.lpush(self.EVENT_BUFFER_KEY, json.dumps(event_data))
        
        # Check if should flush
        buffer_size = await self.redis.llen(self.EVENT_BUFFER_KEY)
        if buffer_size >= self.BUFFER_SIZE:
            await self._flush_buffer()
        
        # Also publish real-time for live dashboards
        if event.name in ["purchase_complete", "boss_attack", "guild_join"]:
            await self.redis.publish(f"analytics:live:{event.name}", json.dumps(event_data))
    
    async def _flush_buffer(self):
        """Flush event buffer to database."""
        events = []
        for _ in range(self.BUFFER_SIZE):
            data = await self.redis.rpop(self.EVENT_BUFFER_KEY)
            if not data:
                break
            events.append(json.loads(data))
        
        if not events:
            return
        
        # Bulk insert to database
        async with async_session_maker() as session:
            # Use copy for performance if available, else bulk insert
            for evt_data in events:
                event = AnalyticsEvent(
                    event_name=evt_data["event_name"],
                    user_id=evt_data["user_id"],
                    session_id=evt_data["session_id"],
                    properties=json.loads(evt_data["properties"]),
                    client_timestamp=datetime.fromisoformat(evt_data["client_timestamp"]) if evt_data["client_timestamp"] else None,
                    ab_test_group=evt_data["ab_test_group"],
                    ab_test_id=evt_data["ab_test_id"]
                )
                session.add(event)
            
            await session.commit()
    
    async def get_user_journey(self, user_id: int, limit: int = 100) -> List[Dict]:
        """Get recent events for a specific user."""
        async with async_session_maker() as session:
            from sqlalchemy import select, desc
            result = await session.execute(
                select(AnalyticsEvent)
                .where(AnalyticsEvent.user_id == user_id)
                .order_by(desc(AnalyticsEvent.created_at))
                .limit(limit)
            )
            events = result.scalars().all()
            return [
                {
                    "event": e.event_name,
                    "time": e.created_at.isoformat(),
                    "props": e.properties
                }
                for e in events
            ]
    
    async def get_funnel_data(
        self,
        event_sequence: List[str],
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get funnel conversion data.
        Example: ["shop_open", "purchase_start", "purchase_complete"]
        """
        # This would typically use a data warehouse
        # Simplified version using recent Redis data
        
        counts = {}
        for event in event_sequence:
            # Count from buffer + recent DB
            buffer_count = await self.redis.llen(self.EVENT_BUFFER_KEY)
            # In real implementation, query time-series DB
            counts[event] = {"count": buffer_count, "conversion": 1.0}
        
        # Calculate conversions
        for i in range(1, len(event_sequence)):
            prev = event_sequence[i-1]
            curr = event_sequence[i]
            if counts[prev]["count"] > 0:
                counts[curr]["conversion"] = counts[curr]["count"] / counts[prev]["count"]
        
        return {
            "funnel": event_sequence,
            "steps": counts,
            "overall_conversion": counts[event_sequence[-1]]["count"] / counts[event_sequence[0]]["count"] 
                if counts[event_sequence[0]]["count"] > 0 else 0
        }


class ABTestManager:
    """
    A/B testing system.
    Assigns users to test groups and tracks performance.
    """
    
    ACTIVE_TESTS = {
        "energy_price": {
            "variants": ["control", "variant_a", "variant_b"],
            "weights": [0.34, 0.33, 0.33],
            "config": {
                "control": {"small_price": 25, "large_price": 80},
                "variant_a": {"small_price": 20, "large_price": 70},  # Discount
                "variant_b": {"small_price": 30, "large_price": 90}   # Premium
            }
        },
        "battle_pass_frequency": {
            "variants": ["control", "variant_a"],
            "weights": [0.5, 0.5],
            "config": {
                "control": {"duration_days": 30, "price": 499},
                "variant_a": {"duration_days": 14, "price": 299}  # Shorter, cheaper
            }
        },
        "drop_rate_visibility": {
            "variants": ["control", "variant_a"],
            "weights": [0.5, 0.5],
            "config": {
                "control": {"show_exact_rates": False},
                "variant_a": {"show_exact_rates": True}  # Transparent gacha
            }
        },
        "guild_requirement_timing": {
            "variants": ["control", "variant_a"],
            "weights": [0.5, 0.5],
            "config": {
                "control": {"required_level": 3, "required_day": 3},
                "variant_a": {"required_level": 5, "required_day": 7}  # Later push
            }
        }
    }
    
    def __init__(self):
        self.redis = get_redis()
        self.analytics = AnalyticsService()
    
    def _get_user_group(self, user_id: int, test_name: str) -> str:
        """Deterministically assign user to test group."""
        # Hash user_id + test_name for consistent assignment
        hash_input = f"{user_id}:{test_name}:ab_test_v1"
        hash_val = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        
        test_config = self.ACTIVE_TESTS[test_name]
        weights = test_config["weights"]
        
        # Weighted random based on hash
        total = sum(weights)
        point = (hash_val % 1000) / 1000 * total
        
        cumulative = 0
        for variant, weight in zip(test_config["variants"], weights):
            cumulative += weight
            if point <= cumulative:
                return variant
        
        return test_config["variants"][-1]
    
    async def get_user_config(self, user_id: int) -> Dict[str, Any]:
        """
        Get all A/B test configs for user.
        Returns merged configuration.
        """
        config = {}
        assignments = {}
        
        for test_name, test_data in self.ACTIVE_TESTS.items():
            # Check if already assigned
            assigned = await self._get_assignment(user_id, test_name)
            
            if assigned:
                group = assigned
            else:
                # New assignment
                group = self._get_user_group(user_id, test_name)
                await self._save_assignment(user_id, test_name, group)
                
                # Track assignment
                await self.analytics.track(TrackedEvent(
                    name="ab_test_assigned",
                    user_id=user_id,
                    session_id=None,
                    properties={"test": test_name, "group": group},
                    ab_test_group=group,
                    ab_test_id=test_name
                ))
            
            assignments[test_name] = group
            config.update(test_data["config"].get(group, {}))
        
        return {
            "config": config,
            "assignments": assignments
        }
    
    async def _get_assignment(self, user_id: int, test_name: str) -> Optional[str]:
        """Get existing assignment from cache or DB."""
        cache_key = f"ab:{user_id}:{test_name}"
        cached = await cache_get(cache_key)
        if cached:
            return cached
        
        # Check DB
        async with async_session_maker() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(ABTestAssignment).where(
                    ABTestAssignment.user_id == user_id,
                    ABTestAssignment.test_name == test_name
                )
            )
            assignment = result.scalar_one_or_none()
            
            if assignment:
                await cache_set(cache_key, assignment.group_name, expire=86400)
                return assignment.group_name
        
        return None
    
    async def _save_assignment(self, user_id: int, test_name: str, group: str):
        """Save assignment to DB and cache."""
        async with async_session_maker() as session:
            from sqlalchemy import select
            # Check exists
            result = await session.execute(
                select(ABTestAssignment).where(
                    ABTestAssignment.user_id == user_id,
                    ABTestAssignment.test_name == test_name
                )
            )
            existing = result.scalar_one_or_none()
            
            if not existing:
                assignment = ABTestAssignment(
                    user_id=user_id,
                    test_name=test_name,
                    group_name=group
                )
                session.add(assignment)
                await session.commit()
        
        # Cache
        await cache_set(f"ab:{user_id}:{test_name}", group, expire=86400)
    
    async def get_test_results(self, test_name: str) -> Dict[str, Any]:
        """
        Get preliminary results for A/B test.
        In production, this would query analytics warehouse.
        """
        if test_name not in self.ACTIVE_TESTS:
            return {"error": "Test not found"}
        
        test_config = self.ACTIVE_TESTS[test_name]
        
        # Simplified metrics from Redis counters
        metrics = {}
        for variant in test_config["variants"]:
            # These would be real metrics in production
            metrics[variant] = {
                "users": await self.redis.get(f"ab_metrics:{test_name}:{variant}:users") or 0,
                "conversion": await self.redis.get(f"ab_metrics:{test_name}:{variant}:conversion") or 0,
                "revenue": await self.redis.get(f"ab_metrics:{test_name}:{variant}:revenue") or 0
            }
        
        return {
            "test": test_name,
            "variants": test_config["variants"],
            "metrics": metrics,
            "recommendation": "Insufficient data"  # Would be calculated
        }


# Global instances
analytics = AnalyticsService()
ab_test_manager = ABTestManager()