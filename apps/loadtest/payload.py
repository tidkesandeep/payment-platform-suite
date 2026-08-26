"""Human authorize payloads for Locust. Unique keys avoid 409 and velocity caps."""

from __future__ import annotations

import uuid

API_KEY = "sk_test_demo"


def payment_headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY, "Content-Type": "application/json"}


def human_payment() -> dict:
    nonce = uuid.uuid4().hex
    return {
        "idempotency_key": f"load-{nonce}",
        "customer_id": f"cust_load_{nonce}",
        "merchant_id": "mer_789",
        "amount_minor": 12550,
        "currency": "USD",
        "merchant_category": "5411",
        "country": "US",
        "device_id": "dev_ok",
        "channel": "human",
        "agent_id": None,
        "intent": None,
    }
