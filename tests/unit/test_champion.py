from __future__ import annotations

from unittest.mock import patch

from payment_platform.champion.columns import vector_to_row
from payment_platform.champion.dataset import synthetic_ieee_like
from payment_platform.champion.model import XGBoostChampion
from payment_platform.champion.train import train_and_save
from payment_platform.contracts import PaymentAttempt
from payment_platform.features.vector import FeatureVector
from payment_platform.fraud import band_for_score


def _attempt() -> PaymentAttempt:
    return PaymentAttempt(
        idempotency_key="k",
        customer_id="c",
        merchant_id="m",
        amount_minor=12550,
        currency="USD",
        merchant_category="5411",
        country="US",
        channel="human",
        agent_id=None,
        intent=None,
        device_id="dev_ok",
    )


def _features(**overrides) -> FeatureVector:
    payload = dict(
        amount_minor=12550,
        merchant_category="5411",
        channel="human",
        hour_of_day=12,
        currency="USD",
        attempt_1h=1,
        attempt_24h=1,
        approved_amount_minor_24h=0,
        txn_count_30d=3,
        avg_amount_30d=8000.0,
        unique_merchants_30d=2,
        days_since_last_txn=2.0,
        account_age_days=40.0,
        merchant_avg_amount=9000.0,
        merchant_fraud_rate=0.01,
        merchant_high_risk=False,
        home_country_match=True,
        new_device=False,
        customers_on_device_24h=1,
        intent_valid=None,
        agent_txn_count=None,
        source="redis",
    )
    payload.update(overrides)
    return FeatureVector(**payload)


def test_time_ordered_split_is_monotonic():
    _x, _y, timestamps = synthetic_ieee_like(n=200, seed=1)
    assert list(timestamps) == sorted(timestamps)


def test_trained_champion_scores_low_risk_below_high_risk(tmp_path):
    from payment_platform.champion import train as train_mod

    dest = tmp_path / "champion.json"
    with patch.object(train_mod, "model_path", return_value=dest):
        with patch.object(train_mod, "metrics_path", return_value=tmp_path / "metrics.json"):
            metrics = train_and_save(n=1200, seed=3)
    assert metrics["split"] == "time-ordered-80-20"
    assert metrics["hot_path"] == "xgboost-champion-only"
    assert "auc_roc" in metrics
    champion = XGBoostChampion.load(dest, timeout_ms=200)
    low = champion.score(_attempt(), _features())
    high = champion.score(
        _attempt(),
        _features(
            amount_minor=60_000,
            new_device=True,
            attempt_1h=10,
            merchant_high_risk=True,
            merchant_fraud_rate=0.25,
        ),
    )
    assert low.score is not None and high.score is not None
    assert high.score >= low.score
    assert low.reason == "xgboost_champion"


def test_timeout_returns_unknown(tmp_path):
    from payment_platform.champion import train as train_mod

    dest = tmp_path / "champion.json"
    with patch.object(train_mod, "model_path", return_value=dest):
        with patch.object(train_mod, "metrics_path", return_value=tmp_path / "metrics.json"):
            train_and_save(n=400, seed=2)
    champion = XGBoostChampion.load(dest, timeout_ms=1)

    def _slow(matrix):
        import time

        time.sleep(0.05)
        return [0.1]

    champion._booster.predict = _slow  # type: ignore[method-assign]
    result = champion.score(_attempt(), _features())
    assert result.band == "UNKNOWN"
    assert result.reason == "timeout"


def test_band_helper_still_maps_critical():
    assert band_for_score(0.97) == "CRITICAL"


def test_vector_row_width_matches_model_columns():
    row = vector_to_row(_features())
    from payment_platform.champion.columns import FEATURE_NAMES

    assert len(row) == len(FEATURE_NAMES)


def test_shap_names_features_and_is_not_used_by_score(tmp_path):
    from payment_platform.champion import train as train_mod

    dest = tmp_path / "champion.json"
    with patch.object(train_mod, "model_path", return_value=dest):
        with patch.object(train_mod, "metrics_path", return_value=tmp_path / "metrics.json"):
            train_and_save(n=400, seed=4)
    champion = XGBoostChampion.load(dest, timeout_ms=200)
    with patch("shap.TreeExplainer") as explainer:
        scored = champion.score(_attempt(), _features())
        explainer.assert_not_called()
    assert scored.reason == "xgboost_champion"
    values = champion.shap_values(_features())
    from payment_platform.champion.columns import FEATURE_NAMES

    assert [row["feature"] for row in values] == FEATURE_NAMES
    assert all(isinstance(row["shap"], float) for row in values)
