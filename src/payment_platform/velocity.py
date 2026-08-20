from __future__ import annotations

from redis import Redis
from redis.exceptions import RedisError

from payment_platform.contracts import VelocitySnapshot

WINDOW_1H = 3600
WINDOW_24H = 86400


class VelocityStore:
    def __init__(self, redis: Redis | None, db: "PostgresStore | None" = None):
        self._redis = redis
        self._db = db

    def increment_attempt(self, customer_id: str) -> VelocitySnapshot:
        return self._incr(
            customer_id,
            attempt_delta=1,
            approved_count_delta=0,
            approved_amount_delta=0,
        )

    def increment_approved(self, customer_id: str, amount_minor: int) -> VelocitySnapshot:
        return self._incr(
            customer_id,
            attempt_delta=0,
            approved_count_delta=1,
            approved_amount_delta=amount_minor,
        )

    def snapshot(self, customer_id: str) -> VelocitySnapshot:
        try:
            return self._read_redis(customer_id)
        except (RedisError, OSError):
            if self._db is not None:
                try:
                    return self._db.read_velocity(customer_id)
                except Exception:
                    return _unavailable()
            return _unavailable()

    def _incr(
        self,
        customer_id: str,
        *,
        attempt_delta: int,
        approved_count_delta: int,
        approved_amount_delta: int,
    ) -> VelocitySnapshot:
        try:
            if self._redis is None:
                raise RedisError("redis disabled")
            pipe = self._redis.pipeline()
            keys = _keys(customer_id)
            if attempt_delta:
                pipe.incrby(keys["attempt_1h"], attempt_delta)
                pipe.expire(keys["attempt_1h"], WINDOW_1H, nx=True)
                pipe.incrby(keys["attempt_24h"], attempt_delta)
                pipe.expire(keys["attempt_24h"], WINDOW_24H, nx=True)
            if approved_count_delta:
                pipe.incrby(keys["approved_count_24h"], approved_count_delta)
                pipe.expire(keys["approved_count_24h"], WINDOW_24H, nx=True)
            if approved_amount_delta:
                pipe.incrby(keys["approved_amount_24h"], approved_amount_delta)
                pipe.expire(keys["approved_amount_24h"], WINDOW_24H, nx=True)
            pipe.get(keys["attempt_1h"])
            pipe.get(keys["attempt_24h"])
            pipe.get(keys["approved_count_24h"])
            pipe.get(keys["approved_amount_24h"])
            results = pipe.execute()
            tail = results[-4:]
            return VelocitySnapshot(
                attempt_1h=_as_int(tail[0]),
                attempt_24h=_as_int(tail[1]),
                approved_count_24h=_as_int(tail[2]),
                approved_amount_minor_24h=_as_int(tail[3]),
                available=True,
            )
        except (RedisError, OSError):
            if self._db is None:
                return _unavailable()
            try:
                return self._db.increment_velocity(
                    customer_id,
                    attempt_delta=attempt_delta,
                    approved_count_delta=approved_count_delta,
                    approved_amount_delta=approved_amount_delta,
                )
            except Exception:
                return _unavailable()

    def _read_redis(self, customer_id: str) -> VelocitySnapshot:
        if self._redis is None:
            raise RedisError("redis disabled")
        keys = _keys(customer_id)
        values = self._redis.mget(
            keys["attempt_1h"],
            keys["attempt_24h"],
            keys["approved_count_24h"],
            keys["approved_amount_24h"],
        )
        return VelocitySnapshot(
            attempt_1h=_as_int(values[0]),
            attempt_24h=_as_int(values[1]),
            approved_count_24h=_as_int(values[2]),
            approved_amount_minor_24h=_as_int(values[3]),
            available=True,
        )


def _keys(customer_id: str) -> dict[str, str]:
    return {
        "attempt_1h": f"vel:attempt:{customer_id}:1h",
        "attempt_24h": f"vel:attempt:{customer_id}:24h",
        "approved_count_24h": f"vel:approved:{customer_id}:24h",
        "approved_amount_24h": f"vel:approved_amount:{customer_id}:24h",
    }


def _as_int(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, bytes):
        return int(value)
    return int(value)


def _unavailable() -> VelocitySnapshot:
    return VelocitySnapshot(
        attempt_1h=0,
        attempt_24h=0,
        approved_count_24h=0,
        approved_amount_minor_24h=0,
        available=False,
    )


# Imported at runtime to avoid a cycle in type hints.
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from payment_platform.db import PostgresStore
