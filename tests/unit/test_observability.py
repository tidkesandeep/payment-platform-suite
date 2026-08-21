from __future__ import annotations

from payment_platform.observability.metrics import PlatformMetrics, percentile
from payment_platform.observability.tracing import make_memory_tracer


def test_percentile_is_measured_from_samples():
    samples = [float(n) for n in range(1, 101)]
    assert percentile(samples, 95) == 95.0
    assert percentile([], 95) is None


def test_histogram_and_p95_are_not_the_slo_target():
    metrics = PlatformMetrics()
    for value in (0.012, 0.018, 0.021, 0.015, 0.014):
        metrics.observe_decision_seconds(value)
    p95 = metrics.decision_p95_seconds()
    assert p95 is not None
    assert 0.01 <= p95 <= 0.03
    assert p95 != 0.1


def test_409_and_reclaim_counters():
    metrics = PlatformMetrics()
    metrics.inc_conflict()
    metrics.inc_reclaim()
    metrics.set_outbox_lag(4)
    assert metrics.conflicts._value.get() == 1
    assert metrics.reclaims._value.get() == 1
    assert metrics.outbox_lag._value.get() == 4


def test_authorize_span_is_exported():
    tracer, exporter = make_memory_tracer()
    with tracer.start_as_current_span("payments.authorize") as span:
        span.set_attribute("http.status_code", 200)
    finished = exporter.get_finished_spans()
    assert len(finished) == 1
    assert finished[0].name == "payments.authorize"
    assert finished[0].attributes["http.status_code"] == 200
