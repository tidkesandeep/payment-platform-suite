from __future__ import annotations

from payment_platform.contracts import AuthStatus, IntentResult
from payment_platform.contracts import PaymentAttempt
from payment_platform.intent import StubIntentVerifier


def test_human_path_is_human():
    verifier = StubIntentVerifier()
    result = verifier.verify(
        PaymentAttempt(
            idempotency_key="k",
            customer_id="c",
            merchant_id="m",
            amount_minor=1,
            currency="USD",
            merchant_category="5411",
            country="US",
            channel="human",
            agent_id=None,
            intent=None,
        )
    )
    assert result.status == AuthStatus.HUMAN.value


def test_agent_path_fails_closed():
    verifier = StubIntentVerifier(fail_closed=True)
    result = verifier.verify(
        PaymentAttempt(
            idempotency_key="k",
            customer_id="c",
            merchant_id="m",
            amount_minor=1,
            currency="USD",
            merchant_category="5411",
            country="US",
            channel="agent",
            agent_id="agent_1",
            intent={"stub": True},
        )
    )
    assert result.status == AuthStatus.INVALID.value
    assert result.reason == "stub_fail_closed"


def test_injected_valid_for_unit_tests():
    verifier = StubIntentVerifier(
        injected=IntentResult(status=AuthStatus.VALID.value, reason="injected")
    )
    result = verifier.verify(
        PaymentAttempt(
            idempotency_key="k",
            customer_id="c",
            merchant_id="m",
            amount_minor=1,
            currency="USD",
            merchant_category="5411",
            country="US",
            channel="agent",
            agent_id="agent_1",
            intent={"stub": True},
        )
    )
    assert result.status == AuthStatus.VALID.value
