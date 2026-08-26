from dataclasses import replace

import pytest

from loadtest.report import LoadReport


def _report(**overrides) -> LoadReport:
    base = LoadReport(
        tool="locust",
        target="POST /v1/payments",
        host="http://127.0.0.1:8000",
        users=4,
        spawn_rate=4.0,
        duration_seconds=10.0,
        requests=200,
        failures=0,
        measured_tps=20.0,
        p50_ms=12.0,
        p95_ms=28.0,
        p99_ms=40.0,
    )
    return replace(base, **overrides)


def test_honest_report_is_accepted():
    _report().validate_honest()


def test_refuses_invented_one_million_tps():
    with pytest.raises(ValueError, match="1M TPS"):
        _report(measured_tps=1_000_000.0).validate_honest()


def test_p95_target_is_not_a_contract():
    with pytest.raises(ValueError, match="not a contract"):
        _report(slo_contractual=True).validate_honest()


def test_requires_measured_p95_and_requests():
    with pytest.raises(ValueError, match="p95"):
        _report(p95_ms=None).validate_honest()
    with pytest.raises(ValueError, match="no requests"):
        _report(requests=0, measured_tps=0.0, p95_ms=10.0).validate_honest()
