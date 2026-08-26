-- Phase 1 schema. Amounts are BIGINT minor units. Never FLOAT/DECIMAL for money.

CREATE TABLE IF NOT EXISTS merchants (
    merchant_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_keys (
    api_key_id TEXT PRIMARY KEY,
    merchant_id TEXT NOT NULL REFERENCES merchants (merchant_id),
    secret_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Stripe-style unique (api_key_id, key). Fingerprint is SHA-256 of canonical body.
CREATE TABLE IF NOT EXISTS idempotency_keys (
    api_key_id TEXT NOT NULL,
    key TEXT NOT NULL,
    transaction_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    status TEXT NOT NULL,
    lease_expires_at TIMESTAMPTZ,
    decision_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (api_key_id, key)
);

CREATE INDEX IF NOT EXISTS idempotency_keys_lease_idx
    ON idempotency_keys (lease_expires_at)
    WHERE lease_expires_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL,
    api_key_id TEXT NOT NULL,
    state TEXT NOT NULL,
    channel TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    merchant_id TEXT NOT NULL,
    amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
    currency CHAR(3) NOT NULL,
    authorization_status TEXT,
    fraud_score DOUBLE PRECISION,
    fraud_band TEXT,
    policy_status TEXT,
    policy_violations JSONB,
    received_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (api_key_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS transactions_merchant_created_idx
    ON transactions (merchant_id, created_at DESC);

-- UNIQUE (event_id, topic): one event can land on payments and transaction-states.
CREATE TABLE IF NOT EXISTS outbox (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    UNIQUE (event_id, topic)
);

CREATE TABLE IF NOT EXISTS policy_rules (
    rule_id TEXT PRIMARY KEY,
    merchant_id TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    code TEXT NOT NULL,
    description TEXT NOT NULL,
    config JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Postgres fallback when Redis is down (Phase 1 in-request INCR).
CREATE TABLE IF NOT EXISTS velocity_counters (
    counter_key TEXT PRIMARY KEY,
    value BIGINT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO merchants (merchant_id, name)
VALUES ('m_demo', 'Demo Merchant')
ON CONFLICT (merchant_id) DO NOTHING;

-- SHA-256 of the demo secret "sk_test_demo".
INSERT INTO api_keys (api_key_id, merchant_id, secret_hash)
VALUES (
    'ak_demo',
    'm_demo',
    '5d48f1024f38b44ad9ddc03dc12b2a8287c7ec690065dcef384cb1fd1753626d'
)
ON CONFLICT (api_key_id) DO NOTHING;

INSERT INTO policy_rules (rule_id, merchant_id, enabled, code, description, config)
VALUES
    (
        'global_amount_cap',
        NULL,
        TRUE,
        'max_amount_minor',
        'Decline amounts above configured minor-unit cap',
        '{"max_amount_minor": 5000000}'::jsonb
    ),
    (
        'global_currency',
        NULL,
        TRUE,
        'currency',
        'Allowlisted currencies only',
        '{"allowlist": ["USD"]}'::jsonb
    ),
    (
        'global_attempt_velocity',
        NULL,
        TRUE,
        'attempt_velocity',
        'Cap attempts per customer (card-testing)',
        '{"max_attempts_1h": 20, "max_attempts_24h": 80}'::jsonb
    ),
    (
        'global_approved_amount',
        NULL,
        TRUE,
        'approved_amount_24h',
        'Cap approved spend per customer over 24h',
        '{"max_approved_amount_minor_24h": 2000000}'::jsonb
    )
ON CONFLICT (rule_id) DO NOTHING;
