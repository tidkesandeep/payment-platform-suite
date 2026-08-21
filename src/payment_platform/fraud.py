"""Fraud bands and the test-only champion stub. Production scoring is XGBoostChampion."""

from __future__ import annotations

from typing import Protocol

from payment_platform.contracts import FraudBand, FraudResult, PaymentAttempt
from payment_platform.features.vector import FeatureVector

LOW_MAX = 0.20
MEDIUM_MAX = 0.70
HIGH_MAX = 0.95


class Scorer(Protocol):
    def score(self, attempt: PaymentAttempt, features: FeatureVector | None = None) -> FraudResult: ...


def band_for_score(score: float | None) -> str:
    if score is None:
        return FraudBand.UNKNOWN.value
    if score < LOW_MAX:
        return FraudBand.LOW.value
    if score < MEDIUM_MAX:
        return FraudBand.MEDIUM.value
    if score < HIGH_MAX:
        return FraudBand.HIGH.value
    return FraudBand.CRITICAL.value


class StubChampionScorer:
    """Maps device_id prefixes to bands so tests can drive H / H2 without ML."""

    def score(self, attempt: PaymentAttempt, features: FeatureVector | None = None) -> FraudResult:
        device = attempt.device_id or ""
        if device.startswith("dev_timeout") or device.startswith("unk_"):
            return FraudResult(score=None, band=FraudBand.UNKNOWN.value, reason="timeout")
        if device.startswith("dev_critical") or device.startswith("crit_"):
            score = 0.97
        elif device.startswith("dev_high") or device.startswith("high_"):
            score = 0.80
        elif device.startswith("dev_medium") or device.startswith("med_"):
            score = 0.35
        elif features is not None and features.merchant_high_risk:
            score = 0.35
        else:
            score = 0.08
        reason = "stub_champion"
        if features is not None:
            reason = f"stub_champion:{features.source}"
        return FraudResult(score=score, band=band_for_score(score), reason=reason)
