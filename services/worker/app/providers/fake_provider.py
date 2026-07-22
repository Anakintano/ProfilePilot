"""Deterministic, template-based recommendation generator.

This is the DEFAULT provider in the local-first beta (no API keys
configured) and the guaranteed-to-succeed final fallback otherwise -- no
network calls, cannot fail for reasons outside our own code. Recommendations
are grounded in the candidate's own extracted_fields: every non-empty
evidence_span is a verbatim quote, and any invented metric is wrapped in
bracketed placeholders ([X], [Y%]) with a rationale telling the user to
replace them with real numbers -- this is honest, not fabricating a false
claim, since the brackets clearly mark placeholders.
"""
from __future__ import annotations

import re
import time

import jsonschema

from ..contracts import load_schema
from ..rubric.engine import (
    DEFAULT_MAX_BULLET_LENGTH,
    DEFAULT_MIN_EXPERIENCE_ENTRIES,
    DEFAULT_REQUIRED_SECTIONS,
    DEFAULT_SIGNAL_REGEX,
    collect_bullets,
    count_experience_entries,
    find_keyword_gap,
    find_role_term_gap,
    group_by_section,
)

_SCHEMA = load_schema("recommendation_output.schema.json")
MAX_RECS = 6  # target range is 3-6; see the note in generate() below.


def _field_ref(section: str, key: str) -> str:
    """"section.field_key", without double-prefixing when field_key already
    starts with the section name (e.g. "experience.0.bullets")."""
    if not key:
        return section
    return key if key == section or key.startswith(f"{section}.") else f"{section}.{key}"


def _tighten(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    cut = text[: max_len - 1]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(",;:.- ") + "."


def _gen_impact_quantification(by_section: dict, req: dict, max_n: int = 2) -> list[dict]:
    pattern = re.compile(req.get("signal_regex", DEFAULT_SIGNAL_REGEX))
    bullets = collect_bullets(by_section)
    unquantified = [(k, t) for k, t in bullets if not pattern.search(t)]

    if not bullets:
        return [{
            "dimension": "impact_quantification",
            "expected_impact": "high",
            "effort": "medium",
            "source_section": "experience",
            "evidence_span": "",
            "proposed_rewrite": (
                "Add 1-2 experience or project bullets describing a concrete, measurable outcome, "
                "such as \"Reduced [metric] by [X]% by [specific action you took].\""
            ),
            "rationale": (
                "No experience or project bullets were found. Quantified impact is the strongest "
                "signal recruiters scan for -- fill in the bracketed placeholders with your real numbers."
            ),
        }]

    recs = []
    for key, text in unquantified[:max_n]:
        rewrite = f"{text.rstrip('.')}, impacting ~[X] users/records and improving [metric] by [Y]%."
        recs.append({
            "dimension": "impact_quantification",
            "expected_impact": "high",
            "effort": "low",
            "source_section": _field_ref("experience", key),
            "evidence_span": text,
            "proposed_rewrite": rewrite,
            "rationale": (
                "This bullet describes a task but no measurable outcome. Replace [X], [metric], and [Y] "
                "with your real numbers -- never leave placeholders in a resume you actually submit."
            ),
        })
    return recs


def _gen_clarity_structure(by_section: dict, req: dict, max_n: int = 2) -> list[dict]:
    required_sections = req.get("required_sections", DEFAULT_REQUIRED_SECTIONS)
    max_len = req.get("max_bullet_length_chars", DEFAULT_MAX_BULLET_LENGTH)
    missing = [s for s in required_sections if not by_section.get(s)]

    recs = []
    for section in missing[:max_n]:
        recs.append({
            "dimension": "clarity_structure",
            "expected_impact": "medium",
            "effort": "low",
            "source_section": section,
            "evidence_span": "",
            "proposed_rewrite": f"Add a clearly labeled '{section.title()}' section so the profile is easy to scan.",
            "rationale": f"No '{section}' section was detected; recruiters and ATS parsers expect one.",
        })

    if len(recs) < max_n:
        bullets = collect_bullets(by_section)
        long_bullets = [(k, t) for k, t in bullets if len(t) > max_len]
        for key, text in long_bullets[: max_n - len(recs)]:
            recs.append({
                "dimension": "clarity_structure",
                "expected_impact": "low",
                "effort": "low",
                "source_section": _field_ref("experience", key),
                "evidence_span": text,
                "proposed_rewrite": _tighten(text, max_len),
                "rationale": (
                    f"This bullet is {len(text)} characters, above the {max_len}-character guideline; "
                    "long bullets are harder to scan quickly."
                ),
            })
    return recs


def _gen_completeness(by_section: dict, req: dict, max_n: int = 2) -> list[dict]:
    required_sections = req.get("required_sections", DEFAULT_REQUIRED_SECTIONS)
    min_entries = req.get("min_experience_entries", DEFAULT_MIN_EXPERIENCE_ENTRIES)
    missing = [s for s in required_sections if not by_section.get(s)]

    recs = []
    for section in missing[:max_n]:
        recs.append({
            "dimension": "completeness",
            "expected_impact": "medium",
            "effort": "medium",
            "source_section": section,
            "evidence_span": "",
            "proposed_rewrite": (
                f"Add a '{section.title()}' section with the relevant details -- it's required for a complete profile."
            ),
            "rationale": f"The '{section}' section is missing entirely, which caps how complete your profile can be.",
        })

    if len(recs) < max_n:
        entry_count = count_experience_entries(by_section)
        if entry_count < min_entries:
            recs.append({
                "dimension": "completeness",
                "expected_impact": "medium",
                "effort": "high",
                "source_section": "experience",
                "evidence_span": "",
                "proposed_rewrite": (
                    "Add another experience, internship, or substantial project entry with 2-3 bullet points "
                    "describing your contributions."
                ),
                "rationale": (
                    f"Only {entry_count} experience entr{'y' if entry_count == 1 else 'ies'} were found; "
                    f"the rubric expects at least {min_entries}."
                ),
            })
    return recs


def _gen_keyword_rec(dimension_key: str, by_section: dict, goal_profile: dict) -> list[dict]:
    if dimension_key == "keyword_alignment":
        source, _all, missing = find_keyword_gap(by_section, goal_profile)
    else:
        source, _all, missing = find_role_term_gap(by_section, goal_profile)
    missing = missing[:5]
    if not missing:
        return []

    skills_fields = by_section.get("skills", [])
    if skills_fields:
        field = skills_fields[0]
        evidence_span = field["_resolved_value"]
        proposed_rewrite = f"{evidence_span.rstrip(', ')}, {', '.join(missing[:3])}"
        source_section = _field_ref("skills", field.get("field_key", ""))
    else:
        evidence_span = ""
        proposed_rewrite = (
            f"Add a Skills section listing your genuine proficiencies, prioritizing any of: "
            f"{', '.join(missing[:3])} that truly apply."
        )
        source_section = "skills"

    return [{
        "dimension": dimension_key,
        "expected_impact": "medium",
        "effort": "low",
        "source_section": source_section,
        "evidence_span": evidence_span,
        "proposed_rewrite": proposed_rewrite,
        "rationale": (
            f"These terms come from {source} and don't currently appear in your profile. "
            "Only add ones that are genuinely true of your experience -- never list a skill you don't have."
        ),
    }]


_DIMENSION_GENERATORS = {
    "impact_quantification": lambda by_section, goal_profile, req: _gen_impact_quantification(by_section, req),
    "clarity_structure": lambda by_section, goal_profile, req: _gen_clarity_structure(by_section, req),
    "completeness": lambda by_section, goal_profile, req: _gen_completeness(by_section, req),
    "relevance_to_role": lambda by_section, goal_profile, req: _gen_keyword_rec("relevance_to_role", by_section, goal_profile),
    "keyword_alignment": lambda by_section, goal_profile, req: _gen_keyword_rec("keyword_alignment", by_section, goal_profile),
}


def generate(
    extracted_fields: list[dict], goal_profile: dict, score_items: list[dict], rubric: dict
) -> tuple[list[dict], dict]:
    start = time.monotonic()
    by_section = group_by_section(extracted_fields)
    evidence_requirements = (rubric or {}).get("evidence_requirements", {}) or {}
    goal_profile = goal_profile or {}

    ordered = sorted(score_items or [], key=lambda item: item["score"])
    recommendations: list[dict] = []
    for item in ordered:
        if len(recommendations) >= MAX_RECS:
            break
        key = item["dimension"]
        generator = _DIMENSION_GENERATORS.get(key)
        if generator is None:
            continue
        req = evidence_requirements.get(key, {}) or {}
        for rec in generator(by_section, goal_profile, req):
            if len(recommendations) >= MAX_RECS:
                break
            recommendations.append(rec)

    # Known edge case: if every dimension already scores well there may
    # genuinely be nothing left to recommend (fewer than the usual 3-6) --
    # that's correct behavior, not a bug. We never fabricate filler recs.
    output = {"recommendations": recommendations}
    jsonschema.validate(output, _SCHEMA)

    latency_ms = int((time.monotonic() - start) * 1000)
    meta = {"model": "template-v1", "prompt_tokens": 0, "completion_tokens": 0, "latency_ms": latency_ms}
    return recommendations, meta
