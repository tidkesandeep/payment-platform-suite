# Payment Platform

**Status:** Canonical — this is the single source of truth  
**Supersedes:** `PAYMENTS_PORTFOLIO_IMPLEMENTATION_GUIDE.md`, `IMPLEMENTATION_GUIDE_COMPARISON.md`, `CLOUD_PROVIDER_STRATEGY.md`, `DOCUMENTATION_INDEX.md`  
**Updated:** 2026-08-20 (industry practices: decision matrix, two-TX idempotency, minor units, HTTP, velocity split)  
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
| Broker | **Redpanda** locally (Kafka protocol) | One choice; Kafka-compatible without ZK |
| Hot path | Synchronous API only | p95 decision &lt; 100ms |
| Async path | Kafka consumers + lakehouse jobs | Metrics, gold tables, retraining — not authorize |
| Stream processor | Kafka consumer group (or Kafka Streams) on the async path; Spark **only** for lakehouse ETL | Spark/micro-batch must never sit on `/v1/payments` |
| Writes | Two short Postgres transactions: **claim** then **complete+outbox** | Do not hold a DB TX across Redis/model I/O |
| Idempotency | Unique `(api_key_id, idempotency_key)` + lease + request fingerprint | Stripe-style; crash-reclaimable |
| Money | Integer **minor units** + ISO 4217 currency | Never `float` for amounts |
| Traffic | Simulator **POSTs `/v1/payments`** | Never produce authorize events straight to Kafka |
| Policy | Deterministic rule table, separate from the model | Velocity/limits are not a fraud score |
| Velocity | Split **attempt** vs **approved** counters | Card-testing vs spend-limit are different |
| Settlement | Async no-op stub after `AUTHORIZED` | This product authorizes; it does not move money |
| Degradation | Table in §5.7 — never fail open | Infra faults: 503 or REVIEW; they do not approve |
| Intent | Official Mastercard Verifiable Intent spec | Standards integration, not invented RSA |
| Decisioning | Authorization × fraud × policy; policy fail always wins | Agentic commerce fails if these are collapsed |
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
┌──────────────┐     complete TX + outbox ┌─────────────────┐
│ API          │ ────────────────────────► │ Redpanda        │
│ 1. claim idempotency (short TX)         └────────┬────────┘
│ 2. validate                                      │
│ 3. intent verify                                 ├─► state projector
│ 4. Redis features + attempt INCR                 ├─► windowed metrics
│ 5. champion score (in-process)                   ├─► lakehouse (Spark)
│ 6. policy rules                                  └─► dashboards / investigator
│ 7. complete TX: persist + outbox
│ 8. return 200 + decision
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
  │                     │ TX1 claim lease    │                     │                   │               │
  │                     │ mint transaction_id│                     │                   │               │
  │                     │ COMMIT             │                     │                   │               │
  │                     │                    │ if terminal: 200 replay                 │               │
  │                     │                    │ if leased (other): 409                  │               │
  │                     │ validate           │                     │                   │               │
  │                     │ verify intent      │                     │                   │               │
  │                     │─────────────────────────────────────────►│                   │               │
  │                     │ INCR attempt vel   │                     │                   │               │
  │                     │ HGET features      │                     │                   │               │
  │                     │─────────────────────────────────────────────────────────────►│               │
  │                     │ champion score     │                     │                   │               │
  │                     │─────────────────────────────────────────────────────────────────────────────►│
  │                     │ policy.evaluate()  │                     │                   │               │
  │                     │ TX2 persist+outbox │                     │                   │               │
  │                     │ INCR approved vel  │  (only if AUTHORIZED)                   │               │
  │                     │ COMMIT             │                     │                   │               │
  │                     │ (publisher drains outbox → Redpanda)     │                   │               │
  │◄──── 200 decision ──│                    │                     │                   │               │
```

The API process owns the state machine on the hot path. Async consumers **project** events; they do not take a second authorize decision.

Do **not** hold TX1 across Redis or model I/O. Claim, then work, then complete.

### Transaction state machine

Hot-path happy path (this is the product):

```
CREATED
  → VALIDATED
  → INTENT_VERIFIED      (skipped on human path; see §6)
  → ENRICHED             (Redis feature materialization, in-request)
  → RISK_SCORED
  → DECISIONED
  → AUTHORIZED | CHALLENGED | MANUAL_REVIEW | RISK_DECLINED
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

Terminal for idempotency: any of `AUTHORIZED`, `CHALLENGED`, `MANUAL_REVIEW`, `VALIDATION_FAILED`, `INTENT_INVALID`, `RISK_DECLINED`, `POLICY_VIOLATION`, `PROCESSING_FAILED`. Replay of the same `(api_key_id, idempotency_key)` with the **same request fingerprint** returns that stored terminal. If the row is still leased (`in_progress` and `lease_expires_at` in the future): **409**. If the lease expired (process crashed): reclaim and process again. If the key is reused with a **different body**: **422**.

`CHALLENGED` and `MANUAL_REVIEW` are **holds**, not pays. Phase 1 returns them as decisions with no step-up protocol. Phase 9–10 may add an operator queue and hold TTL; not required to start.

---

## 4. Decision model

Do not implement `if fraud_score < 0.2: approve`.

Gates, in order (issuer/PSP practice):

1. **Validation** — malformed request never reaches risk
2. **Authorization / intent** — invalid crypto is always decline
3. **Policy** — limit/scope/velocity fail is always decline (**policy fail wins over any fraud band**)
4. **Fraud band** — only if auth is VALID/HUMAN and policy PASS

```
decision = f(authorization, fraud, policy)
```

| Authorization | Fraud | Policy | Decision | State | HTTP |
|---|---|---|---|---|---|
| VALID or HUMAN | LOW | PASS | APPROVE | `AUTHORIZED` | 200 |
| VALID or HUMAN | MEDIUM | PASS | CHALLENGE | `CHALLENGED` | 200 |
| VALID or HUMAN | HIGH | PASS | REVIEW | `MANUAL_REVIEW` | 200 |
| VALID or HUMAN | CRITICAL | PASS | DECLINE | `RISK_DECLINED` | 200 |
| VALID or HUMAN | UNKNOWN | PASS | REVIEW | `MANUAL_REVIEW` | 200 |
| VALID or HUMAN | any | FAIL | DECLINE | `POLICY_VIOLATION` | 200 |
| INVALID / EXPIRED / REPLAY | any | any | DECLINE | `INTENT_INVALID` | 200 |

`RISK_DECLINED` is **only** for CRITICAL auto-decline. Review queues do not scale; extreme scores are not referred to humans. Threat H (valid intent, abusive behaviour): HIGH → `MANUAL_REVIEW`; CRITICAL → `RISK_DECLINED`.

Thresholds are configuration, not architecture. Starting bands:

| Band | Score | Meaning |
|---|---|---|
| LOW | `[0.00, 0.20)` | Approve if policy passes |
| MEDIUM | `[0.20, 0.70)` | Hold / challenge |
| HIGH | `[0.70, 0.95)` | Refer |
| CRITICAL | `[0.95, 1.00]` | Auto-decline |
| UNKNOWN | no score | Refer; never approve |

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
| `amount_minor` | Integer minor units (e.g. `12550` = 125.50 USD). **Never a float.** |
| `currency` | ISO 4217, uppercase |
| `merchant_category` | MCC |
| `country`, `device_id`, `ip_address` | Risk context |
| `timestamp` | Event time (not ingestion time) |
| `channel` | `human` or `agent` |
| `agent_id` | Required when `channel=agent` |
| `intent` | Verifiable Intent payload; **required** when `channel=agent`; **null** when `channel=human` |

**Who mints IDs**

| ID | Minted by | Form |
|---|---|---|
| `idempotency_key` | Client | Opaque string, unique **per API client** |
| `api_key_id` | Server (from the demo API key) | Scopes the idempotency unique key |
| `event_id` | API | ULID per outbox row / event |
| `transaction_id` | API, **minted in the claim TX** | ULID, stable for the payment; reused on replay |

Do not let the client supply `transaction_id` as the idempotency mechanism.

Request JSON (illustrative):

```json
{
  "idempotency_key": "idem_merchant_order_123",
  "customer_id": "cust_001",
  "merchant_id": "mer_789",
  "amount_minor": 12550,
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

Callers of `POST /v1/payments` in local demo: the simulator and a documented API key (compose network). There is no end-user OAuth in Phase 1. `agent_id` on the request must match the intent credential binding when `channel=agent`.

**HTTP (industry: business result in the body, not a 4xx for a legitimate decline):**

| Situation | HTTP | Body |
|---|---|---|
| Terminal business decision (approve / decline / challenge / review) | **200** | decision record |
| Idempotent replay (same key, same fingerprint) | **200** | stored decision |
| Same key, request still leased | **409** | `{ "error": "in_progress" }` |
| Same key, different body fingerprint | **422** | `{ "error": "idempotency_fingerprint_mismatch" }` |
| Schema / validation fail | **422** | `{ "error": "validation_failed", "details": [...] }` |
| Postgres / unrecoverable infra | **503** | `{ "error": "unavailable" }` |

Do not use 402/403 for fraud or policy decline.

### 5.3 Idempotency

Postgres is the idempotency store. Scope is **`(api_key_id, idempotency_key)`**, not a global bare string (avoids two simulators colliding on `order-1`). Store a **SHA-256 fingerprint** of the canonical request body (excluding the key header). Same key + different body is a client bug → 422.

Lease / crash recovery (Stripe-style):

- Claim sets `status=in_progress`, `lease_expires_at = now() + 30s` (above p99 with margin)
- Another caller during the lease → **409** (do not wait-loop in Phase 1)
- If the API crashes, the lease expires; the next POST **reclaims** and processes
- Terminal rows never expire for the demo window (days, not seconds)

Algorithm:

1. Mint `transaction_id` (ULID) in memory
2. **TX1 (claim):** `INSERT` `(api_key_id, key, transaction_id, fingerprint, in_progress, lease_expires_at)` or `SELECT … FOR UPDATE`
   - terminal + fingerprint match → return stored decision
   - terminal + fingerprint mismatch → 422
   - in_progress and lease valid → 409
   - in_progress and lease expired → take over (new `transaction_id` only if no terminal row exists; keep the same `transaction_id` if one was already minted on the row)
3. **COMMIT TX1**
4. Validate, verify intent, Redis features, score, policy (**no open DB TX**)
5. **TX2 (complete):** write `transactions` + `outbox` rows; set idempotency `terminal` + `decision_json`
6. **COMMIT TX2**
7. Publisher drains outbox after commit

Redis `idem:{api_key_id}:{key}` may cache after TX2. It is not authoritative.

### 5.4 Outbox

Do not `INSERT` into Postgres and `produce()` to Kafka as two independent I/O calls.

```
transactions  ─┐
outbox        ─┴─ same Postgres transaction
                 after COMMIT: publisher reads outbox, produces to Kafka, marks published
```

Outbox payload: one row per **(event, topic)**. At-least-once produce is allowed; consumers dedupe on `event_id` **within a topic**.

### 5.5 Clocks and late data

- **Decision clock:** API server UTC (`received_at`). Intent expiry and hour-of-day use this.
- **Client `timestamp`:** risk feature only; it may be spoofed. Ignore it for expiry.
- Async path uses event time = `received_at` (not ingestion lag).
- Late events update Redis / gold features; they do not rewrite a **terminal** decision.
- Terminal decisions are immutable. No reversal API in Phase 1–11 (no money movement).

### 5.6 Postgres (minimum)

```
idempotency_keys (
  api_key_id TEXT NOT NULL,
  key TEXT NOT NULL,
  transaction_id TEXT NOT NULL,  -- minted BEFORE insert
  fingerprint TEXT NOT NULL,     -- sha256 of canonical body
  status TEXT NOT NULL,          -- in_progress | terminal
  lease_expires_at TIMESTAMPTZ,
  decision_json JSONB,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (api_key_id, key)
)

transactions (
  transaction_id TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL,
  api_key_id TEXT NOT NULL,
  state TEXT NOT NULL,
  channel TEXT NOT NULL,
  customer_id TEXT NOT NULL,
  merchant_id TEXT NOT NULL,
  amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
  currency CHAR(3) NOT NULL,
  authorization_status TEXT,
  fraud_score DOUBLE PRECISION,
  fraud_band TEXT,
  policy_status TEXT,
  policy_violations JSONB,
  received_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ,
  UNIQUE (api_key_id, idempotency_key)
)

outbox (
  id BIGSERIAL PRIMARY KEY,
  event_id TEXT NOT NULL,
  topic TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  published_at TIMESTAMPTZ,
  UNIQUE (event_id, topic)
)
```

Each authorize writes two outbox rows (same or different `event_id`s): `payments` and `transaction-states`. Unique is `(event_id, topic)`, not `event_id` alone.

Events on the wire: JSON with `schema_version: 1`. No Avro in Phase 1. Additive fields only.

### 5.7 Degradation

| Dependency | Authorize behavior | `/ready` |
|---|---|---|
| Postgres down | 503 | not ready |
| Intent verifier error (agent path) | fail closed → `INTENT_INVALID`; 503 if process dead | not ready if process dead |
| Redis down | attempt/approved counters unavailable → **policy FAIL** (`velocity_unavailable`); **do not APPROVE** | ready-degraded |
| Redis empty (cold start) | same as missing velocity: **no APPROVE** until counters exist **or** Phase 1 in-request INCR has run for this customer | ready-degraded |
| Fraud model timeout / down | `fraud_band=UNKNOWN` → `MANUAL_REVIEW` if policy PASS | ready-degraded |
| Redpanda / publisher down | TX2 still COMMITs; outbox drains later | ready if DB up; alert on outbox lag |
| Investigator down | authorize unaffected | ready |

Never fail **open**. Missing velocity is a policy fail, not a skipped rule.

### 5.8 Policy engine

Policy is a deterministic rule table evaluated **after** intent and fraud, **never** inside the model.

Split velocity (industry: card-testing vs spend limit are different):

| Counter | When to increment | Used by |
|---|---|---|
| `attempt_1h` / `attempt_24h` | After `VALIDATED`, every attempt including declines | Policy (testing/abuse) + fraud features |
| `approved_count_*` / `approved_amount_minor_*` | Only on `AUTHORIZED` | Policy spend cap |

Phase 1: **INCR in-request** (sync Redis, Postgres fallback if Redis is down). Do not wait for async consumers to create counters. Async jobs may rebuild aggregates from the log later; they must not be the only writer in Phase 1.

| Rule | Fail when |
|---|---|
| `max_amount_minor` | `amount_minor` &gt; limit (global and per-agent) |
| `merchant_allowlist` | merchant not in scope |
| `attempt_velocity_1h` / `_24h` | attempt count exceeds cap |
| `approved_amount_24h` | approved spend exceeds cap |
| `velocity_unavailable` | counters cannot be read **and** cannot be incremented |
| `currency` | not in allowlist (`USD` for Phase 1) |
| `channel_agent_requires_intent` | `channel=agent` and intent missing/invalid |

Evaluation: run **all** rules; record every violation; first fail still determines `POLICY_VIOLATION`. Policy does not call the LLM.

### 5.9 Validation (`VALIDATED`)

422 and `VALIDATION_FAILED` when any of:

- `amount_minor` missing, not integer, or `<= 0`
- `currency` not ISO 4217 / not allowlisted
- `channel` not `human` or `agent`
- `channel=agent` without `agent_id` + `intent`
- `channel=human` with `agent_id` or `intent`
- `customer_id` / `merchant_id` empty
- body larger than a documented cap
- `Idempotency-Key` / `idempotency_key` missing

Client `timestamp` is optional; if present and unparsable, ignore it (feature = null), do not 422.

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
| Valid intent + HIGH fraud | `MANUAL_REVIEW` |
| Valid intent + CRITICAL fraud | `RISK_DECLINED` |

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
| `vel:attempt:{id}:{window}` | Attempt counters (incr after VALIDATED) |
| `vel:approved:{id}:{window}` | Approved count/amount (incr only on AUTHORIZED) |
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

| Model | Role | On `/v1/payments`? |
|---|---|---|
| XGBoost (champion) | Sole scorer | **Yes** — in-process, timeout ~20ms |
| LightGBM | Shadow / challenger | **No** until measured (async later) |
| Small feed-forward net | Shadow | **No** until measured |

Do **not** round-trip Redpanda to score.

Latency budget: champion scoring well under the p95 100ms envelope. SHAP only for HIGH/CRITICAL or `/explain` — never on APPROVE.

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
| B | Delegation abuse (out of spec constraints) | Intent constraint check | `INTENT_INVALID` |
| B2 | Delegation abuse (policy allowlist) | Policy `merchant_allowlist` | `POLICY_VIOLATION` |
| C | Amount manipulation | Bound amount vs `amount_minor` | `INTENT_INVALID` |
| D | Merchant substitution | Bound merchant vs request | `INTENT_INVALID` |
| E | Checkout tampering | Payload vs signed claims | `INTENT_INVALID` |
| F | Replay | intent `jti` / expiry (server clock); idempotency for HTTP retries | `INTENT_INVALID` or 200 replay |
| G | Bad or compromised key | Signature failure | `INTENT_INVALID` |
| H | Valid intent + HIGH fraud | Fraud band HIGH | `MANUAL_REVIEW` |
| H2 | Valid intent + CRITICAL fraud | Fraud band CRITICAL | `RISK_DECLINED` |

H is a central design principle. Tests must include “signature valid, HIGH → review” and “signature valid, CRITICAL → auto-decline.”

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
3. **Simulator** — HTTP client that **POSTs `/v1/payments`** at a configurable rate (hundreds to low thousands TPS). It must **not** write to Redpanda. Authorize, idempotency, and outbox only exist if traffic enters through the API.

Label agentic vs human explicitly so models can be compared with and without intent features.

---

## 14. Local runtime (current target)

Cloud is deferred. The runnable system is Docker Compose.

| Service | Role |
|---|---|
| API (FastAPI) | Ingress, **sync authorize**, outbox writer |
| Outbox publisher | Same app or sidecar; drains Postgres → Kafka |
| Postgres | Transaction + idempotency + outbox (SoR) |
| Redpanda | Event log (async); Kafka protocol |
| Redis | Online features and hot metrics |
| Async consumers | Project states, windows, bronze sink |
| Spark (lakehouse only) | Bronze → silver → gold |
| Fraud | Champion model **in API process** |
| Intent verifier | Official spec adapter (stub until wired); in-request |
| Simulator | Load / demo traffic |
| Prometheus + Grafana | SLOs and dashboards |
| MLflow (optional) | Model registry |
| Investigator (optional) | Read-only agent |

Suggested compose ports: API `8000`, Redpanda `9092`, Redis `6379`, Postgres `5432`, Grafana `3000`, Prometheus `9090`, dashboard `8501` if a Streamlit view is kept.

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

## 16. Industry practices by phase

These are the implementation rules. Later phases must not undo earlier contracts.

### Phase 1 — Foundation (do this, nothing more)

**In:** Compose (API, Postgres, Redis, **Redpanda**), schema, two-TX idempotency, outbox **table** (publisher may start in Phase 2), validation, policy table, stub `IntentVerifier`, champion or deterministic stub scorer, sync Redis `INCR` for attempt/approved, HTTP mapping above.

**Out:** Spark, lakehouse, investigator, official VI library, SHAP, Grafana, load tests at “production” TPS.

**Practices:**

- Money as `BIGINT amount_minor`
- 200 for business declines; 409/422/503 as specified
- Lease 30s; reclaim on expiry; fingerprint mismatch → 422
- Missing Redis velocity → policy fail, not skip
- Agent stub verifier fails closed except injected unit tests
- Simulator is HTTP

**Done when:** concurrent same-key POSTs: one authorize, one 409 or one 200 replay; crash mid-lease then retry succeeds; float amounts are rejected.

### Phase 2 — Streaming

**In:** Outbox publisher, Redpanda, consumers that **project only**, HTTP simulator at modest TPS.

**Out:** Consumers that score or authorize. Direct Kafka produce from the simulator.

**Practices:** at-least-once + dedupe `(topic, event_id)`; authorize still 200 if Redpanda is down (outbox lag alert).

### Phase 3 — Lakehouse

**In:** Spark **jobs** bronze→silver→gold from topics/files.

**Out:** Spark on the API process.

### Phase 4 — Features

**In:** Richer Redis features; async rebuild from gold **in addition to** Phase 1 INCR (INCR remains source of truth for attempt/approved).

**Out:** Replacing in-request INCR with async-only writers (creates a race on the next request).

### Phase 5 — Fraud

**In:** Real XGBoost champion in-process; IEEE-CIS + synthetic; time-ordered split.

**Out:** Weighted three-model blend on the hot path; SageMaker.

Shadow LightGBM only after champion p95 is measured.

### Phase 6 — Observability

**In:** OTel traces on `/v1/payments`, Prom histograms, outbox lag, lease reclaim count, 409 rate.

**Out:** Treating 99.9% as a contractual SLO.

### Phase 7 — Investigator

**In:** Allowlisted read tools, audit log, deterministic template if no LLM.

**Out:** Any tool that mutates `transactions.state`.

### Phase 8 — Verifiable Intent

**In:** Official spec adapter; replace stub; threats A–G as tests.

**Out:** Homemade RSA; forking and renaming the reference repo.

### Phase 9 — Agentic demo

**In:** Human + agent in one compose; H and H2 tests green.

**Out:** Step-up/3DS (still a hold). Hold TTL and operator queue may start here if needed.

### Phase 10 — Security review

**In:** Secrets not in git, no real PII, threat tests in CI.

**Out:** PCI claims.

### Phase 11 — Honest scale

**In:** Published TPS and p95 from Locust against `/v1/payments`.

**Out:** Invented 1M TPS.

### Phase 12 — Cloud

**Deferred.** Do not start.

### Phase 13 — Research

Optional, after 1–11.

---

## 17. Implementation phases

Build **capability layers**. Do not complete “fraud as a standalone repo,” then “streaming as a standalone repo.”

Cloud phase is listed only so it is not forgotten. Do not start it.

| Phase | Capability | Done when |
|---|---|---|
| 1 Foundation | Compose, API, Postgres schema, two-TX idempotency, outbox, policy, stub intent | Concurrent same-key: one authorize + 409/replay; lease reclaim after crash; `amount_minor` integer |
| 2 Streaming | Redpanda, outbox publisher, HTTP simulator, async projectors | Events survive restart; authorize works if broker is down |
| 3 Lakehouse | Bronze → silver → gold on local Delta **via Spark jobs** | A day’s sim data is queryable in gold |
| 4 Features | Redis online (INCR remains SoR) + gold offline rebuild | `/v1/payments` enriches from Redis, not from Spark |
| 5 Fraud engine | Champion in-process + SHAP on demand | Score is a dimension, not the decision |
| 6 Observability | Prom/Grafana, traces, SLO boards, outbox lag, 409 rate | p95 latency is measured, not guessed |
| 7 Investigator | Allowlisted tools, audit, no pay tool | Case file exists; approve is impossible |
| 8 Verifiable Intent | Official spec, not custom RSA | Threats A–G fail closed |
| 9 Agentic demo | Human + agent paths in one flow | H and H2 tests pass |
| 10 Security review | Threat tests, secrets hygiene, no real PII | Checklist green |
| 11 Scale (honest) | Load test at a stated TPS | Publish measured p95, not invented 1M TPS |
| 12 Cloud | AWS/LocalStack | **Deferred** |
| 13 Research | Intent-as-feature experiment | Optional, after the platform works |

Phases 1–7 can proceed with an `IntentVerifier` stub. Phase 8 replaces the stub. Do not implement homemade RSA in the meantime.

---

## 18. Testing

Minimum bar:

- Unit: features, **policy rules**, state transitions, idempotency store
- Concurrent idempotency: two parallel POSTs → one authorize and one **409** (or one 200 replay)
- Fingerprint mismatch on same key → **422**
- Lease expiry: kill API mid-request, retry same key → reclaim, not stuck
- API: create, replay same key, fetch state
- Outbox: killing Redpanda mid-request still leaves drainable rows; unique `(event_id, topic)`
- Threat model: A–G, H, H2
- Float `amount` rejected; `amount_minor` required
- Model: timeout → UNKNOWN → REVIEW, never APPROVE
- Redis down → no APPROVE (policy `velocity_unavailable`)
- Investigator: attempting `approve_payment` is a hard error
- Load: Locust (or equivalent) against `/v1/payments` with a published TPS and p95

No test should require AWS.

---

## 19. Anti-patterns

Do not:

- Call Kafka → Spark → Postgres “a payment platform” without auth, policy, state, and audit
- Put Spark or any micro-batch processor on `/v1/payments`
- `INSERT` then `produce()` without an outbox
- Check-then-act idempotency without a unique row lock
- Ask an LLM “is this fraud?” and take the answer as the system
- Hardcode `score > 0.7 → decline` as the whole framework
- Hold a Postgres transaction open across Redis or model I/O
- Use `float` for money
- Let the simulator produce to Kafka/Redpanda
- Skip velocity when Redis is empty or down
- Blend three models on the 100ms path
- 4xx for a legitimate policy/fraud decline (use **200** + state)
- Global unique idempotency key with no API-key scope
- Use real payment or card data
- Claim PCI, SOX, GDPR certification, or Mastercard partnership
- Invent Verifiable Intent with ad-hoc RSA
- Equate valid authorization with approve
- Put cloud account setup on the critical path
- Publish 600M tx/day, 1M TPS, or 0.92 AUC as facts before they are measured

---

## 20. Optional research (after the platform works)

These questions are valuable. They are not a reason to delay phases 1–11.

1. Do Verifiable Intent features improve fraud models vs traditional features only?
2. Can selective disclosure cut sensitive-data exposure without hurting detection?
3. What should happen when authorization is valid and behavior is anomalous?
4. How should autonomous limits adapt to behavioral risk?

Compare precision, recall, FPR, FNR, AUC. Keep this as an experiment notebook on gold data.

---

## 21. Deferred: cloud

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

## 22. How to use the older documents

| File | Use now |
|---|---|
| `PAYMENT_PLATFORM.md` | **Follow this.** |
| `PAYMENTS_PORTFOLIO_IMPLEMENTATION_GUIDE.md` | Historical. Some feature lists and Docker service names were absorbed here. Ignore custom RSA, fraud-only decisions, ADLS-as-required, and scale theater. |
| `IMPLEMENTATION_GUIDE_COMPARISON.md` | Historical rationale for the locked decisions in §2. |
| `CLOUD_PROVIDER_STRATEGY.md` | Historical. Relevant only when Phase 12 is opened. |
| `DOCUMENTATION_INDEX.md` | Pointer to this file. |

---

## 23. Definition of a credible demo

A reviewer should be able to:

1. `docker compose up` (or the documented equivalent)
2. Drive a human payment and an agent payment
3. See approve / challenge / review / decline with **three** dimensions, not one score
4. Replay the same idempotency key safely, including concurrent 409 vs 200 replay
5. Reject float amounts; accept `amount_minor`
5. Break intent (amount, merchant, replay) and watch fail-closed
6. See a valid intent still go to review under high fraud
7. Open an investigation without any path to `approve_payment`
8. View Grafana latency and lag
9. Query gold aggregates for the session

That is the product. Everything else is optional.
