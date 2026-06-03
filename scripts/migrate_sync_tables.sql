-- Phase 9.2/9.6 — incremental sync state + audit log.
-- Run once (as a DB owner/superuser): psql -d regulation_rag -f migrate_sync_tables.sql

-- Per-title watermark: the eCFR edition date we have fully reconciled up to.
CREATE TABLE IF NOT EXISTS sync_state (
    title_number     integer      PRIMARY KEY,
    last_synced_date date         NOT NULL,
    updated_at       timestamptz  NOT NULL DEFAULT now()
);

-- One row per sync run (audit / monitoring; surfaced in /health).
CREATE TABLE IF NOT EXISTS sync_runs (
    id                bigserial   PRIMARY KEY,
    run_at            timestamptz NOT NULL DEFAULT now(),
    titles            integer[]   NOT NULL,
    titles_changed    integer     NOT NULL DEFAULT 0,
    sections_updated  integer     NOT NULL DEFAULT 0,
    sections_removed  integer     NOT NULL DEFAULT 0,
    status            text        NOT NULL,        -- ok | alert | error | dry_run
    manifest          jsonb
);

-- Initialize the watermark from the current active corpus (the bootstrap edition
-- date per title). Existing rows are left untouched.
INSERT INTO sync_state (title_number, last_synced_date)
SELECT title_number, max(effective_date)
FROM chunks
WHERE status = 'active' AND title_number IS NOT NULL
GROUP BY title_number
ON CONFLICT (title_number) DO NOTHING;

-- The sync job connects as the application role.
GRANT ALL ON sync_state TO regulation_app;
GRANT ALL ON sync_runs  TO regulation_app;
GRANT USAGE, SELECT ON SEQUENCE sync_runs_id_seq TO regulation_app;
