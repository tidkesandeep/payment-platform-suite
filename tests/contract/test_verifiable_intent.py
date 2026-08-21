from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from redis import Redis

from payment_platform.api.main import create_app
from payment_platform.authorize import AppDeps
from payment_platform.config import Settings
from payment_platform.db import PostgresStore
from payment_platform.fraud import StubChampionScorer
from payment_platform.intent import OfficialIntentVerifier
from payment_platform.velocity import VelocityStore
from vi_mint import mint_chain

TEST_DSN = os.environ.get(
    "PAYMENTS_TEST_DATABASE_URL",
    "postgresql://payments:payments@127.0.0.1:5432/payments_test",
)
TEST_REDIS = os.environ.get("PAYMENTS_TEST_REDIS_URL", "redis://127.0.0.1:6379/1")


def _client(minted, **settings_kw) -> TestClient:
    db = PostgresStore(TEST_DSN)
    db.ensure_schema()
    with db.connection() as conn:
        conn.execute(
            "TRUNCATE idempotency_keys, transactions, outbox, velocity_counters, intent_nonces"
        )
        conn.commit()
    redis = Redis.from_url(TEST_REDIS, decode_responses=True)
    redis.flushdb()
    settings = Settings(database_url=TEST_DSN, redis_url=TEST_REDIS, **settings_kw)
    deps = AppDeps(
        settings=settings,
        db=db,
        velocity=VelocityStore(redis, db),
        intent=OfficialIntentVerifier(
            issuer_public_key=minted.issuer_public_key,
            nonce_store=db,
        ),
        scorer=StubChampionScorer(),
    )
    return TestClient(create_app(deps=deps))


def _agent(minted, **overrides) -> dict:
    payload = {
        "idempotency_key": f"idem-{uuid.uuid4()}",
        "customer_id": "cust_001",
        "merchant_id": minted.merchant_id,
        "amount_minor": minted.amount_minor,
        "currency": minted.currency,
        "merchant_category": "5411",
        "country": "US",
        "device_id": "dev_ok",
        "channel": "agent",
        "agent_id": minted.agent_id,
        "intent": minted.intent,
    }
    payload.update(overrides)
    return payload


def test_valid_official_chain_authorizes():
    minted = mint_chain()
    with _client(minted) as client:
        response = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_agent(minted),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "AUTHORIZED"
    assert body["authorization"]["status"] == "VALID"
    assert body["decision"] == "approve"


def test_http_idempotent_replay_returns_200():
    minted = mint_chain()
    idem = f"idem-{uuid.uuid4()}"
    payload = _agent(minted, idempotency_key=idem)
    with _client(minted) as client:
        first = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo", "Idempotency-Key": idem},
            json=payload,
        )
        second = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo", "Idempotency-Key": idem},
            json=payload,
        )
    assert first.status_code == 200
    assert first.json()["state"] == "AUTHORIZED"
    assert second.status_code == 200
    assert second.json()["transaction_id"] == first.json()["transaction_id"]
