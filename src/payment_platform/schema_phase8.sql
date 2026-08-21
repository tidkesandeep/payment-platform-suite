-- Phase 8: replay detection for Verifiable Intent nonces. No private keys.

CREATE TABLE IF NOT EXISTS intent_nonces (
    nonce TEXT PRIMARY KEY,
    seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
