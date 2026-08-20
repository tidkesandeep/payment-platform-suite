from __future__ import annotations

from payment_platform.contracts import (
    AuthStatus,
    Decision,
    DecisionRecord,
    FraudBand,
    PolicyStatus,
    TransactionState,
)

_VALID_AUTH = {AuthStatus.VALID.value, AuthStatus.HUMAN.value}
_INVALID_AUTH = {
    AuthStatus.INVALID.value,
    AuthStatus.EXPIRED.value,
    AuthStatus.REPLAY.value,
}


def decide(
    *,
    transaction_id: str,
    authorization_status: str,
    authorization_reason: str,
    fraud_score: float | None,
    fraud_band: str,
    policy_status: str,
    policy_violations: list[str],
    latency_ms: int | None = None,
) -> DecisionRecord:
    if authorization_status in _INVALID_AUTH:
        decision, state = Decision.DECLINE.value, TransactionState.INTENT_INVALID.value
    elif policy_status == PolicyStatus.FAIL.value:
        decision, state = Decision.DECLINE.value, TransactionState.POLICY_VIOLATION.value
    elif authorization_status in _VALID_AUTH and policy_status == PolicyStatus.PASS.value:
        decision, state = _from_fraud_band(fraud_band)
    else:
        decision, state = Decision.DECLINE.value, TransactionState.INTENT_INVALID.value

    return DecisionRecord(
        transaction_id=transaction_id,
        state=state,
        decision=decision,
        authorization={"status": authorization_status, "reason": authorization_reason},
        fraud={"score": fraud_score, "band": fraud_band},
        policy={"status": policy_status, "violations": list(policy_violations)},
        latency_ms=latency_ms,
    )


def _from_fraud_band(band: str) -> tuple[str, str]:
    if band == FraudBand.LOW.value:
        return Decision.APPROVE.value, TransactionState.AUTHORIZED.value
    if band == FraudBand.MEDIUM.value:
        return Decision.CHALLENGE.value, TransactionState.CHALLENGED.value
    if band == FraudBand.HIGH.value:
        return Decision.REVIEW.value, TransactionState.MANUAL_REVIEW.value
    if band == FraudBand.CRITICAL.value:
        return Decision.DECLINE.value, TransactionState.RISK_DECLINED.value
    return Decision.REVIEW.value, TransactionState.MANUAL_REVIEW.value
