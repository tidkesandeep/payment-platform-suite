from __future__ import annotations

from payment_platform.config import Settings
from payment_platform.contracts import PaymentAttempt, PolicyResult, PolicyStatus, VelocitySnapshot


def evaluate_policy(
    attempt: PaymentAttempt,
    velocity: VelocitySnapshot,
    settings: Settings,
    *,
    allowlist: frozenset[str] | None = None,
) -> PolicyResult:
    violations: list[str] = []

    if attempt.amount_minor > settings.max_amount_minor:
        violations.append("max_amount_minor")

    allowed = {
        c.strip().upper()
        for c in settings.allowed_currencies.split(",")
        if c.strip()
    }
    if attempt.currency not in allowed:
        violations.append("currency")

    if allowlist is not None and attempt.merchant_id not in allowlist:
        violations.append("merchant_allowlist")

    if attempt.channel == "agent" and not attempt.intent:
        violations.append("channel_agent_requires_intent")

    if not velocity.available:
        violations.append("velocity_unavailable")
    else:
        if velocity.attempt_1h > settings.max_attempts_1h:
            violations.append("attempt_velocity_1h")
        if velocity.attempt_24h > settings.max_attempts_24h:
            violations.append("attempt_velocity_24h")
        projected = velocity.approved_amount_minor_24h + attempt.amount_minor
        if projected > settings.max_approved_amount_minor_24h:
            violations.append("approved_amount_24h")

    status = PolicyStatus.FAIL.value if violations else PolicyStatus.PASS.value
    return PolicyResult(status=status, violations=violations)
