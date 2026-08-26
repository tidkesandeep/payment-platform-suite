from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time

import httpx
from redis import Redis

from payment_platform.db import PostgresStore

TEST_DSN = os.environ.get(
    "PAYMENTS_TEST_DATABASE_URL",
    "postgresql://payments:payments@127.0.0.1:5432/payments_test",
)
TEST_REDIS = os.environ.get("PAYMENTS_TEST_REDIS_URL", "redis://127.0.0.1:6379/1")


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_locust_measures_tps_and_p95_against_payments(tmp_path):
    db = PostgresStore(TEST_DSN)
    db.ensure_schema()
    with db.connection() as conn:
        conn.execute(
            "TRUNCATE idempotency_keys, transactions, outbox, velocity_counters, intent_nonces"
        )
        conn.commit()
    redis = Redis.from_url(TEST_REDIS, decode_responses=True)
    redis.flushdb()
    port = _free_port()
    env = os.environ.copy()
    env["PAYMENTS_DATABASE_URL"] = TEST_DSN
    env["PAYMENTS_REDIS_URL"] = TEST_REDIS
    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "payment_platform.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "error",
        ],
        env=env,
    )
    host = f"http://127.0.0.1:{port}"
    json_out = tmp_path / "last-run.json"
    md_out = tmp_path / "MEASURED.md"
    try:
        for _ in range(80):
            try:
                health = httpx.get(f"{host}/health", timeout=0.5)
                if health.status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            raise AssertionError("API did not become healthy")
        ran = subprocess.run(
            [
                sys.executable,
                "-m",
                "loadtest.cli",
                "--host",
                host,
                "--users",
                "3",
                "--spawn-rate",
                "3",
                "--duration",
                "3",
                "--json-out",
                str(json_out),
                "--md-out",
                str(md_out),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(json_out.read_text(encoding="utf-8"))
        assert data["tool"] == "locust"
        assert data["target"] == "POST /v1/payments"
        assert data["requests"] >= 1
        assert 0 < data["measured_tps"] < 1_000_000
        assert data["p95_ms"] is not None
        assert data["slo_contractual"] is False
        assert data["invented_1m_tps"] is False
        assert data["failures"] == 0
        markdown = md_out.read_text(encoding="utf-8")
        assert "not a capacity claim" in markdown.lower() or "not 1M TPS" in markdown
        assert "1M TPS" in markdown
        assert ran.returncode == 0
    finally:
        api.terminate()
        try:
            api.wait(timeout=8)
        except subprocess.TimeoutExpired:
            api.kill()
        redis.close()
        db.close()
