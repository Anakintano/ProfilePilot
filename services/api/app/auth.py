"""Auth: 'dev' mode (single fixed local user, no login UI needed) or
'supabase' mode (verifies a Supabase-issued JWT). Swapping AUTH_MODE in .env
is the only change needed to go from local-first demo to real auth — no
call-site code changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status

from .config import settings
from .db import get_pool

DEV_USER_EMAIL = "dev@local.test"
DEV_USER_DISPLAY_NAME = "Dev User"


@dataclass
class CurrentUser:
    id: UUID
    email: str


def ensure_dev_user() -> UUID:
    """Idempotently seed the fixed dev user. Called once at API startup."""
    with get_pool().connection() as conn:
        row = conn.execute(
            """
            INSERT INTO users (email, display_name)
            VALUES (%s, %s)
            ON CONFLICT (email) DO UPDATE SET display_name = EXCLUDED.display_name
            RETURNING id
            """,
            (DEV_USER_EMAIL, DEV_USER_DISPLAY_NAME),
        ).fetchone()
        conn.commit()
        return row["id"]


def _get_or_create_user(email: str, display_name: str | None = None) -> UUID:
    with get_pool().connection() as conn:
        row = conn.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()
        if row:
            return row["id"]
        row = conn.execute(
            "INSERT INTO users (email, display_name) VALUES (%s, %s) RETURNING id",
            (email, display_name or email),
        ).fetchone()
        conn.commit()
        return row["id"]


async def get_current_user(request: Request) -> CurrentUser:
    if settings.auth_mode == "dev":
        user_id = ensure_dev_user()
        return CurrentUser(id=user_id, email=DEV_USER_EMAIL)

    if settings.auth_mode == "supabase":
        authorization = request.headers.get("authorization", "")
        if not authorization.lower().startswith("bearer "):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
        token = authorization.split(" ", 1)[1]
        try:
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc
        email = payload.get("email")
        if not email:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing email claim")
        user_id = _get_or_create_user(email)
        return CurrentUser(id=user_id, email=email)

    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Unknown AUTH_MODE: {settings.auth_mode}")


CurrentUserDep = Depends(get_current_user)
