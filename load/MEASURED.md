# Measured scale (Phase 11)

This file is a **measurement**, not a capacity claim. It is not 1M TPS.

| Field | Value |
|---|---|
| Tool | locust |
| Target | `POST /v1/payments` |
| Host | `http://127.0.0.1:8000` |
| Users | 6 |
| Spawn rate | 6.0/s |
| Duration | 20.0s |
| Requests | 4262 |
| Failures | 0 |
| **Measured TPS** | **213.10** |
| p50 | 26.0 ms |
| **p95** | **38.0 ms** |
| p99 | 49.0 ms |
| SLO p95 target | 100 ms (not contractual) |
| Measured p95 under target | yes |

Local measurement against POST /v1/payments. Not production capacity. Not 1M TPS. Unique customer_id per request so velocity caps do not dominate.

Do not copy these numbers into a production or 1M TPS claim.
