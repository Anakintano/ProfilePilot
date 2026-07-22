"""Global (not per-user) budget on real LLM provider calls (Groq/OpenRouter),
separate from the per-IP/per-account request throttle in rate_limit.py.
Reuses the same Redis fixed-window counter, just keyed globally rather than
per-user -- same fail-open posture if Redis is unreachable (see rate_limit.py).
"""
from __future__ import annotations

from .config import settings
from .rate_limit import check_and_consume


def check_llm_budget() -> bool:
    """Returns True if this LLM call is within the global per-minute budget."""
    return check_and_consume("llm:global", max_requests=settings.llm_global_rate_limit_per_minute, window_seconds=60)
