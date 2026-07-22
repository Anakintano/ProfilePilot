"""Publishes a scoring pipeline's results as one immutable score_run.

Computes total_score/confidence_band, retires any stale draft score_runs for
this analysis (cleanup from a prior failed attempt -- published runs are
immutable and must never be touched), then inserts the new score_run,
score_items, and recommendations rows. Does not commit/rollback -- runs
inside the caller's single job-attempt transaction (see app/main.py).
"""
from __future__ import annotations

from uuid import UUID

from psycopg.types.json import Jsonb

_IMPACT_RANK = {"high": 0, "medium": 1, "low": 2}
_EFFORT_RANK = {"low": 0, "medium": 1, "high": 2}


def compute_total_score(score_items: list[dict], weights: dict) -> float:
    """Weighted sum of score_items using the rubric's dimension->weight map,
    normalized by the weight actually applied (defensive: rubric v1's
    weights sum to 1.0 exactly, but this degrades gracefully if a future
    rubric's weights don't, or a dimension is missing a weight entry)."""
    total = 0.0
    weight_sum = 0.0
    for item in score_items:
        w = weights.get(item["dimension"])
        if w is None:
            continue
        total += item["score"] * w
        weight_sum += w
    if weight_sum <= 0:
        return 0.0
    return round(total / weight_sum, 1)


def _confidence_band(score_items: list[dict]) -> str:
    if not score_items:
        return "low"
    mean_conf = sum(i["confidence"] for i in score_items) / len(score_items)
    if mean_conf >= 0.75:
        return "high"
    if mean_conf >= 0.5:
        return "medium"
    return "low"


def _rank_recommendations(recommendations: list[dict]) -> list[dict]:
    """priority = rank by expected_impact desc, then effort asc (quick wins
    -- high impact, low effort -- surface first)."""
    return sorted(
        recommendations,
        key=lambda r: (
            _IMPACT_RANK.get(r.get("expected_impact", "low"), 2),
            _EFFORT_RANK.get(r.get("effort", "high"), 2),
        ),
    )


def assemble_and_publish(
    conn,
    analysis_id: UUID,
    rubric_row: dict,
    score_items: list[dict],
    recommendations: list[dict],
    model_versions: dict,
) -> UUID:
    weights = rubric_row["weights"]
    total_score = compute_total_score(score_items, weights)
    confidence_band = _confidence_band(score_items)

    conn.execute("DELETE FROM score_runs WHERE analysis_id = %s AND status = 'draft'", (str(analysis_id),))

    run = conn.execute(
        """
        INSERT INTO score_runs (analysis_id, rubric_version_id, prompt_version, model_versions,
                                 total_score, confidence_band, status, published_at)
        VALUES (%s, %s, %s, %s, %s, %s, 'published', now())
        RETURNING id
        """,
        (
            str(analysis_id), rubric_row["id"], "rec-v1", Jsonb(model_versions or {}),
            total_score, confidence_band,
        ),
    ).fetchone()
    score_run_id = run["id"]

    for item in score_items:
        conn.execute(
            """
            INSERT INTO score_items (score_run_id, dimension, score, confidence, evidence_refs,
                                      reasoning_summary, improvement_conditions)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                score_run_id, item["dimension"], item["score"], item["confidence"],
                Jsonb(item.get("evidence_refs", [])), item["reasoning_summary"],
                Jsonb(item.get("improvement_conditions", [])),
            ),
        )

    for priority, rec in enumerate(_rank_recommendations(recommendations), start=1):
        evidence_span = (rec.get("evidence_span") or "").strip()
        conn.execute(
            """
            INSERT INTO recommendations (score_run_id, priority, expected_impact, effort, source_section,
                                          original_text, proposed_rewrite, research_citations,
                                          audit_status, audit_notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                score_run_id, priority, rec.get("expected_impact", "medium"), rec.get("effort", "medium"),
                rec.get("source_section", ""), evidence_span or None, rec["proposed_rewrite"],
                Jsonb(rec.get("research_citation_ids", [])), rec.get("audit_status", "not_audited"),
                rec.get("audit_notes"),
            ),
        )

    return score_run_id
