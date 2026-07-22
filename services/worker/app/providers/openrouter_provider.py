"""Real OpenRouter API call (OpenAI-compatible chat completions, JSON mode).
Activated by the router when OPENROUTER_API_KEY is set (see .env.example)."""
from __future__ import annotations

from . import _openai_compatible as oai

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# OpenRouter's free-tier model roster changes over time (their :free slugs
# get deprecated/rotated); verified reachable as of this writing via
# GET https://openrouter.ai/api/v1/models -- swap if it's retired.
OPENROUTER_MODEL = "openai/gpt-oss-20b:free"
# Optional but recommended by OpenRouter for attributing/ranking app traffic.
_EXTRA_HEADERS = {"HTTP-Referer": "https://profilepilot.dev", "X-Title": "ProfilePilot"}


def generate(
    extracted_fields: list[dict], goal_profile: dict, score_items: list[dict], rubric: dict
) -> tuple[list[dict], dict]:
    return oai.run(
        base_url=OPENROUTER_URL,
        api_key_env="OPENROUTER_API_KEY",
        model=OPENROUTER_MODEL,
        extracted_fields=extracted_fields,
        goal_profile=goal_profile,
        score_items=score_items,
        rubric=rubric,
        extra_headers=_EXTRA_HEADERS,
    )
