"""Evidence Auditor (renamed from "Claim Verifier"): checks each generated
recommendation against the candidate's own extracted text. Critically, it
never claims to *prove* an achievement -- it only flags recommendations as
unsupported, vague, or (best-effort) contradictory so a human reviews them
before trusting a rewrite.

Fully deterministic -- no LLM calls -- so it works with the fake_provider
default path with zero network dependency, and it also acts as an
independent safety net against a real LLM provider paraphrasing instead of
quoting verbatim.
"""
from __future__ import annotations

import re

import jsonschema

from ..contracts import load_schema

_AUDIT_SCHEMA = load_schema("evidence_audit_output.schema.json")

_PLACEHOLDER_RE = re.compile(r"\[[^\]]{1,40}\]")
# Heuristic for "asserts something specific as fact": a %, $, or multi-digit
# number in the text. Combined with the placeholder check below, this is how
# we distinguish an honest "add [X]%" template from an unverified "improved
# performance by 40%" claim with no evidence_span behind it.
_SPECIFIC_CLAIM_RE = re.compile(r"\d+%|\$[0-9]|\b\d{2,}\b")
_GENERIC_PHRASES = ("responsible for", "worked on", "helped with", "involved in", "assisted with")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _candidate_text_blob(extracted_fields: list[dict]) -> str:
    parts = []
    for f in extracted_fields:
        value = f.get("corrected_value") if f.get("user_corrected") and f.get("corrected_value") else f.get("value")
        if value:
            parts.append(value)
    return _normalize(" \n ".join(parts))


def _looks_generic(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in _GENERIC_PHRASES)


def _audit_one(rec: dict, candidate_blob: str) -> tuple[str, str]:
    span = (rec.get("evidence_span") or "").strip()
    rewrite = rec.get("proposed_rewrite") or ""
    has_placeholder = bool(_PLACEHOLDER_RE.search(rewrite))

    if span:
        if _normalize(span) in candidate_blob:
            return "supported", "Evidence span was found verbatim in the candidate's extracted text."
        return (
            "unsupported",
            "Evidence span was provided but could not be located verbatim in the candidate's extracted "
            "text (it may have been paraphrased or edited from the original).",
        )

    if has_placeholder:
        return (
            "supported",
            "Net-new suggestion that uses bracketed placeholders for the candidate to fill in, rather "
            "than asserting an unverified fact -- not flagged as unsupported.",
        )

    if _SPECIFIC_CLAIM_RE.search(rewrite):
        return (
            "unsupported",
            "Rewrite asserts a specific number or outcome with no evidence_span and no bracketed "
            "placeholder marking it as a fill-in.",
        )

    if len(rewrite.strip()) < 40 or _looks_generic(rewrite):
        return "vague", "Rewrite is generic boilerplate without concrete, checkable specifics."

    return "vague", "No evidence_span was provided, so this rewrite's specifics could not be verified."


def audit_recommendations(recommendations: list[dict], extracted_fields: list[dict]) -> list[dict]:
    candidate_blob = _candidate_text_blob(extracted_fields)

    audited = []
    audits_for_schema = []
    for idx, rec in enumerate(recommendations):
        rec = dict(rec)
        status, notes = _audit_one(rec, candidate_blob)
        rec["audit_status"] = status
        rec["audit_notes"] = notes
        audited.append(rec)
        audits_for_schema.append({"recommendation_index": idx, "audit_status": status, "notes": notes[:500]})

    # Validate against the LLM-stage contract shape even though this path is
    # deterministic -- keeps the audit output structurally honest and catches
    # a status value that ever drifts out of sync with the schema's enum.
    jsonschema.validate({"audits": audits_for_schema}, _AUDIT_SCHEMA)
    return audited
