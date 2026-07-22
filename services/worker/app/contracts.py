"""Loads JSON Schemas from packages/contracts/schemas for validating
LLM-facing structured output (recommendation generation, evidence audit).

The worker container only bind-mounts ./services/worker/app and
./db/migrations (see docker-compose.yml) -- packages/contracts/schemas lives
outside that, so callers must add a matching read-only volume mount for the
worker service (`./packages/contracts/schemas:/app/packages/contracts/schemas:ro`)
mirroring the existing db/migrations pattern. SCHEMAS_DIR can override the
path directly if that convention ever changes.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path


def _find_schemas_dir() -> Path:
    env = os.environ.get("SCHEMAS_DIR")
    if env:
        return Path(env)

    docker_default = Path("/app/packages/contracts/schemas")
    if docker_default.exists():
        return docker_default

    # Dev/test convenience: walk up from this file to find the monorepo root
    # when running outside Docker (e.g. services/worker/tests/smoke_scoring.py).
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "packages" / "contracts" / "schemas"
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "Could not locate packages/contracts/schemas; set the SCHEMAS_DIR env var."
    )


@lru_cache(maxsize=None)
def load_schema(filename: str) -> dict:
    path = _find_schemas_dir() / filename
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
