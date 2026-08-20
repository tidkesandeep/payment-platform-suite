# payment-platform-suite

Local-first platform that authorizes payments — including agent-initiated ones — only when **intent**, **fraud**, and **policy** all pass.

**Single source of truth:** [PAYMENT_PLATFORM.md](./PAYMENT_PLATFORM.md)

Cloud deployment is deferred. Older planning docs are historical; see [DOCUMENTATION_INDEX.md](./DOCUMENTATION_INDEX.md).

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
