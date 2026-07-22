"""Recommendation-provider router.

Picks a real LLM provider based on which API key is configured (GROQ_API_KEY
first, then OPENROUTER_API_KEY), retries transient failures with backoff +
jitter, trips a simple per-provider circuit breaker after repeated failures,
falls back to the next provider in the chain, and always ends with
fake_provider (deterministic, cannot fail) so this function is guaranteed to
return something. Env vars are read directly (no config module dependency --
this package stays self-contained).
"""
from __future__ import annotations

import logging
import os
import random
import time

from . import fake_provider, groq_provider, openrouter_provider, research
from ..llm_rate_limit import check_llm_budget

logger = logging.getLogger("profilepilot.worker.providers")

_MAX_RETRIES = 2
_BASE_BACKOFF_SECONDS = 1.0
_CIRCUIT_FAILURE_THRESHOLD = 3
_CIRCUIT_COOLDOWN_SECONDS = 60.0

# Module-level circuit-breaker state per provider name. A simple in-process
# counter is fine for a single-worker-process beta; it isn't shared across
# processes or persisted across restarts.
_circuit_state: dict[str, dict] = {}


class _ProviderUnavailable(RuntimeError):
    """Raised when a provider's circuit breaker is open; caught the same as
    any other provider failure so the router just moves to the next one."""


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
            recs, meta = call_fn()
            state["failures"] = 0
            meta = dict(meta)
            meta["attempts"] = attempt
            return recs, meta
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


def _configured_providers() -> list[tuple[str, object]]:
    providers = []
    if os.environ.get("GROQ_API_KEY"):
        providers.append(("groq", groq_provider))
    if os.environ.get("OPENROUTER_API_KEY"):
        providers.append(("openrouter", openrouter_provider))
    return providers


def _enrich_with_research(recommendations: list[dict], conn) -> None:
    """Optional enrichment: attach research_citation_ids where a relevant
    research_documents row exists. research_documents is seeded empty in
    this beta, so retrieve_research() returns [] and every rec just gets an
    empty list -- that is expected, not a bug. Never allowed to raise."""
    if conn is None:
        return
    for rec in recommendations:
        if rec.get("research_citation_ids"):
            continue
        try:
            query = f"{rec.get('dimension', '')} {rec.get('proposed_rewrite', '')}"[:500]
            hits = research.retrieve_research(query, top_k=3, conn=conn)
            rec["research_citation_ids"] = [h["id"] for h in hits] if hits else []
        except Exception:  # noqa: BLE001 - research is pure enrichment, never fatal
            logger.warning("Research retrieval enrichment failed", exc_info=True)
            rec.setdefault("research_citation_ids", [])


def generate_recommendations(
    extracted_fields: list[dict],
    goal_profile: dict,
    score_items: list[dict],
    rubric: dict,
    conn=None,
) -> tuple[list[dict], dict]:
    """conn is optional and only used for the research-retrieval enrichment
    step (a live pgvector query needs a connection); every other argument
    matches the documented four-argument contract."""
    providers_tried: list[str] = []

    for name, module in _configured_providers():
        providers_tried.append(name)
        try:
            recs, meta = _call_with_retries(
                name, lambda m=module: m.generate(extracted_fields, goal_profile, score_items, rubric)
            )
        except Exception as exc:  # noqa: BLE001 - fall through to the next provider
            logger.warning("Provider %s failed after retries: %s", name, exc)
            continue

        _enrich_with_research(recs, conn)
        is_primary = len(providers_tried) == 1
        status = "ok" if is_primary and meta.get("attempts", 1) == 1 else ("retried" if is_primary else "fallback")
        usage = {
            "provider": name,
            "model": meta.get("model", ""),
            "prompt_tokens": meta.get("prompt_tokens", 0),
            "completion_tokens": meta.get("completion_tokens", 0),
            "latency_ms": meta.get("latency_ms", 0),
            "status": status,
        }
        return recs, usage

    # All configured real providers failed (or none were configured) --
    # fake_provider is deterministic and cannot fail; it's the guaranteed floor.
    recs, meta = fake_provider.generate(extracted_fields, goal_profile, score_items, rubric)
    _enrich_with_research(recs, conn)
    usage = {
        "provider": "fake",
        "model": meta.get("model", "template-v1"),
        "prompt_tokens": meta.get("prompt_tokens", 0),
        "completion_tokens": meta.get("completion_tokens", 0),
        "latency_ms": meta.get("latency_ms", 0),
        "status": "fallback" if providers_tried else "ok",
    }
    return recs, usage
