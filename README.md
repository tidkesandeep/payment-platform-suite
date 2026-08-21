# payment-platform-suite

Local-first platform that authorizes payments — including agent-initiated ones — only when **intent**, **fraud**, and **policy** all pass.

**Single source of truth:** [PAYMENT_PLATFORM.md](./PAYMENT_PLATFORM.md)

Cloud deployment is deferred. Older planning docs are historical; see [DOCUMENTATION_INDEX.md](./DOCUMENTATION_INDEX.md).

## Phase branches

Commits for a phase land **only** on that phase's branch. Do not mix later-phase work into an earlier branch. Later phases stack on the previous phase. Phase 12 (cloud) is deferred; do not start it.

| Phase | Branch | Merges into |
|---|---|---|
| 1 Foundation | `cursor/phase-1-foundation-0753` | `develop` |
| 2 Streaming | `cursor/phase-02-streaming-0753` | phase 1 |
| 3 Lakehouse | `cursor/phase-03-lakehouse-0753` | phase 2 |
| 4 Features | `cursor/phase-04-features-0753` | phase 3 |
| 5 Fraud | `cursor/phase-05-fraud-0753` | phase 4 |
| 6 Observability | `cursor/phase-06-observability-0753` | phase 5 |
| 7 Investigator | `cursor/phase-07-investigator-0753` | phase 6 |
| 8 Verifiable Intent | `cursor/phase-08-verifiable-intent-0753` | phase 7 |
| 9 Agentic demo | `cursor/phase-09-agentic-demo-0753` | phase 8 |
| 10 Security review | `cursor/phase-10-security-review-0753` | phase 9 |
| 11 Honest scale | `cursor/phase-11-honest-scale-0753` | phase 10 |

## Phase 2

A separate `payment-stream` worker drains the Postgres outbox to Redpanda and projects `payments` / `transaction-states` into a read model. It does not authorize, score, or evaluate policy. `/v1/payments` still returns 200 if the broker is down; unpublished rows stay in the outbox.

```bash
export PAYMENTS_KAFKA_BOOTSTRAP=127.0.0.1:19092
payment-stream
```

Modest-TPS HTTP simulator (still never produces to Kafka):

```bash
payment-simulator --base-url http://127.0.0.1:8000 --count 20 --tps 10 --channel human
```

Compose starts API, stream worker, Postgres, Redis, and Redpanda. The API service does not depend on Redpanda.

## Phase 5

The sole scorer on `/v1/payments` is an in-process XGBoost champion. The score is a dimension of `decision = f(authorization, fraud, policy)`; a high score does not bypass a policy fail. SHAP is computed only on `POST /v1/payments/{id}/explain` and is skipped when the decision was APPROVE.

Train locally (synthetic IEEE-CIS-shaped data; optional Kaggle overlay at `data/ieee-cis/train_transaction.csv` — this repo does not download Kaggle files):

```bash
payment-train-champion
```

The stub scorer remains for tests that drive HIGH/CRITICAL bands via `device_id`. Production `create_app()` loads `champion.json`.

## Phase 4

`/v1/payments` enriches from Redis (`cust:`, `mer:`, `dev:`, plus Phase 1 `vel:*` INCR). Spark is not consulted. An async rebuild job rewrites profile hashes from Postgres; it does **not** overwrite attempt/approved INCR keys.

```bash
payment-features-rebuild
```

## Phase 1

The API is a synchronous authorize path: claim idempotency → validate → intent stub → Redis velocity `INCR` → champion stub → policy → persist + outbox. Spark is not on this path. The outbox publisher (Redpanda produce) starts in Phase 2.

### Run locally (no Docker)

Postgres 16 and Redis must be running. Apply the schema, install the package, start the API:

```bash
sudo -u postgres psql -c "CREATE USER payments WITH PASSWORD 'payments'"
sudo -u postgres psql -c "CREATE DATABASE payments OWNER payments"
sudo -u postgres psql -d payments -f sql/init.sql

python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

export PAYMENTS_DATABASE_URL=postgresql://payments:payments@127.0.0.1:5432/payments
export PAYMENTS_REDIS_URL=redis://127.0.0.1:6379/0
uvicorn payment_platform.api.main:app --host 0.0.0.0 --port 8000
```

Demo key: `sk_test_demo`.

```bash
curl -sS http://127.0.0.1:8000/v1/payments \
  -H 'X-API-Key: sk_test_demo' \
  -H 'Content-Type: application/json' \
  -d '{
    "idempotency_key": "order-1",
    "customer_id": "cust_001",
    "merchant_id": "mer_789",
    "amount_minor": 12550,
    "currency": "USD",
    "merchant_category": "5411",
    "country": "US",
    "device_id": "dev_ok",
    "channel": "human",
    "agent_id": null,
    "intent": null
  }'
```

Agent requests fail closed until Phase 8 (official Verifiable Intent). The Phase 1 stub does not implement cryptography.

HTTP simulator (never writes to Kafka/Redpanda):

```bash
payment-simulator --base-url http://127.0.0.1:8000 --count 5 --channel human
```

### Run with Docker Compose

```bash
docker compose up --build
```

Compose starts API, Postgres, Redis, and Redpanda. Phase 1 does not publish to Redpanda yet.

### Tests

```bash
createdb -U payments payments_test
pytest
```

## Money

Amounts are integer **minor units** (`amount_minor`). Float `amount` values are rejected.
