from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from ..auth import CurrentUser, get_current_user
from ..config import settings
from ..db import get_pool
from ..rate_limit import check_and_consume
from ..schemas.uploads import UploadCreateRequest, UploadCreateResponse, UploadOut
from ..storage import ALLOWED_MIME_TYPES, build_upload_url, upload_path, verify_upload_token
from ..validation import validate_declared_metadata, validate_stored_file

router = APIRouter(prefix="/v1/uploads", tags=["uploads"])


@router.post("", response_model=UploadCreateResponse, status_code=status.HTTP_201_CREATED)
def create_upload(
    body: UploadCreateRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> UploadCreateResponse:
    client_ip = request.client.host if request.client else "unknown"
    if not check_and_consume(f"ip:{client_ip}:uploads", max_requests=30, window_seconds=3600):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many upload requests from this network")
    if not check_and_consume(f"user:{user.id}:uploads", max_requests=20, window_seconds=3600):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many upload requests for this account")

    result = validate_declared_metadata(body.mime_type, body.byte_size)
    if not result.ok:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, result.reason)

    upload_id = uuid4()
    extension = ALLOWED_MIME_TYPES[body.mime_type]
    path = upload_path(user.id, upload_id, extension)

    with get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO uploads (id, user_id, filename, mime_type, byte_size, storage_key, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending')
            """,
            (str(upload_id), str(user.id), body.filename, body.mime_type, body.byte_size, str(path)),
        )
        conn.commit()

    base_url = str(request.base_url).rstrip("/")
    upload_url, expires_at = build_upload_url(base_url, upload_id)
    return UploadCreateResponse(
        upload_id=upload_id,
        upload_url=upload_url,
        expires_at=datetime.fromtimestamp(expires_at, tz=timezone.utc),
    )


@router.put("/{upload_id}/put", status_code=status.HTTP_204_NO_CONTENT)
async def put_upload_bytes(
    upload_id: UUID,
    token: str,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> Response:
    if not verify_upload_token(upload_id, token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Upload token invalid or expired")

    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT * FROM uploads WHERE id = %s AND user_id = %s",
            (str(upload_id), str(user.id)),
        ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload not found")
    if row["status"] != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "Upload already finalized")

    path = upload_path(user.id, upload_id, ALLOWED_MIME_TYPES[row["mime_type"]])
    body = await request.body()
    if len(body) != row["byte_size"]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Uploaded {len(body)} bytes, declared {row['byte_size']} bytes",
        )
    path.write_bytes(body)

    result = validate_stored_file(path, row["mime_type"])
    with get_pool().connection() as conn:
        if result.ok:
            conn.execute(
                "UPDATE uploads SET status = 'validated', page_count = %s WHERE id = %s",
                (result.page_count, str(upload_id)),
            )
        else:
            path.unlink(missing_ok=True)
            conn.execute(
                "UPDATE uploads SET status = 'rejected', rejection_reason = %s WHERE id = %s",
                (result.reason, str(upload_id)),
            )
        conn.commit()

    if not result.ok:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, result.reason)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{upload_id}", response_model=UploadOut)
def get_upload(upload_id: UUID, user: CurrentUser = Depends(get_current_user)) -> UploadOut:
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT * FROM uploads WHERE id = %s AND user_id = %s",
            (str(upload_id), str(user.id)),
        ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload not found")
    return UploadOut(**row)
