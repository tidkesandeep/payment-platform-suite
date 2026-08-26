"""CLI: payment-load — Locust against /v1/payments, write measured TPS and p95."""

from __future__ import annotations

import argparse
from pathlib import Path

from loadtest.report import write_measured_markdown, write_report_json
from loadtest.runner import run_headless


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure TPS and p95 with Locust against POST /v1/payments"
    )
    parser.add_argument("--host", default="http://127.0.0.1:8000")
    parser.add_argument("--users", type=int, default=6)
    parser.add_argument("--spawn-rate", type=float, default=6.0)
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--json-out", default="load/last-run.json")
    parser.add_argument("--md-out", default="load/MEASURED.md")
    args = parser.parse_args(argv)
    report = run_headless(
        host=args.host,
        users=args.users,
        spawn_rate=args.spawn_rate,
        duration_seconds=args.duration,
    )
    write_report_json(report, Path(args.json_out))
    write_measured_markdown(report, Path(args.md_out))
    print(
        f"measured_tps={report.measured_tps:.2f} p95_ms={report.p95_ms:.1f} "
        f"requests={report.requests} failures={report.failures}"
    )
    return 0 if report.failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
