"""Async worker: drain outbox to Redpanda and project events. Not on /v1/payments."""

from __future__ import annotations

import argparse
import sys
import time

from redis import Redis

from payment_platform.config import Settings
from payment_platform.db import PostgresStore
from payment_platform.streaming.broker import BrokerRecord, KafkaBroker
from payment_platform.streaming.projector import StateProjector
from payment_platform.streaming.publisher import OutboxPublisher


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Outbox publisher and project-only consumer")
    parser.add_argument("--once", action="store_true", help="drain unpublished outbox once and exit")
    args = parser.parse_args(argv)

    settings = Settings()
    db = PostgresStore(settings.database_url)
    db.ensure_schema()
    broker = KafkaBroker(settings.kafka_bootstrap)
    publisher = OutboxPublisher(db, broker)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    projector = StateProjector(db, redis)

    if args.once:
        result = publisher.drain_once()
        print(result)
        db.close()
        return 0 if result["failed"] == 0 else 1

    print("payment-stream running (publisher loop); consumer polls Kafka", file=sys.stderr)
    consumer = _kafka_consumer(settings.kafka_bootstrap)
    try:
        while True:
            publisher.drain_once()
            if consumer is not None:
                _poll_and_project(consumer, projector)
            time.sleep(settings.publisher_poll_seconds)
    except KeyboardInterrupt:
        return 0
    finally:
        db.close()


def _kafka_consumer(bootstrap: str):
    try:
        from kafka import KafkaConsumer
    except ImportError:
        print("kafka-python missing; publisher-only mode", file=sys.stderr)
        return None
    try:
        return KafkaConsumer(
            "payments",
            "transaction-states",
            bootstrap_servers=bootstrap.split(","),
            group_id="payment-projector",
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            consumer_timeout_ms=200,
            value_deserializer=lambda b: b,
        )
    except Exception as exc:
        print(f"kafka consumer unavailable: {exc}", file=sys.stderr)
        return None


def _poll_and_project(consumer, projector: StateProjector) -> None:
    import json

    batch = consumer.poll(timeout_ms=200)
    for _tp, messages in batch.items():
        for msg in messages:
            try:
                value = json.loads(msg.value.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                continue
            key = msg.key.decode("utf-8") if isinstance(msg.key, bytes) else str(msg.key or "")
            projector.handle(BrokerRecord(topic=msg.topic, key=key, value=value))
            consumer.commit()


if __name__ == "__main__":
    raise SystemExit(main())
