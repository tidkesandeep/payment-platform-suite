"""Honest load-report types. Refuse 1M TPS theater."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

INVENTED_TPS = 1_000_000.0
SLO_P95_TARGET_MS = 100.0


@dataclass
class LoadReport:
    tool: str
    target: str
    host: str
    users: int
    spawn_rate: float
    duration_seconds: float
    requests: int
    failures: int
    measured_tps: float
    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None
    slo_p95_target_ms: float = SLO_P95_TARGET_MS
    slo_contractual: bool = False
    invented_1m_tps: bool = False
    notes: str = (
        "Local measurement against POST /v1/payments. Not production capacity. "
        "Not 1M TPS. Unique customer_id per request so velocity caps do not dominate."
    )

    def validate_honest(self) -> None:
        if self.invented_1m_tps:
            raise ValueError("refusing to mark invented 1M TPS")
        if self.slo_contractual:
            raise ValueError("p95 < 100ms is a local target, not a contract")
        if self.measured_tps >= INVENTED_TPS:
            raise ValueError("refusing to publish 1M TPS")
        if self.requests < 1:
            raise ValueError("no requests measured")
        if self.p95_ms is None:
            raise ValueError("p95 was not measured")


def write_report_json(report: LoadReport, path: Path) -> None:
    report.validate_honest()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(report), indent=2) + "\n", encoding="utf-8")


def write_measured_markdown(report: LoadReport, path: Path) -> None:
    report.validate_honest()
    hit = "yes" if report.p95_ms is not None and report.p95_ms < report.slo_p95_target_ms else "no"
    body = f"""# Measured scale (Phase 11)

This file is a **measurement**, not a capacity claim. It is not 1M TPS.

| Field | Value |
|---|---|
| Tool | {report.tool} |
| Target | `{report.target}` |
| Host | `{report.host}` |
| Users | {report.users} |
| Spawn rate | {report.spawn_rate}/s |
| Duration | {report.duration_seconds}s |
| Requests | {report.requests} |
| Failures | {report.failures} |
| **Measured TPS** | **{report.measured_tps:.2f}** |
| p50 | {report.p50_ms:.1f} ms |
| **p95** | **{report.p95_ms:.1f} ms** |
| p99 | {report.p99_ms:.1f} ms |
| SLO p95 target | {report.slo_p95_target_ms:.0f} ms (not contractual) |
| Measured p95 under target | {hit} |

{report.notes}

Do not copy these numbers into a production or 1M TPS claim.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
