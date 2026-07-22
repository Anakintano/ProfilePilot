"""Durable job loop: claims one job at a time from Postgres via
FOR UPDATE SKIP LOCKED, dispatches to the extraction or scoring pipeline,
and owns all `jobs` / `analyses` state-machine transitions. The pipeline
modules only write their own domain tables and raise on unrecoverable error
— they never touch jobs.status or analyses.status directly, so there is one
place (this file) that decides retry vs. dead-letter vs. success.

Single process, sequential loop -> satisfies the beta's "one worker job at a
time" concurrency limit by construction; no locking needed beyond the DB row.
"""
from __future__ import annotations

import logging
import os
import random
import socket
import time
import traceback
from pathlib import Path
from uuid import UUID

from .db import get_pool, run_migrations
from .events import append_event
from .secrets_check import check_secrets_on_startup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("profilepilot.worker")

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
POLL_INTERVAL_SECONDS = 2
BASE_BACKOFF_SECONDS = 5
STALE_RUNNING_JOB_MINUTES = 10
UPLOAD_SWEEP_INTERVAL_SECONDS = 600


def _sweep_expired_uploads(conn) -> None:
    """Privacy promise: raw uploads are deleted 24h after creation
    (uploads.expires_at). Structured data derived from them (extracted_fields,
    score_runs, recommendations) is untouched — only the original file and
    its DB row go. Runs in the same process as the job loop since the beta
    has no separate scheduler."""
    rows = conn.execute("SELECT id, storage_key FROM uploads WHERE expires_at < now()").fetchall()
    if not rows:
        return
    conn.execute("DELETE FROM uploads WHERE expires_at < now()")
    for row in rows:
        Path(row["storage_key"]).unlink(missing_ok=True)
    logger.info("Swept %d expired upload(s)", len(rows))


def _reclaim_stale_jobs(conn) -> None:
    """A worker killed mid-job leaves its row stuck in 'running' forever
    (nothing else would ever flip it back). Sweep those back to 'pending' so
    another attempt can claim them — this is what makes stages resumable
    after a restart rather than just resumable after a clean failure."""
    conn.execute(
        """
        UPDATE jobs SET status = 'pending', run_after = now(), updated_at = now(),
               last_error = COALESCE(last_error, '') || ' [reclaimed from stale running state]'
        WHERE status = 'running' AND updated_at < now() - make_interval(mins => %s)
        """,
        (STALE_RUNNING_JOB_MINUTES,),
    )


def _claim_next_job(conn) -> dict | None:
    with conn.transaction():
        job = conn.execute(
            """
            SELECT * FROM jobs
            WHERE status = 'pending' AND run_after <= now()
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """
        ).fetchone()
        if job is None:
            return None
        conn.execute(
            """
            UPDATE jobs SET status = 'running', claimed_by = %s, claimed_at = now(),
                   attempt_count = attempt_count + 1, updated_at = now()
            WHERE id = %s
            """,
            (WORKER_ID, job["id"]),
        )
        job["attempt_count"] += 1
    return job


def _run_pipeline(conn, job: dict) -> None:
    analysis_id = UUID(str(job["analysis_id"]))
    if job["job_type"] == "extract":
        from .extraction.pipeline import run_extraction

        run_extraction(conn, analysis_id)
        conn.execute(
            "UPDATE analyses SET status = 'needs_review', current_stage = 'extract', updated_at = now() WHERE id = %s",
            (str(analysis_id),),
        )
        append_event(conn, analysis_id, "extract", "needs_review", "Extraction complete; ready for your review")
    elif job["job_type"] == "score":
        from .scoring.pipeline import run_scoring

        run_scoring(conn, analysis_id)
        conn.execute(
            "UPDATE analyses SET status = 'completed', current_stage = 'publish', updated_at = now() WHERE id = %s",
            (str(analysis_id),),
        )
        append_event(conn, analysis_id, "publish", "completed", "Report published")
    else:
        raise ValueError(f"Unknown job_type: {job['job_type']}")


def _process_job(job: dict) -> None:
    pool = get_pool()
    with pool.connection() as conn:
        attempt = conn.execute(
            """
            INSERT INTO job_attempts (job_id, attempt_number, worker_id, status)
            VALUES (%s, %s, %s, 'running') RETURNING id
            """,
            (job["id"], job["attempt_count"], WORKER_ID),
        ).fetchone()
        conn.commit()

        try:
            _run_pipeline(conn, job)
        except Exception as exc:  # noqa: BLE001 - any pipeline failure must be caught and classified
            conn.rollback()
            error_text = f"{exc}\n{traceback.format_exc()}"[:4000]
            logger.error("Job %s (analysis %s) failed: %s", job["id"], job["analysis_id"], exc)

            with pool.connection() as err_conn:
                err_conn.execute(
                    "UPDATE job_attempts SET status = 'failed', finished_at = now(), error = %s WHERE id = %s",
                    (error_text, attempt["id"]),
                )
                if job["attempt_count"] < job["max_attempts"]:
                    backoff = BASE_BACKOFF_SECONDS * (2 ** (job["attempt_count"] - 1))
                    backoff += random.uniform(0, backoff * 0.25)
                    err_conn.execute(
                        """
                        UPDATE jobs SET status = 'pending', run_after = now() + make_interval(secs => %s),
                               last_error = %s, updated_at = now()
                        WHERE id = %s
                        """,
                        (backoff, error_text, job["id"]),
                    )
                    append_event(
                        err_conn, UUID(str(job["analysis_id"])), job["job_type"], "running",
                        f"Attempt {job['attempt_count']} failed, retrying: {exc}",
                    )
                else:
                    err_conn.execute(
                        "UPDATE jobs SET status = 'dead_letter', last_error = %s, updated_at = now() WHERE id = %s",
                        (error_text, job["id"]),
                    )
                    err_conn.execute(
                        """
                        UPDATE analyses SET status = 'failed', error_code = 'job_failed',
                               error_message = %s, updated_at = now()
                        WHERE id = %s
                        """,
                        (str(exc)[:500], job["analysis_id"]),
                    )
                    append_event(
                        err_conn, UUID(str(job["analysis_id"])), job["job_type"], "failed",
                        f"Failed after {job['attempt_count']} attempts: {exc}",
                    )
                err_conn.commit()
            return

        conn.execute(
            "UPDATE job_attempts SET status = 'succeeded', finished_at = now() WHERE id = %s",
            (attempt["id"],),
        )
        conn.execute("UPDATE jobs SET status = 'succeeded', updated_at = now() WHERE id = %s", (job["id"],))
        conn.commit()


def main() -> None:
    run_migrations()
    check_secrets_on_startup()
    logger.info("Worker %s started, polling every %ss", WORKER_ID, POLL_INTERVAL_SECONDS)
    pool = get_pool()
    last_reclaim = 0.0
    last_sweep = 0.0
    while True:
        try:
            with pool.connection() as conn:
                if time.monotonic() - last_reclaim > 60:
                    _reclaim_stale_jobs(conn)
                    last_reclaim = time.monotonic()
                if time.monotonic() - last_sweep > UPLOAD_SWEEP_INTERVAL_SECONDS:
                    _sweep_expired_uploads(conn)
                    last_sweep = time.monotonic()
                job = _claim_next_job(conn)
                conn.commit()
        except Exception:  # noqa: BLE001 - never let a claim-loop error kill the worker
            logger.exception("Error claiming job")
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        if job is None:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        logger.info("Claimed job %s (%s) for analysis %s", job["id"], job["job_type"], job["analysis_id"])
        _process_job(job)


if __name__ == "__main__":
    main()
