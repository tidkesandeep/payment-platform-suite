# Payment Platform

**Status:** Canonical — this is the single source of truth  
**Supersedes:** `PAYMENTS_PORTFOLIO_IMPLEMENTATION_GUIDE.md`, `IMPLEMENTATION_GUIDE_COMPARISON.md`, `CLOUD_PROVIDER_STRATEGY.md`, `DOCUMENTATION_INDEX.md`  
**Updated:** 2026-08-20  
**Scope:** Local-first agentic payment platform. Cloud deployment is deferred.

If a prior document disagrees with this one, this one wins.

---

## 1. What this project is

Build **one cohesive payment platform**, not four portfolio components.

The platform authorizes payments — including payments initiated by AI agents — by combining three independent checks:

1. **Authorization** — cryptographic proof that the user intended *this* merchant, amount, and window
2. **Fraud / risk** — empirical score that the attempt looks like abuse
3. **Policy** — programmatic constraints (limits, merchant scope, velocity, agent allowlists)

A transaction is approved only when all three pass. A valid signature is not safety. A low fraud score is not authorization. An LLM never moves money.

### Why it exists

The original documents were written as a Mastercard-targeted senior data/ML portfolio. That motive still explains the problem shape (authorization-latency fraud, streaming, lakehouse governance, agentic commerce). It does **not** justify fake scale claims, custom cryptography, or cloud spend.

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
| Intent | Official Mastercard Verifiable Intent spec | Standards integration, not invented RSA |
| Decisioning | Authorization × fraud × policy | Agentic commerce fails if these are collapsed |
| AI | Investigator with a tool allowlist | LLM explains; deterministic engine decides |
| Data | Kaggle IEEE-CIS + synthetic fraud | Public, realistic, no compliance theater |
| Claims | Honest local demo | No “PCI compliant”, no “600M tx/day in prod” |

---

## 3. System architecture

```
Agent or human checkout
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│  API / INGESTION                                          │
│  validate schema · idempotency key · create transaction   │
└─────────────────────────────┬─────────────────────────────┘
                              ▼
┌───────────────────────────────────────────────────────────┐
│  AUTHORIZATION LAYER                                      │
│  Verifiable Intent (official spec)                        │
│  signature · expiry · replay · constraints · disclosure   │
└─────────────────────────────┬─────────────────────────────┘
                              ▼
┌───────────────────────────────────────────────────────────┐
│  TRANSACTION / STREAMING LAYER                            │
│  Kafka/Redpanda · enrich · window · state in Redis        │
└─────────────────────────────┬─────────────────────────────┘
                              ▼
┌───────────────────────────────────────────────────────────┐
│  INTELLIGENCE LAYER                                       │
│  online features · fraud ensemble · SHAP (on demand)      │
└─────────────────────────────┬─────────────────────────────┘
                              ▼
┌───────────────────────────────────────────────────────────┐
│  DECISION LAYER                                           │
│  policy engine · approve / challenge / decline / review   │
│  append-only audit · events                               │
└───────────────┬─────────────────────────────┬─────────────┘
                ▼                             ▼
     Lakehouse (bronze→gold)        Investigator agent
     dashboards · retraining        read-only tools only
```

Each layer serves the others:

- A transaction cannot proceed without intent verification (or an explicit human-checkout path that still hits policy + fraud).
- Risk cannot score without features.
- Fraud cannot explain without evidence.
- The investigator cannot approve.

### Transaction state machine

Happy path:

```
CREATED
  → VALIDATED
  → ENRICHED
  → INTENT_VERIFIED
  → RISK_SCORED
  → DECISIONED
  → AUTHORIZED
  → SETTLED
```

Failure / hold states:

```
VALIDATION_FAILED
INTENT_INVALID
RISK_DECLINED
POLICY_VIOLATION
MANUAL_REVIEW
PROCESSING_FAILED
```

The state machine is the observability and idempotency backbone. Every transition is an event. Replay must produce the same terminal state for the same `idempotency_key`.

---

## 4. Decision model

Do not implement `if fraud_score < 0.2: approve`.

```
decision = f(authorization, fraud, policy)
```

| Authorization | Fraud | Policy | Decision |
|---|---|---|---|
| VALID | LOW | PASS | APPROVE |
| VALID | MEDIUM | PASS | CHALLENGE / STEP-UP |
| VALID | HIGH | PASS | REVIEW or DECLINE |
| VALID | LOW | FAIL (over limit, bad merchant, velocity) | DECLINE |
| INVALID | LOW | PASS | DECLINE |
| INVALID | HIGH | FAIL | DECLINE |
| EXPIRED / REPLAY | any | any | DECLINE |

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
| `intent` | Verifiable Intent payload (or null on human path with documented fallback) |

JSON shape (illustrative):

```json
{
  "event_id": "evt_01J...",
  "transaction_id": "txn_01J...",
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

### 5.3 Idempotency

```
if idempotency_key in store:
    return stored_result
process()
store(idempotency_key, result)
```

Also persist `event_id` so Kafka replay cannot double-settle. Payment processing must be deterministic under retry.

### 5.4 Event time and late data

Use **event time**, not ingestion time.

- Watermarks on the payment stream
- Windowed aggregations for features and metrics
- Late events update stateful features; they do not rewrite a settled decision
- Settled decisions are immutable; corrections are new compensating events

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

Human checkout may skip agent credentials but still runs fraud + policy.

Until the official library is wired in, **do not ship a parallel crypto module**. Stub the verifier behind an interface (`IntentVerifier`) so the rest of the platform can be built against a fake that only exists in tests.

---

## 7. Streaming and state

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

### Processor responsibilities

1. Schema validate
2. Deduplicate on `event_id`
3. Enrich with Redis online features
4. Emit state transitions
5. Maintain windowed aggregates (1 minute, 5 minute sliding, 1 hour)
6. Sink to Redis (hot path) and to the lakehouse (cold path)

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

Latency budget for scoring: well under the overall p95 decision SLO of 100ms. SHAP only for medium/high risk or explicit `/explain` — not on every approve.

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
| API (FastAPI) | Ingress, decision orchestration |
| Postgres | Transaction + idempotency store |
| Redpanda or Kafka | Event log |
| Redis | Online features and hot metrics |
| Stream processor (Spark or Kafka Streams / Flink-lite) | Enrich, aggregate, sink |
| Fraud workers | Ensemble inference |
| Intent verifier | Official spec adapter (stub until wired) |
| Simulator | Load / demo traffic |
| Lakehouse jobs | Spark + Delta on a local volume |
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
│   ├── stream-processor/
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
| 1 Foundation | Compose, API, Postgres, state machine, idempotency | A payment can be created and fetched; retries are safe |
| 2 Streaming | Broker, simulator, `payments` + `transaction-states` | Events survive restart; lag is visible |
| 3 Lakehouse | Bronze → silver → gold on local Delta | A day’s sim data is queryable in gold |
| 4 Features | Redis online + gold offline | `/v1/payments` enriches before scoring |
| 5 Fraud engine | Ensemble + SHAP on demand | Score is a dimension, not the decision |
| 6 Observability | Prom/Grafana, traces, SLO boards | p95 latency is measured, not guessed |
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

- Unit: features, policy rules, state transitions, idempotency store
- API: create, replay same `idempotency_key`, fetch state
- Threat model: cases A–H as automated tests
- Streaming: duplicate `event_id` does not double-decide
- Model: score in `[0,1]`; high velocity raises score on a fixture
- Investigator: attempting `approve_payment` is a hard error
- Load: Locust (or equivalent) against `/v1/payments` with a published TPS and p95

No test should require AWS.

---

## 18. Anti-patterns

Do not:

- Call Kafka → Spark → Postgres “a payment platform” without auth, policy, state, and audit
- Ask an LLM “is this fraud?” and take the answer as the system
- Hardcode `score > 0.7 → decline` as the whole framework
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

**When cloud is eventually in scope:** AWS is the default port (fintech ecosystem, KMS / Payment Cryptography, broad recruiter familiarity). Azure is a secondary option, not the primary. GCP is a poor fit for this problem. LocalStack is a migration aid, not a week-1 task.

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
3. See approve / challenge / decline with **three** dimensions, not one score
4. Replay the same `idempotency_key` safely
5. Break intent (amount, merchant, replay) and watch fail-closed
6. See a valid intent still go to review under high fraud
7. Open an investigation without any path to `approve_payment`
8. View Grafana latency and lag
9. Query gold aggregates for the session

That is the product. Everything else is optional.
