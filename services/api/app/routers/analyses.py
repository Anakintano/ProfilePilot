from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from ..auth import CurrentUser, get_current_user
from ..config import settings
from ..db import get_pool
from ..events import append_event
from ..schemas.analyses import (
    AnalysisCreateRequest,
    AnalysisCreateResponse,
    AnalysisEventOut,
    AnalysisOut,
)
from ..schemas.common import AnalysisReport, Recommendation, ScoreItem
from ..schemas.extraction import ExtractionOut, ExtractionPatchRequest
from ..schemas.common import ExtractedField, BoundingBox

router = APIRouter(prefix="/v1/analyses", tags=["analyses"])

REQUIRED_SECTIONS = ["contact", "experience", "education", "skills"]


def _load_report(conn, analysis_id: UUID) -> AnalysisReport | None:
    run = conn.execute(
        """
        SELECT sr.*, rv.version AS rubric_version
        FROM score_runs sr
        JOIN rubric_versions rv ON rv.id = sr.rubric_version_id
        WHERE sr.analysis_id = %s AND sr.status = 'published'
        ORDER BY sr.published_at DESC LIMIT 1
        """,
        (str(analysis_id),),
    ).fetchone()
    if run is None:
        return None

    items = conn.execute(
        "SELECT * FROM score_items WHERE score_run_id = %s ORDER BY dimension", (run["id"],)
    ).fetchall()
    recs = conn.execute(
        "SELECT * FROM recommendations WHERE score_run_id = %s ORDER BY priority", (run["id"],)
    ).fetchall()

    dimension_scores = [
        ScoreItem(
            dimension=i["dimension"],
            score=i["score"],
            confidence=i["confidence"],
            evidence_refs=i["evidence_refs"],
            reasoning_summary=i["reasoning_summary"],
            improvement_conditions=i["improvement_conditions"],
        )
        for i in items
    ]
    recommendations = [
        Recommendation(
            id=r["id"],
            priority=r["priority"],
            expected_impact=r["expected_impact"],
            effort=r["effort"],
            source_section=r["source_section"],
            original_text=r["original_text"],
            proposed_rewrite=r["proposed_rewrite"],
            research_citations=r["research_citations"],
            audit_status=r["audit_status"],
            audit_notes=r["audit_notes"],
        )
        for r in recs
    ]
    limitations = [
        "Scores are coaching aids based on document evidence, not predictions of recruiter outcomes.",
        "Extraction accuracy depends on document quality; review flagged low-confidence fields.",
    ]
    action_plan = [r.proposed_rewrite for r in sorted(recommendations, key=lambda x: x.priority)[:3]]

    return AnalysisReport(
        analysis_id=analysis_id,
        score_run_id=run["id"],
        rubric_version=run["rubric_version"],
        prompt_version=run["prompt_version"],
        model_versions=run["model_versions"],
        total_score=run["total_score"],
        confidence_band=run["confidence_band"],
        dimension_scores=dimension_scores,
        limitations=limitations,
        recommendations=recommendations,
        action_plan=action_plan,
        published_at=run["published_at"],
    )


@router.post("", response_model=AnalysisCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def create_analysis(
    body: AnalysisCreateRequest,
    user: CurrentUser = Depends(get_current_user),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> AnalysisCreateResponse:
    with get_pool().connection() as conn:
        existing = conn.execute(
            "SELECT id, status FROM analyses WHERE user_id = %s AND idempotency_key = %s",
            (str(user.id), idempotency_key),
        ).fetchone()
        if existing:
            return AnalysisCreateResponse(analysis_id=existing["id"], status=existing["status"])

        running = conn.execute(
            """
            SELECT COUNT(*) AS n FROM jobs j JOIN analyses a ON a.id = j.analysis_id
            WHERE a.user_id = %s AND j.status IN ('pending', 'claimed', 'running')
            """,
            (str(user.id),),
        ).fetchone()
        if running["n"] >= settings.max_running_jobs_per_user:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Only one analysis may run at a time")

        today_count = conn.execute(
            """
            SELECT COUNT(*) AS n FROM analyses
            WHERE user_id = %s AND created_at >= now() - interval '24 hours'
            """,
            (str(user.id),),
        ).fetchone()
        if today_count["n"] >= settings.max_analyses_per_user_per_day:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Daily quota of {settings.max_analyses_per_user_per_day} analyses reached",
            )

        uploads = conn.execute(
            "SELECT id, status FROM uploads WHERE id = ANY(%s::uuid[]) AND user_id = %s",
            ([str(u) for u in body.upload_ids], str(user.id)),
        ).fetchall()
        if len(uploads) != len(body.upload_ids):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "One or more uploads not found")
        if any(u["status"] != "validated" for u in uploads):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "All uploads must be validated first")

        goal = body.goal_profile
        goal_row = conn.execute(
            """
            INSERT INTO goal_profiles (user_id, target_role, seniority, geography, outcome, job_description)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (str(user.id), goal.target_role, goal.seniority, goal.geography, goal.outcome, goal.job_description),
        ).fetchone()

        analysis_id = uuid4()
        conn.execute(
            """
            INSERT INTO analyses (id, user_id, goal_profile_id, idempotency_key, status, current_stage)
            VALUES (%s, %s, %s, %s, 'queued', 'ingest')
            """,
            (str(analysis_id), str(user.id), goal_row["id"], idempotency_key),
        )
        for upload_id in body.upload_ids:
            conn.execute(
                "INSERT INTO analysis_uploads (analysis_id, upload_id) VALUES (%s, %s)",
                (str(analysis_id), str(upload_id)),
            )
        conn.execute(
            "INSERT INTO jobs (analysis_id, job_type, status) VALUES (%s, 'extract', 'pending')",
            (str(analysis_id),),
        )
        append_event(conn, analysis_id, "ingest", "queued", "Analysis queued")
        conn.commit()

    return AnalysisCreateResponse(analysis_id=analysis_id, status="queued")


@router.get("/{analysis_id}", response_model=AnalysisOut)
def get_analysis(analysis_id: UUID, user: CurrentUser = Depends(get_current_user)) -> AnalysisOut:
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT * FROM analyses WHERE id = %s AND user_id = %s", (str(analysis_id), str(user.id))
        ).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
        report = _load_report(conn, analysis_id) if row["status"] == "completed" else None

    return AnalysisOut(
        id=row["id"],
        status=row["status"],
        current_stage=row["current_stage"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        report=report,
    )


@router.get("/{analysis_id}/extraction", response_model=ExtractionOut)
def get_extraction(analysis_id: UUID, user: CurrentUser = Depends(get_current_user)) -> ExtractionOut:
    with get_pool().connection() as conn:
        analysis = conn.execute(
            "SELECT id FROM analyses WHERE id = %s AND user_id = %s", (str(analysis_id), str(user.id))
        ).fetchone()
        if analysis is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
        rows = conn.execute(
            "SELECT * FROM extracted_fields WHERE analysis_id = %s ORDER BY section, field_key",
            (str(analysis_id),),
        ).fetchall()

    fields = [
        ExtractedField(
            id=r["id"],
            upload_id=r["upload_id"],
            section=r["section"],
            field_key=r["field_key"],
            value=r["value"],
            normalized_value=r["normalized_value"],
            source_page=r["source_page"],
            bbox=BoundingBox(**r["bbox"]) if r["bbox"] else None,
            extraction_method=r["extraction_method"],
            confidence=r["confidence"],
            user_corrected=r["user_corrected"],
            corrected_value=r["corrected_value"],
        )
        for r in rows
    ]
    covered = sorted({f.section for f in fields} & set(REQUIRED_SECTIONS))
    missing = sorted(set(REQUIRED_SECTIONS) - set(covered))
    confidences = [f.confidence for f in fields if f.confidence is not None]
    mean_confidence = sum(confidences) / len(confidences) if confidences else None

    return ExtractionOut(
        analysis_id=analysis_id,
        fields=fields,
        required_sections_covered=covered,
        required_sections_missing=missing,
        mean_confidence=mean_confidence,
    )


@router.patch("/{analysis_id}/extraction", status_code=status.HTTP_202_ACCEPTED)
def patch_extraction(
    analysis_id: UUID,
    body: ExtractionPatchRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    with get_pool().connection() as conn:
        analysis = conn.execute(
            "SELECT id, status FROM analyses WHERE id = %s AND user_id = %s",
            (str(analysis_id), str(user.id)),
        ).fetchone()
        if analysis is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
        if analysis["status"] not in ("needs_review", "completed", "failed"):
            raise HTTPException(status.HTTP_409_CONFLICT, "Analysis is still processing; try again shortly")

        for correction in body.corrections:
            result = conn.execute(
                """
                UPDATE extracted_fields SET corrected_value = %s, user_corrected = true, updated_at = now()
                WHERE id = %s AND analysis_id = %s
                """,
                (correction.corrected_value, str(correction.field_id), str(analysis_id)),
            )
            if result.rowcount == 0:
                raise HTTPException(status.HTTP_404_NOT_FOUND, f"Field {correction.field_id} not found")

        conn.execute(
            "UPDATE analyses SET status = 'scoring', current_stage = 'score', updated_at = now() WHERE id = %s",
            (str(analysis_id),),
        )
        conn.execute(
            "INSERT INTO jobs (analysis_id, job_type, status) VALUES (%s, 'score', 'pending')",
            (str(analysis_id),),
        )
        append_event(conn, analysis_id, "score", "scoring", "Corrections saved; re-scoring")
        conn.commit()

    return {"analysis_id": str(analysis_id), "status": "scoring"}


@router.get("/{analysis_id}/events")
async def stream_events(
    analysis_id: UUID,
    request: Request,
    after_seq: int | None = None,
    user: CurrentUser = Depends(get_current_user),
):
    with get_pool().connection() as conn:
        analysis = conn.execute(
            "SELECT id FROM analyses WHERE id = %s AND user_id = %s", (str(analysis_id), str(user.id))
        ).fetchone()
        if analysis is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")

        start_seq = None
        last_event_id = request.headers.get("last-event-id")
        if last_event_id is not None:
            try:
                start_seq = int(last_event_id)
            except ValueError:
                start_seq = None
        if start_seq is None:
            start_seq = after_seq
        if start_seq is None:
            # Fresh connection, no resume info: stream only events from now
            # on. The frontend already fetches current analysis status via
            # getAnalysis() before opening this stream, so replaying full
            # history serves no purpose -- it previously redelivered a stale
            # event (e.g. an old 'needs_review' from a prior extraction
            # pass) after the analysis had already moved past that stage,
            # bouncing the user back to a screen they'd already left.
            current_max = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS max_seq FROM analysis_events WHERE analysis_id = %s",
                (str(analysis_id),),
            ).fetchone()
            start_seq = current_max["max_seq"]

    async def event_source():
        last_seq = start_seq
        idle_polls = 0
        while True:
            if await request.is_disconnected():
                break
            with get_pool().connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM analysis_events WHERE analysis_id = %s AND seq > %s ORDER BY seq",
                    (str(analysis_id), last_seq),
                ).fetchall()
                terminal = conn.execute(
                    "SELECT status FROM analyses WHERE id = %s", (str(analysis_id),)
                ).fetchone()

            if rows:
                idle_polls = 0
                for r in rows:
                    last_seq = r["seq"]
                    payload = AnalysisEventOut(
                        seq=r["seq"], stage=r["stage"], status=r["status"],
                        message=r["message"], created_at=r["created_at"],
                    )
                    yield f"id: {r['seq']}\ndata: {payload.model_dump_json()}\n\n"
                if terminal and terminal["status"] in ("completed", "failed"):
                    break
            else:
                idle_polls += 1
                yield ": keep-alive\n\n"
                if idle_polls > 600:  # ~10 minutes of no progress
                    break
            await asyncio.sleep(1)

    return StreamingResponse(event_source(), media_type="text/event-stream")
