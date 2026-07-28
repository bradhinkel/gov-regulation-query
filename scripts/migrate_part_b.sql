-- Phase 10 Part B — inline quality, feedback, and the poor-result queue.
-- Idempotent; run as postgres superuser or regulation_app:
--   sudo -u postgres psql regulation_rag < scripts/migrate_part_b.sql

-- Judge / escalation fields on the persisted query row (docx B.4).
ALTER TABLE queries
    ADD COLUMN IF NOT EXISTS escalated           BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS judge_grounding     SMALLINT,
    ADD COLUMN IF NOT EXISTS judge_agreement     BOOLEAN,
    ADD COLUMN IF NOT EXISTS security_downgrade  BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS quality             JSONB,
    -- User feedback: +1 thumbs-up, -1 thumbs-down (docx B.4 — the one quality
    -- signal the system cannot compute itself).
    ADD COLUMN IF NOT EXISTS feedback            SMALLINT,
    ADD COLUMN IF NOT EXISTS feedback_at         TIMESTAMPTZ,
    -- Triage lifecycle (docx B.5): NULL = never queued/needs no triage.
    ADD COLUMN IF NOT EXISTS triage_status       TEXT
        CHECK (triage_status IN ('triaged', 'dismissed', 'promoted')),
    ADD COLUMN IF NOT EXISTS failure_mode        TEXT
        CHECK (failure_mode IN ('retrieval_miss', 'corpus_coverage_gap',
                                'generation_error', 'chunking_artifact', 'other')),
    ADD COLUMN IF NOT EXISTS triaged_at          TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS promoted_question_id UUID REFERENCES eval_questions(id);

CREATE INDEX IF NOT EXISTS idx_queries_escalated ON queries(escalated) WHERE escalated;
CREATE INDEX IF NOT EXISTS idx_queries_feedback  ON queries(feedback)  WHERE feedback IS NOT NULL;

-- Poor-result queue (docx B.4 definition — any of):
--   low judge grounding | forced security downgrade | user thumbs-down |
--   not_found on an in-scope query (every persisted query passed the Phase 8.5
--   intent gate, so a persisted not_found row IS an in-scope not_found).
-- Untriaged rows are the queue; triaged/dismissed/promoted rows drop out.
CREATE OR REPLACE VIEW poor_results AS
SELECT id, query_text, created_at, not_found, escalated,
       judge_grounding, judge_agreement, security_downgrade, feedback,
       triage_status, failure_mode, promoted_question_id,
       ARRAY_REMOVE(ARRAY[
           CASE WHEN judge_grounding IS NOT NULL AND judge_grounding <= 2
                THEN 'low_judge_grounding' END,
           CASE WHEN security_downgrade THEN 'security_downgrade' END,
           CASE WHEN feedback = -1 THEN 'thumbs_down' END,
           CASE WHEN not_found THEN 'in_scope_not_found' END
       ], NULL) AS reasons
FROM queries
WHERE (judge_grounding IS NOT NULL AND judge_grounding <= 2)
   OR security_downgrade
   OR feedback = -1
   OR not_found;

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO regulation_app;
