from datetime import datetime, timezone

from payment_platform.contracts import PaymentAttempt, VelocitySnapshot
from payment_platform.features.store import FeatureStore
from payment_platform.features.vector import FeatureVector
from payment_platform.fraud import StubChampionScorer


def _attempt(**overrides) -> PaymentAttempt:
    payload = dict(
        idempotency_key="k",
        customer_id="c",
        merchant_id="m",
        amount_minor=100,
        currency="USD",
        merchant_category="5411",
        country="US",
        channel="human",
        agent_id=None,
        intent=None,
        device_id="dev_ok",
    )
    payload.update(overrides)
    return PaymentAttempt(**payload)


def test_empty_store_still_returns_transaction_features():
    store = FeatureStore(None)
    velocity = VelocitySnapshot(1, 1, 0, 0, available=True)
    vector = store.materialize(
        _attempt(),
        velocity,
        received_at=datetime(2026, 8, 21, 15, 0, tzinfo=timezone.utc),
    )
    assert vector.source == "empty"
    assert vector.hour_of_day == 15
    assert vector.attempt_1h == 1


def test_scorer_uses_feature_high_risk_when_no_device_override():
    features = FeatureVector(
        amount_minor=100,
        merchant_category="7995",
        channel="human",
        hour_of_day=1,
        currency="USD",
        attempt_1h=1,
        attempt_24h=1,
        approved_amount_minor_24h=0,
        txn_count_30d=1,
        avg_amount_30d=100,
        unique_merchants_30d=1,
        days_since_last_txn=None,
        account_age_days=0,
        merchant_avg_amount=100,
        merchant_fraud_rate=0,
        merchant_high_risk=True,
        home_country_match=True,
        new_device=True,
        customers_on_device_24h=1,
        intent_valid=None,
        agent_txn_count=None,
        source="redis",
    )
    result = StubChampionScorer().score(_attempt(merchant_category="7995"), features)
    assert result.band == "MEDIUM"
    assert result.reason == "stub_champion:redis"
