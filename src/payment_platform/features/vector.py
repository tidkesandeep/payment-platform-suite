from __future__ import annotations

from dataclasses import dataclass


HIGH_RISK_MCCS = frozenset({"7995"})


@dataclass
class FeatureVector:
    amount_minor: int
    merchant_category: str
    channel: str
    hour_of_day: int
    currency: str
    attempt_1h: int
    attempt_24h: int
    approved_amount_minor_24h: int
    txn_count_30d: int
    avg_amount_30d: float
    unique_merchants_30d: int
    days_since_last_txn: float | None
    account_age_days: float | None
    merchant_avg_amount: float
    merchant_fraud_rate: float
    merchant_high_risk: bool
    home_country_match: bool | None
    new_device: bool
    customers_on_device_24h: int
    intent_valid: bool | None
    agent_txn_count: int | None
    source: str = "redis"

    def as_dict(self) -> dict:
        return {
            "amount_minor": self.amount_minor,
            "merchant_category": self.merchant_category,
            "channel": self.channel,
            "hour_of_day": self.hour_of_day,
            "currency": self.currency,
            "attempt_1h": self.attempt_1h,
            "attempt_24h": self.attempt_24h,
            "approved_amount_minor_24h": self.approved_amount_minor_24h,
            "txn_count_30d": self.txn_count_30d,
            "avg_amount_30d": self.avg_amount_30d,
            "unique_merchants_30d": self.unique_merchants_30d,
            "days_since_last_txn": self.days_since_last_txn,
            "account_age_days": self.account_age_days,
            "merchant_avg_amount": self.merchant_avg_amount,
            "merchant_fraud_rate": self.merchant_fraud_rate,
            "merchant_high_risk": self.merchant_high_risk,
            "home_country_match": self.home_country_match,
            "new_device": self.new_device,
            "customers_on_device_24h": self.customers_on_device_24h,
            "intent_valid": self.intent_valid,
            "agent_txn_count": self.agent_txn_count,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FeatureVector":
        return cls(
            amount_minor=int(data.get("amount_minor") or 0),
            merchant_category=str(data.get("merchant_category") or ""),
            channel=str(data.get("channel") or "human"),
            hour_of_day=int(data.get("hour_of_day") or 0),
            currency=str(data.get("currency") or "USD"),
            attempt_1h=int(data.get("attempt_1h") or 0),
            attempt_24h=int(data.get("attempt_24h") or 0),
            approved_amount_minor_24h=int(data.get("approved_amount_minor_24h") or 0),
            txn_count_30d=int(data.get("txn_count_30d") or 0),
            avg_amount_30d=float(data.get("avg_amount_30d") or 0),
            unique_merchants_30d=int(data.get("unique_merchants_30d") or 0),
            days_since_last_txn=data.get("days_since_last_txn"),
            account_age_days=data.get("account_age_days"),
            merchant_avg_amount=float(data.get("merchant_avg_amount") or 0),
            merchant_fraud_rate=float(data.get("merchant_fraud_rate") or 0),
            merchant_high_risk=bool(data.get("merchant_high_risk")),
            home_country_match=data.get("home_country_match"),
            new_device=bool(data.get("new_device")),
            customers_on_device_24h=int(data.get("customers_on_device_24h") or 0),
            intent_valid=data.get("intent_valid"),
            agent_txn_count=data.get("agent_txn_count"),
            source=str(data.get("source") or "redis"),
        )
