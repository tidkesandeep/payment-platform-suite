from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from redis import Redis

from payment_platform.api.main import create_app
from payment_platform.authorize import AppDeps
from payment_platform.config import Settings
from payment_platform.contracts import AuthStatus, IntentResult, VelocitySnapshot
from payment_platform.db import PostgresStore
from payment_platform.fraud import StubChampionScorer
from payment_platform.intent import StubIntentVerifier
from payment_platform.velocity import VelocityStore

TEST_DSN = os.environ.get(
    "PAYMENTS_TEST_DATABASE_URL",
    "postgresql://payments:payments@127.0.0.1:5432/payments_test",
)
TEST_REDIS = os.environ.get("PAYMENTS_TEST_REDIS_URL", "redis://127.0.0.1:6379/1")


class UnavailableVelocity(VelocityStore):
    def increment_attempt(self, customer_id: str) -> VelocitySnapshot:
        return VelocitySnapshot(0, 0, 0, 0, available=False)

    def increment_approved(self, customer_id: str, amount_minor: int) -> VelocitySnapshot:
        return VelocitySnapshot(0, 0, 0, 0, available=False)


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


def _deps(store: PostgresStore, redis_client: Redis, **overrides) -> AppDeps:
    with store.connection() as conn:
        conn.execute(
            "TRUNCATE idempotency_keys, transactions, outbox, velocity_counters"
        )
        conn.commit()
    base = dict(
        settings=Settings(database_url=TEST_DSN, redis_url=TEST_REDIS),
        db=store,
        velocity=VelocityStore(redis_client, store),
        intent=StubIntentVerifier(fail_closed=True),
        scorer=StubChampionScorer(),
    )
    base.update(overrides)
    return AppDeps(**base)


def _client(deps: AppDeps) -> TestClient:
    return TestClient(create_app(deps=deps))


def _headers() -> dict[str, str]:
    return {"X-API-Key": "sk_test_demo", "Content-Type": "application/json"}


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
    payload = _human(
        idem,
        channel="agent",
        agent_id="agent_coffee_buyer",
        intent={"stub": True},
    )
    payload.update(overrides)
    return payload


def test_concurrent_same_key_one_authorize(store: PostgresStore, redis_client: Redis):
    deps = _deps(store, redis_client, delay_after_claim_s=0.25)
    idem = f"idem-{uuid.uuid4()}"
    payload = _human(idem)
    with _client(deps) as client:
        def post():
            return client.post("/v1/payments", headers=_headers(), json=payload)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(post)
            second = pool.submit(post)
            results = [first.result(), second.result()]
    codes = sorted(r.status_code for r in results)
    bodies = [r.json() for r in results]
    assert codes in ([200, 200], [200, 409])
    if codes == [200, 409]:
        assert any(b.get("error") == "in_progress" for b in bodies)
        assert any(b.get("state") == "AUTHORIZED" for b in bodies)
    else:
        txn_ids = {b["transaction_id"] for b in bodies}
        assert len(txn_ids) == 1
        assert all(b["state"] == "AUTHORIZED" for b in bodies)


def test_lease_reclaim_same_fingerprint(store: PostgresStore, redis_client: Redis):
    from payment_platform.fingerprint import canonical_fingerprint

    deps = _deps(store, redis_client)
    idem = f"idem-{uuid.uuid4()}"
    payload = _human(idem)
    fingerprint = canonical_fingerprint(payload)
    claimed = store.claim(
        api_key_id="ak_demo",
        idempotency_key=idem,
        fingerprint=fingerprint,
        lease_seconds=30,
    )
    store.expire_lease("ak_demo", idem)
    with _client(deps) as client:
        response = client.post("/v1/payments", headers=_headers(), json=payload)
    assert response.status_code == 200
    assert response.json()["state"] == "AUTHORIZED"
    assert response.json()["transaction_id"] == claimed.transaction_id


def test_redis_down_does_not_approve(store: PostgresStore, redis_client: Redis):
    deps = _deps(store, redis_client, velocity=UnavailableVelocity(None, None))
    with _client(deps) as client:
        response = client.post(
            "/v1/payments",
            headers=_headers(),
            json=_human(f"idem-{uuid.uuid4()}"),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "POLICY_VIOLATION"
    assert "velocity_unavailable" in body["policy"]["violations"]
    assert body["decision"] != "approve"


def test_high_fraud_valid_intent_is_review(store: PostgresStore, redis_client: Redis):
    deps = _deps(
        store,
        redis_client,
        intent=StubIntentVerifier(
            injected=IntentResult(status=AuthStatus.VALID.value, reason="injected")
        ),
    )
    with _client(deps) as client:
        response = client.post(
            "/v1/payments",
            headers=_headers(),
            json=_agent(f"idem-{uuid.uuid4()}", device_id="dev_high"),
        )
    assert response.status_code == 200
    assert response.json()["state"] == "MANUAL_REVIEW"
    assert response.json()["authorization"]["status"] == "VALID"
    assert response.json()["fraud"]["band"] == "HIGH"


def test_critical_fraud_valid_intent_is_risk_declined(
    store: PostgresStore, redis_client: Redis
):
    deps = _deps(
        store,
        redis_client,
        intent=StubIntentVerifier(
            injected=IntentResult(status=AuthStatus.VALID.value, reason="injected")
        ),
    )
    with _client(deps) as client:
        response = client.post(
            "/v1/payments",
            headers=_headers(),
            json=_agent(f"idem-{uuid.uuid4()}", device_id="dev_critical"),
        )
    assert response.status_code == 200
    assert response.json()["state"] == "RISK_DECLINED"
    assert response.json()["fraud"]["band"] == "CRITICAL"


def test_unknown_fraud_is_review(store: PostgresStore, redis_client: Redis):
    deps = _deps(store, redis_client)
    with _client(deps) as client:
        response = client.post(
            "/v1/payments",
            headers=_headers(),
            json=_human(f"idem-{uuid.uuid4()}", device_id="dev_timeout"),
        )
    assert response.status_code == 200
    assert response.json()["state"] == "MANUAL_REVIEW"
    assert response.json()["fraud"]["band"] == "UNKNOWN"
