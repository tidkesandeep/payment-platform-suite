"""Deterministic case file. Safety does not depend on a hosted LLM."""

from __future__ import annotations

from typing import Any


def render_case(
    *,
    transaction: dict[str, Any],
    features: dict[str, Any] | None,
    intent: dict[str, Any] | None,
    shap: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    state = str(transaction.get("state") or "UNKNOWN")
    fraud_band = str(transaction.get("fraud_band") or "UNKNOWN")
    fraud_score = transaction.get("fraud_score")
    policy_status = str(transaction.get("policy_status") or "UNKNOWN")
    auth_status = str(transaction.get("authorization_status") or "UNKNOWN")
    escalate = state == "MANUAL_REVIEW"
    lines = [
        f"Transaction {transaction.get('transaction_id')} is {state}.",
        f"Authorization status {auth_status}.",
        f"Fraud band {fraud_band} score={fraud_score}.",
        f"Policy {policy_status}.",
        "The investigator cannot approve or decline this payment.",
    ]
    if escalate:
        lines.append("Escalate to a human reviewer.")
    if intent:
        lines.append(
            f"Stored intent status {intent.get('status')} reason={intent.get('reason')}."
        )
    return {
        "can_approve": False,
        "escalation": "human_reviewer_required" if escalate else None,
        "summary": " ".join(lines[:3]),
        "narrative": " ".join(lines),
        "transaction": transaction,
        "features": features,
        "intent": intent,
        "shap": shap,
        "untrusted_data": True,
        "instructions": None,
    }
