# ProfilePilot

A self-service diagnostic tool for students and early-career developers: state
a target role, upload a LinkedIn PDF / screenshot / résumé, review what was
extracted, and get an explainable, evidence-backed report — scores per
dimension, grounded rewrite suggestions, keyword gaps, and a prioritized
action plan.

This is a portfolio/beta project (see "What this is not" below), built to
demonstrate a real async-job backend, a measurable OCR pipeline, and
LLM-assisted-but-verifiable scoring — not a production hiring tool.

## What this is

- A **typed, durable workflow**: `ingest → extract → normalize → score →
  recommend → audit → publish`, running as background jobs claimed from a
  Postgres job table (no separate queue broker).
- **Deterministic where it can be**: file validation, OCR routing, rubric
  scoring/aggregation, and retry/backoff are plain code. LLMs are used only
  where generative reasoning adds value — drafting recommendation rewrites —
  and every rewrite is grounded in a verbatim quote from the candidate's own
  document, then checked by a deterministic Evidence Auditor before it's
  shown.
- **Local-first by default**: runs entirely on your machine via Docker
  Compose with zero external accounts. Point it at real Supabase/Groq/
  OpenRouter/R2 credentials later via `.env` — no code changes required.

## What this is not

- Not a hiring decision system. Scores are a coaching aid, not a prediction
  of recruiter outcomes.
- Not connected to LinkedIn in any way — it never scrapes or automates
  LinkedIn. The only inputs are files you upload yourself.
- Not a SaaS with billing, public sharing, or multi-tenant admin — this is a
  single-track beta for ~20 users.

## Architecture

```
apps/web          Next.js (TypeScript) — public pages + product UI
services/api       FastAPI — auth, uploads, analysis lifecycle, SSE progress
services/worker     Python — durable job loop: extraction, OCR, rubric
                    scoring, LLM recommendations, evidence audit, report
packages/contracts   Shared TypeScript types + JSON Schemas for LLM
                    structured outputs (source of truth is the Pydantic
                    models in services/api/app/schemas/)
db/migrations       Plain SQL migrations, applied by an advisory-locked
                    runner in services/api/app/db.py (no ORM)
docs/adr            Architecture decision records
```

See `docs/adr/` for the reasoning behind the durable-Postgres job queue,
the hybrid OCR pipeline, deterministic-scoring/LLM-recommendations split,
the privacy/data-lifecycle model, and provider routing.

## Data flow

1. Sign in (dev mode: automatic, single local user — see Auth below).
2. Goal intake: target role, seniority, geography, desired outcome, optional
   job description.
3. Upload desk: request a short-lived signed upload URL, validate type /
   magic bytes / page count / dimensions / size, upload directly.
4. Create an analysis (idempotent via `Idempotency-Key`) — returns
   immediately with an `analysis_id`; a background job starts extraction.
5. Extraction: embedded PDF text first, OCR only for pages/regions without
   usable text. Review the extracted sections (with confidence + source
   page) and correct anything wrong before scoring.
6. Scoring: versioned rubric (deterministic), LLM-drafted recommendations
   grounded in your own text, evidence-audited, published as an immutable
   report version. Correcting extraction or changing your goal creates a new
   run rather than overwriting history.
7. Raw uploads are deleted 24 hours after upload (background sweep in the
   worker); structured reports are retained for your account until you
   delete them (`/privacy` → Delete my data).

## Local setup

Two supported paths. Docker is the documented long-term path; native is what
this beta was actually developed and verified against, since Docker Desktop
was unreliable in that environment (see `docs/adr/0006-native-dev-fallback.md`).

### Option A — Docker

```bash
cp .env.example .env
docker compose up --build
```

- Web: http://localhost:3000
- API: http://localhost:8000 (health check at `/health`)
- Postgres: localhost:5432, Redis: localhost:6379

First boot runs DB migrations automatically (both `api` and `worker`
attempt it; an advisory lock makes that race-safe) and seeds one rubric
version (`v1`). Postgres runs `pgvector/pgvector:pg16`, so
`research_documents.embedding` is a real `vector(384)` column here.

### Option B — Native (no Docker)

One-time setup:
1. Install Python 3.11 and Node 20+.
2. `py -3.11 -m venv services/api/.venv && services/api/.venv/Scripts/pip install -r services/api/requirements.txt`
3. `py -3.11 -m venv services/worker/.venv && services/worker/.venv/Scripts/pip install -r services/worker/requirements.txt`
4. `cd apps/web && npm install`
5. Get PostgreSQL 16 running locally. If you can't install it as a Windows
   service (needs admin elevation), download the **binaries zip** (not the
   installer) from https://www.enterprisedb.com/download-postgresql-binaries,
   extract to `.runtime/pg16/`, then:
   ```
   .runtime/pg16/pgsql/bin/initdb.exe -D .runtime/pgdata -U postgres --pwfile=<file with a password>
   .runtime/pg16/pgsql/bin/pg_ctl.exe -D .runtime/pgdata -l .runtime/pg.log -o "-p 5432" start
   .runtime/pg16/pgsql/bin/createuser.exe -h localhost -U postgres -s profilepilot
   .runtime/pg16/pgsql/bin/createdb.exe -h localhost -U postgres -O profilepilot profilepilot
   ```
   No admin rights needed for the binaries-zip path — everything runs as your
   own user account.

Every time after that: `powershell -File scripts/start-native.ps1` starts
Postgres + API + worker + web; `scripts/stop-native.ps1` stops them.

Redis is skipped entirely in native mode — rate limiting fails open without
it by design (see `services/api/app/rate_limit.py`), so nothing breaks, you
just lose the (non-essential, at 20-user beta scale) request throttling.
`research_documents.embedding` falls back to `jsonb` instead of pgvector's
`vector(384)`, since pgvector has no official Windows build — the table is
seeded empty either way, so nothing is functionally lost; see the comment in
`db/migrations/0001_init.sql`.

### Auth modes

`.env` → `AUTH_MODE=dev` (default): every request is treated as one fixed
local user (`dev@local.test`), no login screen needed — this is what makes
the "fully working app, no payment/accounts required" goal possible.
`AUTH_MODE=supabase` verifies a real Supabase JWT instead; set
`SUPABASE_URL` / `SUPABASE_JWT_SECRET` when you're ready to wire that in.

### LLM providers

Recommendation drafting uses, in order: Groq (`GROQ_API_KEY`) → OpenRouter
(`OPENROUTER_API_KEY`) → a deterministic template-based fake provider (no
key, no network call — the default). Scoring itself never calls an LLM (see
`docs/adr/0003-deterministic-scoring-llm-recommendations.md`), so the report
is fully functional with zero keys configured.

Both `services/api` and `services/worker` target Python 3.11 specifically
(Docker containers are pinned to it; native setup step 2/3 above uses it
explicitly too) to sidestep wheel-availability issues on very new Python
versions — this machine had 3.14 installed by default, which several
OCR/vision dependencies don't yet publish wheels for.

## Evaluation methodology

The release gates in the original spec (embedded-text coverage ≥99%, OCR
field-level F1 ≥0.90, schema-compliance ≥99%, citation precision ≥95%, zero
unsupported personal claims, ≤3-point score variance across repeated runs,
P50/P95 latency targets) require a labeled gold set of ~20 consented
profiles that does not exist yet in this beta pass — building and scoring
against that set is the next milestone, not a claim this build makes today.
What *is* true today and mechanically checkable in this repo:
- Rubric scoring is pure, deterministic Python
  (`services/worker/app/rubric/engine.py`) — same input always produces the
  same score, satisfying the variance gate by construction rather than by
  measurement.
- Every recommendation's `evidence_span` is checked against the candidate's
  actual extracted text before being marked `supported`
  (`services/worker/app/scoring/audit.py`).
- Structured LLM outputs are validated against JSON Schema
  (`packages/contracts/schemas/`) with bounded retries.

## Known limitations (beta, honestly stated)

- No labeled gold-set evaluation yet (see above) — accuracy/F1 numbers are
  not yet measured, only architecturally supported.
- `research_documents` (the citation corpus for recommendations) ships
  empty rather than seeded with placeholder sources — we chose not to
  fabricate citation URLs. Recommendations currently carry zero citations
  until a real, verified research corpus is ingested; the retrieval code
  path (pgvector similarity search) is implemented and ready for that data.
- PaddleOCR is a heavy, occasionally fragile dependency. The pipeline
  degrades gracefully (embedded-text extraction still works, OCR'd pages
  are flagged for manual review) if it fails to install or run in a given
  environment — see `docs/adr/0002-hybrid-ocr-pipeline.md`.
- No History/compare-runs UI, no OpenTelemetry tracing, no Parquet/DuckDB
  analytics export, and no cross-model counterfactual-fairness testing yet
  — all explicitly deferred past this first working slice per the delivery
  plan (breadth work follows once the core loop is proven end-to-end).
- Reading order is a global top-to-bottom/left-to-right sort per page
  (`services/worker/app/extraction/pdf_text.py`), not column-aware. On a
  genuine two-column layout (e.g. LinkedIn's PDF export, sidebar + main
  content), blocks from both columns can interleave if they land at similar
  y-coordinates, occasionally attaching a stray line to the wrong section.
  Section *labels* are still correct via the header-keyword pass (and the
  LLM reclassification fallback below); only the ordering within a section
  can be affected. Column-aware reconstruction (cluster by x-position first,
  read each column fully before the next) is a real follow-up, not done yet.
- Contracts (`packages/contracts/src/types.ts`) are hand-maintained to
  mirror the Pydantic schemas rather than codegen'd from the live OpenAPI
  schema, to avoid a fragile build-time codegen step at this scale — keep
  the two in sync by hand when either changes.
- Upload validation sniffs magic bytes with a small hand-rolled 4-signature
  check (`services/api/app/validation.py::_sniff_mime_type`) rather than the
  `python-magic`/libmagic binding — that binding hangs without a system
  libmagic install, which Windows doesn't have by default. This is simpler
  and dependency-free on every platform, not just a Windows workaround.
- If `GROQ_API_KEY` or `OPENROUTER_API_KEY` is already set in your shell
  environment (not just `.env`), the provider router will use it — env vars
  win over an unset `.env` value. To force the deterministic fake provider
  even with ambient keys present, explicitly set both to empty strings in
  the environment you launch the worker from.
- Native mode's Postgres runs as a plain user process (not a Windows
  service), so it does not survive a reboot on its own — rerun
  `scripts/start-native.ps1` after restarting the machine.

## Contract package

Pydantic models in `services/api/app/schemas/` are the source of truth.
`packages/contracts/src/types.ts` mirrors them for the frontend.
`packages/contracts/schemas/*.json` are JSON Schemas enforced on LLM
structured outputs (recommendation generation, evidence audit, and the
vision-LLM layout-classification fallback).
