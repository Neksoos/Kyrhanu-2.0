"""
Anti-cheat and anti-fraud system for Cursed Mounds.
Server-side validation, behavioral analysis, and anomaly detection.
"""
import time
import hmac
import hashlib
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
    3. HMAC verification (action authenticity)
    4. Behavioral scoring (anomaly detection)
    5. Cooldowns and sanctions
    """
    
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

    
    async def validate_tap(
        self,
        user_id: int,
        client_timestamp: int,  # Unix ms from client
        sequence_number: int,   # Monotonic counter from client
        hmac_signature: str,   # HMAC of (user_id:seq:ts:nonce)
        nonce: str,
        current_anomaly_score: float
    ) -> TapValidationResult:
        """Validate a tap action and return validation result."""
        
        if not settings.ANTI_CHEAT_ENABLED:
            return TapValidationResult(is_valid=True)
        
        # 1. Rate limiting (hard)
        rate_ok, rate_reason = await self._check_rate_limit(user_id)
        if not rate_ok:
            return TapValidationResult(
                is_valid=False,
                reason=rate_reason,
                anomaly_delta=5.0,
                new_anomaly_score=current_anomaly_score + 5.0
            )
        
        # 2. Sequence validation
        seq_ok, seq_reason = await self._check_sequence(user_id, sequence_number)
        if not seq_ok:
            return TapValidationResult(
                is_valid=False,
                reason=seq_reason,
                anomaly_delta=3.0,
                new_anomaly_score=current_anomaly_score + 3.0
            )
        
        # 3. Timestamp validation
        time_ok, time_reason = self._check_timestamp(client_timestamp)
        if not time_ok:
            return TapValidationResult(
                is_valid=False,
                reason=time_reason,
                anomaly_delta=2.0,
                new_anomaly_score=current_anomaly_score + 2.0
            )
        
        # 4. HMAC validation
        hmac_ok, hmac_reason = await self._check_hmac(
            user_id, sequence_number, client_timestamp, nonce, hmac_signature
        )
        if not hmac_ok:
            return TapValidationResult(
                is_valid=False,
                reason=hmac_reason,
                anomaly_delta=10.0,
                new_anomaly_score=current_anomaly_score + 10.0
            )
        
        # 5. Behavioral analysis (soft)
        anomaly_delta = await self._analyze_behavior(user_id, client_timestamp)
        new_score = max(0.0, current_anomaly_score + anomaly_delta)
        
        # Apply sanctions if score too high
        if new_score > 50:
            await self._apply_sanction(user_id, "temporary_ban")
            return TapValidationResult(
                is_valid=False,
                reason="Suspicious activity detected",
                anomaly_delta=anomaly_delta,
                new_anomaly_score=new_score
            )
        
        return TapValidationResult(
            is_valid=True,
            anomaly_delta=anomaly_delta,
            new_anomaly_score=new_score
        )
    
    async def _check_rate_limit(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """Check if user is tapping too fast."""
        key = f"anti_cheat:taps:{user_id}"
        now = time.time()
        
        # Use sliding window of 1 second
        window_data = await cache_get(key) or []
        window_data = [t for t in window_data if now - t < 1.0]
        
        if len(window_data) >= settings.MAX_TAPS_PER_SECOND:
            return False, "Too many taps per second"
        
        window_data.append(now)
        await cache_set(key, window_data, ttl=2)
        
        return True, None
    
    async def _check_sequence(self, user_id: int, sequence_number: int) -> Tuple[bool, Optional[str]]:
        """Check if sequence number is valid and monotonic."""
        key = f"anti_cheat:seq:{user_id}"
        last_seq = await cache_get(key) or 0
        
        if sequence_number <= last_seq:
            return False, "Invalid sequence number"
        
        # Check for huge jumps
        if sequence_number - last_seq > 1000:
            return False, "Sequence number jump too large"
        
        await cache_set(key, sequence_number, ttl=3600)
        
        return True, None
    
    def _check_timestamp(self, client_timestamp: int) -> Tuple[bool, Optional[str]]:
        """Validate client timestamp is reasonable."""
        server_time = int(time.time() * 1000)
        diff = abs(server_time - client_timestamp)
        
        # Allow 5 minute drift
        if diff > 5 * 60 * 1000:
            return False, "Timestamp drift too large"
        
        return True, None
    
    async def _check_hmac(
        self,
        user_id: int,
        sequence_number: int,
        client_timestamp: int,
        nonce: str,
        signature: str
    ) -> Tuple[bool, Optional[str]]:
        """Verify HMAC signature to prevent replay/forgery."""
        # Get user's current HMAC key
        key = await hmac_manager.get_current_key()
        
        message = f"{user_id}:{sequence_number}:{client_timestamp}:{nonce}".encode()
        expected = hmac.new(key.encode(), message, hashlib.sha256).hexdigest()
        
        if not secrets.compare_digest(expected, signature):
            return False, "Invalid signature"
        
        # Check nonce reuse
        nonce_key = f"anti_cheat:nonce:{user_id}:{nonce}"
        if await cache_get(nonce_key):
            return False, "Nonce already used"
        
        await cache_set(nonce_key, True, ttl=300)  # 5 min
        
        return True, None
    
    async def _analyze_behavior(self, user_id: int, client_timestamp: int) -> float:
        """Analyze tap timing patterns for bot-like behavior."""
        key = f"anti_cheat:timing:{user_id}"
        
        # Store recent tap intervals
        last_time = await cache_get(f"{key}:last")
        if last_time:
            interval = client_timestamp - last_time
            
            intervals = await cache_get(key) or []
            intervals.append(interval)
            
            # Keep last 50 intervals
            intervals = intervals[-50:]
            await cache_set(key, intervals, ttl=3600)
            
            # Analyze pattern
            if len(intervals) >= 20:
                # Check for perfect rhythm (bots)
                variance = self._calculate_variance(intervals)
                if variance < settings.SUSPICIOUS_PATTERN_THRESHOLD:
                    return 1.0  # Increase anomaly
                
                # Check for impossible speed
                if min(intervals) < settings.MIN_TAP_INTERVAL_MS:
                    return 2.0
            
        await cache_set(f"{key}:last", client_timestamp, ttl=3600)
        
        return -0.1  # Slowly decay anomaly score
    
    def _calculate_variance(self, values: list) -> float:
        """Calculate variance of a list of numbers."""
        if not values:
            return 0.0
        mean = sum(values) / len(values)
        return sum((x - mean) ** 2 for x in values) / len(values)
    
    async def _apply_sanction(self, user_id: int, sanction_type: str):
        """Apply sanction to user (temporary ban, rate limit, etc)."""
        key = f"anti_cheat:sanction:{user_id}"
        
        sanctions = await cache_get(key) or {}
        sanctions[sanction_type] = {
            "applied_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat()
        }
        
        await cache_set(key, sanctions, ttl=3600)
    
    async def is_sanctioned(self, user_id: int) -> bool:
        """Check if user has active sanctions."""
        sanctions = await cache_get(f"anti_cheat:sanction:{user_id}")
        return bool(sanctions)


class HMACKeyManager:
    """Manages HMAC keys for request signing."""
    
    def __init__(self):
        self._current_key = None
        self._key_rotation_time = 0
    
    async def get_current_key(self) -> str:
        """Get current HMAC key, rotate if needed."""
        now = time.time()
        
        # Rotate key every hour
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
            elif isinstance(self._current_key, bytes):
                self._current_key = self._current_key.decode()
        
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