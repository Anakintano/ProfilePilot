"""Scribe provider chain: Groq -> OpenRouter -> deterministic fallback, for
both post writing and comment generation.

Mirrors services/worker/app/providers/router.py's shape (per-provider
retries with backoff+jitter, a simple in-process circuit breaker, the LLM
global budget check) and services/worker/app/providers/_openai_compatible.py's
request/response plumbing (system prompt embeds the JSON Schema inline,
response_format=json_object, one corrective retry on invalid output) --
generalized here to a single system/user prompt pair plus a schema, since
Scribe has two call shapes (post, comment) rather than one hardcoded prompt.

Lives in services/api rather than services/worker per this codebase's
established convention of duplicating small provider-calling infra instead
of sharing a package (see services/worker/app/providers/router.py's own
docstring, and llm_rate_limit.py which is duplicated the same way) -- Scribe
is a single short call with no multi-stage pipeline, so it doesn't need the
worker's crash-resumable job-queue durability.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time

import httpx
import jsonschema

from ..contracts import load_schema
from ..llm_rate_limit import check_llm_budget
from . import fallback

logger = logging.getLogger("profilepilot.api.scribe")

TIMEOUT_SECONDS = 20.0
_MAX_RETRIES = 2
_BASE_BACKOFF_SECONDS = 1.0
_CIRCUIT_FAILURE_THRESHOLD = 3
_CIRCUIT_COOLDOWN_SECONDS = 60.0

_POST_SCHEMA = load_schema("scribe_post_output.schema.json")
_COMMENT_SCHEMA = load_schema("scribe_comment_output.schema.json")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# See services/worker/app/providers/openrouter_provider.py -- OpenRouter's
# free-tier model roster changes over time, swap if this slug is retired.
OPENROUTER_MODEL = "openai/gpt-oss-20b:free"
_OPENROUTER_EXTRA_HEADERS = {"HTTP-Referer": "https://profilepilot.dev", "X-Title": "ProfilePilot"}

# Module-level circuit-breaker state per provider name -- same simple
# in-process-only posture as the worker's router.py (fine for a single beta
# process, not shared across processes or restarts).
_circuit_state: dict[str, dict] = {}

STYLE_GUIDANCE = {
    "professional": "Formal, concise, workplace-appropriate tone. No slang or emoji overload.",
    "storytelling": "Narrative arc with a hook, a turning point, and a takeaway. First person.",
    "thought_leadership": "Confident point of view on an industry trend or practice, backed by reasoning.",
    "casual": "Conversational, friendly tone, contractions welcome, light and sparing emoji ok.",
    "data_driven": "Lead with a number, trend, or stat; structure the rest around evidence.",
    "listicle": "Numbered list format (3-5 short points) with a one-line intro.",
}

COMMENT_GUIDANCE = {
    "engaging": "Add value and spark further discussion; end with a light, specific follow-up thought.",
    "supportive": "Warm and encouraging; affirm the poster's point without being generic.",
    "insightful": "Add a non-obvious angle, a related fact, or a nuance the post didn't cover.",
    "question": "Primarily a genuine, specific question about something the post actually said.",
    "congratulatory": "Celebrate an achievement or milestone mentioned in the post.",
}


class ProviderCallError(RuntimeError):
    """A provider call failed outright (missing key, HTTP error) or its
    structured output was still invalid after the one corrective retry."""


class _ProviderUnavailable(RuntimeError):
    """Raised when a provider's circuit breaker is open; caught the same as
    any other provider failure so the chain just moves to the next one."""


def _build_post_prompt(style: str, topic: str, rough_sketch: str | None, search_results: list[dict]) -> tuple[str, str]:
    schema_json = json.dumps(_POST_SCHEMA)
    system = (
        "You are the Scribe post-writing stage of ProfilePilot, generating a LinkedIn post draft "
        "for a job-seeking candidate.\n\n"
        "STRICT RULES:\n"
        "1. Never fabricate specific facts, statistics, employers, or personal achievements that "
        "were not provided in the topic or rough sketch below.\n"
        "2. If background context from a web search is provided, use it only as general grounding "
        "or inspiration -- never present it as the user's own personal claim, and never invent "
        "specifics beyond what that context actually says.\n"
        "3. Respond with JSON only, matching exactly this JSON Schema (no extra keys, no prose, "
        "no markdown fences):\n"
        f"{schema_json}\n\n"
        f"Style: {style} -- {STYLE_GUIDANCE.get(style, '')}\n"
    )
    user_parts = [f"Topic: {topic}"]
    if rough_sketch:
        user_parts.append(f"User's rough sketch/draft to build from and improve:\n{rough_sketch}")
    if search_results:
        context = "\n".join(f"- {r['title']}: {r['snippet']}" for r in search_results if r.get("snippet"))
        if context:
            user_parts.append(
                f"Background context from a web search (grounding only, do not copy verbatim or "
                f"present as the user's own claim):\n{context}"
            )
    return system, "\n\n".join(user_parts)


def _build_comment_prompt(post_content: str, comment_type: str) -> tuple[str, str]:
    schema_json = json.dumps(_COMMENT_SCHEMA)
    system = (
        "You are the Scribe comment-generation stage of ProfilePilot, drafting a LinkedIn comment "
        "reply on behalf of a job-seeking candidate.\n\n"
        "STRICT RULES:\n"
        "1. Base the comment only on the post text given below -- never invent facts about the "
        "poster or claim shared experience that isn't implied by the post.\n"
        "2. Keep it a genuine comment length (roughly 1-3 sentences), not another full post.\n"
        "3. Respond with JSON only, matching exactly this JSON Schema (no extra keys, no prose, "
        "no markdown fences):\n"
        f"{schema_json}\n\n"
        f"Comment type: {comment_type} -- {COMMENT_GUIDANCE.get(comment_type, '')}\n"
    )
    user = f"Post content:\n{post_content}"
    return system, user


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
            "temperature": 0.6,
            "max_tokens": 1200,
        },
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


def _call_llm(
    *,
    base_url: str,
    api_key_env: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema: dict,
    extra_headers: dict | None = None,
) -> tuple[dict, dict]:
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise ProviderCallError(f"{api_key_env} is not set")

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    start = time.monotonic()
    with httpx.Client() as client:
        data = _post(client, base_url, api_key, model, messages, extra_headers)
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {}) or {}

        try:
            parsed = json.loads(content)
            jsonschema.validate(parsed, schema)
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
                jsonschema.validate(parsed, schema)
            except (json.JSONDecodeError, jsonschema.ValidationError) as exc2:
                raise ProviderCallError(f"Invalid structured output after corrective retry: {exc2}") from exc2

    latency_ms = int((time.monotonic() - start) * 1000)
    meta = {
        "model": model,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "latency_ms": latency_ms,
    }
    return parsed, meta


def _groq_call(system_prompt: str, user_prompt: str, schema: dict) -> tuple[dict, dict]:
    return _call_llm(
        base_url=GROQ_URL, api_key_env="GROQ_API_KEY", model=GROQ_MODEL,
        system_prompt=system_prompt, user_prompt=user_prompt, schema=schema,
    )


def _openrouter_call(system_prompt: str, user_prompt: str, schema: dict) -> tuple[dict, dict]:
    return _call_llm(
        base_url=OPENROUTER_URL, api_key_env="OPENROUTER_API_KEY", model=OPENROUTER_MODEL,
        system_prompt=system_prompt, user_prompt=user_prompt, schema=schema,
        extra_headers=_OPENROUTER_EXTRA_HEADERS,
    )


def _configured_providers() -> list[tuple[str, object]]:
    providers = []
    if os.environ.get("GROQ_API_KEY"):
        providers.append(("groq", _groq_call))
    if os.environ.get("OPENROUTER_API_KEY"):
        providers.append(("openrouter", _openrouter_call))
    return providers


def _call_with_retries(name: str, call_fn):
    state = _circuit_state.setdefault(name, {"failures": 0, "skip_until": 0.0})
    now = time.monotonic()
    if now < state["skip_until"]:
        raise _ProviderUnavailable(f"{name} circuit breaker open, skipping")

    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 2):  # 1 initial try + _MAX_RETRIES retries
        try:
            if not check_llm_budget():
                raise RuntimeError("LLM global rate limit exceeded")
            parsed, meta = call_fn()
            state["failures"] = 0
            meta = dict(meta)
            meta["attempts"] = attempt
            return parsed, meta
        except Exception as exc:  # noqa: BLE001 - any failure here triggers retry/fallback
            last_exc = exc
            if attempt == _MAX_RETRIES + 1:
                break
            delay = _BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
            delay += random.uniform(0, delay * 0.5)
            time.sleep(delay)

    state["failures"] += 1
    if state["failures"] >= _CIRCUIT_FAILURE_THRESHOLD:
        state["skip_until"] = time.monotonic() + _CIRCUIT_COOLDOWN_SECONDS
        state["failures"] = 0
    raise last_exc


def _usage_meta(provider_name: str, meta: dict, status: str) -> dict:
    return {
        "provider": provider_name,
        "model": meta.get("model", "template-v1"),
        "prompt_tokens": meta.get("prompt_tokens", 0),
        "completion_tokens": meta.get("completion_tokens", 0),
        "latency_ms": meta.get("latency_ms", 0),
        "status": status,
    }


def _run_chain(system_prompt: str, user_prompt: str, schema: dict, fallback_fn) -> tuple[dict, dict]:
    providers_tried: list[str] = []

    for name, call_fn in _configured_providers():
        providers_tried.append(name)
        try:
            parsed, meta = _call_with_retries(name, lambda c=call_fn: c(system_prompt, user_prompt, schema))
        except Exception as exc:  # noqa: BLE001 - fall through to the next provider
            logger.warning("Scribe provider %s failed after retries: %s", name, exc)
            continue

        is_primary = len(providers_tried) == 1
        status = "ok" if is_primary and meta.get("attempts", 1) == 1 else ("retried" if is_primary else "fallback")
        return parsed, _usage_meta(name, meta, status)

    # All configured real providers failed (or none were configured) --
    # fallback.py is deterministic and cannot fail; it's the guaranteed floor.
    parsed, meta = fallback_fn()
    return parsed, _usage_meta("fake", meta, "fallback" if providers_tried else "ok")


def generate_post(
    *, style: str, topic: str, rough_sketch: str | None, search_results: list[dict]
) -> tuple[dict, dict]:
    system, user = _build_post_prompt(style, topic, rough_sketch, search_results)
    return _run_chain(
        system, user, _POST_SCHEMA, lambda: fallback.generate_post(style, topic, rough_sketch)
    )


def generate_comment(*, post_content: str, comment_type: str) -> tuple[dict, dict]:
    system, user = _build_comment_prompt(post_content, comment_type)
    return _run_chain(
        system, user, _COMMENT_SCHEMA, lambda: fallback.generate_comment(post_content, comment_type)
    )
