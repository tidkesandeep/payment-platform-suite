from __future__ import annotations

import re
from typing import Any

from payment_platform.contracts import PaymentAttempt

_ISO4217 = re.compile(r"^[A-Z]{3}$")
_CHANNELS = frozenset({"human", "agent"})


def validate_payment(
    body: dict[str, Any],
    *,
    idempotency_key: str | None,
    allowed_currencies: frozenset[str],
) -> tuple[PaymentAttempt | None, list[str]]:
    details: list[str] = []

    if not idempotency_key:
        details.append("idempotency_key is required")

    amount = body.get("amount_minor", None)
    if "amount" in body and "amount_minor" not in body:
        details.append("amount_minor is required; float amount is rejected")
    if isinstance(amount, float) or isinstance(amount, bool):
        details.append("amount_minor must be an integer minor-unit value")
        amount_minor = None
    elif isinstance(amount, int):
        if amount <= 0:
            details.append("amount_minor must be > 0")
        amount_minor = amount
    elif amount is None:
        details.append("amount_minor is required")
        amount_minor = None
    else:
        details.append("amount_minor must be an integer minor-unit value")
        amount_minor = None

    currency = body.get("currency")
    if not isinstance(currency, str) or not _ISO4217.fullmatch(currency):
        details.append("currency must be ISO 4217 (uppercase)")
        currency_ok = None
    elif currency not in allowed_currencies:
        details.append(f"currency {currency} is not allowlisted")
        currency_ok = currency
    else:
        currency_ok = currency

    channel = body.get("channel")
    if channel not in _CHANNELS:
        details.append("channel must be human or agent")
        channel_ok = None
    else:
        channel_ok = channel

    customer_id = body.get("customer_id")
    merchant_id = body.get("merchant_id")
    if not isinstance(customer_id, str) or not customer_id.strip():
        details.append("customer_id is required")
        customer_id = None
    if not isinstance(merchant_id, str) or not merchant_id.strip():
        details.append("merchant_id is required")
        merchant_id = None

    agent_id = body.get("agent_id")
    intent = body.get("intent")
    if channel_ok == "agent":
        if not isinstance(agent_id, str) or not agent_id.strip():
            details.append("agent_id is required when channel=agent")
        if not isinstance(intent, dict) or not intent:
            details.append("intent is required when channel=agent")
    elif channel_ok == "human":
        if agent_id is not None:
            details.append("agent_id must be null when channel=human")
        if intent is not None:
            details.append("intent must be null when channel=human")

    merchant_category = body.get("merchant_category")
    if not isinstance(merchant_category, str) or not merchant_category.strip():
        details.append("merchant_category is required")
        merchant_category = ""

    country = body.get("country")
    if not isinstance(country, str) or not country.strip():
        details.append("country is required")
        country = ""

    timestamp = body.get("timestamp")
    if timestamp is not None and not isinstance(timestamp, str):
        timestamp = None

    if details or idempotency_key is None or amount_minor is None or currency_ok is None:
        return None, details
    if channel_ok is None or customer_id is None or merchant_id is None:
        return None, details

    attempt = PaymentAttempt(
        idempotency_key=idempotency_key,
        customer_id=customer_id,
        merchant_id=merchant_id,
        amount_minor=amount_minor,
        currency=currency_ok,
        merchant_category=merchant_category,
        country=country,
        channel=channel_ok,
        agent_id=agent_id if isinstance(agent_id, str) else None,
        intent=intent if isinstance(intent, dict) else None,
        device_id=body.get("device_id") if isinstance(body.get("device_id"), str) else None,
        ip_address=body.get("ip_address") if isinstance(body.get("ip_address"), str) else None,
        timestamp=timestamp if isinstance(timestamp, str) else None,
    )
    return attempt, []
