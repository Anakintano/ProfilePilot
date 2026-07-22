"""Global (not per-user) budget on real LLM provider calls (Groq/OpenRouter),
duplicated from services/api/app/llm_rate_limit.py -- see db.py's header
comment for why small shared infra is duplicated rather than factored into a
shared package between api/worker. Redis is a disposable cache here (same
posture as the API's rate_limit.py): if it's unreachable, fail open rather
than block extraction/scoring on a cost-control nicety. The worker has no
pydantic Settings class, so env vars are read directly, matching db.py.
"""
from __future__ import annotations

import os
import time

import redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
LLM_GLOBAL_RATE_LIMIT_PER_MINUTE = int(os.environ.get("LLM_GLOBAL_RATE_LIMIT_PER_MINUTE", "20"))

_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=1)
    return _client


def check_llm_budget() -> bool:
    """Fixed-window counter, keyed globally. Returns True if this LLM call is
    within the global per-minute budget."""
    try:
        client = _get_client()
        bucket = f"ratelimit:llm:global:{int(time.time()) // 60}"
        count = client.incr(bucket)
        if count == 1:
            client.expire(bucket, 60)
        return count <= LLM_GLOBAL_RATE_LIMIT_PER_MINUTE
    except redis.RedisError:
        return True
