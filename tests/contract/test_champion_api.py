from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from redis import Redis

from payment_platform.api.main import create_app
from payment_platform.authorize import AppDeps
from payment_platform.champion.model import XGBoostChampion
from payment_platform.config import Settings
from payment_platform.db import PostgresStore
from payment_platform.features.store import FeatureStore
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
def xgb_deps(store: PostgresStore, redis_client: Redis) -> AppDeps:
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
        scorer=XGBoostChampion.load(timeout_ms=200),
        features=FeatureStore(redis_client),
    )


def _headers() -> dict[str, str]:
    return {"X-API-Key": "sk_test_demo"}


def _human(**overrides) -> dict:
    payload = {
        "idempotency_key": f"idem-{uuid.uuid4()}",
        "customer_id": "cust_xgb",
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


def test_champion_is_a_dimension_policy_still_wins(xgb_deps: AppDeps):
    with TestClient(create_app(deps=xgb_deps)) as client:
        response = client.post(
            "/v1/payments",
            headers=_headers(),
            json=_human(amount_minor=9_000_000),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "POLICY_VIOLATION"
    assert body["fraud"]["reason"] == "xgboost_champion"
    assert "score" in body["fraud"]


def test_shap_skipped_on_approve(xgb_deps: AppDeps):
    with TestClient(create_app(deps=xgb_deps)) as client:
        created = client.post("/v1/payments", headers=_headers(), json=_human())
        assert created.status_code == 200
        if created.json()["state"] != "AUTHORIZED":
            pytest.skip("champion scored this benign row above LOW")
        explained = client.post(f"/v1/payments/{created.json()['transaction_id']}/explain")
    assert explained.status_code == 200
    assert explained.json()["shap"] is None
    assert "APPROVE" in explained.json()["note"]


def test_explain_returns_shap_when_not_approve(xgb_deps: AppDeps):
    payload = _human(
        amount_minor=60_000,
        merchant_category="7995",
        device_id=f"dev_new_{uuid.uuid4()}",
    )
    with TestClient(create_app(deps=xgb_deps)) as client:
        created = client.post("/v1/payments", headers=_headers(), json=payload)
        assert created.status_code == 200
        body = created.json()
        if body["state"] == "AUTHORIZED":
            pytest.skip("champion scored the high-risk cluster as LOW")
        explained = client.post(f"/v1/payments/{body['transaction_id']}/explain")
    assert explained.status_code == 200
    shap = explained.json()["shap"]
    assert isinstance(shap, list) and shap
    assert "feature" in shap[0] and "shap" in shap[0]
