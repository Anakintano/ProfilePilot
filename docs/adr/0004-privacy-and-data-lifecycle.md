# ADR 0004: Privacy — 24h raw-object lifecycle, no scraping, consent-gated analytics

## Status
Accepted

## Context
Uploaded documents (résumés, LinkedIn exports, screenshots) are sensitive
personal data. The product must never touch LinkedIn directly (ToS and
ethics), and must not become a silent data hoard.

## Decision
- Raw uploaded files live under `STORAGE_DIR` (local disk in the beta,
  Cloudflare R2 target in production) and are addressed only via
  short-lived HMAC-signed upload tokens (`services/api/app/storage.py`) —
  never publicly served, never executed.
- Structured outputs (extracted fields, scores, recommendations) are
  retained for authenticated users; raw files are deleted 24 hours after
  upload. `uploads.expires_at` defaults to `now() + 24h`; the worker process
  sweeps expired rows every 10 minutes (`services/worker/app/main.py::_sweep_expired_uploads`),
  deleting both the DB row and the on-disk file. Running this in the worker
  loop rather than a separate scheduler is a deliberate beta-scale
  simplification (see README "Known limitations").
- No LinkedIn automation or scraping anywhere in this codebase — the only
  ingestion paths are user-provided PDF/image uploads and typed job
  descriptions.
- `DELETE /v1/me/data` (`services/api/app/routers/me.py`) removes analyses,
  uploads (DB rows + on-disk files), and goal profiles for the requesting
  user, and anonymizes (nulls `user_id` on) rather than deletes
  `product_events`, since those rows carry no PII once unlinked and back
  aggregate counters.
- Document text/PII is never written to logs (`logging` calls in this
  codebase log IDs, counts, and status strings — never field values).
- Every report/upload query is scoped by `user_id` at the SQL level (see
  `WHERE ... AND user_id = %s` in every router) — no cross-tenant reads.

## Consequences
- Beta users can trust that a rejected/abandoned upload doesn't linger
  indefinitely once the deletion sweep ships, and that deleting their
  account data actually removes the sensitive material, not just hides it.
- The 24h auto-expiry sweep itself (a cron-style job that deletes expired
  `uploads` rows + files) is scoped as a near-term follow-up, not yet wired
  into `docker-compose.yml` — see README.