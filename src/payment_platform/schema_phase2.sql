-- Phase 2: projector read models. Consumer dedupe is (topic, event_id).

CREATE TABLE IF NOT EXISTS processed_events (
    topic TEXT NOT NULL,
    event_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (topic, event_id)
);

CREATE TABLE IF NOT EXISTS transaction_projections (
    transaction_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    customer_id TEXT,
    payload JSONB NOT NULL,
    settled BOOLEAN NOT NULL DEFAULT FALSE,
    settlement_emitted BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS outbox_unpublished_idx
    ON outbox (id)
    WHERE published_at IS NULL;
