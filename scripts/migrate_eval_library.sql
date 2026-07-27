-- Phase 10 Part A — self-maintaining evaluation library.
-- Run once: psql -d regulation_rag -f scripts/migrate_eval_library.sql
--
-- Design (docs/Phase 10 (Revised)): every question is ANCHORED to the CFR
-- section + effective date it was generated against. The weekly sync refresh
-- retires questions on removed sections and regenerates ground truth on changed
-- ones; times_refreshed > 0 removes a question from the "stable core" — the
-- only longitudinally comparable trend line.

CREATE TABLE IF NOT EXISTS eval_questions (
    id                     uuid        PRIMARY KEY DEFAULT uuid_generate_v4(),
    question               text        NOT NULL,
    -- definition | numeric_standard | procedure | penalty | enumerated_list
    -- | adversarial | negative  (negative = out-of-corpus, expects not_found)
    question_type          text        NOT NULL,
    ground_truth           text,
    ground_truth_reference text,       -- '7 CFR § 205.301' ('|'-separated if multiple)
    anchor_cfr_reference   text,       -- NULL for negatives
    anchor_title           integer,    -- NULL for negatives
    anchor_effective_date  date,       -- section version the ground truth was written against
    status                 text        NOT NULL DEFAULT 'active',    -- active | retired
    origin                 text        NOT NULL DEFAULT 'generated', -- generated | regression | manual
    times_refreshed        integer     NOT NULL DEFAULT 0,
    retired_reason         text,
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_eval_questions_status ON eval_questions(status);
CREATE INDEX IF NOT EXISTS idx_eval_questions_anchor ON eval_questions(anchor_cfr_reference);
CREATE INDEX IF NOT EXISTS idx_eval_questions_strata ON eval_questions(question_type, anchor_title);

-- One row per scheduled/manual eval run (weekly core, monthly full).
CREATE TABLE IF NOT EXISTS eval_runs (
    id             bigserial   PRIMARY KEY,
    run_at         timestamptz NOT NULL DEFAULT now(),
    scope          text        NOT NULL,  -- core | full
    status         text        NOT NULL,  -- ok | error | aborted_cost_cap
    num_questions  integer     NOT NULL DEFAULT 0,
    num_core       integer     NOT NULL DEFAULT 0,
    composite_all  real,                  -- quality score, full set run
    composite_core real,                  -- quality score, stable core only (the trend line)
    scores         jsonb,                 -- per-title / per-stratum breakdown + run config
    input_tokens   bigint      NOT NULL DEFAULT 0,
    output_tokens  bigint      NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS eval_results (
    id            bigserial   PRIMARY KEY,
    run_id        bigint      NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
    question_id   uuid        NOT NULL REFERENCES eval_questions(id) ON DELETE CASCADE,
    is_core       boolean     NOT NULL DEFAULT false,
    composite     real,
    not_found     boolean,
    scores        jsonb,      -- judge output + retrieval metrics + confidence tier
    plain_english text,       -- kept for triage/debugging of poor results
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_eval_results_run ON eval_results(run_id);
CREATE INDEX IF NOT EXISTS idx_eval_results_question ON eval_results(question_id);

GRANT ALL ON eval_questions, eval_runs, eval_results TO regulation_app;
GRANT USAGE, SELECT ON SEQUENCE eval_runs_id_seq, eval_results_id_seq TO regulation_app;
