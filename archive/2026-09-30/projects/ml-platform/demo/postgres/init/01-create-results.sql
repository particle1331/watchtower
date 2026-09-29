CREATE DATABASE results;

\connect results

CREATE TABLE IF NOT EXISTS results (
    id           TEXT PRIMARY KEY,
    parent_id    TEXT NULL REFERENCES results(id),
    name         TEXT NOT NULL,
    status       TEXT NOT NULL,
    output       JSONB NULL,
    error        TEXT NULL,
    attempts     INT NOT NULL DEFAULT 0,
    triggered_by TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_results_parent_status
    ON results (parent_id, status);
