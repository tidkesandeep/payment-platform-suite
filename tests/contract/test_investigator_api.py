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
from payment_platform.features.store import FeatureStore
from payment_platform.fraud import StubChampionScorer
from payment_platform.intent import StubIntentVerifier
from payment_platform.investigator.service import Investigator
from payment_platform.investigator.tools import ToolDenied
from payment_platform.observability.metrics import PlatformMetrics
from payment_platform.velocity import VelocityStore

TEST_DSN = os.environ.get(
    "PAYMENTS_TEST_DATABASE_URL",
    "postgresql://payments:payments@127.0.0.1:5432/payments_test",
)
TEST_REDIS = os.environ.get("PAYMENTS_TEST_REDIS_URL", "redis://127.0.0.1:6379/1")


def _store() -> PostgresStore:
    db = PostgresStore(TEST_DSN)
    db.ensure_schema()
    return db


def _human(**overrides) -> dict:
    payload = {
        "idempotency_key": f"idem-{uuid.uuid4()}",
        "customer_id": "cust_inv",
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


def _deps(store: PostgresStore, redis_client: Redis, *, investigator: Investigator | None) -> AppDeps:
    with store.connection() as conn:
        conn.execute(
            "TRUNCATE idempotency_keys, transactions, outbox, velocity_counters, "
            "processed_events, transaction_projections, investigations, investigator_audit"
        )
        conn.commit()
    metrics = PlatformMetrics()
    return AppDeps(
        settings=Settings(database_url=TEST_DSN, redis_url=TEST_REDIS),
        db=store,
        velocity=VelocityStore(redis_client, store),
        intent=StubIntentVerifier(fail_closed=True),
        scorer=StubChampionScorer(),
        features=FeatureStore(redis_client),
        metrics=metrics,
        investigator=investigator,
    )


def test_case_file_exists_and_cannot_approve():
    store = _store()
    redis = Redis.from_url(TEST_REDIS, decode_responses=True)
    redis.flushdb()
    investigator = Investigator(store, StubChampionScorer(), metrics=PlatformMetrics())
    deps = _deps(store, redis, investigator=investigator)
    with TestClient(create_app(deps=deps)) as client:
        created = client.post("/v1/payments", headers={"X-API-Key": "sk_test_demo"}, json=_human())
        assert created.status_code == 200
        txn_id = created.json()["transaction_id"]
        state = created.json()["state"]
        opened = client.post(
            "/v1/investigations",
            headers={"X-API-Key": "sk_test_demo"},
            json={"transaction_id": txn_id, "agent_id": "investigator_1"},
        )
        fetched = client.get(f"/v1/payments/{txn_id}")
        case = client.get(f"/v1/investigations/{opened.json()['investigation_id']}")
    redis.close()
    assert opened.status_code == 200
    body = opened.json()
    assert body["case_file"]["can_approve"] is False
    assert body["case_file"]["untrusted_data"] is True
    assert fetched.json()["state"] == state
    assert case.status_code == 200
    assert case.json()["case_file"]["can_approve"] is False
    audit = store.list_investigator_audit(body["investigation_id"])
    tools = {row["tool"] for row in audit}
    assert "create_investigation" in tools
    assert "get_transaction" in tools


def test_approve_payment_tool_is_http_hard_error():
    store = _store()
    redis = Redis.from_url(TEST_REDIS, decode_responses=True)
    redis.flushdb()
    investigator = Investigator(store, StubChampionScorer(), metrics=PlatformMetrics())
    deps = _deps(store, redis, investigator=investigator)
    with TestClient(create_app(deps=deps)) as client:
        response = client.post(
            "/v1/investigations",
            headers={"X-API-Key": "sk_test_demo"},
            json={"tool": "approve_payment", "agent_id": "rogue", "transaction_id": "txn_x"},
        )
    redis.close()
    assert response.status_code == 422
    assert response.json()["error"] == "tool_denied"
    assert response.json()["tool"] == "approve_payment"


def test_manual_review_escalates_without_changing_state():
    store = _store()
    redis = Redis.from_url(TEST_REDIS, decode_responses=True)
    redis.flushdb()
    investigator = Investigator(store, StubChampionScorer(), metrics=PlatformMetrics())
    deps = _deps(store, redis, investigator=investigator)
    with TestClient(create_app(deps=deps)) as client:
        created = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_human(device_id="dev_high"),
        )
        opened = client.post(
            "/v1/investigations",
            headers={"X-API-Key": "sk_test_demo"},
            json={"transaction_id": created.json()["transaction_id"], "agent_id": "investigator_1"},
        )
        fetched = client.get(f"/v1/payments/{created.json()['transaction_id']}")
    redis.close()
    assert created.json()["state"] == "MANUAL_REVIEW"
    assert opened.json()["status"] == "escalated"
    assert opened.json()["case_file"]["escalation"] == "human_reviewer_required"
    assert fetched.json()["state"] == "MANUAL_REVIEW"


def test_investigator_down_does_not_block_authorize():
    store = _store()
    redis = Redis.from_url(TEST_REDIS, decode_responses=True)
    redis.flushdb()
    deps = _deps(store, redis, investigator=None)
    with TestClient(create_app(deps=deps)) as client:
        denied = client.post(
            "/v1/investigations",
            headers={"X-API-Key": "sk_test_demo"},
            json={"transaction_id": "txn_missing", "agent_id": "investigator_1"},
        )
        paid = client.post("/v1/payments", headers={"X-API-Key": "sk_test_demo"}, json=_human())
        ready = client.get("/ready")
    redis.close()
    assert denied.status_code == 503
    assert paid.status_code == 200
    assert ready.status_code == 200


def test_invoke_approve_is_hard_error_without_http():
    store = _store()
    investigator = Investigator(store, StubChampionScorer())
    with pytest.raises(ToolDenied):
        investigator.invoke("approve_payment", {}, agent_id="rogue")

