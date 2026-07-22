"""Startup secrets hygiene check -- a loud log, not a hard failure (this is a
beta/dev tool). Never logs the actual secret values, only whether they look
wrong, referencing the env var name.
"""
from __future__ import annotations

import logging
import os

from .config import settings

logger = logging.getLogger("profilepilot.api")

_PLACEHOLDER_SUBSTRINGS = ("your-key", "xxx", "changeme")


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _PLACEHOLDER_SUBSTRINGS)


def check_secrets_on_startup() -> None:
    if settings.secret_key == "dev-only-insecure-secret-change-in-production" and settings.auth_mode != "dev":
        logger.critical(
            "SECRET_KEY is still the insecure default while AUTH_MODE is not 'dev' -- "
            "set a real SECRET_KEY before this handles real user sessions."
        )

    for env_var in ("GROQ_API_KEY", "OPENROUTER_API_KEY"):
        value = os.environ.get(env_var)
        if value and _looks_like_placeholder(value):
            logger.warning("%s looks like a placeholder value, not a real key.", env_var)
