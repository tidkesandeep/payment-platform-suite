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
from payment_platform.streaming.broker import BrokerRecord, InMemoryBroker
from payment_platform.streaming.projector import StateProjector
from payment_platform.streaming.publisher import OutboxPublisher
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
    )


def _human(idem: str) -> dict:
    return {
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


def test_authorize_succeeds_when_broker_is_down(deps: AppDeps, store: PostgresStore):
    app = create_app(deps=deps)
    with TestClient(app) as client:
        response = client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_human(f"idem-{uuid.uuid4()}"),
        )
    assert response.status_code == 200
    assert response.json()["state"] == "AUTHORIZED"
    assert store.outbox_lag() >= 2


def test_publisher_marks_published_and_retries_after_outage(deps: AppDeps, store: PostgresStore):
    app = create_app(deps=deps)
    with TestClient(app) as client:
        client.post(
            "/v1/payments",
            headers={"X-API-Key": "sk_test_demo"},
            json=_human(f"idem-{uuid.uuid4()}"),
        )
    broker = InMemoryBroker()
    broker.fail = True
    first = OutboxPublisher(store, broker).drain_once()
    assert first["published"] == 0
    assert first["failed"] == 1
    lag_after_fail = store.outbox_lag()
    assert lag_after_fail >= 2

    broker.fail = False
    second = OutboxPublisher(store, broker).drain_once()
    assert second["published"] == lag_after_fail
    assert store.outbox_lag() == 0
    third = OutboxPublisher(store, broker).drain_once()
    assert third["published"] == 0
    topics = sorted(r.topic for r in broker.records)
    assert "payments" in topics
    assert "transaction-states" in topics


def test_projector_dedupes_and_emits_settled_once(store: PostgresStore, redis_client: Redis):
    with store.connection() as conn:
        conn.execute(
            "TRUNCATE outbox, processed_events, transaction_projections"
        )
        conn.commit()
    projector = StateProjector(store, redis_client)
    payload = {
        "schema_version": 1,
        "event_id": "evt_1",
        "transaction_id": "txn_1",
        "state": "AUTHORIZED",
        "customer_id": "cust_001",
        "received_at": "2026-08-21T00:00:00+00:00",
    }
    record = BrokerRecord(topic="transaction-states", key="txn_1", value=payload)
    assert projector.handle(record) == "projected"
    assert projector.handle(record) == "duplicate"
    projection = store.get_projection("txn_1")
    assert projection is not None
    assert projection["state"] == "AUTHORIZED"
    unpublished = store.unpublished_outbox()
    settled = [r for r in unpublished if r["payload"]["state"] == "SETTLED"]
    assert len(settled) == 1

    settled_event = dict(settled[0]["payload"])
    assert (
        projector.handle(
            BrokerRecord(
                topic="transaction-states",
                key="txn_1",
                value=settled_event,
            )
        )
        == "projected"
    )
    assert store.get_projection("txn_1")["settled"] is True


def test_outbox_unique_event_id_and_topic(store: PostgresStore):
    with store.connection() as conn:
        conn.execute("TRUNCATE outbox")
        conn.commit()
    store.enqueue_outbox("evt_dup", "payments", {"schema_version": 1, "event_id": "evt_dup"})
    store.enqueue_outbox("evt_dup", "payments", {"schema_version": 1, "event_id": "evt_dup"})
    store.enqueue_outbox(
        "evt_dup", "transaction-states", {"schema_version": 1, "event_id": "evt_dup"}
    )
    rows = store.unpublished_outbox()
    pairs = sorted((r["event_id"], r["topic"]) for r in rows)
    assert pairs == [("evt_dup", "payments"), ("evt_dup", "transaction-states")]


def test_simulator_never_imports_kafka():
    import simulator.cli as cli

    source = open(cli.__file__, encoding="utf-8").read()
    assert "import kafka" not in source
    assert "KafkaProducer" not in source
    assert "from kafka" not in source
