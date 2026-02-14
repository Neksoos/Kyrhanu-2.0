"""
Anti-cheat and anti-fraud system for Cursed Mounds.
Server-side validation, behavioral analysis, and anomaly detection.
"""
import time
import secrets
from typing import Dict, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

from config import settings
from redis_client import get_redis, cache_get, cache_set


@dataclass
class TapValidationResult:
    is_valid: bool
    reason: Optional[str] = None
    anomaly_delta: float = 0.0
    new_anomaly_score: float = 0.0


class AntiCheatService:
    """
    Multi-layer anti-cheat:
    1. Rate limiting (hard caps)
    2. Timing analysis (human-like patterns)
    3. (Optional) authenticity checks
    4. Behavioral scoring (anomaly detection)
    5. Cooldowns and sanctions
    """
    
    def __init__(self):
        self.redis = get_redis()
    
    async def validate_tap(
        self,
        user_id: int,
        client_timestamp: int,  # Unix ms from client
        sequence_number: int,   # Monotonic counter from client
        nonce: str,
        current_anomaly_score: float
    ) -> TapValidationResult:
        """
        Validate tap action with multiple checks.
        """
        now = int(time.time() * 1000)
        
        # 1. Check timestamp drift (prevent replay-ish patterns)
        drift = abs(now - client_timestamp)
        if drift > 30000:  # 30 seconds max drift
            return TapValidationResult(
                is_valid=False,
                reason="Timestamp drift too large",
                anomaly_delta=15.0,
                new_anomaly_score=min(100.0, current_anomaly_score + 15.0)
            )
        
        # 2. Rate limiting - hard cap
        rate_key = f"ratelimit:taps:{user_id}:{now // 1000}"
        current_count = await self.redis.incr(rate_key)
        if current_count == 1:
            await self.redis.expire(rate_key, 1)  # 1-second window
        
        max_taps_per_second = int(settings.MAX_TAPS_PER_SECOND)
        if current_count > max_taps_per_second:
            return TapValidationResult(
                is_valid=False,
                reason="Rate limit exceeded",
                anomaly_delta=10.0,
                new_anomaly_score=min(100.0, current_anomaly_score + 10.0)
            )
        
        # 3. Sequence number check (prevent replay)
        last_seq_key = f"seq:last:{user_id}"
        last_seq = await self.redis.get(last_seq_key)
        if last_seq and int(last_seq) >= sequence_number:
            return TapValidationResult(
                is_valid=False,
                reason="Sequence number replay",
                anomaly_delta=30.0,
                new_anomaly_score=min(100.0, current_anomaly_score + 30.0)
            )
        await self.redis.setex(last_seq_key, 300, sequence_number)  # 5-min TTL
        
        # 4. Behavioral analysis - timing patterns
        pattern_key = f"pattern:taps:{user_id}"
        pattern_data = await cache_get(pattern_key) or {
            "intervals": [],
            "last_ts": None,
            "perfect_count": 0
        }
        
        anomaly_delta = 0.0
        
        if pattern_data["last_ts"]:
            interval = client_timestamp - pattern_data["last_ts"]
            
            # Check for inhuman consistency (bot-like)
            if len(pattern_data["intervals"]) >= 10:
                recent_intervals = pattern_data["intervals"][-10:]
                avg_interval = sum(recent_intervals) / len(recent_intervals)
                variance = sum((i - avg_interval) ** 2 for i in recent_intervals) / len(recent_intervals)
                
                # Perfect rhythm = very low variance
                if variance < 100:  # Less than 100ms variance
                    pattern_data["perfect_count"] += 1
                    if pattern_data["perfect_count"] >= settings.SUSPICIOUS_PATTERN_THRESHOLD:
                        anomaly_delta += 5.0  # Escalating penalty
                else:
                    pattern_data["perfect_count"] = max(0, pattern_data["perfect_count"] - 1)
            
            pattern_data["intervals"].append(interval)
            if len(pattern_data["intervals"]) > 50:
                pattern_data["intervals"] = pattern_data["intervals"][-50:]
        
        pattern_data["last_ts"] = client_timestamp
        await cache_set(pattern_key, pattern_data, expire=600)  # 10-min window
        
        # 5. Check for rapid-fire (autoclicker)
        if pattern_data.get("intervals"):
            recent = pattern_data["intervals"][-5:]
            if all(i < settings.MIN_TAP_INTERVAL_MS for i in recent):
                anomaly_delta += 8.0
        
        new_score = min(100.0, current_anomaly_score + anomaly_delta)
        
        return TapValidationResult(
            is_valid=True,
            reason=None,
            anomaly_delta=anomaly_delta,
            new_anomaly_score=new_score
        )
    
    # NOTE: This project intentionally does NOT rely on a client-held secret.
    # If you later want signed actions, implement a per-session signing key
    # delivered to the client and validated server-side.
    
    async def apply_sanctions(self, user_id: int, anomaly_score: float) -> Dict[str, Any]:
        """
        Apply progressive sanctions based on anomaly score.
        """
        sanctions = {
            "shadow_nerf": False,
            "cooldown_seconds": 0,
            "banned": False,
            "review_required": False
        }
        
        if anomaly_score >= 100:
            # Auto-ban
            sanctions["banned"] = True
            sanctions["review_required"] = True
            
        elif anomaly_score >= 80:
            # Shadow nerf + cooldown
            sanctions["shadow_nerf"] = True
            sanctions["cooldown_seconds"] = 300  # 5 min
            
        elif anomaly_score >= 60:
            # Warning cooldown
            sanctions["cooldown_seconds"] = 60  # 1 min
            
        elif anomaly_score >= 40:
            # Soft shadow nerf (reduced drops)
            sanctions["shadow_nerf"] = True
        
        # Store sanctions in Redis for quick lookup
        if sanctions["cooldown_seconds"] > 0:
            await self.redis.setex(
                f"sanction:cooldown:{user_id}",
                sanctions["cooldown_seconds"],
                "1"
            )
        
        if sanctions["shadow_nerf"]:
            await self.redis.setex(
                f"sanction:nerf:{user_id}",
                3600,  # 1 hour
                str(anomaly_score)
            )
        
        return sanctions
    
    async def is_under_cooldown(self, user_id: int) -> Tuple[bool, int]:
        """Check if user is under cooldown."""
        ttl = await self.redis.ttl(f"sanction:cooldown:{user_id}")
        if ttl > 0:
            return True, ttl
        return False, 0
    
    async def is_shadow_nerfed(self, user_id: int) -> Tuple[bool, float]:
        """Check if user has shadow nerf active."""
        nerf_data = await self.redis.get(f"sanction:nerf:{user_id}")
        if nerf_data:
            return True, float(nerf_data)
        return False, 0.0
    
    def generate_client_nonce(self) -> str:
        """Generate nonce for client to use in HMAC."""
        return secrets.token_hex(16)
    
    async def get_client_config(self, user_id: int) -> Dict[str, Any]:
        """
        Config sent to client for HMAC generation.
        Includes fresh nonce.
        """
        nonce = self.generate_client_nonce()
        
        # Store nonce for validation (short TTL)
        await self.redis.setex(f"nonce:{user_id}:{nonce}", 60, "1")
        
        return {
            "nonce": nonce,
            "max_taps_per_second": settings.MAX_TAPS_PER_SECOND,
            "min_tap_interval_ms": settings.MIN_TAP_INTERVAL_MS,
            "hmac_key_hint": "use server secret via /auth",  # Client gets key after auth
        }


class HMACKeyManager:
    """
    Rotating HMAC keys for client-side signing.
    """
    def __init__(self):
        self._current_key = None
        self._key_rotation_time = 0
    
    async def get_current_key(self) -> str:
        """Get or rotate HMAC key."""
        now = time.time()
        
        if now - self._key_rotation_time > 3600:  # Rotate hourly
            self._current_key = secrets.token_urlsafe(32)
            self._key_rotation_time = now
            
            # Store in Redis for multi-instance consistency
            redis = get_redis()
            await redis.setex("hmac:current_key", 7200, self._current_key)
        
        if self._current_key is None:
            # Try to get from Redis
            redis = get_redis()
            self._current_key = await redis.get("hmac:current_key")
            if self._current_key is None:
                self._current_key = secrets.token_urlsafe(32)
                await redis.setex("hmac:current_key", 7200, self._current_key)
        
        return self._current_key
    
    async def validate_key(self, key: str) -> bool:
        """Validate if key is current or recent."""
        current = await self.get_current_key()
        if secrets.compare_digest(key, current):
            return True
        
        # Check previous key (grace period)
        redis = get_redis()
        previous = await redis.get("hmac:previous_key")
        if previous and secrets.compare_digest(key, previous):
            return True
        
        return False
    
    async def rotate(self):
        """Force key rotation."""
        self._key_rotation_time = 0
        redis = get_redis()
        current = await redis.get("hmac:current_key")
        if current:
            await redis.setex("hmac:previous_key", 1800, current)  # 30-min grace


# Global instances
anti_cheat = AntiCheatService()
hmac_manager = HMACKeyManager()