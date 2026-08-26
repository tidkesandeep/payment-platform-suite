-- Phase 7: investigator case files and append-only tool audit. No mutation of transactions.state.

CREATE TABLE IF NOT EXISTS investigations (
    investigation_id TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    status TEXT NOT NULL,
    case_file JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS investigations_transaction_idx
    ON investigations (transaction_id);

CREATE TABLE IF NOT EXISTS investigator_audit (
    id BIGSERIAL PRIMARY KEY,
    investigation_id TEXT,
    agent_id TEXT NOT NULL,
    tool TEXT NOT NULL,
    arguments JSONB NOT NULL,
    result JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS investigator_audit_created_idx
    ON investigator_audit (created_at DESC);
