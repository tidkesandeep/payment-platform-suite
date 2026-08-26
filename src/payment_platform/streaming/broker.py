"""Broker ports. Produce is never on the /v1/payments call stack."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol


class BrokerError(Exception):
    """Produce or consume failed. Outbox rows stay unpublished."""


@dataclass(frozen=True)
class BrokerRecord:
    topic: str
    key: str
    value: dict[str, Any]


class Broker(Protocol):
    def produce(self, topic: str, key: str, value: dict[str, Any]) -> None: ...


class InMemoryBroker:
    def __init__(self) -> None:
        self.records: list[BrokerRecord] = []
        self.fail = False

    def produce(self, topic: str, key: str, value: dict[str, Any]) -> None:
        if self.fail:
            raise BrokerError("broker unavailable")
        self.records.append(BrokerRecord(topic=topic, key=key, value=dict(value)))


class KafkaBroker:
    def __init__(self, bootstrap: str):
        self._bootstrap = bootstrap
        self._producer = None

    def produce(self, topic: str, key: str, value: dict[str, Any]) -> None:
        producer = self._client()
        try:
            future = producer.send(
                topic,
                key=key.encode("utf-8") if key else None,
                value=json.dumps(value, separators=(",", ":")).encode("utf-8"),
            )
            future.get(timeout=5)
        except Exception as exc:
            raise BrokerError(str(exc)) from exc

    def _client(self):
        if self._producer is None:
            try:
                from kafka import KafkaProducer
            except ImportError as exc:
                raise BrokerError("kafka-python is not installed") from exc
            try:
                self._producer = KafkaProducer(
                    bootstrap_servers=self._bootstrap.split(","),
                    acks="all",
                    retries=2,
                    request_timeout_ms=5000,
                    api_version_auto_timeout_ms=5000,
                )
            except Exception as exc:
                raise BrokerError(str(exc)) from exc
        return self._producer
