-- Government Regulation RAG — PostgreSQL schema
-- Run as: sudo -u postgres psql < src/db/schema.sql

\c postgres

-- Create DB and user
CREATE DATABASE regulation_rag;
CREATE USER regulation_app WITH ENCRYPTED PASSWORD 'regulation_dev_password';
GRANT ALL PRIVILEGES ON DATABASE regulation_rag TO regulation_app;

\c regulation_rag

-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

GRANT USAGE ON SCHEMA public TO regulation_app;
GRANT CREATE ON SCHEMA public TO regulation_app;

-- ── Chunk status ENUM ───────────────────────────────────────────────────────
-- active   = currently in production; included in all retrieval queries
-- staged   = freshly ingested but not yet visible; awaiting atomic swap
-- archived = replaced by a newer version; retained for temporal queries + rollback
CREATE TYPE chunk_status AS ENUM ('active', 'staged', 'archived');

-- ── Chunks table ────────────────────────────────────────────────────────────
CREATE TABLE chunks (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Version tracking (Phase 8: corpus freshness & versioned replacement)
    -- All retrieval queries MUST include: AND status = 'active'
    -- This is enforced in src/query.py, not per call-site.
    status          chunk_status    NOT NULL DEFAULT 'active',
    version_id      TEXT            NOT NULL DEFAULT 'v1',

    -- Source identification (corpus-agnostic, same as Sword Coast pattern)
    source_system   TEXT            NOT NULL DEFAULT 'federal_regulations',
    corpus_type     TEXT            NOT NULL DEFAULT 'cfr',
    source_id       TEXT            NOT NULL,  -- e.g. "cfr_title_7"

    -- CFR hierarchy metadata
    title_number    INTEGER,                    -- 7
    part_number     TEXT,                       -- "205"
    subpart         TEXT,                       -- "A"
    section_number  TEXT,                       -- "205.301"
    section_heading TEXT,                       -- "Allowed and prohibited substances..."
    agency          TEXT,                       -- "Agricultural Marketing Service"
    cfr_reference   TEXT,                       -- "7 CFR § 205.301"
    effective_date  DATE,                       -- from eCFR API

    -- Location reference (human-readable, for display)
    location_reference TEXT,

    -- Content
    chunk_text      TEXT            NOT NULL,
    chunk_index     INTEGER         NOT NULL DEFAULT 0,

    -- Embedding (text-embedding-3-small = 1536 dimensions)
    embedding       vector(1536),

    -- Timestamps
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    ingested_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Retrieval index (cosine similarity)
-- IMPORTANT: only build after initial ingest when row count is known;
-- adjust `lists` to ~sqrt(num_rows) for optimal performance.
-- At ~40K chunks: lists=200 is appropriate.
-- CREATE INDEX idx_chunks_embedding ON chunks
--     USING ivfflat (embedding vector_cosine_ops) WITH (lists = 200);

-- Metadata indexes
CREATE INDEX idx_chunks_source_system   ON chunks(source_system);
CREATE INDEX idx_chunks_status          ON chunks(status);
CREATE INDEX idx_chunks_version_id      ON chunks(version_id);

-- Composite index for atomic-swap queries (Phase 8):
-- SELECT ... WHERE cfr_reference = $1 AND status = 'active'
CREATE INDEX idx_chunks_cfr_ref_status  ON chunks(cfr_reference, status);

CREATE INDEX idx_chunks_title_number    ON chunks(title_number);
CREATE INDEX idx_chunks_part_number     ON chunks(part_number);
CREATE INDEX idx_chunks_effective_date  ON chunks(effective_date);

-- ── Query history table ──────────────────────────────────────────────────────
CREATE TABLE queries (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    query_text      TEXT            NOT NULL,
    source_system   TEXT            NOT NULL DEFAULT 'federal_regulations',
    plain_english   TEXT,
    legal_language  TEXT,
    citations       JSONB,
    llm_strategy    TEXT,
    latency_ms      INTEGER,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_queries_source_system  ON queries(source_system);
CREATE INDEX idx_queries_created_at     ON queries(created_at DESC);

-- Grant table access
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO regulation_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO regulation_app;
