"""Real Groq API call (OpenAI-compatible chat completions, JSON mode).
Activated by the router when GROQ_API_KEY is set (see .env.example)."""
from __future__ import annotations

from . import _openai_compatible as oai

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"


def generate(
    extracted_fields: list[dict], goal_profile: dict, score_items: list[dict], rubric: dict
) -> tuple[list[dict], dict]:
    return oai.run(
        base_url=GROQ_URL,
        api_key_env="GROQ_API_KEY",
        model=GROQ_MODEL,
        extracted_fields=extracted_fields,
        goal_profile=goal_profile,
        score_items=score_items,
        rubric=rubric,
    )
