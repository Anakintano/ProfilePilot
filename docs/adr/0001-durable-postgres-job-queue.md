# ADR 0001: Durable Postgres job queue instead of Redis-backed queue

## Status
Accepted

## Context
The workflow (ingest → extract → normalize → score → recommend → audit → publish)
runs as background jobs picked up by a single worker process. We need
at-least-once delivery, crash recovery, and no duplicate report generation —
for roughly 20 beta users, not internet scale.

## Decision
Use a plain Postgres `jobs` table as the source of truth, claimed with
`SELECT ... FOR UPDATE SKIP LOCKED`. Redis is used only as a disposable
cache and per-IP/per-account rate limiter (see `services/api/app/rate_limit.py`)
— if Redis is unreachable, rate limiting fails open rather than blocking
requests, because it is not the durability boundary.

A stale-job reaper (`services/worker/app/main.py::_reclaim_stale_jobs`) flips
jobs stuck in `running` for >10 minutes (worker crash) back to `pending`.
Bounded retries with exponential backoff + jitter move a job to
`dead_letter` after `max_attempts`, at which point the parent `analyses` row
is marked `failed` with a user-facing message.

## Consequences
- One fewer moving part to operate/pay for at this scale (no separate queue
  broker).
- `FOR UPDATE SKIP LOCKED` naturally caps concurrency at "number of worker
  processes querying the table" — matches the beta's "one worker job at a
  time" quota by just running a single worker replica.
- Would need revisiting (e.g. a real queue, multiple workers with partition
  keys) if throughput or worker-count grows well past the beta.