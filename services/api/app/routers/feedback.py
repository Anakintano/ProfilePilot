from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import CurrentUser, get_current_user
from ..db import get_pool
from ..schemas.feedback import FeedbackCreateRequest, FeedbackOut

router = APIRouter(prefix="/v1/analyses", tags=["feedback"])


@router.post("/{analysis_id}/feedback", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
def create_feedback(
    analysis_id: str,
    body: FeedbackCreateRequest,
    user: CurrentUser = Depends(get_current_user),
) -> FeedbackOut:
    if str(body.analysis_id) != analysis_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "analysis_id mismatch between path and body")

    with get_pool().connection() as conn:
        owned = conn.execute(
            "SELECT id FROM analyses WHERE id = %s AND user_id = %s", (analysis_id, str(user.id))
        ).fetchone()
        if owned is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")

        rec = conn.execute(
            """
            SELECT r.id FROM recommendations r
            JOIN score_runs sr ON sr.id = r.score_run_id
            WHERE r.id = %s AND sr.analysis_id = %s
            """,
            (str(body.recommendation_id), analysis_id),
        ).fetchone()
        if rec is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Recommendation not found for this analysis")

        row = conn.execute(
            """
            INSERT INTO feedback (user_id, recommendation_id, analysis_id, accepted, rejection_reason, usefulness_score, corrected_text)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (
                str(user.id), str(body.recommendation_id), analysis_id,
                body.accepted, body.rejection_reason, body.usefulness_score, body.corrected_text,
            ),
        ).fetchone()
        conn.commit()

    return FeedbackOut(id=row["id"])
