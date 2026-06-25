import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
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
        return {"active_keys": active_keys, "active_hits": active_hits}


rate_limiter = SlidingWindowRateLimiter()


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
