"""Drain unpublished outbox rows to the broker. At-least-once; consumers dedupe."""

from __future__ import annotations

from typing import Any

from payment_platform.db import PostgresStore
from payment_platform.streaming.broker import Broker, BrokerError


class OutboxPublisher:
    def __init__(self, db: PostgresStore, broker: Broker):
        self._db = db
        self._broker = broker

    def drain_once(self, limit: int = 100) -> dict[str, int]:
        published = 0
        failed = 0
        for row in self._db.unpublished_outbox(limit=limit):
            payload = _as_dict(row["payload"])
            key = _partition_key(row["topic"], payload)
            try:
                self._broker.produce(row["topic"], key, payload)
            except BrokerError:
                failed += 1
                break
            self._db.mark_published(int(row["id"]))
            published += 1
        return {"published": published, "failed": failed}


def _partition_key(topic: str, payload: dict[str, Any]) -> str:
    if topic == "payments":
        return str(payload.get("customer_id") or payload.get("transaction_id") or "")
    return str(payload.get("transaction_id") or payload.get("event_id") or "")


def _as_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    return {}
