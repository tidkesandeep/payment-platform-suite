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
from payment_platform.intent import StubIntentVerifier
from payment_platform.velocity import VelocityStore

TEST_DSN = os.environ.get(
    "PAYMENTS_TEST_DATABASE_URL",
    "postgresql://payments:payments@127.0.0.1:5432/payments_test",
)
TEST_REDIS = os.environ.get("PAYMENTS_TEST_REDIS_URL", "redis://127.0.0.1:6379/1")
API_KEY = "sk_test_demo"


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
            "TRUNCATE idempotency_keys, transactions, outbox, velocity_counters"
        )
        conn.commit()
    return AppDeps(
        settings=Settings(database_url=TEST_DSN, redis_url=TEST_REDIS),
        db=store,
        velocity=VelocityStore(redis_client, store),
        intent=StubIntentVerifier(fail_closed=True),
        scorer=StubChampionScorer(),
    )


@pytest.fixture
def client(deps: AppDeps) -> TestClient:
    app = create_app(deps=deps)
    with TestClient(app) as test_client:
        yield test_client


def _headers(idem: str | None = None) -> dict[str, str]:
    headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
    if idem:
        headers["Idempotency-Key"] = idem
    return headers


def _human(idem: str, **overrides) -> dict:
    payload = {
        "idempotency_key": idem,
        "customer_id": "cust_001",
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


def _agent(idem: str, **overrides) -> dict:
    payload = _human(idem, channel="agent", agent_id="agent_coffee_buyer", intent={"stub": True})
    payload.update(overrides)
    return payload


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_human_payment_authorized(client: TestClient):
    idem = f"idem-{uuid.uuid4()}"
    response = client.post("/v1/payments", headers=_headers(), json=_human(idem))
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "AUTHORIZED"
    assert body["decision"] == "approve"
    assert body["authorization"]["status"] == "HUMAN"
    assert body["policy"]["status"] == "PASS"
    assert body["fraud"]["band"] == "LOW"
    fetched = client.get(f"/v1/payments/{body['transaction_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["state"] == "AUTHORIZED"


def test_replay_same_key_same_body(client: TestClient):
    idem = f"idem-{uuid.uuid4()}"
    first = client.post("/v1/payments", headers=_headers(), json=_human(idem))
    second = client.post("/v1/payments", headers=_headers(), json=_human(idem))
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["transaction_id"] == second.json()["transaction_id"]
    assert second.json()["state"] == "AUTHORIZED"


def test_fingerprint_mismatch_returns_422(client: TestClient):
    idem = f"idem-{uuid.uuid4()}"
    first = client.post("/v1/payments", headers=_headers(), json=_human(idem))
    assert first.status_code == 200
    second = client.post(
        "/v1/payments",
        headers=_headers(),
        json=_human(idem, amount_minor=20000),
    )
    assert second.status_code == 422
    assert second.json()["error"] == "idempotency_fingerprint_mismatch"


def test_float_amount_rejected(client: TestClient):
    idem = f"idem-{uuid.uuid4()}"
    response = client.post(
        "/v1/payments",
        headers=_headers(),
        json=_human(idem, amount_minor=12.55),
    )
    assert response.status_code == 422
    assert response.json()["error"] == "validation_failed"


def test_agent_stub_fails_closed(client: TestClient):
    idem = f"idem-{uuid.uuid4()}"
    response = client.post("/v1/payments", headers=_headers(), json=_agent(idem))
    assert response.status_code == 200
    assert response.json()["state"] == "INTENT_INVALID"
    assert response.json()["decision"] == "decline"


def test_policy_amount_cap(client: TestClient):
    idem = f"idem-{uuid.uuid4()}"
    response = client.post(
        "/v1/payments",
        headers=_headers(),
        json=_human(idem, amount_minor=9_000_000),
    )
    assert response.status_code == 200
    assert response.json()["state"] == "POLICY_VIOLATION"


def test_outbox_writes_two_topics(client: TestClient, store: PostgresStore):
    idem = f"idem-{uuid.uuid4()}"
    response = client.post("/v1/payments", headers=_headers(), json=_human(idem))
    txn_id = response.json()["transaction_id"]
    with store.connection() as conn:
        rows = conn.execute(
            "SELECT topic FROM outbox WHERE payload->>'transaction_id' = %s ORDER BY topic",
            (txn_id,),
        ).fetchall()
    topics = [r["topic"] for r in rows]
    assert topics == ["payments", "transaction-states"]


def test_unauthorized_without_api_key(client: TestClient):
    response = client.post("/v1/payments", json=_human("k"))
    assert response.status_code == 401
