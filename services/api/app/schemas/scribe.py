from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ScribeStyle = Literal[
    "professional", "storytelling", "thought_leadership", "casual", "data_driven", "listicle"
]
ScribeCommentType = Literal["engaging", "supportive", "insightful", "question", "congratulatory"]


class ScribePostRequest(BaseModel):
    style: ScribeStyle
    topic: str = Field(min_length=2, max_length=500)
    rough_sketch: str | None = Field(default=None, max_length=3000)
    use_web_search: bool = False


class ScribePostResponse(BaseModel):
    post_text: str
    hashtags: list[str] = Field(default_factory=list)


class ScribeCommentRequest(BaseModel):
    post_content: str = Field(min_length=2, max_length=5000)
    comment_type: ScribeCommentType


class ScribeCommentResponse(BaseModel):
    comment_text: str
