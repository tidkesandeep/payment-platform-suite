from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from payment_platform.config import Settings
from payment_platform.contracts import (
    AuthStatus,
    Decision,
    DecisionRecord,
    PaymentAttempt,
    TransactionState,
)
from payment_platform.db import ClaimOutcome, ClaimResult
from payment_platform.decision import decide
from payment_platform.fingerprint import canonical_fingerprint
from payment_platform.fraud import StubChampionScorer
from payment_platform.intent import IntentVerifier
from payment_platform.policy import evaluate_policy
from payment_platform.validation import validate_payment
from payment_platform.velocity import VelocityStore


class AuthorizeError(Exception):
    def __init__(self, status_code: int, body: dict[str, Any]):
        super().__init__(body.get("error", "error"))
        self.status_code = status_code
        self.body = body


@dataclass
class AppDeps:
    settings: Settings
    db: PostgresStore
    velocity: VelocityStore
    intent: IntentVerifier
    scorer: StubChampionScorer
    delay_after_claim_s: float = 0.0
    redis_ok: bool = True


def authorize_payment(
    *,
    deps: AppDeps,
    api_key_id: str,
    raw_body: dict[str, Any],
    idempotency_key: str | None,
    body_bytes_len: int,
) -> tuple[int, dict[str, Any]]:
    started = time.perf_counter()
    received_at = datetime.now(timezone.utc)

    if body_bytes_len > deps.settings.body_max_bytes:
        raise AuthorizeError(422, {"error": "validation_failed", "details": ["body too large"]})

    fingerprint = canonical_fingerprint(raw_body)
    if not idempotency_key:
        idempotency_key = raw_body.get("idempotency_key")
        if not isinstance(idempotency_key, str):
            idempotency_key = None
    if not idempotency_key:
        raise AuthorizeError(
            422,
            {"error": "validation_failed", "details": ["idempotency_key is required"]},
        )

    try:
        claim = deps.db.claim(
            api_key_id=api_key_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            lease_seconds=deps.settings.lease_seconds,
        )
    except Exception as exc:
        raise AuthorizeError(503, {"error": "unavailable"}) from exc

    if claim.outcome == ClaimOutcome.MISMATCH:
        return 422, {"error": "idempotency_fingerprint_mismatch"}
    if claim.outcome == ClaimOutcome.CONFLICT:
        return 409, {"error": "in_progress"}
    if claim.outcome == ClaimOutcome.REPLAY:
        decision = claim.decision or {}
        if decision.get("state") == TransactionState.VALIDATION_FAILED.value:
            details = list((decision.get("policy") or {}).get("violations") or [])
            return 422, {"error": "validation_failed", "details": details}
        return 200, decision

    if deps.delay_after_claim_s:
        time.sleep(deps.delay_after_claim_s)

    allowed = frozenset(
        c.strip().upper()
        for c in deps.settings.allowed_currencies.split(",")
        if c.strip()
    )
    attempt, details = validate_payment(
        raw_body, idempotency_key=idempotency_key, allowed_currencies=allowed
    )
    if attempt is None:
        record = _validation_failed(claim.transaction_id, details, started)
        _complete_safe(
            deps,
            api_key_id=api_key_id,
            attempt=None,
            transaction_id=claim.transaction_id,
            record=record,
            received_at=received_at,
            customer_id=str(raw_body.get("customer_id") or "unknown"),
            merchant_id=str(raw_body.get("merchant_id") or "unknown"),
            amount_minor=_safe_amount(raw_body),
            currency=_safe_currency(raw_body),
            channel=str(raw_body.get("channel") or "human"),
            idempotency_key=idempotency_key,
            authorization_status=None,
            fraud_score=None,
            fraud_band=None,
            policy_status=None,
            policy_violations=details,
        )
        return 422, {"error": "validation_failed", "details": details}

    try:
        record = _evaluate(deps, claim, attempt, started)
    except Exception:
        record = DecisionRecord(
            transaction_id=claim.transaction_id,
            state=TransactionState.PROCESSING_FAILED.value,
            decision=Decision.DECLINE.value,
            authorization={"status": AuthStatus.INVALID.value, "reason": "processing_failed"},
            fraud={"score": None, "band": "UNKNOWN"},
            policy={"status": "FAIL", "violations": ["processing_failed"]},
            latency_ms=_latency(started),
        )

    try:
        deps.db.complete(
            api_key_id=api_key_id,
            attempt=attempt,
            transaction_id=claim.transaction_id,
            state=record.state,
            authorization_status=record.authorization.get("status"),
            fraud_score=record.fraud.get("score"),
            fraud_band=record.fraud.get("band"),
            policy_status=record.policy.get("status"),
            policy_violations=list(record.policy.get("violations") or []),
            decision=record.to_json(),
            received_at=received_at,
            customer_id=attempt.customer_id,
            merchant_id=attempt.merchant_id,
            amount_minor=attempt.amount_minor,
            currency=attempt.currency,
            channel=attempt.channel,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        raise AuthorizeError(503, {"error": "unavailable"}) from exc

    if record.state == TransactionState.AUTHORIZED.value:
        deps.velocity.increment_approved(attempt.customer_id, attempt.amount_minor)

    return 200, record.to_json()


def _evaluate(
    deps: AppDeps,
    claim: ClaimResult,
    attempt: PaymentAttempt,
    started: float,
) -> DecisionRecord:
    intent = deps.intent.verify(attempt)
    velocity = deps.velocity.increment_attempt(attempt.customer_id)
    fraud = deps.scorer.score(attempt)
    policy = evaluate_policy(attempt, velocity, deps.settings)
    return decide(
        transaction_id=claim.transaction_id,
        authorization_status=intent.status,
        authorization_reason=intent.reason,
        fraud_score=fraud.score,
        fraud_band=fraud.band,
        policy_status=policy.status,
        policy_violations=policy.violations,
        latency_ms=_latency(started),
    )


def _complete_safe(deps: AppDeps, **kwargs: Any) -> None:
    record: DecisionRecord = kwargs.pop("record")
    try:
        deps.db.complete(
            **kwargs,
            state=record.state,
            decision=record.to_json(),
        )
    except Exception as exc:
        raise AuthorizeError(503, {"error": "unavailable"}) from exc


def _validation_failed(transaction_id: str, details: list[str], started: float) -> DecisionRecord:
    return DecisionRecord(
        transaction_id=transaction_id,
        state=TransactionState.VALIDATION_FAILED.value,
        decision=Decision.DECLINE.value,
        authorization={"status": AuthStatus.INVALID.value, "reason": "validation_failed"},
        fraud={"score": None, "band": "UNKNOWN"},
        policy={"status": "FAIL", "violations": details},
        latency_ms=_latency(started),
    )


def _latency(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _safe_amount(body: dict[str, Any]) -> int:
    amount = body.get("amount_minor")
    if isinstance(amount, int) and not isinstance(amount, bool) and amount > 0:
        return amount
    return 1


def _safe_currency(body: dict[str, Any]) -> str:
    currency = body.get("currency")
    if isinstance(currency, str) and len(currency) == 3:
        return currency.upper()
    return "USD"
