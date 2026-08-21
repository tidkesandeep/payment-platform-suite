from __future__ import annotations

import logging
import time
from contextlib import nullcontext
from dataclasses import dataclass, field
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
from payment_platform.features.store import FeatureStore
from payment_platform.fingerprint import canonical_fingerprint
from payment_platform.fraud import Scorer
from payment_platform.intent import IntentVerifier
from payment_platform.observability.metrics import PlatformMetrics
from payment_platform.policy import evaluate_policy
from payment_platform.validation import validate_payment
from payment_platform.velocity import VelocityStore

_LOG = logging.getLogger("payment_platform")


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
    scorer: Scorer
    features: FeatureStore | None = None
    delay_after_claim_s: float = 0.0
    redis_ok: bool = True
    metrics: PlatformMetrics | None = None
    tracer: Any = None


@dataclass
class _Obs:
    reclaimed: bool = False
    replay: bool = False
    conflict: bool = False
    intent_s: float | None = None
    model_s: float | None = None
    extras: dict[str, Any] = field(default_factory=dict)


def authorize_payment(
    *,
    deps: AppDeps,
    api_key_id: str,
    idempotency_key: str | None,
    raw_body: dict[str, Any],
    body_bytes_len: int,
) -> tuple[int, dict[str, Any]]:
    started = time.perf_counter()
    obs = _Obs()
    span_cm = (
        deps.tracer.start_as_current_span("payments.authorize")
        if deps.tracer is not None
        else nullcontext()
    )
    status_code = 500
    body: dict[str, Any] = {}
    with span_cm as span:
        try:
            status_code, body = _authorize(
                deps=deps,
                api_key_id=api_key_id,
                raw_body=raw_body,
                idempotency_key=idempotency_key,
                body_bytes_len=body_bytes_len,
                started=started,
                obs=obs,
            )
            return status_code, body
        except AuthorizeError as exc:
            status_code, body = exc.status_code, exc.body
            raise
        finally:
            _record_observability(deps, started, status_code, body, obs, span)


def _authorize(
    *,
    deps: AppDeps,
    api_key_id: str,
    raw_body: dict[str, Any],
    idempotency_key: str | None,
    body_bytes_len: int,
    started: float,
    obs: _Obs,
) -> tuple[int, dict[str, Any]]:
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

    if claim.reclaimed:
        obs.reclaimed = True

    if claim.outcome == ClaimOutcome.MISMATCH:
        return 422, {"error": "idempotency_fingerprint_mismatch"}
    if claim.outcome == ClaimOutcome.CONFLICT:
        obs.conflict = True
        return 409, {"error": "in_progress"}
    if claim.outcome == ClaimOutcome.REPLAY:
        obs.replay = True
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
        record = _evaluate(deps, claim, attempt, started, received_at, obs)
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
    received_at: datetime,
    obs: _Obs,
) -> DecisionRecord:
    intent_started = time.perf_counter()
    intent = deps.intent.verify(attempt)
    obs.intent_s = time.perf_counter() - intent_started
    obs.extras["channel"] = attempt.channel
    velocity = deps.velocity.increment_attempt(attempt.customer_id)
    feature_vec = None
    if deps.features is not None:
        feature_vec = deps.features.materialize(
            attempt,
            velocity,
            received_at=received_at,
            intent=intent,
        )
    model_started = time.perf_counter()
    fraud = deps.scorer.score(attempt, feature_vec)
    obs.model_s = time.perf_counter() - model_started
    policy = evaluate_policy(attempt, velocity, deps.settings)
    record = decide(
        transaction_id=claim.transaction_id,
        authorization_status=intent.status,
        authorization_reason=intent.reason,
        fraud_score=fraud.score,
        fraud_band=fraud.band,
        policy_status=policy.status,
        policy_violations=policy.violations,
        latency_ms=_latency(started),
    )
    if feature_vec is not None:
        record.fraud["features"] = feature_vec.as_dict()
        record.fraud["reason"] = fraud.reason
    else:
        record.fraud["reason"] = fraud.reason
    return record


def _record_observability(
    deps: AppDeps,
    started: float,
    status_code: int,
    body: dict[str, Any],
    obs: _Obs,
    span: Any,
) -> None:
    elapsed = max(0.0, time.perf_counter() - started)
    metrics = deps.metrics
    if metrics is not None:
        metrics.observe_decision_seconds(elapsed)
        if obs.intent_s is not None:
            metrics.observe_intent_seconds(obs.intent_s)
        if obs.model_s is not None:
            metrics.observe_model_seconds(obs.model_s)
        if obs.conflict:
            metrics.inc_conflict()
        if obs.reclaimed:
            metrics.inc_reclaim()
        if obs.replay:
            metrics.inc_replay()
        state = body.get("state")
        if isinstance(state, str):
            channel = str(obs.extras.get("channel") or body.get("channel") or "unknown")
            metrics.inc_decision(state, channel)
    if span is not None:
        try:
            span.set_attribute("http.status_code", int(status_code))
            span.set_attribute("payments.latency_ms", int(elapsed * 1000))
            if obs.conflict:
                span.set_attribute("payments.idempotency", "conflict")
            elif obs.replay:
                span.set_attribute("payments.idempotency", "replay")
            elif obs.reclaimed:
                span.set_attribute("payments.idempotency", "reclaim")
            state = body.get("state")
            if isinstance(state, str):
                span.set_attribute("payments.state", state)
            txn = body.get("transaction_id")
            if isinstance(txn, str):
                span.set_attribute("payments.transaction_id", txn)
        except Exception:
            pass
    _LOG.info(
        "authorize",
        extra={
            "http_status": status_code,
            "transaction_id": body.get("transaction_id"),
            "state": body.get("state"),
            "latency_ms": int(elapsed * 1000),
            "path": "/v1/payments",
        },
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
