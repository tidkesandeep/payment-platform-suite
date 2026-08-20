from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from psycopg import Connection
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from payment_platform.contracts import IdempotencyStatus, PaymentAttempt
from payment_platform.ids import new_ulid

def _schema_path() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        here.parent / "schema.sql",
        here.parents[2] / "sql" / "init.sql",
        Path.cwd() / "sql" / "init.sql",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("schema.sql / sql/init.sql")


class ClaimOutcome:
    REPLAY = "replay"
    CONFLICT = "conflict"
    MISMATCH = "mismatch"
    CLAIMED = "claimed"


@dataclass
class ClaimResult:
    outcome: str
    transaction_id: str
    decision: dict[str, Any] | None = None
    fingerprint: str | None = None


class PostgresStore:
    def __init__(self, dsn: str):
        self._pool = ConnectionPool(
            dsn, min_size=1, max_size=8, open=True, kwargs={"row_factory": dict_row}
        )

    def close(self) -> None:
        self._pool.close()

    def ping(self) -> bool:
        with self._pool.connection() as conn:
            conn.execute("SELECT 1")
        return True

    def ensure_schema(self) -> None:
        sql = _schema_path().read_text(encoding="utf-8")
        with self._pool.connection() as conn:
            for statement in _sql_statements(sql):
                conn.execute(statement)

    def resolve_api_key(self, secret: str, configured_secret: str, configured_id: str) -> str | None:
        if secret == configured_secret:
            return configured_id
        digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT api_key_id FROM api_keys WHERE secret_hash = %s",
                (digest,),
            ).fetchone()
        if row is None:
            return None
        return row["api_key_id"]

    def claim(
        self,
        *,
        api_key_id: str,
        idempotency_key: str,
        fingerprint: str,
        lease_seconds: int,
    ) -> ClaimResult:
        now = datetime.now(timezone.utc)
        lease_until = now + timedelta(seconds=lease_seconds)
        transaction_id = new_ulid()
        with self._pool.connection() as conn:
            conn.execute("BEGIN")
            try:
                row = conn.execute(
                    """
                    SELECT api_key_id, key, transaction_id, fingerprint, status,
                           lease_expires_at, decision_json
                    FROM idempotency_keys
                    WHERE api_key_id = %s AND key = %s
                    FOR UPDATE
                    """,
                    (api_key_id, idempotency_key),
                ).fetchone()
                if row is None:
                    try:
                        conn.execute(
                            """
                            INSERT INTO idempotency_keys (
                                api_key_id, key, transaction_id, fingerprint, status,
                                lease_expires_at, decision_json, created_at, updated_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, NULL, %s, %s)
                            """,
                            (
                                api_key_id,
                                idempotency_key,
                                transaction_id,
                                fingerprint,
                                IdempotencyStatus.IN_PROGRESS.value,
                                lease_until,
                                now,
                                now,
                            ),
                        )
                    except UniqueViolation:
                        conn.execute("ROLLBACK")
                        return self.claim(
                            api_key_id=api_key_id,
                            idempotency_key=idempotency_key,
                            fingerprint=fingerprint,
                            lease_seconds=lease_seconds,
                        )
                    conn.execute("COMMIT")
                    return ClaimResult(
                        outcome=ClaimOutcome.CLAIMED,
                        transaction_id=transaction_id,
                        fingerprint=fingerprint,
                    )

                if row["fingerprint"] != fingerprint:
                    conn.execute("COMMIT")
                    return ClaimResult(
                        outcome=ClaimOutcome.MISMATCH,
                        transaction_id=row["transaction_id"],
                        fingerprint=row["fingerprint"],
                    )

                if row["status"] == IdempotencyStatus.TERMINAL.value:
                    conn.execute("COMMIT")
                    return ClaimResult(
                        outcome=ClaimOutcome.REPLAY,
                        transaction_id=row["transaction_id"],
                        decision=row["decision_json"],
                        fingerprint=row["fingerprint"],
                    )

                lease = row["lease_expires_at"]
                if lease is not None and lease > now:
                    conn.execute("COMMIT")
                    return ClaimResult(
                        outcome=ClaimOutcome.CONFLICT,
                        transaction_id=row["transaction_id"],
                    )

                conn.execute(
                    """
                    UPDATE idempotency_keys
                    SET status = %s, lease_expires_at = %s, updated_at = %s
                    WHERE api_key_id = %s AND key = %s
                    """,
                    (
                        IdempotencyStatus.IN_PROGRESS.value,
                        lease_until,
                        now,
                        api_key_id,
                        idempotency_key,
                    ),
                )
                conn.execute("COMMIT")
                return ClaimResult(
                    outcome=ClaimOutcome.CLAIMED,
                    transaction_id=row["transaction_id"],
                    fingerprint=fingerprint,
                )
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def complete(
        self,
        *,
        api_key_id: str,
        attempt: PaymentAttempt | None,
        transaction_id: str,
        state: str,
        authorization_status: str | None,
        fraud_score: float | None,
        fraud_band: str | None,
        policy_status: str | None,
        policy_violations: list[str] | None,
        decision: dict[str, Any],
        received_at: datetime,
        customer_id: str,
        merchant_id: str,
        amount_minor: int,
        currency: str,
        channel: str,
        idempotency_key: str,
    ) -> None:
        event_id = new_ulid()
        now = datetime.now(timezone.utc)
        payments_payload = {
            "schema_version": 1,
            "event_id": event_id,
            "transaction_id": transaction_id,
            "state": state,
            "customer_id": customer_id,
            "merchant_id": merchant_id,
            "amount_minor": amount_minor,
            "currency": currency,
            "channel": channel,
            "decision": decision,
            "received_at": received_at.isoformat(),
        }
        if attempt is not None:
            payments_payload["request"] = attempt.as_dict()
        states_payload = {
            "schema_version": 1,
            "event_id": event_id,
            "transaction_id": transaction_id,
            "state": state,
            "received_at": received_at.isoformat(),
        }
        with self._pool.connection() as conn:
            conn.execute("BEGIN")
            try:
                conn.execute(
                    """
                    INSERT INTO transactions (
                        transaction_id, idempotency_key, api_key_id, state, channel,
                        customer_id, merchant_id, amount_minor, currency,
                        authorization_status, fraud_score, fraud_band, policy_status,
                        policy_violations, received_at, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    ON CONFLICT (transaction_id) DO UPDATE SET
                        state = EXCLUDED.state,
                        authorization_status = EXCLUDED.authorization_status,
                        fraud_score = EXCLUDED.fraud_score,
                        fraud_band = EXCLUDED.fraud_band,
                        policy_status = EXCLUDED.policy_status,
                        policy_violations = EXCLUDED.policy_violations,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        transaction_id,
                        idempotency_key,
                        api_key_id,
                        state,
                        channel,
                        customer_id,
                        merchant_id,
                        amount_minor,
                        currency,
                        authorization_status,
                        fraud_score,
                        fraud_band,
                        policy_status,
                        Json(policy_violations or []),
                        received_at,
                        now,
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO outbox (event_id, topic, payload, created_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (event_id, topic) DO NOTHING
                    """,
                    (event_id, "payments", Json(payments_payload), now),
                )
                conn.execute(
                    """
                    INSERT INTO outbox (event_id, topic, payload, created_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (event_id, topic) DO NOTHING
                    """,
                    (event_id, "transaction-states", Json(states_payload), now),
                )
                conn.execute(
                    """
                    UPDATE idempotency_keys
                    SET status = %s,
                        lease_expires_at = NULL,
                        decision_json = %s,
                        updated_at = %s
                    WHERE api_key_id = %s AND key = %s
                    """,
                    (
                        IdempotencyStatus.TERMINAL.value,
                        Json(decision),
                        now,
                        api_key_id,
                        idempotency_key,
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def get_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM transactions WHERE transaction_id = %s",
                (transaction_id,),
            ).fetchone()
        return dict(row) if row else None

    def expire_lease(self, api_key_id: str, idempotency_key: str) -> None:
        """Test helper: force the lease into the past so the next POST can reclaim."""
        past = datetime.now(timezone.utc) - timedelta(seconds=1)
        with self._pool.connection() as conn:
            conn.execute(
                """
                UPDATE idempotency_keys
                SET lease_expires_at = %s, status = %s, updated_at = NOW()
                WHERE api_key_id = %s AND key = %s
                """,
                (past, IdempotencyStatus.IN_PROGRESS.value, api_key_id, idempotency_key),
            )
            conn.commit()

    def increment_velocity(
        self,
        customer_id: str,
        *,
        attempt_delta: int,
        approved_count_delta: int,
        approved_amount_delta: int,
    ):
        from payment_platform.velocity import VelocitySnapshot, WINDOW_1H, WINDOW_24H

        now = datetime.now(timezone.utc)
        specs = [
            (f"vel:attempt:{customer_id}:1h", attempt_delta, WINDOW_1H),
            (f"vel:attempt:{customer_id}:24h", attempt_delta, WINDOW_24H),
            (f"vel:approved:{customer_id}:24h", approved_count_delta, WINDOW_24H),
            (f"vel:approved_amount:{customer_id}:24h", approved_amount_delta, WINDOW_24H),
        ]
        with self._pool.connection() as conn:
            values = []
            for key, delta, ttl in specs:
                row = conn.execute(
                    """
                    INSERT INTO velocity_counters (counter_key, value, expires_at, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (counter_key) DO UPDATE SET
                        value = CASE
                            WHEN velocity_counters.expires_at <= EXCLUDED.updated_at THEN EXCLUDED.value
                            ELSE velocity_counters.value + EXCLUDED.value
                        END,
                        expires_at = CASE
                            WHEN velocity_counters.expires_at <= EXCLUDED.updated_at THEN EXCLUDED.expires_at
                            ELSE velocity_counters.expires_at
                        END,
                        updated_at = EXCLUDED.updated_at
                    RETURNING value
                    """,
                    (key, delta, now + timedelta(seconds=ttl), now),
                ).fetchone()
                values.append(int(row["value"]) if row else 0)
        return VelocitySnapshot(
            attempt_1h=values[0],
            attempt_24h=values[1],
            approved_count_24h=values[2],
            approved_amount_minor_24h=values[3],
            available=True,
        )

    def read_velocity(self, customer_id: str):
        from payment_platform.velocity import VelocitySnapshot

        keys = [
            f"vel:attempt:{customer_id}:1h",
            f"vel:attempt:{customer_id}:24h",
            f"vel:approved:{customer_id}:24h",
            f"vel:approved_amount:{customer_id}:24h",
        ]
        now = datetime.now(timezone.utc)
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT counter_key, value FROM velocity_counters
                WHERE counter_key = ANY(%s) AND expires_at > %s
                """,
                (keys, now),
            ).fetchall()
        found = {r["counter_key"]: int(r["value"]) for r in rows}
        return VelocitySnapshot(
            attempt_1h=found.get(keys[0], 0),
            attempt_24h=found.get(keys[1], 0),
            approved_count_24h=found.get(keys[2], 0),
            approved_amount_minor_24h=found.get(keys[3], 0),
            available=True,
        )

    def connection(self) -> Connection:
        return self._pool.connection()


def _sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(buf).strip()
            if statement:
                statements.append(statement)
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements
