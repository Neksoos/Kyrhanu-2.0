"""Anti-cheat and anti-fraud system for Cursed Mounds.

Important note: the client is not a trusted environment. Anything the client can compute
(including secrets) can be extracted by an attacker. Therefore this module focuses on
**server-side** validation (rate limits, replay protection, behavioral scoring) and avoids
schemes that require a client-held secret.
"""

import time
import secrets
from typing import Dict, Optional, Tuple, Any
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
    """Multi-layer anti-cheat.

    1) Rate limiting (hard caps)
    2) Replay protection (nonce + monotonic-ish sequence)
    3) Timing analysis (human-like patterns, autoclick detection)
    4) Progressive sanctions (cooldowns / shadow-nerf)
    """

    def __init__(self):
        self.redis = get_redis()

    async def validate_tap(
        self,
        user_id: int,
        client_timestamp: int,  # Unix ms from client (best-effort)
        sequence_number: int,
        nonce: str,
        current_anomaly_score: float,
    ) -> TapValidationResult:
        """Validate a tap action.

        The timestamp is not trusted, but we keep a small drift check to catch obvious
        replays from stale clients. Stronger protection comes from nonce + sequence.
        """
        if not settings.ANTI_CHEAT_ENABLED:
            return TapValidationResult(True, new_anomaly_score=current_anomaly_score)

        now_ms = int(time.time() * 1000)

        # 1) Nonce replay protection (2 minutes window)
        nonce_key = f"nonce:tap:{user_id}:{nonce}"
        if await self.redis.get(nonce_key):
            new_score = min(100.0, current_anomaly_score + 20.0)
            return TapValidationResult(False, "Nonce replay", 20.0, new_score)
        await self.redis.setex(nonce_key, 120, "1")

        # 2) Timestamp drift (best-effort)
        drift = abs(now_ms - int(client_timestamp))
        if drift > 5 * 60 * 1000:  # 5 minutes
            new_score = min(100.0, current_anomaly_score + 10.0)
            return TapValidationResult(False, "Client timestamp drift too large", 10.0, new_score)

        # 3) Rate limiting - hard cap per second
        rate_key = f"ratelimit:taps:{user_id}:{now_ms // 1000}"
        current_count = await self.redis.incr(rate_key)
        if current_count == 1:
            await self.redis.expire(rate_key, 1)

        max_tps = int(settings.MAX_TAPS_PER_SECOND)
        if current_count > max_tps:
            new_score = min(100.0, current_anomaly_score + 10.0)
            return TapValidationResult(False, "Rate limit exceeded", 10.0, new_score)

        # 4) Sequence replay protection (5 minute window)
        last_seq_key = f"seq:last:{user_id}"
        last_seq_raw = await self.redis.get(last_seq_key)
        if last_seq_raw is not None:
            last_seq = int(last_seq_raw)
            if sequence_number <= last_seq:
                new_score = min(100.0, current_anomaly_score + 30.0)
                return TapValidationResult(False, "Sequence replay", 30.0, new_score)
            # Jumps can happen on reload; mild penalty.
            if sequence_number > last_seq + 1:
                current_anomaly_score = min(100.0, current_anomaly_score + 2.0)
        await self.redis.setex(last_seq_key, 300, int(sequence_number))

        # 5) Behavioral analysis (server-receive intervals)
        pattern_key = f"pattern:taps:{user_id}"
        pattern = await cache_get(pattern_key) or {"intervals": [], "last_ts": None, "perfect_count": 0}

        anomaly_delta = 0.0
        last_ts = pattern.get("last_ts")
        if last_ts:
            interval = now_ms - int(last_ts)
            pattern["intervals"].append(interval)
            if len(pattern["intervals"]) > 50:
                pattern["intervals"] = pattern["intervals"][-50:]

            # Autoclicker: last 5 intervals all too small
            recent = pattern["intervals"][-5:]
            if len(recent) == 5 and all(i < settings.MIN_TAP_INTERVAL_MS for i in recent):
                anomaly_delta += 8.0

            # Bot-like perfect rhythm: extremely low variance over last 10
            if len(pattern["intervals"]) >= 10:
                recent10 = pattern["intervals"][-10:]
                avg = sum(recent10) / 10.0
                var = sum((i - avg) ** 2 for i in recent10) / 10.0
                if var < 100.0:
                    pattern["perfect_count"] = int(pattern.get("perfect_count", 0)) + 1
                    if pattern["perfect_count"] >= settings.SUSPICIOUS_PATTERN_THRESHOLD:
                        anomaly_delta += 5.0
                else:
                    pattern["perfect_count"] = max(0, int(pattern.get("perfect_count", 0)) - 1)

        pattern["last_ts"] = now_ms
        await cache_set(pattern_key, pattern, expire=600)

        new_score = min(100.0, current_anomaly_score + anomaly_delta)
        return TapValidationResult(True, None, anomaly_delta, new_score)

    async def apply_sanctions(self, user_id: int, anomaly_score: float) -> Dict[str, Any]:
        """Apply progressive sanctions based on anomaly score."""
        sanctions = {
            "shadow_nerf": False,
            "cooldown_seconds": 0,
            "banned": False,
            "review_required": False,
        }

        if anomaly_score >= 100:
            sanctions["banned"] = True
            sanctions["review_required"] = True
        elif anomaly_score >= 80:
            sanctions["shadow_nerf"] = True
            sanctions["cooldown_seconds"] = 300
        elif anomaly_score >= 60:
            sanctions["cooldown_seconds"] = 60
        elif anomaly_score >= 40:
            sanctions["shadow_nerf"] = True

        if sanctions["cooldown_seconds"] > 0:
            await self.redis.setex(
                f"sanction:cooldown:{user_id}", sanctions["cooldown_seconds"], "1"
            )

        if sanctions["shadow_nerf"]:
            await self.redis.setex(
                f"sanction:nerf:{user_id}", 3600, str(anomaly_score)
            )

        return sanctions

    async def is_under_cooldown(self, user_id: int) -> Tuple[bool, int]:
        ttl = await self.redis.ttl(f"sanction:cooldown:{user_id}")
        if ttl and ttl > 0:
            return True, int(ttl)
        return False, 0

    async def is_shadow_nerfed(self, user_id: int) -> Tuple[bool, float]:
        nerf_data = await self.redis.get(f"sanction:nerf:{user_id}")
        if nerf_data:
            return True, float(nerf_data)
        return False, 0.0

    def generate_client_nonce(self) -> str:
        """Legacy helper. Clients can generate their own nonces; we keep this for convenience."""
        return secrets.token_hex(16)

    async def get_client_config(self, user_id: int) -> Dict[str, Any]:
        """Config that the client may use to self-throttle and reduce false positives."""
        return {
            "max_taps_per_second": int(settings.MAX_TAPS_PER_SECOND),
            "min_tap_interval_ms": int(settings.MIN_TAP_INTERVAL_MS),
            "nonce_hint": "Send a fresh random nonce per tap (uuid/hex).",
        }


# Global instance
anti_cheat = AntiCheatService()
