"""LLM-based section reclassification: engaged only when the deterministic
heuristic (sectionize.py) didn't find one or more required sections after
its pass. Only reclassifies blocks the heuristic tagged 'other' -- it never
overrides a block already confidently assigned to a real section.

Text-only, not vision: extraction has already produced text by this point,
so this is a cheaper call than the spec's vision-LLM layout fallback, and
follows the same rule that fallback was built on -- relabel existing text,
never invent content.

Provider order mirrors recommendation generation (see
app/providers/router.py): Groq -> OpenRouter -> a deterministic
keyword-expansion fallback (broader net than sectionize.py's strict
"short standalone header line" rule) when no key is configured or both
real providers fail. This module is deliberately independent of
app/providers/router.py -- that one is wired tightly to the recommendation
schema/prompt; duplicating the small amount of HTTP/retry plumbing here
keeps both simple rather than forcing a shared abstraction neither fully fits.
"""
from __future__ import annotations

import json
import logging
import os

import httpx
import jsonschema

from ..contracts import load_schema
from ..llm_rate_limit import check_llm_budget

logger = logging.getLogger("profilepilot.worker.extraction.reclassify")

_SCHEMA = load_schema("layout_classification_output.schema.json")
TIMEOUT_SECONDS = 20.0
MAX_CANDIDATE_BLOCKS = 60  # bounds prompt size/cost; excess 'other' blocks are left alone

_PROVIDERS = [
    ("groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1/chat/completions", "llama-3.3-70b-versatile", None),
    (
        "openrouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/chat/completions",
        "meta-llama/llama-3.3-70b-instruct:free",
        {"HTTP-Referer": "https://profilepilot.dev", "X-Title": "ProfilePilot"},
    ),
]

# Broader synonym net than sectionize.py's strict header-line match -- used
# only when no LLM key is configured, as the deterministic path's last
# resort rather than giving up on missing sections entirely.
_FALLBACK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "skills": ("skill", "proficient", "technolog", "competenc", "languages:", "tools:"),
    "experience": ("intern", "engineer", "developer", "analyst", " manager", "responsible for"),
    "education": ("university", "college", "bachelor", "master", "b.s.", "b.e.", "m.s.", "degree"),
    "contact": ("@", "linkedin.com/in/", "github.com/", "mobile", "phone"),
}


def reclassify_missing_sections(blocks: list[dict], missing_sections: list[str]) -> int:
    """Mutates the `section` of blocks currently tagged 'other', in place,
    where a section in missing_sections can be confidently assigned. Returns
    how many blocks were reclassified."""
    candidates = [b for b in blocks if b.get("section") == "other"][:MAX_CANDIDATE_BLOCKS]
    if not candidates:
        return 0

    for name, key_env, url, model, extra_headers in _PROVIDERS:
        if not os.environ.get(key_env):
            continue
        try:
            assignments = _call_llm(key_env, url, model, extra_headers, candidates, missing_sections)
        except Exception as exc:  # noqa: BLE001 - fall through to the next provider/fallback
            logger.warning("Section reclassification via %s failed: %s", name, exc)
            continue
        return _apply(candidates, assignments)

    return _apply_keyword_fallback(candidates, missing_sections)


def _call_llm(key_env, url, model, extra_headers, candidates, missing_sections) -> dict[int, str]:
    if not check_llm_budget():
        raise RuntimeError("LLM global rate limit exceeded")

    api_key = os.environ[key_env]
    regions = [{"region_id": str(i), "text": b["text"][:300]} for i, b in enumerate(candidates)]
    schema_json = json.dumps(_SCHEMA)
    system = (
        "You classify résumé/profile text blocks into sections. You are given blocks the "
        "system could not confidently classify, plus a list of sections known to be missing "
        "so far. For each block, decide whether it clearly belongs to one of the missing "
        "sections; if it's genuinely ambiguous or belongs to none of them, use \"other\". "
        "Never invent or rewrite content -- you are only labeling text that already exists.\n\n"
        f"Missing sections to look for: {', '.join(missing_sections)}\n\n"
        "Respond with JSON only, matching exactly this schema (no prose, no markdown fences):\n"
        f"{schema_json}"
    )
    user = json.dumps({"regions": regions})
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)

    with httpx.Client() as client:
        resp = client.post(
            url,
            headers=headers,
            json={
                "model": model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "response_format": {"type": "json_object"},
                "temperature": 0,
                "max_tokens": 1500,
            },
            timeout=TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

    parsed = json.loads(content)
    jsonschema.validate(parsed, _SCHEMA)

    valid_sections = set(missing_sections)
    assignments: dict[int, str] = {}
    for region in parsed.get("regions", []):
        try:
            idx = int(region["region_id"])
        except (KeyError, ValueError, TypeError):
            continue
        section = region.get("section")
        if section in valid_sections and 0 <= idx < len(candidates):
            assignments[idx] = section
    return assignments


def _apply(candidates: list[dict], assignments: dict[int, str]) -> int:
    for idx, section in assignments.items():
        candidates[idx]["section"] = section
    return len(assignments)


def _apply_keyword_fallback(candidates: list[dict], missing_sections: list[str]) -> int:
    count = 0
    for block in candidates:
        lowered = block["text"].lower()
        for section in missing_sections:
            if any(kw in lowered for kw in _FALLBACK_KEYWORDS.get(section, ())):
                block["section"] = section
                count += 1
                break
    return count
