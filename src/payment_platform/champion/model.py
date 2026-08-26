"""In-process XGBoost champion. Sole scorer on /v1/payments. No model blend."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path

import numpy as np
import xgboost as xgb

from payment_platform.champion.columns import FEATURE_NAMES, model_path, vector_to_row
from payment_platform.contracts import FraudResult, PaymentAttempt
from payment_platform.features.vector import FeatureVector
from payment_platform.fraud import band_for_score


class XGBoostChampion:
    def __init__(self, booster: xgb.Booster, *, timeout_ms: int = 20):
        self._booster = booster
        self._timeout_s = timeout_ms / 1000.0
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="xgb")

    @classmethod
    def load(cls, path: Path | None = None, *, timeout_ms: int = 20) -> "XGBoostChampion":
        booster = xgb.Booster()
        booster.load_model(str(path or model_path()))
        booster.set_param({"nthread": 1})
        dummy = xgb.DMatrix(
            np.zeros((1, len(FEATURE_NAMES)), dtype=np.float32),
            feature_names=FEATURE_NAMES,
        )
        booster.predict(dummy)
        return cls(booster, timeout_ms=timeout_ms)

    def score(self, attempt: PaymentAttempt, features: FeatureVector | None = None) -> FraudResult:
        row = vector_to_row(features) if features is not None else vector_to_row(_from_attempt(attempt))
        matrix = xgb.DMatrix(np.array([row], dtype=np.float32), feature_names=FEATURE_NAMES)
        try:
            future = self._pool.submit(self._booster.predict, matrix)
            proba = float(future.result(timeout=self._timeout_s)[0])
        except FuturesTimeout:
            return FraudResult(score=None, band=band_for_score(None), reason="timeout")
        except Exception:
            return FraudResult(score=None, band=band_for_score(None), reason="model_error")
        proba = min(1.0, max(0.0, proba))
        return FraudResult(score=proba, band=band_for_score(proba), reason="xgboost_champion")

    def shap_values(self, features: FeatureVector) -> list[dict[str, float | str]]:
        import shap

        row = np.array([vector_to_row(features)], dtype=np.float32)
        explainer = shap.TreeExplainer(self._booster)
        values = explainer.shap_values(row)
        if isinstance(values, list):
            values = values[1] if len(values) > 1 else values[0]
        flat = values[0]
        return [
            {"feature": name, "shap": float(flat[i])}
            for i, name in enumerate(FEATURE_NAMES)
        ]


def _from_attempt(attempt: PaymentAttempt) -> FeatureVector:
    from datetime import datetime, timezone

    hour = datetime.now(timezone.utc).hour
    return FeatureVector(
        amount_minor=attempt.amount_minor,
        merchant_category=attempt.merchant_category,
        channel=attempt.channel,
        hour_of_day=hour,
        currency=attempt.currency,
        attempt_1h=1,
        attempt_24h=1,
        approved_amount_minor_24h=0,
        txn_count_30d=1,
        avg_amount_30d=float(attempt.amount_minor),
        unique_merchants_30d=1,
        days_since_last_txn=None,
        account_age_days=0.0,
        merchant_avg_amount=float(attempt.amount_minor),
        merchant_fraud_rate=0.0,
        merchant_high_risk=attempt.merchant_category == "7995",
        home_country_match=True,
        new_device=True,
        customers_on_device_24h=1,
        intent_valid=None if attempt.channel != "agent" else False,
        agent_txn_count=None,
        source="attempt",
    )
