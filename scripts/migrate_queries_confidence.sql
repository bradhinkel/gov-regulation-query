-- migrate_queries_confidence.sql
-- Adds not_found and confidence columns to the queries table.
-- Run after the initial schema.sql has been applied.
--
--   psql postgresql://regulation_app:regulation_dev_password@localhost:5432/regulation_rag < scripts/migrate_queries_confidence.sql

\c regulation_rag

ALTER TABLE queries
    ADD COLUMN IF NOT EXISTS not_found  BOOLEAN     NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS confidence JSONB;

\echo 'Migration complete: queries.not_found (BOOLEAN) and queries.confidence (JSONB) added.'
