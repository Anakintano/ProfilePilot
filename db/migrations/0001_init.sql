-- ProfilePilot core schema.
-- Applied by services/api/app/migrate.py (advisory-locked, idempotent) — not by Postgres initdb.
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;
EXCEPTION WHEN OTHERS THEN
    -- Native Windows Postgres (no Docker) has no pgvector build available.
    -- research_documents.embedding falls back to jsonb below; retrieval
    -- (services/worker/app/providers/research.py) already treats any query
    -- failure as "no results" so this degrades safely. Revert to a hard
    -- `CREATE EXTENSION vector;` + `embedding vector(384)` once running
    -- against the pgvector/pgvector Docker image again.
    RAISE NOTICE 'pgvector extension unavailable; research_documents.embedding will use jsonb fallback';
END $$;
CREATE EXTENSION IF NOT EXISTS pgcrypto; -- gen_random_uuid()

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    display_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS consents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    analytics_opt_in BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id)
);

CREATE TABLE IF NOT EXISTS goal_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_role TEXT NOT NULL,
    seniority TEXT NOT NULL CHECK (seniority IN ('intern', 'entry', 'junior')),
    geography TEXT NOT NULL,
    outcome TEXT NOT NULL,
    job_description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS uploads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    byte_size BIGINT NOT NULL,
    page_count INT,
    storage_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'validated', 'rejected')),
    rejection_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '24 hours')
);
CREATE INDEX IF NOT EXISTS idx_uploads_expires_at ON uploads(expires_at);
CREATE INDEX IF NOT EXISTS idx_uploads_user_id ON uploads(user_id);

CREATE TABLE IF NOT EXISTS analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    goal_profile_id UUID NOT NULL REFERENCES goal_profiles(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'needs_review', 'scoring', 'completed', 'failed')),
    current_stage TEXT NOT NULL DEFAULT 'ingest' CHECK (current_stage IN ('ingest', 'extract', 'normalize', 'score', 'recommend', 'audit', 'publish')),
    error_code TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_analyses_user_id ON analyses(user_id);

CREATE TABLE IF NOT EXISTS analysis_uploads (
    analysis_id UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    upload_id UUID NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    PRIMARY KEY (analysis_id, upload_id)
);

CREATE TABLE IF NOT EXISTS analysis_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    seq INT NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(analysis_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_analysis_events_analysis_id ON analysis_events(analysis_id, seq);

CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL CHECK (job_type IN ('extract', 'score')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'claimed', 'running', 'succeeded', 'failed', 'dead_letter')),
    run_after TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_by TEXT,
    claimed_at TIMESTAMPTZ,
    attempt_count INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 3,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_jobs_claim ON jobs(status, run_after);
CREATE INDEX IF NOT EXISTS idx_jobs_analysis_id ON jobs(analysis_id);

CREATE TABLE IF NOT EXISTS job_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    attempt_number INT NOT NULL,
    worker_id TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_job_attempts_job_id ON job_attempts(job_id);

CREATE TABLE IF NOT EXISTS extracted_fields (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    upload_id UUID NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    section TEXT NOT NULL,
    field_key TEXT NOT NULL,
    value TEXT NOT NULL,
    normalized_value JSONB,
    source_page INT,
    bbox JSONB,
    extraction_method TEXT NOT NULL CHECK (extraction_method IN ('embedded_text', 'ocr', 'vision_llm')),
    confidence REAL,
    user_corrected BOOLEAN NOT NULL DEFAULT false,
    corrected_value TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_extracted_fields_analysis_id ON extracted_fields(analysis_id);

CREATE TABLE IF NOT EXISTS rubric_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version TEXT UNIQUE NOT NULL,
    effective_date DATE NOT NULL,
    audience TEXT NOT NULL,
    dimensions JSONB NOT NULL,
    weights JSONB NOT NULL,
    evidence_requirements JSONB NOT NULL,
    research_snapshot_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS score_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    rubric_version_id UUID NOT NULL REFERENCES rubric_versions(id),
    prompt_version TEXT NOT NULL,
    model_versions JSONB NOT NULL DEFAULT '{}',
    total_score REAL,
    confidence_band TEXT CHECK (confidence_band IN ('low', 'medium', 'high')),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_score_runs_analysis_id ON score_runs(analysis_id);

CREATE TABLE IF NOT EXISTS score_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    score_run_id UUID NOT NULL REFERENCES score_runs(id) ON DELETE CASCADE,
    dimension TEXT NOT NULL,
    score REAL NOT NULL,
    confidence REAL NOT NULL,
    evidence_refs JSONB NOT NULL DEFAULT '[]',
    reasoning_summary TEXT NOT NULL,
    improvement_conditions JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_score_items_score_run_id ON score_items(score_run_id);

CREATE TABLE IF NOT EXISTS recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    score_run_id UUID NOT NULL REFERENCES score_runs(id) ON DELETE CASCADE,
    priority INT NOT NULL,
    expected_impact TEXT NOT NULL CHECK (expected_impact IN ('low', 'medium', 'high')),
    effort TEXT NOT NULL CHECK (effort IN ('low', 'medium', 'high')),
    source_section TEXT NOT NULL,
    original_text TEXT,
    proposed_rewrite TEXT NOT NULL,
    research_citations JSONB NOT NULL DEFAULT '[]',
    audit_status TEXT NOT NULL DEFAULT 'not_audited' CHECK (audit_status IN ('supported', 'unsupported', 'vague', 'contradictory', 'not_audited')),
    audit_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_recommendations_score_run_id ON recommendations(score_run_id);

CREATE TABLE IF NOT EXISTS feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recommendation_id UUID NOT NULL REFERENCES recommendations(id) ON DELETE CASCADE,
    analysis_id UUID NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    accepted BOOLEAN,
    rejection_reason TEXT,
    usefulness_score INT CHECK (usefulness_score BETWEEN 1 AND 5),
    corrected_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_feedback_analysis_id ON feedback(analysis_id);

CREATE TABLE IF NOT EXISTS research_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_url TEXT NOT NULL,
    publisher TEXT NOT NULL,
    retrieved_at DATE NOT NULL,
    effective_date DATE NOT NULL,
    claim TEXT NOT NULL,
    audience TEXT NOT NULL,
    confidence TEXT NOT NULL CHECK (confidence IN ('low', 'medium', 'high')),
    -- TEMPORARY (native/no-Docker beta only): pgvector has no official
    -- Windows build, so this is jsonb instead of `vector(384)` for now.
    -- research_documents is seeded empty either way (see 0002_seed_rubric_v1.sql
    -- header) so nothing reads/writes this column yet. Revert to
    -- `vector(384)` once back on the pgvector/pgvector Docker image.
    embedding jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS model_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID REFERENCES analyses(id) ON DELETE SET NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    stage TEXT NOT NULL,
    prompt_tokens INT NOT NULL DEFAULT 0,
    completion_tokens INT NOT NULL DEFAULT 0,
    latency_ms INT NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('ok', 'retried', 'fallback', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_model_usage_analysis_id ON model_usage(analysis_id);

CREATE TABLE IF NOT EXISTS product_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    event_name TEXT NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}',
    consented BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_product_events_created_at ON product_events(created_at);
