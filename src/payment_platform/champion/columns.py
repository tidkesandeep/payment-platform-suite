from __future__ import annotations

from pathlib import Path

from payment_platform.features.vector import FeatureVector

MODEL_NAME = "champion.json"


def model_path() -> Path:
    return Path(__file__).resolve().parent / MODEL_NAME


def metrics_path() -> Path:
    return Path(__file__).resolve().parent / "metrics.json"


FEATURE_NAMES = [
    "amount_minor",
    "hour_of_day",
    "attempt_1h",
    "attempt_24h",
    "approved_amount_minor_24h",
    "txn_count_30d",
    "avg_amount_30d",
    "unique_merchants_30d",
    "days_since_last_txn",
    "account_age_days",
    "merchant_avg_amount",
    "merchant_fraud_rate",
    "merchant_high_risk",
    "home_country_match",
    "new_device",
    "customers_on_device_24h",
    "intent_valid",
    "agent_channel",
    "agent_txn_count",
]


def vector_to_row(features: FeatureVector) -> list[float]:
    return [
        float(features.amount_minor),
        float(features.hour_of_day),
        float(features.attempt_1h),
        float(features.attempt_24h),
        float(features.approved_amount_minor_24h),
        float(features.txn_count_30d),
        float(features.avg_amount_30d),
        float(features.unique_merchants_30d),
        float(features.days_since_last_txn if features.days_since_last_txn is not None else -1.0),
        float(features.account_age_days if features.account_age_days is not None else -1.0),
        float(features.merchant_avg_amount),
        float(features.merchant_fraud_rate),
        1.0 if features.merchant_high_risk else 0.0,
        -1.0 if features.home_country_match is None else (1.0 if features.home_country_match else 0.0),
        1.0 if features.new_device else 0.0,
        float(features.customers_on_device_24h),
        -1.0 if features.intent_valid is None else (1.0 if features.intent_valid else 0.0),
        1.0 if features.channel == "agent" else 0.0,
        float(features.agent_txn_count if features.agent_txn_count is not None else -1.0),
    ]


def attempt_to_row(amount_minor: int, *, hour: int = 12, high_risk: bool = False, agent: bool = False) -> list[float]:
    return [
        float(amount_minor),
        float(hour),
        1.0,
        1.0,
        0.0,
        1.0,
        float(amount_minor),
        1.0,
        -1.0,
        0.0,
        float(amount_minor),
        0.0,
        1.0 if high_risk else 0.0,
        1.0,
        1.0,
        1.0,
        -1.0 if not agent else 1.0,
        1.0 if agent else 0.0,
        -1.0,
    ]
