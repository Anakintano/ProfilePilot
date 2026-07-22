# ADR 0006: Native (no-Docker) development fallback

## Status
Accepted

## Context
The architecture (ADR 0001) targets Docker Compose for local dev — Postgres
with pgvector, Redis, and three application services. On the machine this
beta was actually built and verified on, Docker Desktop proved unreliable:
the worker image's build failed twice in a row with two unrelated failure
modes (a corrupted download after a network connection reset, then an I/O
error immediately followed by the Docker daemon itself dropping the RPC
connection). The second failure in particular pointed at something unstable
in that machine's Docker Desktop/WSL2 backend rather than anything in this
codebase.

## Decision
Rather than keep fighting an unreliable Docker Desktop install, the app was
verified end-to-end running as plain native Windows processes instead:
- PostgreSQL 16 via EDB's **binaries zip** (not the installer, which
  requires admin elevation this environment couldn't grant non-interactively)
  — extracted to `.runtime/pg16/`, initialized with `initdb`, run with
  `pg_ctl` as the current user on port 5432. No Windows service, no admin
  rights.
- Redis skipped entirely — it's a disposable cache/rate-limiter by design
  (ADR 0001), and `services/api/app/rate_limit.py` already fails open when
  Redis is unreachable, so nothing breaks.
- `services/api` and `services/worker` run in Python 3.11 venvs directly
  (not containers) — same Python version the Docker images pin, for the
  same wheel-availability reasons.
- `apps/web` runs via plain `npm run dev`.
- `db/migrations/0001_init.sql`'s `CREATE EXTENSION vector` is wrapped in a
  `DO $$ ... EXCEPTION WHEN OTHERS ...` block, and
  `research_documents.embedding` is `jsonb` instead of `vector(384)`, since
  pgvector has no official Windows build. `research_documents` is seeded
  empty regardless (ADR — see the header of `0002_seed_rubric_v1.sql`), so
  this costs nothing functionally today.
- `scripts/start-native.ps1` / `stop-native.ps1` codify this so it's a
  one-command operation, not a remembered sequence of manual steps.

Docker Compose remains the documented, intended path (README Option A) and
nothing about the application code assumes native mode — the only
Docker-vs-native-specific code is the pgvector fallback above and reading
`MIGRATIONS_DIR`/`STORAGE_DIR` from the environment (already
environment-driven, not hardcoded, so no new indirection was needed there).

## Consequences
- The beta is verified against native execution, not the Docker path — if
  Docker becomes reliable on this machine again, the Docker path should be
  re-verified before being trusted, and the pgvector fallback should be
  reverted (swap `jsonb` back to `vector(384)`, drop the `DO $$` wrapper).
- Anyone picking up this project on a healthy Docker setup gets the
  documented, simpler path (`docker compose up --build`) with no changes
  needed.
- This is explicitly a workaround for one environment's instability, not a
  statement that Docker Compose was the wrong architectural choice (ADR
  0001's reasoning still holds).