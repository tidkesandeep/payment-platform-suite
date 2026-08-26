"""Rebuild Redis profile hashes from Postgres. Never overwrites vel:* INCR keys."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from redis import Redis

from payment_platform.db import PostgresStore
from payment_platform.features.vector import HIGH_RISK_MCCS

TTL_30D = 30 * 86400
TTL_24H = 86400


class FeatureRebuild:
    """Gold-shaped rebuild from the transaction store until the lakehouse exists."""

    def __init__(self, db: PostgresStore, redis: Redis):
        self._db = db
        self._redis = redis

    def run(self) -> dict[str, int]:
        rows = self._db.list_transactions_for_features()
        payloads = self._db.list_payment_outbox_payloads()
        device_by_txn = _devices_from_outbox(payloads)
        customers: dict[str, dict[str, Any]] = {}
        merchants: dict[str, dict[str, Any]] = {}
        merchant_sets: dict[str, set[str]] = defaultdict(set)
        devices: dict[str, dict[str, Any]] = {}
        device_customers: dict[str, set[str]] = defaultdict(set)

        for row in rows:
            customer_id = row["customer_id"]
            merchant_id = row["merchant_id"]
            amount = int(row["amount_minor"])
            received = row["received_at"]
            ts = received.timestamp() if hasattr(received, "timestamp") else datetime.now(timezone.utc).timestamp()
            cust = customers.setdefault(
                customer_id,
                {"first_seen": ts, "txn_count_30d": 0, "amount_sum_30d": 0, "last_txn_at": ts, "last_country": ""},
            )
            cust["txn_count_30d"] += 1
            cust["amount_sum_30d"] += amount
            cust["last_txn_at"] = ts
            cust["first_seen"] = min(float(cust["first_seen"]), ts)
            extra = device_by_txn.get(row["transaction_id"], {})
            if extra.get("country"):
                cust["last_country"] = extra["country"]
            merchant_sets[customer_id].add(merchant_id)

            mer = merchants.setdefault(
                merchant_id, {"txn_count": 0, "amount_sum": 0, "decline_count": 0, "high_risk": "0"}
            )
            mer["txn_count"] += 1
            mer["amount_sum"] += amount
            if row.get("fraud_band") in {"HIGH", "CRITICAL"}:
                mer["decline_count"] += 1
            if extra.get("merchant_category") in HIGH_RISK_MCCS:
                mer["high_risk"] = "1"

            device_id = extra.get("device_id")
            if device_id:
                dev = devices.setdefault(device_id, {"first_seen": ts})
                dev["first_seen"] = min(float(dev["first_seen"]), ts)
                device_customers[device_id].add(customer_id)

        pipe = self._redis.pipeline()
        for customer_id, fields in customers.items():
            key = f"cust:{customer_id}"
            pipe.delete(key)
            pipe.hset(
                key,
                mapping={k: str(v) for k, v in fields.items()},
            )
            pipe.expire(key, TTL_30D)
            mer_key = f"cust:{customer_id}:merchants"
            pipe.delete(mer_key)
            if merchant_sets[customer_id]:
                pipe.sadd(mer_key, *merchant_sets[customer_id])
                pipe.expire(mer_key, TTL_30D)
        for merchant_id, fields in merchants.items():
            key = f"mer:{merchant_id}"
            pipe.delete(key)
            pipe.hset(key, mapping={k: str(v) for k, v in fields.items()})
            pipe.expire(key, TTL_30D)
        for device_id, fields in devices.items():
            key = f"dev:{device_id}"
            pipe.delete(key)
            pipe.hset(key, mapping={k: str(v) for k, v in fields.items()})
            pipe.expire(key, TTL_30D)
            ckey = f"dev:{device_id}:customers"
            pipe.delete(ckey)
            if device_customers[device_id]:
                pipe.sadd(ckey, *device_customers[device_id])
                pipe.expire(ckey, TTL_24H)
        pipe.execute()
        return {
            "customers": len(customers),
            "merchants": len(merchants),
            "devices": len(devices),
            "velocity_keys_written": 0,
        }


def _devices_from_outbox(payloads: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    for payload in payloads:
        txn = payload.get("transaction_id")
        if not txn:
            continue
        request = payload.get("request") or {}
        found[str(txn)] = {
            "device_id": str(request.get("device_id") or ""),
            "country": str(request.get("country") or ""),
            "merchant_category": str(request.get("merchant_category") or payload.get("merchant_category") or ""),
        }
    return found
