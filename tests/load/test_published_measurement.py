import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_published_measurement_is_locust_not_one_million_tps():
    data = json.loads((ROOT / "load" / "last-run.json").read_text(encoding="utf-8"))
    markdown = (ROOT / "load" / "MEASURED.md").read_text(encoding="utf-8")
    assert data["tool"] == "locust"
    assert data["target"] == "POST /v1/payments"
    assert data["requests"] >= 1
    assert data["p95_ms"] is not None
    assert 0 < data["measured_tps"] < 1_000_000
    assert data["slo_contractual"] is False
    assert data["invented_1m_tps"] is False
    assert "1M TPS" in markdown
    assert "not contractual" in markdown
    assert f"{data['measured_tps']:.2f}" in markdown
    assert f"{data['p95_ms']:.1f} ms" in markdown
