"""Postgres connection pool and idempotent migration runner.

No ORM: the durable job table relies on raw `FOR UPDATE SKIP LOCKED` SQL,
so every other query in this service stays in plain SQL too, for consistency.
"""
from __future__ import annotations

import os
from pathlib import Path

from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://profilepilot:profilepilot@localhost:5432/profilepilot"
)
MIGRATIONS_DIR = Path(os.environ.get("MIGRATIONS_DIR", "/app/db/migrations"))

pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=10, kwargs={"row_factory": dict_row}, open=False)


def get_pool() -> ConnectionPool:
    if pool.closed:
        pool.open(wait=True, timeout=30)
    return pool


# Arbitrary fixed key for the migration advisory lock so concurrent api/worker
# startups never apply the same migration twice.
_MIGRATION_LOCK_KEY = 725_001

def run_migrations() -> None:
    if not MIGRATIONS_DIR.exists():
        raise RuntimeError(f"Migrations directory not found: {MIGRATIONS_DIR}")

    with get_pool().connection() as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (_MIGRATION_LOCK_KEY,))
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            applied = {
                row["version"] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
            }
            files = sorted(MIGRATIONS_DIR.glob("*.sql"))
            for path in files:
                if path.name in applied:
                    continue
                sql = path.read_text(encoding="utf-8")
                conn.execute(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,)
                )
                conn.commit()
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_MIGRATION_LOCK_KEY,))
            conn.commit()
