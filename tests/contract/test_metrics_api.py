from __future__ import annotations

import os
import uuid

from fastapi.testclient import TestClient
from redis import Redis

from payment_platform.api.main import create_app
from payment_platform.authorize import AppDeps
from payment_platform.config import Settings
from payment_platform.db import PostgresStore
from payment_platform.features.store import FeatureStore
from payment_platform.fingerprint import canonical_fingerprint
from payment_platform.fraud import StubChampionScorer
from payment_platform.intent import StubIntentVerifier
from payment_platform.observability.metrics import PlatformMetrics
from payment_platform.observability.tracing import make_memory_tracer
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
        "customer_id": "cust_obs",
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


def _deps(store: PostgresStore, redis_client: Redis, *, tracer=None) -> AppDeps:
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
        metrics=PlatformMetrics(),
        tracer=tracer,
    )


def test_metrics_exposes_histogram_after_authorize():
    store = _store()
    redis = Redis.from_url(TEST_REDIS, decode_responses=True)
    redis.flushdb()
    deps = _deps(store, redis)
    with TestClient(create_app(deps=deps)) as client:
        created = client.post("/v1/payments", headers={"X-API-Key": "sk_test_demo"}, json=_human())
        assert created.status_code == 200
        scraped = client.get("/metrics")
        ready = client.get("/ready")
    redis.close()
    text = scraped.text
    assert scraped.status_code == 200
    assert "payments_decision_latency_seconds_bucket" in text
    assert "payments_idempotency_conflicts_total" in text
    assert "payments_lease_reclaims_total" in text
    assert "payments_outbox_lag" in text
    p95 = ready.json()["p95_decision_ms"]
    assert p95 is not None
    assert p95 != 100
    assert ready.json()["slo"]["contractual"] is False


def test_409_increments_conflict_counter():
    store = _store()
    redis = Redis.from_url(TEST_REDIS, decode_responses=True)
    redis.flushdb()
    deps = _deps(store, redis)
    payload = _human()
    store.claim(
        api_key_id="ak_demo",
        idempotency_key=payload["idempotency_key"],
        fingerprint=canonical_fingerprint(payload),
        lease_seconds=30,
    )
    with TestClient(create_app(deps=deps)) as client:
        response = client.post("/v1/payments", headers={"X-API-Key": "sk_test_demo"}, json=payload)
        scraped = client.get("/metrics")
    redis.close()
    assert response.status_code == 409
    assert "payments_idempotency_conflicts_total 1.0" in scraped.text


def test_reclaim_increments_reclaim_counter():
    store = _store()
    redis = Redis.from_url(TEST_REDIS, decode_responses=True)
    redis.flushdb()
    deps = _deps(store, redis)
    payload = _human()

    store.claim(
        api_key_id="ak_demo",
        idempotency_key=payload["idempotency_key"],
        fingerprint=canonical_fingerprint(payload),
        lease_seconds=30,
    )
    store.expire_lease("ak_demo", payload["idempotency_key"])
    with TestClient(create_app(deps=deps)) as client:
        response = client.post("/v1/payments", headers={"X-API-Key": "sk_test_demo"}, json=payload)
        scraped = client.get("/metrics")
    redis.close()
    assert response.status_code == 200
    assert "payments_lease_reclaims_total 1.0" in scraped.text


def test_authorize_emits_otel_span():
    store = _store()
    redis = Redis.from_url(TEST_REDIS, decode_responses=True)
    redis.flushdb()
    tracer, exporter = make_memory_tracer()
    deps = _deps(store, redis, tracer=tracer)
    with TestClient(create_app(deps=deps)) as client:
        response = client.post("/v1/payments", headers={"X-API-Key": "sk_test_demo"}, json=_human())
    redis.close()
    assert response.status_code == 200
    names = [span.name for span in exporter.get_finished_spans()]
    assert "payments.authorize" in names
