from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from redis import Redis

from payment_platform.api.main import create_app
from payment_platform.authorize import AppDeps
from payment_platform.config import Settings
from payment_platform.contracts import AuthStatus, IntentResult
from payment_platform.db import PostgresStore
from payment_platform.fraud import StubChampionScorer
from payment_platform.intent import StubIntentVerifier
from payment_platform.velocity import VelocityStore

TEST_DSN = os.environ.get(
    "PAYMENTS_TEST_DATABASE_URL",
    "postgresql://payments:payments@127.0.0.1:5432/payments_test",
)
TEST_REDIS = os.environ.get("PAYMENTS_TEST_REDIS_URL", "redis://127.0.0.1:6379/1")


def _client(intent: StubIntentVerifier) -> TestClient:
    db = PostgresStore(TEST_DSN)
    db.ensure_schema()
    with db.connection() as conn:
        conn.execute(
            "TRUNCATE idempotency_keys, transactions, outbox, velocity_counters"
        )
        conn.commit()
    redis = Redis.from_url(TEST_REDIS, decode_responses=True)
    redis.flushdb()
    deps = AppDeps(
        settings=Settings(database_url=TEST_DSN, redis_url=TEST_REDIS),
        db=db,
        velocity=VelocityStore(redis, db),
        intent=intent,
        scorer=StubChampionScorer(),
    )
    return TestClient(create_app(deps=deps))


def _agent(**overrides) -> dict:
    payload = {
        "idempotency_key": f"idem-{uuid.uuid4()}",
        "customer_id": "cust_001",
        "merchant_id": "mer_789",
        "amount_minor": 12550,
        "currency": "USD",
        "merchant_category": "5411",
        "country": "US",
        "device_id": "dev_ok",
        "channel": "agent",
        "agent_id": "agent_coffee_buyer",
        "intent": {"stub": True},
    }
    payload.update(overrides)
    return payload


def test_threat_a_impersonation_invalid_intent():
    with _client(StubIntentVerifier(fail_closed=True)) as client:
        response = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_agent(),
        )
    assert response.status_code == 200
    assert response.json()["state"] == "INTENT_INVALID"


def test_threat_h_valid_plus_high_is_review():
    verifier = StubIntentVerifier(
        injected=IntentResult(status=AuthStatus.VALID.value, reason="injected")
    )
    with _client(verifier) as client:
        response = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_agent(device_id="dev_high"),
        )
    assert response.json()["state"] == "MANUAL_REVIEW"


def test_threat_h2_valid_plus_critical_is_risk_declined():
    verifier = StubIntentVerifier(
        injected=IntentResult(status=AuthStatus.VALID.value, reason="injected")
    )
    with _client(verifier) as client:
        response = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_agent(device_id="dev_critical"),
        )
    assert response.json()["state"] == "RISK_DECLINED"


def test_investigator_approve_payment_is_hard_error():
    from payment_platform.investigator.tools import ToolDenied, assert_allowlisted

    with pytest.raises(ToolDenied) as caught:
        assert_allowlisted("approve_payment")
    assert caught.value.tool == "approve_payment"
