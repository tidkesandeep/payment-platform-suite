"""Project broker events into read models. Never authorizes, scores, or evaluates policy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from payment_platform.db import PostgresStore
from payment_platform.ids import new_ulid
from payment_platform.streaming.broker import BrokerRecord

SETTLED = "SETTLED"
AUTHORIZED = "AUTHORIZED"


class StateProjector:
    def __init__(self, db: PostgresStore, redis=None):
        self._db = db
        self._redis = redis

    def handle(self, record: BrokerRecord) -> str:
        payload = dict(record.value)
        event_id = str(payload.get("event_id") or "")
        if not event_id:
            return "skipped"
        if not self._db.claim_processed(record.topic, event_id):
            return "duplicate"
        transaction_id = str(payload.get("transaction_id") or "")
        state = str(payload.get("state") or "")
        customer_id = payload.get("customer_id")
        if isinstance(customer_id, str) or customer_id is None:
            customer_ok = customer_id
        else:
            customer_ok = str(customer_id)
        if transaction_id and state:
            self._db.upsert_projection(
                transaction_id=transaction_id,
                state=state,
                customer_id=customer_ok,
                payload=payload,
                settled=(state == SETTLED),
            )
            if state == AUTHORIZED:
                self._maybe_emit_settled(transaction_id, payload)
        self._bump_metric(state)
        return "projected"

    def _maybe_emit_settled(self, transaction_id: str, payload: dict[str, Any]) -> None:
        if not self._db.mark_settlement_emitted(transaction_id):
            return
        event_id = new_ulid()
        settled = {
            "schema_version": 1,
            "event_id": event_id,
            "transaction_id": transaction_id,
            "state": SETTLED,
            "received_at": payload.get("received_at")
            or datetime.now(timezone.utc).isoformat(),
        }
        self._db.enqueue_outbox(event_id, "transaction-states", settled)

    def _bump_metric(self, state: str) -> None:
        if not state or self._redis is None:
            return
        try:
            key = f"metric:projected:{state}"
            pipe = self._redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, 86400, nx=True)
            pipe.execute()
        except Exception:
            return
