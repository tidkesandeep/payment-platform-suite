from __future__ import annotations

from payment_platform.config import Settings
from payment_platform.contracts import PaymentAttempt, VelocitySnapshot
from payment_platform.policy import evaluate_policy


def _attempt(**overrides) -> PaymentAttempt:
    payload = dict(
        idempotency_key="k",
        customer_id="cust",
        merchant_id="mer_789",
        amount_minor=12550,
        currency="USD",
        merchant_category="5411",
        country="US",
        channel="human",
        agent_id=None,
        intent=None,
    )
    payload.update(overrides)
    return PaymentAttempt(**payload)


def _velocity(**overrides) -> VelocitySnapshot:
    payload = dict(
        attempt_1h=1,
        attempt_24h=1,
        approved_count_24h=0,
        approved_amount_minor_24h=0,
        available=True,
    )
    payload.update(overrides)
    return VelocitySnapshot(**payload)


def test_velocity_unavailable_fails_closed():
    result = evaluate_policy(_attempt(), _velocity(available=False), Settings())
    assert result.status == "FAIL"
    assert "velocity_unavailable" in result.violations


def test_amount_cap():
    result = evaluate_policy(_attempt(amount_minor=9_000_000), _velocity(), Settings())
    assert "max_amount_minor" in result.violations


def test_attempt_velocity_cap():
    result = evaluate_policy(_attempt(), _velocity(attempt_1h=21), Settings())
    assert "attempt_velocity_1h" in result.violations


def test_pass_when_within_limits():
    result = evaluate_policy(_attempt(), _velocity(), Settings())
    assert result.status == "PASS"
    assert result.violations == []


def test_merchant_allowlist():
    result = evaluate_policy(
        _attempt(merchant_id="mer_evil"),
        _velocity(),
        Settings(),
        allowlist=frozenset({"mer_789"}),
    )
    assert result.status == "FAIL"
    assert "merchant_allowlist" in result.violations
