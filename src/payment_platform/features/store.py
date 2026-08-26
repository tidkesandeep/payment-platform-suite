"""Online Redis features for /v1/payments. Velocity INCR stays the SoR for attempt/approved."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from payment_platform.contracts import IntentResult, PaymentAttempt, VelocitySnapshot
from payment_platform.features.vector import HIGH_RISK_MCCS, FeatureVector

TTL_30D = 30 * 86400
TTL_24H = 86400


class FeatureStore:
    def __init__(self, redis: Redis | None):
        self._redis = redis

    def materialize(
        self,
        attempt: PaymentAttempt,
        velocity: VelocitySnapshot,
        *,
        received_at: datetime,
        intent: IntentResult | None = None,
    ) -> FeatureVector:
        hour = received_at.astimezone(timezone.utc).hour if received_at.tzinfo else received_at.hour
        base = FeatureVector(
            amount_minor=attempt.amount_minor,
            merchant_category=attempt.merchant_category,
            channel=attempt.channel,
            hour_of_day=hour,
            currency=attempt.currency,
            attempt_1h=velocity.attempt_1h,
            attempt_24h=velocity.attempt_24h,
            approved_amount_minor_24h=velocity.approved_amount_minor_24h,
            txn_count_30d=0,
            avg_amount_30d=0.0,
            unique_merchants_30d=0,
            days_since_last_txn=None,
            account_age_days=None,
            merchant_avg_amount=0.0,
            merchant_fraud_rate=0.0,
            merchant_high_risk=attempt.merchant_category in HIGH_RISK_MCCS,
            home_country_match=None,
            new_device=True,
            customers_on_device_24h=0,
            intent_valid=_intent_valid(attempt, intent),
            agent_txn_count=None,
            source="empty",
        )
        if self._redis is None:
            return base
        try:
            vector = self._read_and_write(attempt, received_at, base)
            vector.source = "redis"
            return vector
        except (RedisError, OSError):
            base.source = "empty"
            return base

    def _read_and_write(
        self,
        attempt: PaymentAttempt,
        received_at: datetime,
        base: FeatureVector,
    ) -> FeatureVector:
        redis = self._redis
        assert redis is not None
        now_ts = received_at.timestamp()
        cust_key = f"cust:{attempt.customer_id}"
        mer_key = f"mer:{attempt.merchant_id}"
        mer_set = f"cust:{attempt.customer_id}:merchants"
        cust = redis.hgetall(cust_key)
        mer = redis.hgetall(mer_key)
        prior_count = _as_int(cust.get("txn_count_30d"))
        prior_sum = _as_int(cust.get("amount_sum_30d"))
        last_txn = _as_float(cust.get("last_txn_at"))
        first_seen = _as_float(cust.get("first_seen"))
        last_country = cust.get("last_country") or None
        mer_count = _as_int(mer.get("txn_count"))
        mer_sum = _as_int(mer.get("amount_sum"))
        mer_bad = _as_int(mer.get("decline_count"))

        unique_before = redis.scard(mer_set)
        new_device = True
        customers_24h = 0
        if attempt.device_id:
            dev_key = f"dev:{attempt.device_id}"
            new_device = redis.hsetnx(dev_key, "first_seen", str(now_ts)) == 1
            redis.expire(dev_key, TTL_30D)
            cust_set = f"dev:{attempt.device_id}:customers"
            redis.sadd(cust_set, attempt.customer_id)
            redis.expire(cust_set, TTL_24H)
            customers_24h = int(redis.scard(cust_set))

        agent_count = None
        if attempt.channel == "agent" and attempt.agent_id:
            agent_key = f"agent:{attempt.agent_id}"
            agent_count = _as_int(redis.hget(agent_key, "txn_count"))
            pipe = redis.pipeline()
            pipe.hsetnx(agent_key, "first_seen", str(now_ts))
            pipe.hincrby(agent_key, "txn_count", 1)
            if base.intent_valid is not None:
                pipe.hset(agent_key, "last_intent_status", "VALID" if base.intent_valid else "INVALID")
            pipe.expire(agent_key, TTL_30D)
            pipe.execute()
            agent_count = (agent_count or 0) + 1

        txn_count = prior_count + 1
        amount_sum = prior_sum + attempt.amount_minor
        avg = amount_sum / txn_count if txn_count else 0.0
        mer_txn = mer_count + 1
        mer_amount = mer_sum + attempt.amount_minor
        mer_avg = mer_amount / mer_txn if mer_txn else 0.0
        fraud_rate = mer_bad / mer_count if mer_count else 0.0

        home_match = None
        if last_country and attempt.country:
            home_match = last_country == attempt.country
        elif attempt.country:
            home_match = True

        days_since = None if last_txn is None else max(0.0, (now_ts - last_txn) / 86400.0)
        age_days = None if first_seen is None else max(0.0, (now_ts - first_seen) / 86400.0)
        if first_seen is None:
            age_days = 0.0

        pipe = redis.pipeline()
        pipe.hsetnx(cust_key, "first_seen", str(now_ts))
        pipe.hincrby(cust_key, "txn_count_30d", 1)
        pipe.hincrby(cust_key, "amount_sum_30d", attempt.amount_minor)
        pipe.hset(cust_key, mapping={"last_txn_at": str(now_ts), "last_country": attempt.country or ""})
        pipe.expire(cust_key, TTL_30D)
        pipe.sadd(mer_set, attempt.merchant_id)
        pipe.expire(mer_set, TTL_30D)
        pipe.hincrby(mer_key, "txn_count", 1)
        pipe.hincrby(mer_key, "amount_sum", attempt.amount_minor)
        pipe.hset(mer_key, "high_risk", "1" if base.merchant_high_risk else "0")
        pipe.expire(mer_key, TTL_30D)
        pipe.execute()
        unique_after = int(redis.scard(mer_set))

        return FeatureVector(
            amount_minor=base.amount_minor,
            merchant_category=base.merchant_category,
            channel=base.channel,
            hour_of_day=base.hour_of_day,
            currency=base.currency,
            attempt_1h=base.attempt_1h,
            attempt_24h=base.attempt_24h,
            approved_amount_minor_24h=base.approved_amount_minor_24h,
            txn_count_30d=txn_count,
            avg_amount_30d=avg,
            unique_merchants_30d=unique_after if unique_after else int(unique_before) + 1,
            days_since_last_txn=days_since,
            account_age_days=age_days,
            merchant_avg_amount=mer_avg,
            merchant_fraud_rate=fraud_rate,
            merchant_high_risk=base.merchant_high_risk,
            home_country_match=home_match,
            new_device=bool(new_device),
            customers_on_device_24h=customers_24h,
            intent_valid=base.intent_valid,
            agent_txn_count=agent_count,
            source="redis",
        )


def _intent_valid(attempt: PaymentAttempt, intent: IntentResult | None) -> bool | None:
    if attempt.channel != "agent":
        return None
    if intent is None:
        return False
    return intent.status in {"VALID"}


def _as_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(value)


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
