import time
from collections import defaultdict, deque

from redis import Redis

from app.config import settings


class SlidingWindowRateLimiter:
    backend = "memory"

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        remaining = max(0, limit - len(bucket))
        if len(bucket) >= limit:
            return False, 0
        bucket.append(now)
        return True, max(0, remaining - 1)

    def snapshot(self) -> dict:
        now = time.monotonic()
        active_keys = 0
        active_hits = 0
        for bucket in self._hits.values():
            while bucket and now - bucket[0] > 3600:
                bucket.popleft()
            if bucket:
                active_keys += 1
                active_hits += len(bucket)
        return {"backend": self.backend, "active_keys": active_keys, "active_hits": active_hits}


class RedisWindowRateLimiter:
    backend = "redis"

    def __init__(self, redis_url: str, prefix: str) -> None:
        self.prefix = prefix
        self.client = Redis.from_url(redis_url, decode_responses=True)
        self.client.ping()

    def allow(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = int(time.time())
        bucket = f"{self.prefix}:{key}:{now // window_seconds}"
        count = int(self.client.incr(bucket))
        if count == 1:
            self.client.expire(bucket, window_seconds + 5)
        return count <= limit, max(0, limit - count)

    def snapshot(self) -> dict:
        pattern = f"{self.prefix}:*"
        active_keys = 0
        active_hits = 0
        for key in self.client.scan_iter(match=pattern, count=100):
            active_keys += 1
            try:
                active_hits += int(self.client.get(key) or 0)
            except ValueError:
                continue
            if active_keys >= 500:
                break
        return {"backend": self.backend, "active_keys": active_keys, "active_hits": active_hits}


def _build_rate_limiter():
    backend = settings.RATE_LIMIT_BACKEND.lower()
    if backend in {"auto", "redis"}:
        try:
            return RedisWindowRateLimiter(settings.REDIS_URL, settings.RATE_LIMIT_REDIS_PREFIX)
        except Exception:
            if backend == "redis":
                raise
    return SlidingWindowRateLimiter()


rate_limiter = _build_rate_limiter()


def client_ip(request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit_policy(path: str) -> tuple[int, int] | None:
    if path in {"/auth/login", "/auth/register", "/auth/refresh"}:
        return 120, 60
    if path.startswith("/query/ask"):
        return 120, 60
    if path.startswith("/documents/upload-url") or path.endswith("/retry-ocr"):
        return 240, 60
    if path.startswith("/whatsapp/send-manual"):
        return 120, 60
    if path.startswith("/events") or path.startswith("/integrations") or path.startswith("/diagnostics"):
        return 600, 60
    return 1200, 60
