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
from payment_platform.features.rebuild import FeatureRebuild
from payment_platform.features.store import FeatureStore
from payment_platform.fraud import StubChampionScorer
from payment_platform.intent import StubIntentVerifier
from payment_platform.velocity import VelocityStore

TEST_DSN = os.environ.get(
    "PAYMENTS_TEST_DATABASE_URL",
    "postgresql://payments:payments@127.0.0.1:5432/payments_test",
)
TEST_REDIS = os.environ.get("PAYMENTS_TEST_REDIS_URL", "redis://127.0.0.1:6379/1")


@pytest.fixture(scope="session")
def store() -> PostgresStore:
    db = PostgresStore(TEST_DSN)
    db.ensure_schema()
    return db


@pytest.fixture
def redis_client():
    client = Redis.from_url(TEST_REDIS, decode_responses=True)
    client.flushdb()
    yield client
    client.flushdb()
    client.close()


@pytest.fixture
def deps(store: PostgresStore, redis_client: Redis) -> AppDeps:
    with store.connection() as conn:
        conn.execute(
            "TRUNCATE idempotency_keys, transactions, outbox, velocity_counters, "
            "processed_events, transaction_projections"
        )
        conn.commit()
    return AppDeps(
        settings=Settings(database_url=TEST_DSN, redis_url=TEST_REDIS),
        db=store,
        velocity=VelocityStore(redis_client, store),
        intent=StubIntentVerifier(fail_closed=True),
        scorer=StubChampionScorer(),
        features=FeatureStore(redis_client),
    )


def _headers() -> dict[str, str]:
    return {"X-API-Key": "sk_test_demo", "Content-Type": "application/json"}


def _human(idem: str, customer_id: str = "cust_feat") -> dict:
    return {
        "idempotency_key": idem,
        "customer_id": customer_id,
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


def test_authorize_enriches_from_redis(deps: AppDeps, redis_client: Redis):
    customer = f"cust_{uuid.uuid4().hex[:8]}"
    with TestClient(create_app(deps=deps)) as client:
        first = client.post("/v1/payments", headers=_headers(), json=_human(f"idem-{uuid.uuid4()}", customer))
        second = client.post("/v1/payments", headers=_headers(), json=_human(f"idem-{uuid.uuid4()}", customer))
    assert first.status_code == 200
    assert second.status_code == 200
    profile = redis_client.hgetall(f"cust:{customer}")
    assert int(profile["txn_count_30d"]) == 2
    assert redis_client.exists(f"vel:attempt:{customer}:1h")
    assert int(redis_client.get(f"vel:attempt:{customer}:1h")) == 2


def test_rebuild_restores_profiles_without_touching_velocity(
    deps: AppDeps, store: PostgresStore, redis_client: Redis
):
    customer = f"cust_{uuid.uuid4().hex[:8]}"
    with TestClient(create_app(deps=deps)) as client:
        client.post("/v1/payments", headers=_headers(), json=_human(f"idem-{uuid.uuid4()}", customer))
    attempt_key = f"vel:attempt:{customer}:1h"
    before = redis_client.get(attempt_key)
    assert before is not None
    redis_client.delete(f"cust:{customer}")
    redis_client.delete(f"mer:mer_789")
    assert not redis_client.exists(f"cust:{customer}")
    result = FeatureRebuild(store, redis_client).run()
    assert result["velocity_keys_written"] == 0
    assert redis_client.get(attempt_key) == before
    assert redis_client.exists(f"cust:{customer}")
    assert int(redis_client.hget(f"cust:{customer}", "txn_count_30d")) >= 1


def test_high_risk_mcc_uses_features(deps: AppDeps):
    with TestClient(create_app(deps=deps)) as client:
        response = client.post(
            "/v1/payments",
            headers=_headers(),
            json={
                **_human(f"idem-{uuid.uuid4()}"),
                "merchant_category": "7995",
                "amount_minor": 1000,
            },
        )
    assert response.status_code == 200
    # 7995 is a feature signal (MEDIUM) and is not the policy MCC block in Phase 1 rules.
    assert response.json()["fraud"]["band"] == "MEDIUM"
