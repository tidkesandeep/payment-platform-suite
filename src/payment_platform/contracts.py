from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal


class Channel(StrEnum):
    HUMAN = "human"
    AGENT = "agent"


class IdempotencyStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    TERMINAL = "terminal"


class AuthStatus(StrEnum):
    VALID = "VALID"
    HUMAN = "HUMAN"
    INVALID = "INVALID"
    EXPIRED = "EXPIRED"
    REPLAY = "REPLAY"


class FraudBand(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class PolicyStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class Decision(StrEnum):
    APPROVE = "approve"
    CHALLENGE = "challenge"
    REVIEW = "review"
    DECLINE = "decline"


class TransactionState(StrEnum):
    AUTHORIZED = "AUTHORIZED"
    CHALLENGED = "CHALLENGED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    RISK_DECLINED = "RISK_DECLINED"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    INTENT_INVALID = "INTENT_INVALID"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PROCESSING_FAILED = "PROCESSING_FAILED"


TERMINAL_STATES = frozenset(s.value for s in TransactionState)

DecisionName = Literal["approve", "challenge", "review", "decline"]


@dataclass(frozen=True)
class IntentResult:
    status: str
    reason: str
    claims: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FraudResult:
    score: float | None
    band: str
    reason: str = "champion"


@dataclass(frozen=True)
class PolicyResult:
    status: str
    violations: list[str]


@dataclass(frozen=True)
class VelocitySnapshot:
    attempt_1h: int
    attempt_24h: int
    approved_count_24h: int
    approved_amount_minor_24h: int
    available: bool


@dataclass
class PaymentAttempt:
    idempotency_key: str
    customer_id: str
    merchant_id: str
    amount_minor: int
    currency: str
    merchant_category: str
    country: str
    channel: str
    agent_id: str | None
    intent: dict[str, Any] | None
    device_id: str | None = None
    ip_address: str | None = None
    timestamp: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "idempotency_key": self.idempotency_key,
            "customer_id": self.customer_id,
            "merchant_id": self.merchant_id,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "merchant_category": self.merchant_category,
            "country": self.country,
            "channel": self.channel,
            "agent_id": self.agent_id,
            "intent": self.intent,
            "device_id": self.device_id,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp,
        }


@dataclass
class DecisionRecord:
    transaction_id: str
    state: str
    decision: str
    authorization: dict[str, Any]
    fraud: dict[str, Any]
    policy: dict[str, Any]
    latency_ms: int | None = None

    def to_json(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "transaction_id": self.transaction_id,
            "state": self.state,
            "decision": self.decision,
            "authorization": self.authorization,
            "fraud": self.fraud,
            "policy": self.policy,
        }
        if self.latency_ms is not None:
            body["latency_ms"] = self.latency_ms
        return body
