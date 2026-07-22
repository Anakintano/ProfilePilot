"""Redis token-bucket rate limiter. Redis is a disposable cache here — if it's
unreachable we fail open (log-free, best-effort) rather than take the API down,
since durable quota enforcement (daily analysis count, concurrent jobs) lives
in Postgres, not here.
"""
from __future__ import annotations

import time

import redis

from .config import settings

_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=1)
    return _client


def check_and_consume(key: str, max_requests: int, window_seconds: int) -> bool:
    """Fixed-window counter. Returns True if the request is allowed."""
    try:
        client = _get_client()
        bucket = f"ratelimit:{key}:{int(time.time()) // window_seconds}"
        count = client.incr(bucket)
        if count == 1:
            client.expire(bucket, window_seconds)
        return count <= max_requests
    except redis.RedisError:
        return True
