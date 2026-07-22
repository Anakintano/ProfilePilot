from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Seniority(StrEnum):
    intern = "intern"
    entry = "entry"
    junior = "junior"


class AnalysisStatus(StrEnum):
    queued = "queued"
    running = "running"
    needs_review = "needs_review"
    scoring = "scoring"
    completed = "completed"
    failed = "failed"


class Stage(StrEnum):
    ingest = "ingest"
    extract = "extract"
    normalize = "normalize"
    score = "score"
    recommend = "recommend"
    audit = "audit"
    publish = "publish"


class ExtractionMethod(StrEnum):
    embedded_text = "embedded_text"
    ocr = "ocr"
    vision_llm = "vision_llm"


class AuditStatus(StrEnum):
    supported = "supported"
    unsupported = "unsupported"
    vague = "vague"
    contradictory = "contradictory"
    not_audited = "not_audited"


class ImpactEffort(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class ConfidenceBand(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class GoalProfile(BaseModel):
    id: UUID | None = None
    target_role: str = Field(min_length=2, max_length=200)
    seniority: Seniority
    geography: str = Field(min_length=2, max_length=200)
    outcome: str = Field(min_length=2, max_length=500)
    job_description: str | None = Field(default=None, max_length=20_000)


class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class ExtractedField(BaseModel):
    id: UUID
    upload_id: UUID
    section: str
    field_key: str
    value: str
    normalized_value: Any | None = None
    source_page: int | None = None
    bbox: BoundingBox | None = None
    extraction_method: ExtractionMethod
    confidence: float | None = None
    user_corrected: bool
    corrected_value: str | None = None


class ScoreItem(BaseModel):
    dimension: str
    score: float
    confidence: float
    evidence_refs: list[str]
    reasoning_summary: str
    improvement_conditions: list[str]


class Recommendation(BaseModel):
    id: UUID
    priority: int
    expected_impact: ImpactEffort
    effort: ImpactEffort
    source_section: str
    original_text: str | None
    proposed_rewrite: str
    research_citations: list[str]
    audit_status: AuditStatus
    audit_notes: str | None


class RubricVersionOut(BaseModel):
    version: str
    effective_date: date
    audience: str
    dimensions: list[str]


class AnalysisReport(BaseModel):
    analysis_id: UUID
    score_run_id: UUID
    rubric_version: str
    prompt_version: str
    model_versions: dict[str, str]
    total_score: float
    confidence_band: ConfidenceBand
    dimension_scores: list[ScoreItem]
    limitations: list[str]
    recommendations: list[Recommendation]
    action_plan: list[str]
    published_at: datetime
