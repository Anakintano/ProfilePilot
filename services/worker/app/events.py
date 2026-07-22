"""Append-only analysis_events log with monotonic per-analysis sequence
numbers, backing the SSE progress endpoint. Not a message queue — just an
audit trail the API tails by polling.
"""
from __future__ import annotations

from uuid import UUID

from psycopg import Connection
from psycopg.errors import UniqueViolation


def append_event(conn: Connection, analysis_id: UUID, stage: str, status: str, message: str) -> None:
    for _ in range(3):
        try:
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO analysis_events (analysis_id, seq, stage, status, message)
                    SELECT %s, COALESCE(MAX(seq), 0) + 1, %s, %s, %s
                    FROM analysis_events WHERE analysis_id = %s
                    """,
                    (str(analysis_id), stage, status, message, str(analysis_id)),
                )
            return
        except UniqueViolation:
            continue
    raise RuntimeError(f"Could not append event for analysis {analysis_id} after 3 retries")
