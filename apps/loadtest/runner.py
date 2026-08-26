"""Run Locust headless against POST /v1/payments and return a measured report."""

from __future__ import annotations

import gevent
from locust.env import Environment
from locust.log import setup_logging

from loadtest.locustfile import AuthorizeUser
from loadtest.report import LoadReport


def _percentile(stats, q: float) -> float | None:
    if stats.num_requests < 1:
        return None
    value = stats.get_response_time_percentile(q)
    return float(value) if value is not None else None


def run_headless(
    *,
    host: str,
    users: int,
    spawn_rate: float,
    duration_seconds: float,
) -> LoadReport:
    setup_logging("WARNING", None)
    env = Environment(user_classes=[AuthorizeUser], host=host.rstrip("/"))
    env.create_local_runner()
    assert env.runner is not None
    env.runner.start(users, spawn_rate=spawn_rate)
    gevent.sleep(duration_seconds)
    env.runner.quit()
    total = env.stats.total
    duration = max(duration_seconds, 0.001)
    report = LoadReport(
        tool="locust",
        target="POST /v1/payments",
        host=host.rstrip("/"),
        users=users,
        spawn_rate=spawn_rate,
        duration_seconds=duration_seconds,
        requests=int(total.num_requests),
        failures=int(total.num_failures),
        measured_tps=float(total.num_requests) / duration,
        p50_ms=_percentile(total, 0.50),
        p95_ms=_percentile(total, 0.95),
        p99_ms=_percentile(total, 0.99),
    )
    report.validate_honest()
    return report
