"""Shared request/response plumbing for OpenAI-chat-completions-compatible
providers (Groq, OpenRouter). Both speak the identical JSON-mode chat
completions API; only the base URL, API key env var, and model differ, so
that part is factored out here instead of duplicated in groq_provider.py and
openrouter_provider.py. Not a public provider itself -- groq_provider.py /
openrouter_provider.py are the ones the router imports.
"""
from __future__ import annotations

import json
import os
import time

import httpx
import jsonschema

from ..contracts import load_schema

TIMEOUT_SECONDS = 20.0
_SCHEMA = load_schema("recommendation_output.schema.json")


class ProviderCallError(RuntimeError):
    """Raised for a provider call that fails outright (missing key) or whose
    structured output is still invalid after the one corrective retry. The
    router catches this (and any other exception, e.g. network/timeout
    errors from httpx) to decide on retry/fallback."""


def _resolve(field: dict) -> str:
    if field.get("user_corrected") and field.get("corrected_value"):
        return field["corrected_value"]
    return field.get("value") or ""


def _build_system_prompt(rubric: dict) -> str:
    dims = (rubric or {}).get("dimensions", [])
    dim_lines = "\n".join(f"- {d['key']}: {d['label']} -- {d['description']}" for d in dims)
    schema_json = json.dumps(_SCHEMA)
    return (
        "You are the recommendation-generation stage of ProfilePilot, a resume/profile "
        "coaching tool for intern-to-junior candidates. You are given the candidate's "
        "extracted profile text, their goal profile, and current rubric dimension scores. "
        "Generate 3-6 recommendations targeting the lowest-scoring dimensions.\n\n"
        "STRICT RULES:\n"
        "1. Every non-empty 'evidence_span' MUST be a verbatim quote copied exactly from the "
        "candidate's own extracted text below. Never invent, embellish, or assume achievements, "
        "employers, titles, or numbers not present in the source text.\n"
        "2. If a suggestion cannot be grounded in existing text, set evidence_span to an empty "
        "string and phrase the rewrite as a clearly net-new addition, not a rewrite of something "
        "that already exists.\n"
        "3. If you propose a quantified metric the candidate hasn't provided, use bracketed "
        "placeholders like [X] or [Y%] and say so in the rationale -- never present a fabricated "
        "specific number as if it were real.\n"
        "4. Respond with JSON only, matching exactly this JSON Schema (no extra keys, no prose, "
        "no markdown fences):\n"
        f"{schema_json}\n\n"
        f"Rubric dimensions:\n{dim_lines}\n"
    )


def _build_user_prompt(extracted_fields: list[dict], goal_profile: dict, score_items: list[dict]) -> str:
    profile_lines = [
        f"[{f.get('section')}/{f.get('field_key')}] {_resolve(f)}"
        for f in extracted_fields
        if _resolve(f).strip()
    ]
    score_lines = [
        f"- {s['dimension']}: {s['score']}/100 (confidence {s['confidence']}) -- {s['reasoning_summary']}"
        for s in sorted(score_items or [], key=lambda s: s["score"])
    ]
    goal_profile = goal_profile or {}
    return (
        f"Target role: {goal_profile.get('target_role')}\n"
        f"Seniority: {goal_profile.get('seniority')}\n"
        f"Geography: {goal_profile.get('geography')}\n"
        f"Outcome sought: {goal_profile.get('outcome')}\n"
        f"Job description: {goal_profile.get('job_description') or '(none provided)'}\n\n"
        "Current dimension scores (lowest first):\n" + "\n".join(score_lines) + "\n\n"
        "Candidate's extracted profile fields:\n" + "\n".join(profile_lines)
    )


def _post(client: httpx.Client, url: str, api_key: str, model: str, messages: list[dict], extra_headers):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    resp = client.post(
        url,
        headers=headers,
        json={
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.4,
            "max_tokens": 2000,
        },
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


def run(
    *,
    base_url: str,
    api_key_env: str,
    model: str,
    extracted_fields: list[dict],
    goal_profile: dict,
    score_items: list[dict],
    rubric: dict,
    extra_headers: dict | None = None,
) -> tuple[list[dict], dict]:
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise ProviderCallError(f"{api_key_env} is not set")

    messages = [
        {"role": "system", "content": _build_system_prompt(rubric)},
        {"role": "user", "content": _build_user_prompt(extracted_fields, goal_profile, score_items)},
    ]

    start = time.monotonic()
    with httpx.Client() as client:
        data = _post(client, base_url, api_key, model, messages, extra_headers)
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {}) or {}

        try:
            parsed = json.loads(content)
            jsonschema.validate(parsed, _SCHEMA)
        except (json.JSONDecodeError, jsonschema.ValidationError) as exc:
            # One corrective retry: show the model its own bad output and ask it to fix it.
            messages.append({"role": "assistant", "content": content})
            messages.append({
                "role": "user",
                "content": (
                    f"Your previous response was invalid: {exc}. Respond again with ONLY corrected "
                    "JSON matching the required schema -- no prose, no markdown fences."
                ),
            })
            data = _post(client, base_url, api_key, model, messages, extra_headers)
            content = data["choices"][0]["message"]["content"]
            usage2 = data.get("usage", {}) or {}
            usage = {
                "prompt_tokens": usage.get("prompt_tokens", 0) + usage2.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0) + usage2.get("completion_tokens", 0),
            }
            try:
                parsed = json.loads(content)
                jsonschema.validate(parsed, _SCHEMA)
            except (json.JSONDecodeError, jsonschema.ValidationError) as exc2:
                raise ProviderCallError(f"Invalid structured output after corrective retry: {exc2}") from exc2

    latency_ms = int((time.monotonic() - start) * 1000)
    meta = {
        "model": model,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "latency_ms": latency_ms,
    }
    return parsed["recommendations"], meta
