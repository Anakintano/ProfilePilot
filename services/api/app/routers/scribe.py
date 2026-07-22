from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..auth import CurrentUser, get_current_user
from ..db import get_pool
from ..rate_limit import check_and_consume
from ..schemas.scribe import (
    ScribeCommentRequest,
    ScribeCommentResponse,
    ScribePostRequest,
    ScribePostResponse,
)
from ..scribe import provider, web_search

router = APIRouter(prefix="/v1/scribe", tags=["scribe"])


def _check_rate_limit(request: Request, user: CurrentUser) -> None:
    client_ip = request.client.host if request.client else "unknown"
    if not check_and_consume(f"ip:{client_ip}:scribe", max_requests=30, window_seconds=3600):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many Scribe requests from this network")
    if not check_and_consume(f"user:{user.id}:scribe", max_requests=20, window_seconds=3600):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many Scribe requests for this account")


def _log_model_usage(stage: str, usage: dict) -> None:
    """Best-effort model_usage logging -- analysis_id is NULL since Scribe has
    no associated analysis. Mirrors the SAVEPOINT pattern in
    services/worker/app/scoring/pipeline.py: a logging hiccup must never fail
    the actual request."""
    try:
        with get_pool().connection() as conn:
            conn.execute(
                """
                INSERT INTO model_usage (analysis_id, provider, model, stage, prompt_tokens,
                                          completion_tokens, latency_ms, status)
                VALUES (NULL, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    usage.get("provider", "fake"), usage.get("model", ""), stage,
                    usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                    usage.get("latency_ms", 0), usage.get("status", "ok"),
                ),
            )
            conn.commit()
    except Exception:  # noqa: BLE001 - logging model usage must never fail the request
        pass


@router.post("/post", response_model=ScribePostResponse)
def generate_post(
    body: ScribePostRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> ScribePostResponse:
    _check_rate_limit(request, user)

    search_results = web_search.search(body.topic) if body.use_web_search else []
    result, usage = provider.generate_post(
        style=body.style,
        topic=body.topic,
        rough_sketch=body.rough_sketch,
        search_results=search_results,
    )
    _log_model_usage("scribe_post", usage)
    return ScribePostResponse(**result)


@router.post("/comment", response_model=ScribeCommentResponse)
def generate_comment(
    body: ScribeCommentRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> ScribeCommentResponse:
    _check_rate_limit(request, user)

    result, usage = provider.generate_comment(
        post_content=body.post_content, comment_type=body.comment_type
    )
    _log_model_usage("scribe_comment", usage)
    return ScribeCommentResponse(**result)
