from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from .common import ExtractedField


class ExtractionOut(BaseModel):
    analysis_id: UUID
    fields: list[ExtractedField]
    required_sections_covered: list[str]
    required_sections_missing: list[str]
    mean_confidence: float | None


class FieldCorrection(BaseModel):
    field_id: UUID
    corrected_value: str


class ExtractionPatchRequest(BaseModel):
    corrections: list[FieldCorrection]
