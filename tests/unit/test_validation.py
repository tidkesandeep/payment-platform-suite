from __future__ import annotations

from payment_platform.fingerprint import canonical_fingerprint
from payment_platform.validation import validate_payment

ALLOWED = frozenset({"USD"})


def _body(**overrides):
    payload = {
        "idempotency_key": "idem_1",
        "customer_id": "cust_001",
        "merchant_id": "mer_789",
        "amount_minor": 12550,
        "currency": "USD",
        "merchant_category": "5411",
        "country": "US",
        "channel": "human",
        "agent_id": None,
        "intent": None,
    }
    payload.update(overrides)
    return payload


def test_float_amount_rejected():
    attempt, details = validate_payment(
        _body(amount_minor=12.55),
        idempotency_key="idem_1",
        allowed_currencies=ALLOWED,
    )
    assert attempt is None
    assert any("integer" in d for d in details)


def test_legacy_float_amount_field_rejected():
    body = _body()
    body.pop("amount_minor")
    body["amount"] = 12.55
    attempt, details = validate_payment(body, idempotency_key="idem_1", allowed_currencies=ALLOWED)
    assert attempt is None
    assert any("amount_minor" in d for d in details)


def test_agent_requires_intent_and_agent_id():
    attempt, details = validate_payment(
        _body(channel="agent", agent_id=None, intent=None),
        idempotency_key="idem_1",
        allowed_currencies=ALLOWED,
    )
    assert attempt is None
    assert any("agent_id" in d for d in details)
    assert any("intent" in d for d in details)


def test_human_rejects_intent_blob():
    attempt, details = validate_payment(
        _body(intent={"nope": True}),
        idempotency_key="idem_1",
        allowed_currencies=ALLOWED,
    )
    assert attempt is None


def test_valid_human_parses():
    attempt, details = validate_payment(
        _body(), idempotency_key="idem_1", allowed_currencies=ALLOWED
    )
    assert details == []
    assert attempt is not None
    assert attempt.amount_minor == 12550


def test_fingerprint_ignores_idempotency_key():
    a = canonical_fingerprint(_body(idempotency_key="a"))
    b = canonical_fingerprint(_body(idempotency_key="b"))
    assert a == b
    c = canonical_fingerprint(_body(amount_minor=1))
    assert a != c
