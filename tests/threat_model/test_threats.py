from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from redis import Redis

from payment_platform.api.main import create_app
from payment_platform.authorize import AppDeps
from payment_platform.config import Settings
from payment_platform.db import PostgresStore
from payment_platform.fraud import StubChampionScorer
from payment_platform.intent import IntentVerifier, OfficialIntentVerifier, StubIntentVerifier
from payment_platform.velocity import VelocityStore
from vi_mint import mint_chain

TEST_DSN = os.environ.get(
    "PAYMENTS_TEST_DATABASE_URL",
    "postgresql://payments:payments@127.0.0.1:5432/payments_test",
)
TEST_REDIS = os.environ.get("PAYMENTS_TEST_REDIS_URL", "redis://127.0.0.1:6379/1")


def _client(intent: IntentVerifier, **settings_kw) -> TestClient:
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
        intent=intent,
        scorer=StubChampionScorer(),
    )
    return TestClient(create_app(deps=deps))


def _official(minted) -> OfficialIntentVerifier:
    db = PostgresStore(TEST_DSN)
    db.ensure_schema()
    return OfficialIntentVerifier(
        issuer_public_key=minted.issuer_public_key,
        nonce_store=db,
    )


def _agent(minted=None, **overrides) -> dict:
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
    if minted is not None:
        payload.update(
            {
                "merchant_id": minted.merchant_id,
                "amount_minor": minted.amount_minor,
                "currency": minted.currency,
                "agent_id": minted.agent_id,
                "intent": minted.intent,
            }
        )
    payload.update(overrides)
    return payload


def test_threat_a_impersonation_invalid_intent():
    minted = mint_chain(agent_id="agent_coffee_buyer")
    with _client(_official(minted)) as client:
        response = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_agent(minted, agent_id="agent_impostor"),
        )
    assert response.status_code == 200
    assert response.json()["state"] == "INTENT_INVALID"
    assert response.json()["authorization"]["reason"] == "agent_mismatch"


def test_threat_b_constraint_violation():
    minted = mint_chain(max_amount=1000, l3_amount=12550, amount_minor=12550)
    with _client(_official(minted)) as client:
        response = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_agent(minted),
        )
    assert response.json()["state"] == "INTENT_INVALID"
    assert response.json()["authorization"]["reason"] == "constraint_violation"


def test_threat_b2_policy_merchant_allowlist():
    minted = mint_chain()
    with _client(_official(minted), merchant_allowlist="mer_other") as client:
        response = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_agent(minted),
        )
    assert response.json()["state"] == "POLICY_VIOLATION"
    assert "merchant_allowlist" in response.json()["policy"]["violations"]


def test_threat_c_amount_manipulation():
    minted = mint_chain(amount_minor=12550, max_amount=200_000)
    with _client(_official(minted)) as client:
        response = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_agent(minted, amount_minor=99999),
        )
    assert response.json()["state"] == "INTENT_INVALID"
    assert response.json()["authorization"]["reason"] == "amount_mismatch"


def test_threat_d_merchant_substitution():
    minted = mint_chain(merchant_id="mer_789")
    with _client(_official(minted)) as client:
        response = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_agent(minted, merchant_id="mer_evil"),
        )
    assert response.json()["state"] == "INTENT_INVALID"
    assert response.json()["authorization"]["reason"] == "merchant_mismatch"


def test_threat_e_checkout_tampering():
    minted = mint_chain(currency="EUR")
    with _client(_official(minted)) as client:
        response = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_agent(minted, currency="USD"),
        )
    assert response.status_code == 200
    assert response.json()["state"] == "INTENT_INVALID"
    assert response.json()["authorization"]["reason"] == "claim_mismatch"


def test_threat_e_payload_vs_signed_claims():
    minted = mint_chain()
    tampered = dict(minted.intent)
    tampered["l2_payment"] = minted.intent["l2"]
    with _client(_official(minted)) as client:
        response = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_agent(minted, intent=tampered),
        )
    assert response.json()["state"] == "INTENT_INVALID"


def test_threat_f_nonce_replay():
    minted = mint_chain()
    verifier = _official(minted)
    with _client(verifier) as client:
        first = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_agent(minted),
        )
        second = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_agent(minted, idempotency_key=f"idem-{uuid.uuid4()}"),
        )
    assert first.json()["state"] == "AUTHORIZED"
    assert second.json()["state"] == "INTENT_INVALID"
    assert second.json()["authorization"]["status"] == "REPLAY"


def test_threat_f_expired_intent():
    minted = mint_chain(l2_exp_offset=-400)
    with _client(_official(minted)) as client:
        response = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_agent(minted),
        )
    assert response.json()["state"] == "INTENT_INVALID"
    assert response.json()["authorization"]["status"] in {"EXPIRED", "INVALID"}


def test_threat_g_bad_signature():
    minted = mint_chain()
    token = minted.intent["l3_payment"]
    tampered = dict(minted.intent)
    tampered["l3_payment"] = token[:-2] + ("A" if token[-1] != "A" else "B") + token[-1]
    with _client(_official(minted)) as client:
        response = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_agent(minted, intent=tampered),
        )
    assert response.json()["state"] == "INTENT_INVALID"


def test_threat_h_valid_plus_high_is_review():
    minted = mint_chain()
    with _client(_official(minted)) as client:
        response = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_agent(minted, device_id="dev_high"),
        )
    assert response.json()["state"] == "MANUAL_REVIEW"
    assert response.json()["authorization"]["status"] == "VALID"


def test_threat_h2_valid_plus_critical_is_risk_declined():
    minted = mint_chain()
    with _client(_official(minted)) as client:
        response = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_agent(minted, device_id="dev_critical"),
        )
    assert response.json()["state"] == "RISK_DECLINED"
    assert response.json()["authorization"]["status"] == "VALID"


def test_investigator_approve_payment_is_hard_error():
    from payment_platform.investigator.tools import ToolDenied, assert_allowlisted

    with pytest.raises(ToolDenied) as caught:
        assert_allowlisted("approve_payment")
    assert caught.value.tool == "approve_payment"


def test_stub_still_fails_closed_without_injection():
    with _client(StubIntentVerifier(fail_closed=True)) as client:
        response = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_agent(),
        )
    assert response.json()["state"] == "INTENT_INVALID"
