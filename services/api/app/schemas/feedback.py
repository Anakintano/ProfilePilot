from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class FeedbackCreateRequest(BaseModel):
    recommendation_id: UUID
    analysis_id: UUID
    accepted: bool | None = None
    rejection_reason: str | None = Field(default=None, max_length=1000)
    usefulness_score: int | None = Field(default=None, ge=1, le=5)
    corrected_text: str | None = Field(default=None, max_length=5000)


class FeedbackOut(BaseModel):
    id: UUID
