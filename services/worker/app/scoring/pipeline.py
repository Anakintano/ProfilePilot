"""Scoring-stage orchestrator, invoked by app.main for job_type='score'.

Runs inside the single Postgres transaction main.py owns for the job attempt
(see app/main.py _run_pipeline): must not commit/rollback and must not touch
jobs/analyses -- that state machine belongs to main.py alone. Raises a plain
Exception on unrecoverable failure so main.py's retry/dead-letter logic
takes over.
"""
from __future__ import annotations

from uuid import UUID

from ..events import append_event
from ..providers import router
from ..report import assemble
from ..rubric import engine
from . import audit


def _resolve_field(row: dict) -> dict:
    value = row["corrected_value"] if row["user_corrected"] and row["corrected_value"] else row["value"]
    return {**row, "value": value}


def run_scoring(conn, analysis_id: UUID) -> None:
    append_event(conn, analysis_id, "score", "running", "Scoring profile against rubric v1")

    rows = conn.execute(
        "SELECT * FROM extracted_fields WHERE analysis_id = %s", (str(analysis_id),)
    ).fetchall()
    extracted_fields = [_resolve_field(row) for row in rows]

    analysis = conn.execute(
        "SELECT goal_profile_id FROM analyses WHERE id = %s", (str(analysis_id),)
    ).fetchone()
    if analysis is None:
        raise Exception(f"Analysis {analysis_id} not found")

    goal_profile = conn.execute(
        "SELECT * FROM goal_profiles WHERE id = %s", (analysis["goal_profile_id"],)
    ).fetchone()
    if goal_profile is None:
        raise Exception(f"Goal profile for analysis {analysis_id} not found")

    rubric_row = conn.execute("SELECT * FROM rubric_versions WHERE version = 'v1'").fetchone()
    if rubric_row is None:
        raise Exception("Rubric version v1 not found; has 0002_seed_rubric_v1.sql been applied?")

    score_items = engine.compute_scores(extracted_fields, goal_profile, rubric_row)
    append_event(conn, analysis_id, "score", "running", f"Computed scores for {len(score_items)} dimensions")

    append_event(conn, analysis_id, "recommend", "running", "Generating recommendations")
    recommendations, usage = router.generate_recommendations(
        extracted_fields, goal_profile, score_items, rubric_row, conn=conn
    )

    try:
        # SAVEPOINT via conn.transaction(): this insert is best-effort
        # logging. A bare conn.execute() failure here (without a savepoint)
        # would poison the whole job-attempt transaction for every statement
        # that follows, including the score_items/recommendations inserts in
        # assemble.assemble_and_publish -- so a logging hiccup must not be
        # allowed to take those down with it.
        with conn.transaction():
            conn.execute(
                """
                INSERT INTO model_usage (analysis_id, provider, model, stage, prompt_tokens,
                                          completion_tokens, latency_ms, status)
                VALUES (%s, %s, %s, 'recommend', %s, %s, %s, %s)
                """,
                (
                    str(analysis_id), usage.get("provider", "fake"), usage.get("model", ""),
                    usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                    usage.get("latency_ms", 0), usage.get("status", "ok"),
                ),
            )
    except Exception:  # noqa: BLE001 - logging model usage must never fail the pipeline
        pass

    append_event(conn, analysis_id, "audit", "running", "Auditing recommendations for evidence support")
    recommendations = audit.audit_recommendations(recommendations, extracted_fields)

    model_versions = {
        "rubric": "v1",
        "recommend_provider": usage.get("provider", "fake"),
        "recommend_model": usage.get("model", ""),
    }
    score_run_id = assemble.assemble_and_publish(
        conn, analysis_id, rubric_row, score_items, recommendations, model_versions
    )

    total_score = assemble.compute_total_score(score_items, rubric_row["weights"])
    append_event(
        conn, analysis_id, "publish", "running",
        f"Published report {score_run_id}, total score {total_score:.0f}/100",
    )
