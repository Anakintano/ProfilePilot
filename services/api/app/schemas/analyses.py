from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from .common import AnalysisReport, AnalysisStatus, GoalProfile, Stage


class AnalysisCreateRequest(BaseModel):
    goal_profile: GoalProfile
    upload_ids: list[UUID] = Field(min_length=1, max_length=5)


class AnalysisCreateResponse(BaseModel):
    analysis_id: UUID
    status: AnalysisStatus


class AnalysisOut(BaseModel):
    id: UUID
    status: AnalysisStatus
    current_stage: Stage
    created_at: datetime
    updated_at: datetime
    error_code: str | None
    error_message: str | None
    report: AnalysisReport | None = None


class AnalysisEventOut(BaseModel):
    seq: int
    stage: Stage
    status: AnalysisStatus
    message: str
    created_at: datetime
