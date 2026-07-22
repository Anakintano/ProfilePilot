from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UploadCreateRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str
    byte_size: int = Field(gt=0)


class UploadCreateResponse(BaseModel):
    upload_id: UUID
    upload_url: str
    expires_at: datetime


class UploadOut(BaseModel):
    id: UUID
    filename: str
    mime_type: str
    byte_size: int
    page_count: int | None
    status: str
    rejection_reason: str | None
    created_at: datetime
    expires_at: datetime
