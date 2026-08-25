"""CLI for the Phase 10 security scan."""

from __future__ import annotations

from payment_platform.security.scan import report_json, scan_repository


def main() -> int:
    report = scan_repository()
    print(report_json(report), end="")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
