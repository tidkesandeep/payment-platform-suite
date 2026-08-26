from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from redis import Redis

from demo.issuer import ensure_issuer_keys, load_issuer_private_key
from demo.mint import mint_chain
from payment_platform.api.main import create_app
from payment_platform.authorize import AppDeps
from payment_platform.config import Settings
from payment_platform.db import PostgresStore
from payment_platform.fraud import StubChampionScorer
from payment_platform.intent import OfficialIntentVerifier
from payment_platform.velocity import VelocityStore

TEST_DSN = os.environ.get(
    "PAYMENTS_TEST_DATABASE_URL",
    "postgresql://payments:payments@127.0.0.1:5432/payments_test",
)
TEST_REDIS = os.environ.get("PAYMENTS_TEST_REDIS_URL", "redis://127.0.0.1:6379/1")


def _human(**overrides) -> dict:
    payload = {
        "idempotency_key": f"idem-{uuid.uuid4()}",
        "customer_id": "cust_demo_human",
        "merchant_id": "mer_789",
        "amount_minor": 12550,
        "currency": "USD",
        "merchant_category": "5411",
        "country": "US",
        "device_id": "dev_ok",
        "channel": "human",
        "agent_id": None,
        "intent": None,
    }
    payload.update(overrides)
    return payload


def _agent(minted, **overrides) -> dict:
    payload = {
        "idempotency_key": f"idem-{uuid.uuid4()}",
        "customer_id": "cust_demo_agent",
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


def test_human_and_agent_flow_including_h_and_h2(tmp_path):
    ensure_issuer_keys(tmp_path)
    issuer = load_issuer_private_key(tmp_path)
    minted = mint_chain(issuer_private_key=issuer)

    db = PostgresStore(TEST_DSN)
    db.ensure_schema()
    with db.connection() as conn:
        conn.execute(
            "TRUNCATE idempotency_keys, transactions, outbox, velocity_counters, intent_nonces"
        )
        conn.commit()
    redis = Redis.from_url(TEST_REDIS, decode_responses=True)
    redis.flushdb()
    deps = AppDeps(
        settings=Settings(
            database_url=TEST_DSN,
            redis_url=TEST_REDIS,
            vi_issuer_jwk_file=str(tmp_path / "issuer.pub.jwk"),
            hold_ttl_seconds=900,
        ),
        db=db,
        velocity=VelocityStore(redis, db),
        intent=OfficialIntentVerifier(
            issuer_public_key=minted.issuer_public_key,
            nonce_store=db,
        ),
        scorer=StubChampionScorer(),
    )
    headers = {"X-API-Key": "sk_test_demo"}
    with TestClient(create_app(deps=deps)) as client:
        human = client.post("/v1/payments", headers=headers, json=_human())
        assert human.status_code == 200
        assert human.json()["state"] == "AUTHORIZED"
        assert human.json()["authorization"]["status"] == "HUMAN"

        low = mint_chain(issuer_private_key=issuer)
        agent_ok = client.post("/v1/payments", headers=headers, json=_agent(low))
        assert agent_ok.status_code == 200
        assert agent_ok.json()["state"] == "AUTHORIZED"
        assert agent_ok.json()["authorization"]["status"] == "VALID"

        high = mint_chain(issuer_private_key=issuer)
        threat_h = client.post(
            "/v1/payments",
            headers=headers,
            json=_agent(high, device_id="dev_high"),
        )
        assert threat_h.json()["state"] == "MANUAL_REVIEW"
        assert threat_h.json()["authorization"]["status"] == "VALID"

        critical = mint_chain(issuer_private_key=issuer)
        threat_h2 = client.post(
            "/v1/payments",
            headers=headers,
            json=_agent(critical, device_id="dev_critical"),
        )
        assert threat_h2.json()["state"] == "RISK_DECLINED"
        assert threat_h2.json()["authorization"]["status"] == "VALID"

        holds = client.get("/v1/holds", headers=headers)
        assert holds.status_code == 200
        ids = {item["transaction_id"] for item in holds.json()["holds"]}
        assert threat_h.json()["transaction_id"] in ids
        assert threat_h2.json()["transaction_id"] not in ids
        for item in holds.json()["holds"]:
            assert "3DS" in item["note"]
            assert item["ttl_elapsed"] is False
