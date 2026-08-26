"""Prometheus metrics for /v1/payments. Local SLO targets are not contractual."""

from __future__ import annotations

import math
from collections import deque

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

DECISION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0)
INTENT_BUCKETS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25)
MODEL_BUCKETS = (0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.25)

# Demo-window target only. Phase 6 must not treat 99.9% as a contract.
DECISION_P95_TARGET_SECONDS = 0.1


def percentile(samples: list[float], p: float) -> float | None:
    if not samples:
        return None
    ordered = sorted(samples)
    rank = max(1, int(math.ceil((p / 100.0) * len(ordered))))
    return ordered[rank - 1]


class PlatformMetrics:
    def __init__(self, registry: CollectorRegistry | None = None):
        self.registry = registry or CollectorRegistry()
        self._decision_samples: deque[float] = deque(maxlen=4096)
        self.decision_latency = Histogram(
            "payments_decision_latency_seconds",
            "Authorize path latency including 409/422/200. p95 target 100ms is local, not contractual.",
            buckets=DECISION_BUCKETS,
            registry=self.registry,
        )
        self.intent_latency = Histogram(
            "payments_intent_latency_seconds",
            "Intent verification latency. p95 target 50ms is local, not contractual.",
            buckets=INTENT_BUCKETS,
            registry=self.registry,
        )
        self.model_latency = Histogram(
            "payments_model_latency_seconds",
            "Champion scoring latency.",
            buckets=MODEL_BUCKETS,
            registry=self.registry,
        )
        self.http_requests = Counter(
            "payments_http_requests_total",
            "HTTP responses by path and status.",
            ["path", "status"],
            registry=self.registry,
        )
        self.conflicts = Counter(
            "payments_idempotency_conflicts_total",
            "HTTP 409 in-flight idempotency leases.",
            registry=self.registry,
        )
        self.reclaims = Counter(
            "payments_lease_reclaims_total",
            "Expired idempotency leases reclaimed and processed.",
            registry=self.registry,
        )
        self.replays = Counter(
            "payments_idempotency_replays_total",
            "Terminal idempotency replays.",
            registry=self.registry,
        )
        self.decisions = Counter(
            "payments_decisions_total",
            "Terminal authorize decisions.",
            ["state", "channel"],
            registry=self.registry,
        )
        self.outbox_lag = Gauge(
            "payments_outbox_lag",
            "Unpublished outbox rows. Alert if draining stalls; authorize still 200.",
            registry=self.registry,
        )
        self.investigator_calls = Counter(
            "payments_investigator_tool_calls_total",
            "Investigator tool invocations.",
            ["tool", "result"],
            registry=self.registry,
        )
        self.investigator_failures = Counter(
            "payments_investigator_tool_failures_total",
            "Investigator tool failures and denials.",
            ["tool"],
            registry=self.registry,
        )

    def observe_decision_seconds(self, seconds: float) -> None:
        value = max(0.0, float(seconds))
        self.decision_latency.observe(value)
        self._decision_samples.append(value)

    def observe_intent_seconds(self, seconds: float) -> None:
        self.intent_latency.observe(max(0.0, float(seconds)))

    def observe_model_seconds(self, seconds: float) -> None:
        self.model_latency.observe(max(0.0, float(seconds)))

    def observe_http(self, path: str, status: int) -> None:
        self.http_requests.labels(path=path, status=str(status)).inc()

    def inc_conflict(self) -> None:
        self.conflicts.inc()

    def inc_reclaim(self) -> None:
        self.reclaims.inc()

    def inc_replay(self) -> None:
        self.replays.inc()

    def inc_decision(self, state: str, channel: str) -> None:
        self.decisions.labels(state=state or "unknown", channel=channel or "unknown").inc()

    def set_outbox_lag(self, lag: int) -> None:
        self.outbox_lag.set(lag)

    def decision_p95_seconds(self) -> float | None:
        return percentile(list(self._decision_samples), 95)

    def inc_investigator_call(self, tool: str, result: str) -> None:
        self.investigator_calls.labels(tool=tool or "unknown", result=result or "error").inc()

    def inc_investigator_failure(self, tool: str) -> None:
        self.investigator_failures.labels(tool=tool or "unknown").inc()
