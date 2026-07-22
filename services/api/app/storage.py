"""Local-disk object storage that mimics a signed-URL flow.

STORAGE_MODE=local (the beta default): the "signed URL" is an HMAC-signed
token scoped to one upload_id with a short TTL, and the client PUTs bytes
straight to this API. STORAGE_MODE=r2 is the production target (Cloudflare
R2 presigned PUT) — swap the two functions below when that's wired up; no
caller changes needed.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path
from uuid import UUID

from .config import settings

ALLOWED_MIME_TYPES: dict[str, str] = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


def _storage_root() -> Path:
    root = Path(settings.storage_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def upload_path(user_id: UUID, upload_id: UUID, extension: str) -> Path:
    user_dir = _storage_root() / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / f"{upload_id}{extension}"


def sign_upload_token(upload_id: UUID, expires_at: int) -> str:
    if settings.storage_mode != "local":
        raise NotImplementedError("Only STORAGE_MODE=local is implemented in the beta.")
    message = f"{upload_id}:{expires_at}".encode()
    digest = hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()
    return f"{expires_at}.{digest}"


def verify_upload_token(upload_id: UUID, token: str) -> bool:
    try:
        expires_at_str, digest = token.split(".", 1)
        expires_at = int(expires_at_str)
    except (ValueError, AttributeError):
        return False
    if time.time() > expires_at:
        return False
    expected = sign_upload_token(upload_id, expires_at).split(".", 1)[1]
    return hmac.compare_digest(expected, digest)


def build_upload_url(base_url: str, upload_id: UUID) -> tuple[str, int]:
    expires_at = int(time.time()) + settings.upload_url_ttl_seconds
    token = sign_upload_token(upload_id, expires_at)
    url = f"{base_url}/v1/uploads/{upload_id}/put?token={token}"
    return url, expires_at


def delete_upload_file(path: Path) -> None:
    if path.exists():
        path.unlink()
