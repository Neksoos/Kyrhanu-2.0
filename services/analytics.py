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
from models import AnalyticsEvent


@dataclass
class TrackedEvent:
    """Analytics event data structure."""
    name: str
    user_id: int
    session_id: Optional[str]
    properties: Dict[str, Any]
    client_timestamp: Optional[datetime] = None
    
    def to_dict(self):
        data = asdict(self)
        if self.client_timestamp:
            data['client_timestamp'] = self.client_timestamp.isoformat()
        return data


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
        # NOTE: Redis is initialized asynchronously in app startup.
        # Do NOT call get_redis() at import time.
        self._redis = None

    @property
    def redis(self):
        """Lazy Redis client (available after init_redis())."""
        if self._redis is None:
            self._redis = get_redis()
        return self._redis

    
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
            "properties": event.properties,
            "client_timestamp": event.client_timestamp.isoformat()
        }
        
        # Add to Redis buffer
        buffer = await cache_get(self.EVENT_BUFFER_KEY) or []
        buffer.append(event_data)
        
        # Flush if buffer full
        if len(buffer) >= self.BUFFER_SIZE:
            await self._flush_to_db(buffer)
            buffer = []
        
        await cache_set(self.EVENT_BUFFER_KEY, buffer, ttl=3600)
    
    async def _flush_to_db(self, events: List[Dict[str, Any]]):
        """Flush events to database."""
        async with async_session_maker() as session:
            for event_data in events:
                analytics_event = AnalyticsEvent(
                    event_name=event_data["event_name"],
                    user_id=event_data["user_id"],
                    session_id=event_data["session_id"],
                    properties=event_data["properties"],
                    client_timestamp=datetime.fromisoformat(event_data["client_timestamp"])
                )
                session.add(analytics_event)
            
            await session.commit()
    
    async def _flush_buffer(self):
        """Flush current buffer to DB (called periodically)."""
        buffer = await cache_get(self.EVENT_BUFFER_KEY)
        if buffer:
            await self._flush_to_db(buffer)
            await cache_set(self.EVENT_BUFFER_KEY, [], ttl=3600)
    
    async def get_user_metrics(self, user_id: int) -> Dict[str, Any]:
        """Get aggregated metrics for a user."""
        cache_key = f"analytics:user:{user_id}:metrics"
        cached = await cache_get(cache_key)
        if cached:
            return cached
        
        async with async_session_maker() as session:
            # Get event counts and last activity
            from sqlalchemy import select, func
            
            result = await session.execute(
                select(
                    AnalyticsEvent.event_name,
                    func.count(AnalyticsEvent.id).label('count'),
                    func.max(AnalyticsEvent.client_timestamp).label('last_time')
                ).where(
                    AnalyticsEvent.user_id == user_id
                ).group_by(AnalyticsEvent.event_name)
            )
            
            metrics = {
                "events": {},
                "last_activity": None,
                "total_events": 0
            }
            
            for row in result:
                metrics["events"][row.event_name] = {
                    "count": row.count,
                    "last_time": row.last_time.isoformat() if row.last_time else None
                }
                metrics["total_events"] += row.count
                
                if not metrics["last_activity"] or (row.last_time and row.last_time > datetime.fromisoformat(metrics["last_activity"])):
                    metrics["last_activity"] = row.last_time.isoformat()
            
            # Cache for 5 minutes
            await cache_set(cache_key, metrics, ttl=300)
            
            return metrics
    
    async def get_funnel_analysis(self, funnel_steps: List[str], days: int = 7) -> Dict[str, Any]:
        """Analyze conversion funnel."""
        async with async_session_maker() as session:
            from sqlalchemy import select, func
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            funnel_data = {}
            previous_users = None
            
            for step in funnel_steps:
                # Get unique users for this step
                result = await session.execute(
                    select(func.count(func.distinct(AnalyticsEvent.user_id)))
                    .where(
                        AnalyticsEvent.event_name == step,
                        AnalyticsEvent.client_timestamp >= cutoff
                    )
                )
                user_count = result.scalar()
                
                conversion = 1.0
                if previous_users and previous_users > 0:
                    conversion = user_count / previous_users
                
                funnel_data[step] = {
                    "users": user_count,
                    "conversion": conversion
                }
                
                previous_users = user_count
            
            return {
                "period_days": days,
                "steps": funnel_data
            }


class ABTestManager:
    """
    A/B testing manager.
    Assigns users to test groups and manages experiment configs.
    """
    
    ACTIVE_TESTS = {
        "energy_regen_rate": {
            "variants": ["control", "variant_a", "variant_b"],
            "weights": [0.5, 0.25, 0.25],
            "config": {
                "control": {"regen_minutes": 30},
                "variant_a": {"regen_minutes": 25},
                "variant_b": {"regen_minutes": 35}
            }
        },
        "daily_reward_amount": {
            "variants": ["control", "variant_a"],
            "weights": [0.7, 0.3],
            "config": {
                "control": {"reward_multiplier": 1.0},
                "variant_a": {"reward_multiplier": 1.5}
            }
        },
        "boss_difficulty_curve": {
            "variants": ["control", "variant_a", "variant_b"],
            "weights": [0.6, 0.2, 0.2],
            "config": {
                "control": {"hp_multiplier": 1.0, "damage_multiplier": 1.0},
                "variant_a": {"hp_multiplier": 0.8, "damage_multiplier": 0.9},
                "variant_b": {"hp_multiplier": 1.2, "damage_multiplier": 1.1}
            }
        },
        "gacha_transparency": {
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
        # NOTE: Redis is initialized asynchronously in app startup.
        # Do NOT call get_redis() at import time.
        self._redis = None
        self.analytics = AnalyticsService()

    @property
    def redis(self):
        """Lazy Redis client (available after init_redis())."""
        if self._redis is None:
            self._redis = get_redis()
        return self._redis
    
    def _get_user_group(self, user_id: int, test_name: str) -> str:
        """Deterministically assign user to test group."""
        # Hash user_id + test_name for consistent assignment
        hash_input = f"{user_id}:{test_name}:ab_test_v1"
        hash_val = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        
        test_config = self.ACTIVE_TESTS[test_name]
        variants = test_config["variants"]
        weights = test_config["weights"]
        
        # Use hash to pick variant
        total_weight = sum(weights)
        pick = (hash_val % 1000) / 1000.0 * total_weight
        
        cumulative = 0
        for variant, weight in zip(variants, weights):
            cumulative += weight
            if pick <= cumulative:
                return variant
        
        return variants[0]  # Fallback
    
    async def get_variant(self, user_id: int, test_name: str) -> str:
        """Get user's assigned variant for a test."""
        if test_name not in self.ACTIVE_TESTS:
            return "control"
        
        cache_key = f"abtest:{test_name}:user:{user_id}"
        cached = await cache_get(cache_key)
        if cached:
            return cached
        
        variant = self._get_user_group(user_id, test_name)
        await cache_set(cache_key, variant, ttl=86400 * 30)  # 30 days
        
        return variant
    
    async def get_config(self, user_id: int, test_name: str) -> Dict[str, Any]:
        """Get configuration for user's variant."""
        variant = await self.get_variant(user_id, test_name)
        test_config = self.ACTIVE_TESTS.get(test_name, {})
        
        return test_config.get("config", {}).get(variant, {})
    
    async def track_conversion(self, user_id: int, test_name: str, metric: str, value: float = 1.0):
        """Track conversion metric for A/B test."""
        variant = await self.get_variant(user_id, test_name)
        
        # Track as analytics event
        await self.analytics.track(TrackedEvent(
            name="ab_test_metric",
            user_id=user_id,
            session_id=None,
            properties={
                "test": test_name,
                "variant": variant,
                "metric": metric,
                "value": value
            }
        ))
        
        # Store aggregated metrics in Redis
        metrics_key = f"abtest:{test_name}:metrics:{variant}:{metric}"
        current = await cache_get(metrics_key) or {"count": 0, "sum": 0}
        current["count"] += 1
        current["sum"] += value
        await cache_set(metrics_key, current, ttl=86400 * 90)  # 90 days
    
    async def get_test_results(self, test_name: str) -> Dict[str, Any]:
        """Get aggregated results for a test."""
        if test_name not in self.ACTIVE_TESTS:
            return {}
        
        test_config = self.ACTIVE_TESTS[test_name]
        results = {}
        
        # Get metrics for each variant
        for variant in test_config["variants"]:
            variant_metrics = {}
            
            # Common metrics to track
            metrics = ["retention_day1", "retention_day7", "purchase_rate", "avg_session_length"]
            
            for metric in metrics:
                metrics_key = f"abtest:{test_name}:metrics:{variant}:{metric}"
                data = await cache_get(metrics_key) or {"count": 0, "sum": 0}
                
                avg = 0
                if data["count"] > 0:
                    avg = data["sum"] / data["count"]
                
                variant_metrics[metric] = {
                    "count": data["count"],
                    "average": avg,
                    "total": data["sum"]
                }
            
            results[variant] = variant_metrics
        
        return {
            "test": test_name,
            "variants": test_config["variants"],
            "metrics": results,
            "recommendation": "Insufficient data"  # Would be calculated
        }


# Global instances
analytics = AnalyticsService()
ab_test_manager = ABTestManager()