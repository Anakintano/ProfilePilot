from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import ensure_dev_user
from .config import settings
from .db import run_migrations
from .routers import analyses, feedback, me, scribe, uploads
from .secrets_check import check_secrets_on_startup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("profilepilot.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    check_secrets_on_startup()
    if settings.auth_mode == "dev":
        ensure_dev_user()
    logger.info("API ready (auth_mode=%s, storage_mode=%s)", settings.auth_mode, settings.storage_mode)
    yield


app = FastAPI(title="ProfilePilot API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(uploads.router)
app.include_router(analyses.router)
app.include_router(feedback.router)
app.include_router(me.router)
app.include_router(scribe.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
