# Payment Platform

**Status:** Canonical — this is the single source of truth  
**Supersedes:** `PAYMENTS_PORTFOLIO_IMPLEMENTATION_GUIDE.md`, `IMPLEMENTATION_GUIDE_COMPARISON.md`, `CLOUD_PROVIDER_STRATEGY.md`, `DOCUMENTATION_INDEX.md`  
**Updated:** 2026-08-20 (HLD/LLD: two-plane design, outbox, degradation, policy)  
**Scope:** Local-first agentic payment platform. Cloud deployment is deferred.

If a prior document disagrees with this one, this one wins.

---

## 1. What this project is

Build **one cohesive payment platform**, not four disconnected components.

The platform authorizes payments — including payments initiated by AI agents — by combining three independent checks:

1. **Authorization** — cryptographic proof that the user intended *this* merchant, amount, and window
2. **Fraud / risk** — empirical score that the attempt looks like abuse
3. **Policy** — programmatic constraints (limits, merchant scope, velocity, agent allowlists)

A transaction is approved only when all three pass. A valid signature is not safety. A low fraud score is not authorization. An LLM never moves money.

### Why it exists

The problem is agentic commerce on card rails: authorization-latency fraud, streaming at payment volume, lakehouse governance, and cryptographic proof of user intent (Mastercard Verifiable Intent). That domain does **not** justify fake scale claims, custom cryptography, or cloud spend.

### What we are not building

- A live card processor, issuer switch, or acquirer
- A PCI-compliant production system
- A Mastercard-certified product
- Custom cryptography that parallels Verifiable Intent
- An LLM that approves or declines payments
- AWS/Azure/GCP infrastructure (deferred)

Use synthetic or public data only. Never real card numbers, PANs, or customer PII.

---

## 2. Locked decisions

| Decision | Choice | Why |
|---|---|---|
| Shape | One platform with layered capabilities | Systems thinking, not four disconnected demos |
| Runtime | Local Docker Compose first | Cloud is not a current priority |
| Broker | Kafka or Redpanda locally | Industry-standard event log; swap later if needed |
| Hot path | Synchronous API only | p95 decision &lt; 100ms |
| Async path | Kafka consumers + lakehouse jobs | Metrics, gold tables, retraining — not authorize |
| Stream processor | Kafka consumer group (or Kafka Streams) on the async path; Spark **only** for lakehouse ETL | Spark/micro-batch must never sit on `/v1/payments` |
| Writes | Postgres transaction + transactional outbox | No dual-write to DB and Kafka |
| Idempotency | Unique `idempotency_key` + in-flight row | Close the check-then-act race |
| Policy | Deterministic rule table, separate from the model | Velocity/limits are not a fraud score |
| Settlement | Async no-op stub after `AUTHORIZED` | This product authorizes; it does not move money |
| Degradation | Table in §5.7 — fail closed on intent/policy | Infra faults return 503; they do not silently approve |
| Intent | Official Mastercard Verifiable Intent spec | Standards integration, not invented RSA |
| Decisioning | Authorization × fraud × policy | Agentic commerce fails if these are collapsed |
| AI | Investigator with a tool allowlist | LLM explains; deterministic engine decides |
| Data | Kaggle IEEE-CIS + synthetic fraud | Public, realistic, no compliance theater |
| Claims | Honest local demo | No “PCI compliant”, no “600M tx/day in prod” |

---

## 3. System architecture

Two planes. **Authorize is synchronous. Streaming is not on the authorize path.**

```
SYNC  (p95 < 100ms)                         ASYNC  (lag < 5s)
────────────────────                        ─────────────────
Agent or human
      │
      ▼
┌──────────────┐     outbox (same TX)     ┌─────────────────┐
│ API          │ ───────────────────────► │ Kafka/Redpanda  │
│ 1. idempotency                          └────────┬────────┘
│ 2. validate                                      │
│ 3. intent verify                                 ├─► state projector
│ 4. Redis features                                ├─► windowed metrics
│ 5. fraud score (in-process / local RPC)          ├─► lakehouse (Spark)
│ 6. policy rules                                  └─► dashboards / investigator reads
│ 7. persist decision
│ 8. return
└──────────────┘
      │
      ▼
 Postgres (SoR for current row)
```

Hard rule: Spark, Flink, and Kafka consumer lag **must not** be in the `/v1/payments` call stack.

Each concern still depends on the others, but not in one blocking pipeline:

- Agent payments cannot proceed without intent verification. Human checkout uses the human path in §6 (still fraud + policy).
- Risk scores from **Redis online features**, not from a stream join on the request.
- Stream jobs **maintain** Redis and gold; they do not authorize.
- Fraud cannot explain without stored evidence.
- The investigator cannot approve.

### 3.1 Sequence (authorize)

```
Client                API                 Postgres            IntentVerifier         Redis           Fraud
  │ POST /v1/payments   │                    │                     │                   │               │
  │────────────────────►│                    │                     │                   │               │
  │                     │ BEGIN              │                     │                   │               │
  │                     │ insert/lock idempotency key              │                   │               │
  │                     │───────────────────►│                     │                   │               │
  │                     │                    │ if completed: return stored result      │               │
  │                     │ validate           │                     │                   │               │
  │                     │ verify intent      │                     │                   │               │
  │                     │─────────────────────────────────────────►│                   │               │
  │                     │ HGET features      │                     │                   │               │
  │                     │─────────────────────────────────────────────────────────────►│               │
  │                     │ score              │                     │                   │               │
  │                     │─────────────────────────────────────────────────────────────────────────────►│
  │                     │ policy.evaluate()  │                     │                   │               │
  │                     │ update txn + outbox│                     │                   │               │
  │                     │ COMMIT             │                     │                   │               │
  │                     │ (publisher drains outbox → Kafka)        │                   │               │
  │◄──── decision ──────│                    │                     │                   │               │
```

The API process owns the state machine on the hot path. Async consumers **project** events; they do not take a second authorize decision.

### Transaction state machine

Hot-path happy path (this is the product):

```
CREATED
  → VALIDATED
  → INTENT_VERIFIED      (skipped on human path; see §6)
  → ENRICHED             (Redis feature materialization, in-request)
  → RISK_SCORED
  → DECISIONED
  → AUTHORIZED | CHALLENGED | MANUAL_REVIEW
```

Failure / hold:

```
VALIDATION_FAILED
INTENT_INVALID
RISK_DECLINED
POLICY_VIOLATION
PROCESSING_FAILED
```

Async stub (not money movement):

```
AUTHORIZED → SETTLED
```

`SETTLED` means “demo projector wrote a settlement event.” No ledger, capture, or scheme clearing. Do not implement a real settlement engine.

Terminal for idempotency: any of `AUTHORIZED`, `CHALLENGED`, `MANUAL_REVIEW`, `VALIDATION_FAILED`, `INTENT_INVALID`, `RISK_DECLINED`, `POLICY_VIOLATION`, `PROCESSING_FAILED`. Replay of the same `idempotency_key` returns that stored terminal (or waits if the row is still `CREATED`/`VALIDATED`/…).

`CHALLENGED` and `MANUAL_REVIEW` are **holds**, not pays. Phase 1 returns them as decisions with no step-up protocol. A later phase may add an operator queue; it is not required to start.

---

## 4. Decision model

Do not implement `if fraud_score < 0.2: approve`.

```
decision = f(authorization, fraud, policy)
```

| Authorization | Fraud | Policy | Decision | State |
|---|---|---|---|---|
| VALID (or HUMAN) | LOW | PASS | APPROVE | `AUTHORIZED` |
| VALID (or HUMAN) | MEDIUM | PASS | CHALLENGE | `CHALLENGED` |
| VALID (or HUMAN) | HIGH | PASS | REVIEW | `MANUAL_REVIEW` |
| VALID (or HUMAN) | LOW | FAIL | DECLINE | `POLICY_VIOLATION` |
| INVALID | any | any | DECLINE | `INTENT_INVALID` |
| EXPIRED / REPLAY | any | any | DECLINE | `INTENT_INVALID` |

Thresholds are configuration, not architecture. Suggested starting bands for the fraud dimension only:

- LOW: score `< 0.20`
- MEDIUM: `0.20 – 0.70`
- HIGH: `> 0.70`

Those bands never override an invalid intent or a policy fail.

---

## 5. Core contracts

### 5.1 Payment event

Every payment attempt carries:

| Field | Role |
|---|---|
| `event_id` | Unique event identity (for exactly-once processing) |
| `transaction_id` | Business identity of the payment |
| `idempotency_key` | Client-supplied key; same key → same result |
| `customer_id` | Payer |
| `merchant_id` | Payee |
| `amount`, `currency` | Value |
| `merchant_category` | MCC |
| `country`, `device_id`, `ip_address` | Risk context |
| `timestamp` | Event time (not ingestion time) |
| `channel` | `human` or `agent` |
| `agent_id` | Required when `channel=agent` |
| `intent` | Verifiable Intent payload; **required** when `channel=agent`; **null** when `channel=human` |

**Who mints IDs**

| ID | Minted by | Form |
|---|---|---|
| `idempotency_key` | Client | Opaque string, unique per client intent (e.g. `merchant_id + order_id`) |
| `event_id` | API | ULID (time-sortable, unique per attempt/event) |
| `transaction_id` | API | ULID, stable for the payment; reused on idempotent replay |

Do not let the client supply `transaction_id` as the idempotency mechanism.

Request JSON (illustrative):

```json
{
  "idempotency_key": "idem_merchant_order_123",
  "customer_id": "cust_001",
  "merchant_id": "mer_789",
  "amount": 125.50,
  "currency": "USD",
  "merchant_category": "5411",
  "country": "US",
  "device_id": "dev_xyz",
  "ip_address": "10.0.0.1",
  "timestamp": "2026-08-20T15:30:45Z",
  "channel": "agent",
  "agent_id": "agent_coffee_buyer",
  "intent": { "...official Verifiable Intent payload..." }
}
```

`event_id` and `transaction_id` are assigned by the API, not the client.

### 5.2 HTTP API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/payments` | Create / authorize a payment (idempotent) |
| `GET` | `/v1/payments/{transaction_id}` | Fetch current state |
| `POST` | `/v1/payments/{transaction_id}/explain` | SHAP + decision evidence |
| `POST` | `/v1/investigations` | Open an investigator case (does not pay) |
| `GET` | `/health` | Liveness |
| `GET` | `/ready` | Readiness (models, broker, redis, db) |
| `GET` | `/metrics` | Prometheus |

`POST /v1/payments` returns the decision record, not only a fraud score:

```json
{
  "transaction_id": "txn_01J...",
  "state": "AUTHORIZED",
  "decision": "approve",
  "authorization": { "status": "VALID", "reason": "intent_verified" },
  "fraud": { "score": 0.12, "band": "LOW" },
  "policy": { "status": "PASS", "violations": [] },
  "latency_ms": 47
}
```

There is no public `approve_payment` tool for the LLM.

Callers of `POST /v1/payments` in local demo: the simulator and a documented API key (or compose-only network). There is no end-user OAuth in Phase 1. `agent_id` on the request must match the intent credential binding when `channel=agent`.

### 5.3 Idempotency

Postgres, not Redis, is the idempotency store.

```sql
UNIQUE (idempotency_key)
```

Algorithm:

1. `BEGIN`
2. `INSERT` into `idempotency_keys` (`key`, `status=in_progress`) **or** `SELECT … FOR UPDATE` if the key exists
3. If existing row is terminal: `COMMIT` (no work) and return stored `transaction_id` / decision
4. If existing row is `in_progress`: wait/retry with a short backoff (or return 409). Do not start a second authorize
5. Process authorize
6. Write `transactions` + `outbox` in the **same** transaction
7. Mark idempotency row terminal
8. `COMMIT`
9. Outbox publisher pushes to Kafka after commit

Redis `idem:{key}` may cache the result after commit. It is not authoritative.

### 5.4 Outbox

Do not `INSERT` into Postgres and `produce()` to Kafka as two independent I/O calls.

```
transactions  ─┐
outbox        ─┴─ same Postgres transaction
                 after COMMIT: publisher reads outbox, produces to Kafka, marks published
```

Outbox payload: state-transition event (`transaction-states`) plus, on first create, the `payments` event. At-least-once produce is allowed; consumers dedupe on `event_id`.

### 5.5 Event time and late data

Use **event time**, not ingestion time.

- Watermarks on the payment stream
- Windowed aggregations for features and metrics (async path)
- Late events update Redis / gold features; they do not rewrite a **terminal** decision
- Terminal decisions are immutable; corrections are new compensating events (new `event_id`, new `transaction_id` or an explicit reversal event — not an in-place update)

Clock for intent expiry: **API server UTC**. Do not trust the client clock.

### 5.6 Postgres (minimum)

```
idempotency_keys (
  key TEXT PRIMARY KEY,
  transaction_id TEXT NOT NULL,
  status TEXT NOT NULL,          -- in_progress | terminal
  decision_json JSONB,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ
)

transactions (
  transaction_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE,
  idempotency_key TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL,
  channel TEXT NOT NULL,
  customer_id, merchant_id, amount, currency, ...
  authorization_status TEXT,
  fraud_score DOUBLE PRECISION,
  fraud_band TEXT,
  policy_status TEXT,
  policy_violations JSONB,
  created_at, updated_at TIMESTAMPTZ
)

outbox (
  id BIGSERIAL PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE,
  topic TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  published_at TIMESTAMPTZ
)
```

Events on the wire: JSON with a schema version field (`schema_version: 1`). No Avro registry required for Phase 1. Additive fields only; do not reuse names.

### 5.7 Degradation

| Dependency | Authorize behavior | `/ready` |
|---|---|---|
| Postgres down | 503 | not ready |
| Intent verifier error (agent path) | fail closed → `INTENT_INVALID` or 503 if verifier process is dead | not ready if process dead |
| Redis down | fail closed for features: treat online features as missing; **policy still runs**; do not approve by skipping velocity | ready-degraded (metric) |
| Fraud model timeout / down | no score → `fraud_band=UNKNOWN`; policy + intent still apply; **do not APPROVE** (map UNKNOWN to REVIEW) | ready-degraded |
| Kafka / outbox publisher down | request can still COMMIT; outbox drains when publisher returns (authorize does not wait on Kafka) | ready if DB up; alert on outbox lag |
| Investigator down | authorize unaffected | ready |

Never fail **open** (approve because a dependency is down).

### 5.8 Policy engine

Policy is a deterministic rule table evaluated **after** intent and fraud, **never** inside the model.

Phase 1 rules (config, not code forks):

| Rule | Fail when |
|---|---|
| `max_amount` | amount &gt; limit (global and per-agent) |
| `merchant_allowlist` | merchant not in agent/human scope |
| `velocity_1h` / `velocity_24h` | Redis (or DB) count exceeds cap |
| `currency` | unsupported currency |
| `channel_agent_requires_intent` | `channel=agent` and intent missing/invalid (belt and suspenders) |

Evaluation: **first fail wins** (all violations still recorded on the decision). Policy does not call the LLM. Fraud score is an input to the decision matrix, not a policy rule.

---

## 6. Authorization — Verifiable Intent

Treat Mastercard Verifiable Intent as a **standard to integrate**, not a crypto project to invent.

### Do

- Implement against the official specification / reference implementation
- ES256 (not homemade RSA-PSS)
- SD-JWT and key-binding (KB-SD-JWT)
- Selective disclosure
- Constraint validation from the spec (merchant, amount, validity window, agent binding)
- L1–L3 credential chain as specified
- Store verification outcome and disclosed claims as decision evidence

### Do not

- Generate an app-local RSA keypair and call it Verifiable Intent
- Fork the reference repo and rename it
- Treat a valid signature as an approve
- Put private keys in git, Docker images, or logs

### What the platform must prove

For an agent-initiated payment, verification must fail closed on:

| Attack | Expected result |
|---|---|
| Agent impersonation | `INTENT_INVALID` |
| Out-of-scope delegation | constraint violation → `POLICY_VIOLATION` or `INTENT_INVALID` |
| Amount manipulation | `INTENT_INVALID` |
| Merchant substitution | `INTENT_INVALID` |
| Checkout tampering | `INTENT_INVALID` |
| Replay / expired intent | `INTENT_INVALID` |
| Key compromise / bad signature | `INTENT_INVALID` |
| Valid intent + high fraud | `MANUAL_REVIEW` or `RISK_DECLINED` |

**Human path (`channel=human`):**

- `intent` must be null
- `agent_id` must be null
- Authorization status is `HUMAN` (not `VALID` crypto). The decision matrix treats `HUMAN` like `VALID` for the auth column only
- Fraud + policy still run
- Do not accept `channel=human` with an intent blob, or `channel=agent` without one

Until the official library is wired in, **do not ship a parallel crypto module**. Stub the verifier behind an interface (`IntentVerifier.verify(request) -> {status, reason, claims}`) so the rest of the platform can be built against a fake that only exists in tests. The stub **fails closed** for agent paths except in unit tests that inject `VALID`.

---

## 7. Streaming and state (async only)

Streaming **projects** what the API already decided. It does not authorize.

### Topics

| Topic | Key | Purpose | Retention (local) |
|---|---|---|---|
| `payments` | `customer_id` | Raw payment attempts | 7 days |
| `transaction-states` | `transaction_id` | State transitions | 30 days |
| `fraud-scores` | `transaction_id` | Model output | 30 days |
| `decisions` | `transaction_id` | Final decision records | 30 days |
| `fraud-alerts` | `transaction_id` | High-risk / review | 30 days |
| `metrics` | window + dimension | Aggregates for dashboards / lakehouse | 90 days |

Local partition counts can be small (3–8). Replication factor 1 is acceptable locally. Do not claim 1M TPS.

Async processor: **Kafka consumer group** in the API/worker process (Kafka Streams is acceptable). **Spark is not this processor.** Spark jobs read from topics or files into Delta (lakehouse only).

### Processor responsibilities (async)

1. Dedupe on `event_id`
2. Project state to read models / Redis metrics
3. Windowed aggregates (1 minute, 5 minute sliding, 1 hour) → Redis + `metrics` topic
4. Sink to lakehouse bronze
5. Optional: `AUTHORIZED` → `SETTLED` stub event

Do not re-run intent, fraud, or policy in the consumer.

### Redis (online state)

| Key pattern | Contents |
|---|---|
| `cust:{id}` | Profile + rolling aggregates |
| `mer:{id}` | Merchant risk stats |
| `dev:{id}` | Device graph-lite stats |
| `vel:{id}:{window}` | Velocity counters |
| `idem:{key}` | Prior decision |
| `metric:{window}:{dim}` | Dashboard aggregates |

TTL should exceed the feature window. This is the sub-100ms feature path. It is not the system of record. The system of record is the event log + lakehouse + transaction store.

### Transaction store

Postgres (local) holds the current transaction row and decision. Kafka is the log. Redis is a cache and feature store. Do not make Redis the source of truth for money movement.

---

## 8. Intelligence — features and fraud

Fraud is a **signal**, not the decision engine.

### 8.1 Real-time features

**Transaction:** amount, MCC, channel, hour of day, currency.

**Customer (Redis):** account age, txn count 30d, avg amount 30d, velocity 1h / 24h, unique merchants 30d, days since last txn.

**Merchant:** avg amount, fraud rate, chargeback rate, high-risk flag.

**Location / device:** home-country match, distance from last txn, country fraud rate, new device, customers/cards on same device 24h.

**Agentic (when channel=agent):** intent validity, constraint fail count, agent age, agent velocity, consent freshness. These features exist so research question 1 is answerable later: *does cryptographic authorization improve fraud detection?*

### 8.2 Offline / aggregate features

Hourly (or on a local schedule) from the lakehouse into Redis and `gold/ml_features`:

- Customer: sum/count/max/std amount over 24h, 7d, 30d; prior fraud/chargeback flags
- Merchant: volume, fraud rate, chargeback rate
- Device: unique customers/cards, fraud rate

### 8.3 Models

Ensemble of three models on ~50 features:

| Model | Role | Weight |
|---|---|---|
| XGBoost | Primary tabular | 0.50 |
| LightGBM | Fast second opinion | 0.30 |
| Small feed-forward net | Non-linear residual | 0.20 |

Latency budget for scoring: well under the overall p95 decision SLO of 100ms. **Hot path runs the champion model only** (XGBoost). LightGBM and the net may run as shadow/async later; they must not block `/v1/payments` until measured. SHAP only for medium/high risk or explicit `/explain` — never on the approve hot path.

Serve the champion **in-process in the API** (or a local RPC with a hard timeout, e.g. 20ms). Do not round-trip Kafka to score.

Training:

- Source: gold layer / labeled historical set (IEEE-CIS + synthetic)
- Time-ordered split (no random shuffle across time)
- Metrics: AUC-ROC, PR-AUC, precision, recall, FPR, FNR — by segment (new customer, high amount, agent vs human)
- Registry: MLflow locally
- Cadence: manual or weekly job; champion/challenger later

Do not call Amazon Fraud Detector or SageMaker while cloud is deferred. Local sklearn/XGBoost is enough.

---

## 9. Lakehouse

Medallion layout on **local disk** (Delta Lake). Object-store paths can stay abstract (`s3://` / `adls://`) only as comments for a future port.

```
bronze/payments          raw events, partitioned by date
bronze/fraud_scores      model outputs
bronze/decisions         decision records
silver/transactions      deduped, typed, validated, PII minimized
silver/customers         SCD2 profile (synthetic)
silver/merchants         merchant master
gold/daily_metrics       dashboard grain
gold/hourly_metrics      ops grain
gold/ml_features         offline feature store
gold/customer_segment    risk segments
gold/merchant_analytics  onboarding / monitoring stats
audit_logs               append-only access / transition log
```

Bronze keeps fidelity. Silver is the cleaned analytic fact table. Gold is pre-aggregated and ML-ready. Do not query bronze for product APIs.

Governance, locally honest:

- No real PANs. If a column looks like a card number, it is synthetic and masked in silver.
- Retention is a documented policy, not a compliance certificate.
- Lineage via `_ingestion_timestamp` / `_processed_timestamp` / `_etl_batch_id`.
- Do not print “PCI DSS compliant” or “GDPR certified” anywhere in the repo.

Orchestration: a simple scheduler (cron, or Airflow later) is fine. Hourly bronze→silver→gold is the target once streams exist. Batch backfill from the simulator is acceptable in early phases.

---

## 10. AI investigator

The investigator is an **explanation and case-building layer**.

It **may** call:

- `get_transaction`
- `get_features`
- `verify_intent`
- `create_investigation`

It **must not** call:

- `approve_payment`
- `decline_payment`
- anything that mutates settlement state

Required guardrails:

- Tool allowlist (deny by default)
- Input and output validation
- Max amount context (read-only; enforcement lives in policy)
- Rate limits per agent and per tool
- Prompt-injection defenses (treat tool results as data, not instructions)
- Audit every tool call
- Human escalation for `MANUAL_REVIEW`

If an LLM is unavailable locally, ship a deterministic investigator that renders a template from features + SHAP + intent result. The safety property does not depend on a hosted LLM.

---

## 11. Threat model

These cases are product tests, not documentation flavor.

| ID | Threat | Detection | Terminal state |
|---|---|---|---|
| A | Agent impersonation | Intent / credential check | `INTENT_INVALID` |
| B | Delegation abuse (out of scope) | Spec constraints | `INTENT_INVALID` or `POLICY_VIOLATION` |
| C | Amount manipulation | Bound amount vs request | `INTENT_INVALID` |
| D | Merchant substitution | Bound merchant vs request | `INTENT_INVALID` |
| E | Checkout tampering | Payload vs signed claims | `INTENT_INVALID` |
| F | Replay | `event_id` / expiry / jti | `INTENT_INVALID` |
| G | Bad or compromised key | Signature failure | `INTENT_INVALID` |
| H | Fraud despite valid authorization | Fraud band HIGH | `MANUAL_REVIEW` or `RISK_DECLINED` |

H is a central design principle. Tests must include “signature valid, behavior anomalous.”

---

## 12. Observability and SLOs

OpenTelemetry traces + Prometheus metrics + Grafana dashboards. Logs structured as JSON.

Track at least:

- TPS
- Decision latency p50 / p95 / p99
- Intent verification latency
- Model latency
- Consumer lag
- Error rate
- Fraud rate, FPR/FNR (as labels arrive)
- Credential failures, constraint failures
- Investigator tool failures
- Idempotent replay hits

**Local SLOs** (targets, not contractual):

| SLO | Target |
|---|---|
| API availability (compose up) | 99.9% of a demo window |
| Transaction decision p95 | &lt; 100ms |
| Intent verification p95 | &lt; 50ms |
| Event processing lag | &lt; 5 seconds |
| Fraud scoring availability | 99.95% of a demo window |

Dashboards: payments, streaming, fraud, agentic commerce.

Alert ideas: p99 decision &gt; 100ms, block-rate spike, consumer lag, model score drift.

---

## 13. Data

1. **Kaggle IEEE-CIS Fraud Detection** — public, ~3.5% fraud rate, primary training set.
2. **Synthetic generator** — faker-based merchants/customers; inject velocity abuse, geo-impossibility, amount outliers, card testing, agent replay.
3. **Live simulator** — Kafka producer at a configurable rate (start at hundreds to low thousands TPS, not 1M).

Label agentic vs human explicitly so models can be compared with and without intent features.

---

## 14. Local runtime (current target)

Cloud is deferred. The runnable system is Docker Compose.

| Service | Role |
|---|---|
| API (FastAPI) | Ingress, **sync authorize**, outbox writer |
| Outbox publisher | Same app or sidecar; drains Postgres → Kafka |
| Postgres | Transaction + idempotency + outbox (SoR) |
| Redpanda or Kafka | Event log (async) |
| Redis | Online features and hot metrics |
| Async consumers | Project states, windows, bronze sink |
| Spark (lakehouse only) | Bronze → silver → gold |
| Fraud | Champion model **in API process** |
| Intent verifier | Official spec adapter (stub until wired); in-request |
| Simulator | Load / demo traffic |
| Prometheus + Grafana | SLOs and dashboards |
| MLflow (optional) | Model registry |
| Investigator (optional) | Read-only agent |

Suggested compose ports: API `8000`, broker `9092`, Redis `6379`, Postgres `5432`, Grafana `3000`, Prometheus `9090`, dashboard `8501` if a Streamlit view is kept.

Kubernetes, Terraform, AWS Payment Cryptography, SageMaker, Kinesis, Glue, Bedrock, and multi-region replicas are **out of scope until cloud is explicitly prioritized**.

---

## 15. Repository layout

```
payment-platform-suite/
├── PAYMENT_PLATFORM.md          ← this file (canonical)
├── README.md
├── docker-compose.yml
├── apps/
│   ├── api/                     # FastAPI orchestrator
│   ├── simulator/
│   ├── stream-processor/        # async Kafka consumers only
│   ├── fraud/
│   ├── intent/                  # official spec adapter
│   ├── investigator/
│   └── dashboard/
├── libs/
│   ├── contracts/               # events, states, decision types
│   ├── features/
│   └── policy/
├── lakehouse/
│   ├── bronze|silver|gold jobs
│   └── governance notes
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── threat_model/
│   └── load/
└── ops/
    ├── prometheus.yml
    └── grafana/
```

Prior docs remain in the repo as historical input. They are not implementation instructions.

---

## 16. Implementation phases

Build **capability layers**. Do not complete “fraud as a standalone repo,” then “streaming as a standalone repo.”

Cloud phase is listed only so it is not forgotten. Do not start it.

| Phase | Capability | Done when |
|---|---|---|
| 1 Foundation | Compose, API, Postgres schema, outbox, state machine, idempotency | A payment can be created and fetched; concurrent same-key retries are safe |
| 2 Streaming | Broker, outbox publisher, simulator, async consumers | Events survive restart; lag is visible; authorize still works if Kafka is down (outbox backs up) |
| 3 Lakehouse | Bronze → silver → gold on local Delta **via Spark jobs** | A day’s sim data is queryable in gold |
| 4 Features | Redis online (async writers + sync readers) + gold offline | `/v1/payments` enriches from Redis, not from Spark |
| 5 Fraud engine | Champion in-process + SHAP on demand | Score is a dimension, not the decision |
| 6 Observability | Prom/Grafana, traces, SLO boards, outbox lag | p95 latency is measured, not guessed |
| 7 Investigator | Allowlisted tools, audit, no pay tool | Case file exists; approve is impossible |
| 8 Verifiable Intent | Official spec, not custom RSA | Threats A–G fail closed |
| 9 Agentic demo | Human + agent paths in one flow | Threat H is a passing test |
| 10 Security review | Threat tests, secrets hygiene, no real PII | Checklist green |
| 11 Scale (honest) | Load test at a stated TPS | Publish measured p95, not invented 1M TPS |
| 12 Cloud | AWS/LocalStack | **Deferred** |
| 13 Research | Intent-as-feature experiment | Optional, after the platform works |

Phases 1–7 can proceed with an `IntentVerifier` stub. Phase 8 replaces the stub. Do not implement homemade RSA in the meantime.

---

## 17. Testing

Minimum bar:

- Unit: features, **policy rules**, state transitions, idempotency store
- Concurrent idempotency: two parallel POSTs with the same key → one authorize
- API: create, replay same `idempotency_key`, fetch state
- Outbox: killing Kafka mid-request still leaves a drainable outbox row
- Threat model: cases A–H as automated tests
- Streaming: duplicate `event_id` does not double-project
- Model: score in `[0,1]`; timeout → UNKNOWN → REVIEW, never APPROVE
- Investigator: attempting `approve_payment` is a hard error
- Load: Locust (or equivalent) against `/v1/payments` with a published TPS and p95

No test should require AWS.

---

## 18. Anti-patterns

Do not:

- Call Kafka → Spark → Postgres “a payment platform” without auth, policy, state, and audit
- Put Spark or any micro-batch processor on `/v1/payments`
- `INSERT` then `produce()` without an outbox
- Check-then-act idempotency without a unique row lock
- Ask an LLM “is this fraud?” and take the answer as the system
- Hardcode `score > 0.7 → decline` as the whole framework
- Approve when Redis or the model is down
- Use real payment or card data
- Claim PCI, SOX, GDPR certification, or Mastercard partnership
- Invent Verifiable Intent with ad-hoc RSA
- Equate valid authorization with approve
- Put cloud account setup on the critical path
- Publish 600M tx/day, 1M TPS, or 0.92 AUC as facts before they are measured

---

## 19. Optional research (after the platform works)

These questions are valuable. They are not a reason to delay phases 1–11.

1. Do Verifiable Intent features improve fraud models vs traditional features only?
2. Can selective disclosure cut sensitive-data exposure without hurting detection?
3. What should happen when authorization is valid and behavior is anomalous?
4. How should autonomous limits adapt to behavioral risk?

Compare precision, recall, FPR, FNR, AUC. Keep this as an experiment notebook on gold data.

---

## 20. Deferred: cloud

Recorded so the decision is not relitigated every week.

**When cloud is eventually in scope:** AWS is the default port (fintech ecosystem, KMS / Payment Cryptography). Azure is a secondary option, not the primary. GCP is a poor fit for this problem. LocalStack is a migration aid, not a week-1 task.

**Until then:** local Compose is the environment. Do not create cloud accounts, Terraform, or provider-specific services for this project.

Mapping for a future port (do not implement now):

| Local | Possible AWS later |
|---|---|
| Kafka / Redpanda | Kinesis or MSK |
| Redis | ElastiCache |
| Postgres | RDS |
| Local disk Delta | S3 + Delta / Glue |
| Local XGBoost | SageMaker or still local containers |
| Local keys | KMS / Payment Cryptography |
| Prom/Grafana | CloudWatch plus or instead |

Portability is an interface concern (broker, store, secrets). It is not a multi-cloud rewrite.

---

## 21. How to use the older documents

| File | Use now |
|---|---|
| `PAYMENT_PLATFORM.md` | **Follow this.** |
| `PAYMENTS_PORTFOLIO_IMPLEMENTATION_GUIDE.md` | Historical. Some feature lists and Docker service names were absorbed here. Ignore custom RSA, fraud-only decisions, ADLS-as-required, and scale theater. |
| `IMPLEMENTATION_GUIDE_COMPARISON.md` | Historical rationale for the locked decisions in §2. |
| `CLOUD_PROVIDER_STRATEGY.md` | Historical. Relevant only when Phase 12 is opened. |
| `DOCUMENTATION_INDEX.md` | Pointer to this file. |

---

## 22. Definition of a credible demo

A reviewer should be able to:

1. `docker compose up` (or the documented equivalent)
2. Drive a human payment and an agent payment
3. See approve / challenge / review / decline with **three** dimensions, not one score
4. Replay the same `idempotency_key` safely, including concurrent retries
5. Break intent (amount, merchant, replay) and watch fail-closed
6. See a valid intent still go to review under high fraud
7. Open an investigation without any path to `approve_payment`
8. View Grafana latency and lag
9. Query gold aggregates for the session

That is the product. Everything else is optional.
