-- infra/results/schema.sql — Results DB DDL.
-- Idempotent: wrapped in IF NOT EXISTS guards so it can be run on every deploy.
-- The deploy administrator creates this table; grants.sql applies workload
-- privileges after this file runs. The Compose init copy mirrors this DDL.

CREATE TABLE IF NOT EXISTS results (
    id           TEXT PRIMARY KEY,                        -- UUID or deterministic hash for idempotent items
    parent_id    TEXT NULL REFERENCES results(id),        -- NULL = top-level run; set = child of a batch
    name         TEXT NOT NULL,                           -- workflow/task type, e.g. 'batch:score-fraud'
    status       TEXT NOT NULL,                           -- PENDING|STARTED|SUCCESS|RETRY|FAILURE|REVOKED
    output       JSONB NULL,                              -- per-task metadata; big payloads go to Blob
    error        TEXT NULL,                               -- traceback/message on failure
    attempts     INT NOT NULL DEFAULT 0,
    triggered_by TEXT NOT NULL,                           -- 'schedule' or caller email (audit)
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_results_parent_status ON results (parent_id, status);
