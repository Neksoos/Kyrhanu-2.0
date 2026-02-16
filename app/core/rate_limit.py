import time
from collections import defaultdict, deque

class SimpleRateLimiter:
    def __init__(self):
        self.hits = defaultdict(deque)  # key -> timestamps

    def allow(self, key: str, limit: int, per_sec: int) -> bool:
        now = time.time()
        q = self.hits[key]
        while q and now - q[0] > per_sec:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True

rate_limiter = SimpleRateLimiter()