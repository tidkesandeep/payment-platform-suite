from loadtest.payload import human_payment, payment_headers


def test_human_payload_uses_integer_minor_units_and_unique_keys():
    first = human_payment()
    second = human_payment()
    assert first["amount_minor"] == 12550
    assert "amount" not in first
    assert first["channel"] == "human"
    assert first["intent"] is None
    assert first["idempotency_key"] != second["idempotency_key"]
    assert first["customer_id"] != second["customer_id"]
    assert payment_headers()["X-API-Key"] == "sk_test_demo"
