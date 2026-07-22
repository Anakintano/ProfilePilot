"""Startup secrets hygiene check for the worker, duplicated from
services/api/app/secrets_check.py (see db.py's header comment for why small
shared infra is duplicated rather than factored into a shared package). The
worker doesn't touch secret_key/auth_mode -- those are API-only concerns --
so this only needs the GROQ/OPENROUTER placeholder check. Never logs the
actual secret values, only whether they look wrong, referencing the env var
name.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("profilepilot.worker")

_PLACEHOLDER_SUBSTRINGS = ("your-key", "xxx", "changeme")


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _PLACEHOLDER_SUBSTRINGS)


def check_secrets_on_startup() -> None:
    for env_var in ("GROQ_API_KEY", "OPENROUTER_API_KEY"):
        value = os.environ.get(env_var)
        if value and _looks_like_placeholder(value):
            logger.warning("%s looks like a placeholder value, not a real key.", env_var)
