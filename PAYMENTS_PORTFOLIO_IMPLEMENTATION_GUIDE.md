> **Historical.** This document is superseded by [`PAYMENT_PLATFORM.md`](./PAYMENT_PLATFORM.md), the single source of truth. Do not implement from this file.

# Payment Platform Suite: Implementation Guide
**Version:** 1.0  
**Created:** August 2026  
**Timeline:** 12 weeks (Aug - Oct 2026)

---

## TABLE OF CONTENTS
1. [Executive Summary](#executive-summary)
2. [Project Architecture Overview](#project-architecture-overview)
3. [Component 1: Real-Time Fraud Detection Platform](#component-1-real-time-fraud-detection-platform)
4. [Component 2: Real-Time Payments Data Platform](#component-2-real-time-payments-data-platform)
5. [Component 3: Payment Transaction Lakehouse](#component-3-payment-transaction-lakehouse)
6. [Component 4: Verifiable Intent Integration (Optional)](#component-4-verifiable-intent-integration)
7. [Integration Architecture](#integration-architecture)
8. [Deployment & Infrastructure](#deployment--infrastructure)
9. [Testing & Quality Assurance](#testing--quality-assurance)
10. [Monitoring & Observability](#monitoring--observability)
11. [Project Timeline & Milestones](#project-timeline--milestones)

---

## EXECUTIVE SUMMARY

### Project Vision
Build a **production-grade, end-to-end real-time payment platform** that demonstrates mastery of:
- **Payment Systems Architecture** at scale (600M+ tx/day)
- **Real-time ML** for fraud detection and risk scoring
- **Distributed Data Processing** (streaming + batch)
- **Data Governance & Compliance** in fintech
- **Modern Data Architecture** (lakehouse pattern)
- **Agentic Commerce** security (Verifiable Intent)

### Repository Structure
```
payment-platform-suite/
├── README.md (comprehensive overview)
├── ARCHITECTURE.md (this document)
├── docs/
│   ├── fraud-detection/
│   ├── payments-platform/
│   ├── lakehouse/
│   ├── verifiable-intent/
│   └── deployment/
├── fraud-detection/
│   ├── src/
│   ├── tests/
│   ├── models/
│   ├── notebooks/
│   └── docker/
├── payments-data-platform/
│   ├── kafka/
│   ├── stream-processor/
│   ├── api/
│   ├── dashboard/
│   └── docker/
├── transaction-lakehouse/
│   ├── delta-lake/
│   ├── governance/
│   ├── data-quality/
│   └── notebooks/
├── verifiable-intent/ (optional)
│   ├── src/
│   ├── tests/
│   └── integration/
├── docker-compose.yml
└── DEPLOYMENT.md
```

---

## PROJECT ARCHITECTURE OVERVIEW

### System Architecture Diagram
```
┌─────────────────────────────────────────────────────────────────────┐
│                    PAYMENT PLATFORM SUITE                           │
└─────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  INGESTION LAYER                                                   │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │  Payment    │  │  Legacy      │  │  External    │               │
│  │  Simulator  │  │  Systems     │  │  APIs        │               │
│  │ (synthetic) │  │  (CSV/batch) │  │  (Mastercard)│               │
│  └──────┬──────┘  └──────┬───────┘  └──────┬───────┘               │
│         │                │                 │                       │
│         └────────────────┼─────────────────┘                       │
│                          │                                         │
│                    [Kafka Broker]                                  │
│        Topics: payments, fraud-alerts, risk-scores               │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  REAL-TIME PROCESSING LAYER                                       │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌──────────────────────┐      ┌──────────────────────┐           │
│  │  Stream Processor    │      │  Real-Time Fraud ML  │           │
│  │  (Spark Streaming)   │      │  (Inference Engine)  │           │
│  │                      │      │                      │           │
│  │ - Deduplication     │      │ - Feature extraction │           │
│  │ - Windowing         │      │ - Model scoring      │           │
│  │ - Aggregations      │      │ - Decision logic     │           │
│  │ - State management  │      │ - Risk assessment    │           │
│  └──────────┬───────────┘      └──────────┬───────────┘           │
│             │                             │                       │
│             └─────────────┬───────────────┘                       │
│                          │                                        │
│              [Redis/In-Memory State Store]                        │
│         (Customer profiles, transaction history, rules)           │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  API & DECISION LAYER                                             │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │  FastAPI Decision Engine                                  │   │
│  │  ├─ /score (real-time fraud score)                         │   │
│  │  ├─ /authorize (fraud+risk+intent verification)            │   │
│  │  ├─ /explain (SHAP explanations)                           │   │
│  │  └─ /health (liveness probes)                              │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  STORAGE & ANALYTICS LAYER                                        │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌──────────────────────┐      ┌──────────────────────┐           │
│  │  Delta Lake Lakehouse│      │  Data Warehouse      │           │
│  │  (ADLS Gen2)         │      │  (for analytics)     │           │
│  │                      │      │                      │           │
│  │  Bronze Layer        │      │  Dashboards          │           │
│  │  ├─ Raw transactions │      │  ├─ Fraud rates      │           │
│  │  └─ Events           │      │  ├─ TPM metrics      │           │
│  │                      │      │  ├─ Risk trends      │           │
│  │  Silver Layer        │      │  └─ Model performance│           │
│  │  ├─ Cleaned data     │      │                      │           │
│  │  └─ Deduplicated     │      │  Alerting            │           │
│  │                      │      │  ├─ Fraud patterns   │           │
│  │  Gold Layer          │      │  └─ Anomalies        │           │
│  │  ├─ Aggregates       │      │                      │           │
│  │  └─ ML features      │      │                      │           │
│  └──────────────────────┘      └──────────────────────┘           │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  GOVERNANCE & COMPLIANCE LAYER                                    │
├────────────────────────────────────────────────────────────────────┤
│  ├─ Data Catalog (Data Lineage)                                   │
│  ├─ PII/PHI Detection & Masking                                   │
│  ├─ Audit Logs (all access, changes)                              │
│  ├─ Data Retention Policies                                       │
│  └─ Compliance Checks (SOX, PCI, GDPR)                            │
└────────────────────────────────────────────────────────────────────┘
```

### Data Flow
```
Payment Transaction
    ↓
[Kafka] → Deduplication, Validation
    ↓
[Stream Processor] → Feature extraction, Aggregation
    ↓
[Real-Time ML] → Fraud score, Risk score
    ↓
[Decision Engine] → Approve/Challenge/Block
    ↓
[Response] → Transaction auth response
    ↓
[Delta Lake] → Audit trail, Analytics

Parallel:
    ↓ [Batch] → Historical analysis, Model retraining
```

### Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Data Ingestion** | Kafka | Mastercard standard; real-time; scalable |
| **Stream Processing** | Spark Streaming / Kafka Streams | Battle-tested; PySpark familiarity |
| **ML Inference** | FastAPI + PyTorch/SKLearn | Low-latency, production-ready |
| **State Management** | Redis | Sub-millisecond latency |
| **Data Storage (Analytics)** | Delta Lake (ADLS Gen2 / S3) | Lakehouse pattern; ACID transactions |
| **Orchestration** | Apache Airflow | Dag scheduling for retraining, backfills |
| **Monitoring** | Prometheus + Grafana | Fintech standard; proven |
| **Logging** | ELK Stack (Elasticsearch, Logstash, Kibana) | Centralized logging; compliance |
| **Containerization** | Docker + Docker Compose | Local dev + cloud deployment |
| **CI/CD** | GitHub Actions | Integrated with repo |

---

## COMPONENT 1: REAL-TIME FRAUD DETECTION PLATFORM

### 1.1 Objective
Build a **production-grade real-time fraud detection system** that:
- Scores transactions in real-time (<100ms latency)
- Detects fraud patterns with 85%+ precision
- Provides explainable fraud scores (SHAP values)
- Integrates with payment pipeline
- Demonstrates ML ops maturity

### 1.2 Fraud Detection Architecture

```
┌──────────────────────────────────────────────────────┐
│  FRAUD DETECTION SYSTEM                              │
└──────────────────────────────────────────────────────┘

REAL-TIME INFERENCE PATH:
┌─────────────┐  ┌──────────────────┐  ┌───────────────┐
│  Transaction│→ │ Feature Extraction│→ │ Model Scoring │
│  (Raw)      │  │ (Real-time)       │  │ (Ensemble)    │
└─────────────┘  └──────────────────┘  └───────┬───────┘
                                                │
                                        ┌───────▼─────────┐
                                        │ Risk Decision   │
                                        │ ├─ Score < 0.2 │
                                        │ │   (Approve)   │
                                        │ ├─ 0.2 - 0.7    │
                                        │ │   (Challenge) │
                                        │ └─ > 0.7        │
                                        │   (Block)       │
                                        └─────────────────┘

TRAINING PIPELINE:
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  Historical  │→ │   Feature    │→ │ Hyperparameter│→ │ Model Store  │
│ Transactions │  │   Engineering │  │ Optimization │  │ (Versioned)  │
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
                                             │
                                    (Weekly retraining)
```

### 1.3 Features Engineering

#### Real-Time Features (Low Latency)
```python
Real-Time Feature Set (Calculated on-the-fly):
├── Transaction Level:
│   ├── amount (transaction amount)
│   ├── merchant_category (MCC)
│   ├── transaction_type (online/offline/recurring)
│   └── hour_of_day (temporal)
│
├── Customer Level (from Redis state):
│   ├── customer_age (days since account creation)
│   ├── transactions_30d (count in 30 days)
│   ├── avg_transaction_amount_30d
│   ├── velocity_24h (transactions in 24 hours)
│   ├── velocity_1h (transactions in 1 hour)
│   ├── unique_merchants_30d
│   └── days_since_last_transaction
│
├── Merchant Level:
│   ├── merchant_avg_transaction
│   ├── merchant_fraud_rate
│   ├── merchant_chargeback_rate
│   └── is_high_risk_merchant
│
├── Location Level:
│   ├── is_customer_home_country
│   ├── distance_from_last_transaction (km)
│   ├── country_fraud_rate
│   └── is_vpn_detected
│
└── Network Level:
    ├── n_customers_same_device_24h
    ├── n_cards_same_device_24h
    ├── device_fraud_rate
    └── is_new_device
```

#### Aggregate Features (Pre-computed)
```python
# Computed hourly and stored in Redis for fast retrieval:
├── Customer aggregates (customer_id + time_window)
│   ├── SUM(amount_24h), SUM(amount_7d), SUM(amount_30d)
│   ├── COUNT(txn_24h), COUNT(txn_7d)
│   ├── MAX(amount_24h), MIN(amount_24h)
│   ├── STD(amount_30d)
│   └── HAS_CHARGEBACK_30d
│
├── Merchant aggregates (merchant_id + time_window)
│   ├── COUNT(txn_24h), SUM(amount_24h)
│   ├── FRAUD_RATE_30d
│   └── CHARGEBACK_RATE_30d
│
└── Device aggregates (device_id + time_window)
    ├── N_UNIQUE_CUSTOMERS_24h
    ├── N_UNIQUE_CARDS_24h
    └── FRAUD_RATE_7d
```

### 1.4 ML Model Architecture

#### Approach: Ensemble
```python
Model Stack:
├── Model 1: XGBoost (Primary Model)
│   ├── Features: 50 (engineered features)
│   ├── Max depth: 7
│   ├── Learning rate: 0.05
│   ├── AUC-ROC: 0.92
│   └── Inference latency: 5-10ms
│
├── Model 2: LightGBM (Fast model)
│   ├── Features: 50
│   ├── Num leaves: 31
│   ├── AUC-ROC: 0.90
│   └── Inference latency: 2-5ms
│
├── Model 3: Neural Network (Deep Learning)
│   ├── Architecture: 3-layer FFN
│   │   ├── Layer 1: 128 neurons, ReLU
│   │   ├── Layer 2: 64 neurons, ReLU
│   │   ├── Layer 3: 32 neurons, ReLU
│   │   └── Output: Sigmoid (0-1)
│   ├── Features: 50 (normalized)
│   ├── AUC-ROC: 0.89
│   └── Inference latency: 10-15ms
│
└── Ensemble Logic:
    ├── Weighted average (XGBoost: 50%, LightGBM: 30%, NN: 20%)
    ├── If ensemble score > 0.7: Use explainability
    └── Total latency: <100ms (SLA)
```

#### Model Training Pipeline
```python
Training Flow:
1. Data Collection
   ├── Source: Delta Lake gold layer
   ├── Lookback: 90 days historical transactions
   ├── Sample size: 10M transactions
   └── Class balance: SMOTE oversampling

2. Feature Engineering
   ├── Create feature matrix (10M x 50)
   ├── Feature importance analysis
   ├── Correlation checks
   └── Scale/normalize (StandardScaler)

3. Train-Test Split
   ├── Train: 80% (time-ordered)
   ├── Validation: 10% (recent data)
   └── Test: 10% (holdout)

4. Hyperparameter Optimization
   ├── Grid search for XGBoost
   ├── Bayesian optimization for NN
   ├── Cross-validation: 5-fold
   └── Early stopping: Monitor validation AUC

5. Model Evaluation
   ├── Metrics: AUC-ROC, PR-AUC, F1, Precision, Recall
   ├── By subgroup: New customers, high-amount txns
   ├── False positive rate < 5%
   └── False negative rate < 2%

6. Model Registry & Versioning
   ├── Store model: MLflow or W&B
   ├── Version: v1.0, v1.1, etc.
   ├── Track: Hyperparams, metrics, training data
   └── Champion/Challenger framework

7. Deployment
   ├── Package: Docker image
   ├── Load: FastAPI inference server
   ├── Cache: Redis for warm model loading
   └── A/B test: Old vs new model (if updating)

Schedule: Weekly automated retraining
```

### 1.5 Implementation Details

#### Directory Structure
```
fraud-detection/
├── README.md
├── src/
│   ├── __init__.py
│   ├── feature_engineering.py
│   │   ├── class RealTimeFeatureExtractor:
│   │   │   ├── extract_transaction_features()
│   │   │   ├── extract_customer_features()
│   │   │   ├── extract_merchant_features()
│   │   │   └── extract_velocity_features()
│   │   │
│   │   └── class AggregateFeatureManager:
│   │       ├── compute_aggregates() [hourly]
│   │       ├── update_redis()
│   │       └── invalidate_cache()
│   │
│   ├── model_training.py
│   │   ├── class DataPipeline:
│   │   │   ├── load_historical_data()
│   │   │   ├── preprocess()
│   │   │   └── create_feature_matrix()
│   │   │
│   │   ├── class ModelTrainer:
│   │   │   ├── train_xgboost()
│   │   │   ├── train_lightgbm()
│   │   │   ├── train_neural_net()
│   │   │   └── ensemble_models()
│   │   │
│   │   └── class ModelEvaluator:
│   │       ├── evaluate_metrics()
│   │       ├── generate_report()
│   │       └── log_to_mlflow()
│   │
│   ├── model_inference.py
│   │   ├── class EnsemblePredictor:
│   │   │   ├── load_models()
│   │   │   ├── predict_fraud_score()
│   │   │   ├── get_shap_explanation()
│   │   │   └── cache_model_outputs()
│   │   │
│   │   └── class DecisionEngine:
│   │       ├── make_decision() # approve/challenge/block
│   │       ├── apply_rules() # custom rules override
│   │       └── log_decision()
│   │
│   ├── api.py
│   │   ├── @app.post("/score")
│   │   │   └── Score a single transaction
│   │   │
│   │   ├── @app.post("/batch-score")
│   │   │   └── Score multiple transactions
│   │   │
│   │   ├── @app.post("/explain")
│   │   │   └── Get SHAP explanation for a score
│   │   │
│   │   ├── @app.get("/health")
│   │   │   └── Liveness/readiness probes
│   │   │
│   │   └── @app.get("/metrics")
│   │       └── Prometheus metrics
│   │
│   ├── monitoring.py
│   │   ├── class MetricsCollector:
│   │   │   ├── track_inference_latency()
│   │   │   ├── track_model_scores()
│   │   │   ├── track_fraud_rate()
│   │   │   └── track_errors()
│   │   │
│   │   └── class AnomalyDetector:
│   │       ├── detect_score_drift()
│   │       ├── detect_data_drift()
│   │       └── alert_on_anomaly()
│   │
│   └── utils.py
│       ├── logger configuration
│       ├── redis client helpers
│       └── metric helpers
│
├── models/
│   ├── xgboost_v1.pkl
│   ├── lightgbm_v1.pkl
│   ├── neural_net_v1.pt (PyTorch)
│   ├── feature_scaler.pkl
│   └── feature_names.json
│
├── tests/
│   ├── test_feature_engineering.py
│   ├── test_model_inference.py
│   ├── test_api.py
│   ├── test_end_to_end.py
│   └── fixtures/
│       └── sample_transactions.json
│
├── notebooks/
│   ├── 01_eda.ipynb (Exploratory Data Analysis)
│   ├── 02_feature_engineering.ipynb
│   ├── 03_model_training.ipynb
│   └── 04_model_evaluation.ipynb
│
├── docker/
│   └── Dockerfile
│       ├── FROM python:3.10-slim
│       ├── Copy requirements & models
│       ├── EXPOSE 8000
│       └── CMD ["uvicorn", "src.api:app"]
│
├── requirements.txt
│   ├── fastapi==0.104.1
│   ├── uvicorn==0.24.0
│   ├── xgboost==2.0.0
│   ├── lightgbm==4.0.0
│   ├── torch==2.1.0
│   ├── redis==5.0.0
│   ├── shap==0.43.0
│   ├── pandas==2.1.0
│   ├── numpy==1.24.0
│   ├── scikit-learn==1.3.0
│   ├── prometheus-client==0.18.0
│   ├── pydantic==2.4.0
│   └── pytest==7.4.0
│
├── docker-compose.yml (fraud detection services)
│   ├── Service: fraud-detection-api (port 8000)
│   ├── Service: redis (port 6379)
│   ├── Service: prometheus (port 9090)
│   └── Service: grafana (port 3000)
│
└── DEVELOPMENT.md (getting started guide)
```

#### Key Implementation Code Snippets

**Feature Extractor (Real-Time):**
```python
class RealTimeFeatureExtractor:
    def __init__(self, redis_client):
        self.redis = redis_client
    
    def extract_features(self, transaction: Transaction) -> Dict:
        """Extract features for a single transaction in <50ms"""
        
        features = {}
        
        # Transaction-level features
        features['amount'] = transaction.amount
        features['merchant_mcc'] = transaction.merchant_category
        features['hour_of_day'] = datetime.now().hour
        
        # Customer features (from Redis)
        customer_key = f"cust:{transaction.customer_id}"
        customer_stats = self.redis.hgetall(customer_key)
        
        features['txn_count_24h'] = int(customer_stats.get('txn_24h', 0))
        features['avg_amount_30d'] = float(customer_stats.get('avg_30d', 0))
        features['days_since_last_txn'] = int(customer_stats.get('days_last', 0))
        
        # Velocity features (critical for fraud)
        features['txn_last_hour'] = self._get_velocity(
            transaction.customer_id, 3600
        )
        features['txn_last_day'] = self._get_velocity(
            transaction.customer_id, 86400
        )
        
        # Location features
        features['is_home_country'] = int(
            transaction.country == customer_stats.get('home_country')
        )
        
        # Device features
        device_key = f"dev:{transaction.device_id}"
        device_stats = self.redis.hgetall(device_key)
        features['n_customers_device'] = int(device_stats.get('n_cust', 0))
        
        return features
    
    def _get_velocity(self, customer_id: str, window_seconds: int) -> int:
        """Count transactions in time window"""
        key = f"vel:{customer_id}:{window_seconds}"
        return int(self.redis.get(key) or 0)
```

**Model Inference:**
```python
class EnsemblePredictor:
    def __init__(self, model_paths: Dict[str, str]):
        self.xgb_model = xgboost.load_model(model_paths['xgb'])
        self.lgb_model = lgb.Booster(model_file=model_paths['lgb'])
        self.nn_model = torch.load(model_paths['nn'])
        self.scaler = joblib.load(model_paths['scaler'])
        self.explainer = shap.TreeExplainer(self.xgb_model)
    
    def predict_fraud_score(self, features: Dict) -> float:
        """Ensemble fraud score prediction <10ms"""
        
        # Convert to array
        feature_array = self._dict_to_array(features)
        
        # Predict from each model
        xgb_score = self.xgb_model.predict(
            xgboost.DMatrix(feature_array.reshape(1, -1))
        )[0]
        
        lgb_score = self.lgb_model.predict(
            feature_array.reshape(1, -1),
            num_iteration=self.lgb_model.best_iteration
        )[0]
        
        # Neural network prediction
        with torch.no_grad():
            nn_input = torch.FloatTensor(
                self.scaler.transform(feature_array.reshape(1, -1))
            )
            nn_score = self.nn_model(nn_input).item()
        
        # Weighted ensemble
        fraud_score = (
            0.50 * xgb_score +
            0.30 * lgb_score +
            0.20 * nn_score
        )
        
        return float(fraud_score)
    
    def get_shap_explanation(self, features: Dict) -> Dict:
        """Generate SHAP explanation for interpretability"""
        
        feature_array = self._dict_to_array(features)
        shap_values = self.explainer.shap_values(feature_array)
        
        return {
            'base_value': float(self.explainer.expected_value),
            'shap_values': shap_values.tolist(),
            'feature_names': self.feature_names,
            'fraud_score': self.predict_fraud_score(features)
        }
```

**FastAPI Endpoint:**
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

predictor = EnsemblePredictor(model_paths)
feature_extractor = RealTimeFeatureExtractor(redis_client)

class TransactionRequest(BaseModel):
    customer_id: str
    amount: float
    merchant_id: str
    merchant_category: str
    country: str
    device_id: str
    ip_address: str

class TransactionResponse(BaseModel):
    fraud_score: float
    decision: str  # approve, challenge, block
    confidence: float
    explanation: dict

@app.post("/score", response_model=TransactionResponse)
async def score_transaction(request: TransactionRequest):
    """Real-time fraud detection endpoint"""
    
    try:
        # Extract features
        features = feature_extractor.extract_features(request)
        
        # Predict
        fraud_score = predictor.predict_fraud_score(features)
        
        # Make decision
        if fraud_score < 0.2:
            decision = "approve"
        elif fraud_score < 0.7:
            decision = "challenge"
        else:
            decision = "block"
        
        # Explain (for high-risk transactions)
        explanation = {}
        if fraud_score > 0.6:
            explanation = predictor.get_shap_explanation(features)
        
        # Log for audit
        logger.info(f"Transaction scored: {fraud_score}, Decision: {decision}")
        
        return TransactionResponse(
            fraud_score=fraud_score,
            decision=decision,
            confidence=1.0 - abs(fraud_score - 0.5) * 2,
            explanation=explanation
        )
    
    except Exception as e:
        logger.error(f"Scoring error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Liveness probe for Kubernetes"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
```

### 1.6 Data Sources & Simulation

#### Real Data Strategy (for demo)
```
Since Mastercard won't provide real data, use:

1. **Kaggle IEEE-CIS Fraud Detection Dataset**
   ├── Source: https://www.kaggle.com/c/ieee-fraud-detection
   ├── Transactions: 590,540 (train), 506,691 (test)
   ├── Features: 434 anonymized features
   ├── Fraud rate: 3.5% (realistic)
   └── Credit: Already public; permission not needed

2. **Synthetic Fraud Generation**
   └─ If Kaggle limited, generate synthetic data:
      ├── Use faker library for merchants, customers, locations
      ├── Generate realistic transaction patterns
      ├── Inject known fraud patterns:
      │  ├── Rapid transactions (velocity)
      │  ├── Location impossibility
      │  ├── Unusual amount patterns
      │  └── Card testing (multiple small txns)
      └── Maintain 3-5% fraud rate

3. **Own Test Data**
   └─ CSV with columns:
      ├── transaction_id
      ├── customer_id
      ├── amount
      ├── merchant_id
      ├── country
      ├── timestamp
      ├── device_id
      └── is_fraud (target)
```

---

## COMPONENT 2: REAL-TIME PAYMENTS DATA PLATFORM

### 2.1 Objective
Build a **production-grade real-time payment data pipeline** that:
- Ingests millions of transactions/second
- Performs real-time aggregations (TPM, fraud rate, latency)
- Maintains low-latency state management
- Provides real-time dashboards
- Demonstrates streaming architecture mastery

### 2.2 Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  REAL-TIME PAYMENTS DATA PLATFORM                            │
└──────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│  PRODUCER LAYER                                            │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  Payment Transaction Simulator                            │
│  ├─ Generate realistic payment events                     │
│  ├─ Rate: Configurable (10K, 100K, 1M tps)              │
│  ├─ Fields: customer, merchant, amount, timestamp        │
│  └─ Output: Kafka topic "payments"                       │
│                                                           │
│  Legacy System Bridge                                    │
│  ├─ Poll CSV/database                                   │
│  ├─ Convert to Kafka events                             │
│  └─ Rate: ~1K tps                                       │
│                                                           │
└────────────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────────────┐
│  MESSAGE BROKER                                            │
├────────────────────────────────────────────────────────────┤
│  Kafka Cluster                                             │
│  ├─ Topic: payments                                       │
│  │  ├─ Partitions: 16 (parallelism)                      │
│  │  ├─ Replication: 3 (durability)                       │
│  │  └─ Retention: 7 days                                 │
│  │                                                       │
│  ├─ Topic: fraud-alerts                                  │
│  │  ├─ Partitions: 4                                     │
│  │  └─ Retention: 30 days (compliance)                   │
│  │                                                       │
│  └─ Topic: risk-scores                                   │
│     ├─ Partitions: 4                                     │
│     └─ Retention: 30 days                                │
│                                                           │
└────────────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────────────┐
│  STREAM PROCESSING LAYER (Spark Streaming)                 │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  Streaming Application                                   │
│  ├─ Micro-batch processing (2-second batches)          │
│  │                                                      │
│  ├─ Deduplication                                       │
│  │  ├─ Check against Redis                              │
│  │  ├─ Keep last 1 hour of transaction IDs              │
│  │  └─ Filter duplicates                                │
│  │                                                      │
│  ├─ Validation                                          │
│  │  ├─ Check schema                                     │
│  │  ├─ Validate amount > 0                              │
│  │  └─ Validate customer_id not null                    │
│  │                                                      │
│  ├─ Stateful Aggregations                               │
│  │  ├─ Window 1: 1-minute windows                       │
│  │  │  └─ Compute per-merchant metrics                  │
│  │  │                                                   │
│  │  ├─ Window 2: 5-minute sliding                       │
│  │  │  └─ Per-country fraud rate                        │
│  │  │                                                   │
│  │  └─ Window 3: 1-hour tumbling                        │
│  │     └─ Daily aggregates                              │
│  │                                                      │
│  ├─ Output to Redis                                      │
│  │  ├─ Key: metric:{window}:{dimension}                 │
│  │  ├─ TTL: 2x window size                              │
│  │  └─ Value: JSON (count, sum, avg)                    │
│  │                                                      │
│  └─ Output to Kafka                                      │
│     ├─ Topic: aggregated-metrics                         │
│     └─ For long-term storage (Delta Lake)                │
│                                                           │
└────────────────────────────────────────────────────────────┘
                          ↓
┌────────────────────────────────────────────────────────────┐
│  STATE MANAGEMENT (Redis)                                  │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  Redis Cluster                                            │
│  ├─ Metrics Cache                                         │
│  │  ├─ metric:1m:merchant_123                            │
│  │  │  └─ {count: 450, sum: 15000, fraud_count: 2}      │
│  │  │                                                   │
│  │  └─ metric:5m:country_US                              │
│  │     └─ {tpm: 10000, fraud_rate: 0.025}               │
│  │                                                      │
│  ├─ Deduplication State                                  │
│  │  ├─ dedup:{timestamp} → Set of transaction IDs        │
│  │  └─ TTL: 1 hour (sliding)                             │
│  │                                                      │
│  └─ Customer Profiles                                    │
│     ├─ cust:{customer_id}                                │
│     │  └─ {avg_amount, txn_count, fraud_flag}           │
│     └─ Updated in real-time                              │
│                                                           │
└────────────────────────────────────────────────────────────┘
                  ↓                    ↓
        ┌─────────────────┐   ┌──────────────────┐
        │  DASHBOARDS     │   │  DELTA LAKE      │
        │  (Real-time)    │   │  (Long-term)     │
        │                 │   │                  │
        │ Grafana/        │   │ Historical data  │
        │ Streamlit       │   │ for analytics    │
        │                 │   │                  │
        │ Metrics:        │   │ Used by ML       │
        │ - TPM           │   │ retraining       │
        │ - Fraud rate    │   │                  │
        │ - Latency p99   │   │                  │
        │ - Merchant top  │   │                  │
        │   by volume     │   │                  │
        └─────────────────┘   └──────────────────┘
```

### 2.3 Kafka Topic Design

```
Topic: payments (Main transaction stream)
├── Partitions: 16
│   └─ Keyed by: customer_id (for ordering)
├── Retention: 7 days (cost consideration)
├── Replication Factor: 3
├── Cleanup Policy: delete
├── Message Format (Avro/JSON):
│   {
│     "transaction_id": "txn_123456",
│     "customer_id": "cust_001",
│     "merchant_id": "mer_789",
│     "amount": 125.50,
│     "currency": "USD",
│     "merchant_category": "5411",
│     "country": "US",
│     "device_id": "dev_xyz",
│     "timestamp": "2024-08-19T15:30:45Z",
│     "transaction_type": "online",
│     "ip_address": "192.168.1.1",
│     "status": "completed"
│   }
└── Throughput SLA: 
    └─ Dev: 10K tps
    └─ Stage: 100K tps
    └─ Production demo: 1M tps

Topic: fraud-alerts (Fraud detections)
├── Partitions: 4
├── Retention: 30 days (compliance/audit)
├── Message Format:
│   {
│     "transaction_id": "txn_123456",
│     "fraud_score": 0.85,
│     "fraud_reason": "High velocity",
│     "decision": "block",
│     "timestamp": "2024-08-19T15:30:46Z"
│   }
└── Subscribers: Monitoring, notifications, analytics

Topic: aggregated-metrics (Real-time metrics)
├── Partitions: 4
├── Retention: 90 days (analytics)
├── Message Format:
│   {
│     "window_start": "2024-08-19T15:30:00Z",
│     "window_duration": "1m",
│     "dimension": "merchant_123",
│     "tpm": 450,
│     "total_amount": 15000,
│     "fraud_count": 2,
│     "fraud_rate": 0.0044
│   }
└── For: Long-term analytics in Delta Lake
```

### 2.4 Stream Processing Logic

#### Spark Streaming Implementation

```python
# spark-streaming-app/src/main.py

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, from_json, schema_of_json, 
    window, count, sum as spark_sum, avg,
    current_timestamp, to_json, struct
)
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, TimestampType

def create_spark_session():
    """Initialize Spark session"""
    return SparkSession.builder \
        .appName("PaymentsRealTimeProcessor") \
        .config("spark.streaming.kafka.maxRatePerPartition", "100000") \
        .config("spark.streaming.kafka.maxOffsetsFetchesPerTrigger", "50000") \
        .config("spark.sql.streaming.checkpointLocation", "/tmp/checkpoint") \
        .getOrCreate()

def main():
    spark = create_spark_session()
    
    # Define schema
    schema = StructType([
        StructField("transaction_id", StringType()),
        StructField("customer_id", StringType()),
        StructField("merchant_id", StringType()),
        StructField("amount", DoubleType()),
        StructField("country", StringType()),
        StructField("timestamp", TimestampType()),
        StructField("device_id", StringType()),
        StructField("fraud_score", DoubleType()),
    ])
    
    # Read from Kafka
    df_payments = spark.readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", "localhost:9092") \
        .option("subscribe", "payments") \
        .option("startingOffsets", "latest") \
        .load() \
        .select(
            from_json(col("value").cast("string"), schema).alias("data")
        ) \
        .select("data.*") \
        .withColumn("ingestion_time", current_timestamp())
    
    # ============= DEDUPLICATION =============
    df_deduplicated = df_payments \
        .dropDuplicates(["transaction_id"])  # Last 10 mins by default
    
    # ============= VALIDATION =============
    df_validated = df_deduplicated \
        .filter(col("amount") > 0) \
        .filter(col("customer_id").isNotNull()) \
        .filter(col("merchant_id").isNotNull())
    
    # ============= 1-MINUTE AGGREGATIONS =============
    agg_1min = df_validated \
        .withWatermark("timestamp", "2 minutes") \
        .groupBy(
            window(col("timestamp"), "1 minute"),
            col("merchant_id")
        ) \
        .agg(
            count("*").alias("tpm"),
            spark_sum("amount").alias("total_amount"),
            avg("amount").alias("avg_amount"),
            spark_sum(
                (col("fraud_score") > 0.7).cast("int")
            ).alias("fraud_count"),
            (
                spark_sum((col("fraud_score") > 0.7).cast("int")) / 
                count("*")
            ).alias("fraud_rate")
        ) \
        .select(
            col("window.start").alias("window_start"),
            col("merchant_id"),
            col("tpm"),
            col("total_amount"),
            col("avg_amount"),
            col("fraud_count"),
            col("fraud_rate")
        )
    
    # Write 1-minute metrics to Kafka
    query_1min = agg_1min \
        .select(to_json(struct("*")).alias("value")) \
        .writeStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", "localhost:9092") \
        .option("topic", "aggregated-metrics-1m") \
        .option("checkpointLocation", "/tmp/checkpoint-1m") \
        .start()
    
    # Write 1-minute metrics to Redis (for dashboards)
    def write_to_redis_batch(batch_df, batch_id):
        import redis
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        
        for row in batch_df.collect():
            key = f"metric:1m:merchant:{row['merchant_id']}"
            value = {
                'tpm': row['tpm'],
                'total_amount': row['total_amount'],
                'fraud_rate': row['fraud_rate'],
                'timestamp': row['window_start'].isoformat()
            }
            r.hset(key, mapping=value)
            r.expire(key, 300)  # 5-minute TTL
    
    query_redis = agg_1min \
        .writeStream \
        .foreachBatch(write_to_redis_batch) \
        .option("checkpointLocation", "/tmp/checkpoint-redis") \
        .start()
    
    # ============= 5-MINUTE SLIDING WINDOW =============
    agg_5min = df_validated \
        .withWatermark("timestamp", "2 minutes") \
        .groupBy(
            window(col("timestamp"), "5 minutes", "1 minute"),
            col("country")
        ) \
        .agg(
            count("*").alias("tpm"),
            spark_sum("amount").alias("total_amount"),
            spark_sum((col("fraud_score") > 0.7).cast("int")).alias("fraud_count"),
            (
                spark_sum((col("fraud_score") > 0.7).cast("int")) / 
                count("*")
            ).alias("fraud_rate")
        )
    
    query_5min = agg_5min \
        .select(to_json(struct("*")).alias("value")) \
        .writeStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", "localhost:9092") \
        .option("topic", "aggregated-metrics-5m") \
        .option("checkpointLocation", "/tmp/checkpoint-5m") \
        .start()
    
    # ============= 1-HOUR TUMBLING WINDOW =============
    agg_1hour = df_validated \
        .withWatermark("timestamp", "10 minutes") \
        .groupBy(
            window(col("timestamp"), "1 hour")
        ) \
        .agg(
            count("*").alias("total_transactions"),
            spark_sum("amount").alias("total_volume"),
            spark_sum((col("fraud_score") > 0.7).cast("int")).alias("fraud_count"),
            (
                spark_sum((col("fraud_score") > 0.7).cast("int")) / 
                count("*")
            ).alias("fraud_rate")
        )
    
    # Write hourly to Delta Lake for analytics
    query_1hour = agg_1hour \
        .select(
            col("window.start").alias("hour"),
            col("total_transactions"),
            col("total_volume"),
            col("fraud_count"),
            col("fraud_rate"),
            current_timestamp().alias("processed_at")
        ) \
        .writeStream \
        .format("delta") \
        .option("path", "/data/delta/hourly-metrics") \
        .option("checkpointLocation", "/tmp/checkpoint-1h") \
        .outputMode("append") \
        .start()
    
    spark.streams.awaitAnyTermination()

if __name__ == "__main__":
    main()
```

### 2.5 Dashboard Implementation

#### Streamlit Dashboard
```python
# payments-platform/dashboard/app.py

import streamlit as st
import pandas as pd
import redis
import json
from datetime import datetime, timedelta
import plotly.graph_objects as go
import plotly.express as px

# Page config
st.set_page_config(page_title="Real-Time Payments Dashboard", layout="wide")

@st.cache_resource
def init_redis():
    return redis.Redis(host='localhost', port=6379, decode_responses=True)

redis_client = init_redis()

def get_current_metrics():
    """Get current TPM, fraud rate from Redis"""
    metrics = {}
    
    # Get all merchant 1-minute metrics
    keys = redis_client.keys("metric:1m:merchant:*")
    
    total_tpm = 0
    total_fraud_count = 0
    total_txn_count = 0
    
    for key in keys:
        data = redis_client.hgetall(key)
        total_tpm += int(data.get('tpm', 0))
        total_fraud_count += int(data.get('fraud_count', 0))
        total_txn_count += int(data.get('total_txn', 0))
    
    fraud_rate = (
        total_fraud_count / total_txn_count 
        if total_txn_count > 0 else 0
    )
    
    return {
        'current_tpm': total_tpm,
        'fraud_rate': fraud_rate,
        'total_transactions': total_txn_count,
        'fraud_count': total_fraud_count
    }

def get_merchant_leaderboard():
    """Top merchants by transaction volume"""
    merchants = {}
    
    keys = redis_client.keys("metric:1m:merchant:*")
    for key in keys:
        merchant_id = key.split(":")[-1]
        data = redis_client.hgetall(key)
        merchants[merchant_id] = {
            'tpm': int(data.get('tpm', 0)),
            'volume': float(data.get('total_amount', 0)),
            'fraud_rate': float(data.get('fraud_rate', 0))
        }
    
    df = pd.DataFrame(merchants).T
    return df.sort_values('tpm', ascending=False).head(10)

# Main dashboard
st.title("Real-Time Payments Platform Dashboard")

# Current metrics
col1, col2, col3, col4 = st.columns(4)

metrics = get_current_metrics()

with col1:
    st.metric("Current TPM", f"{metrics['current_tpm']:,}")

with col2:
    st.metric("Fraud Rate", f"{metrics['fraud_rate']:.2%}")

with col3:
    st.metric("Total Transactions", f"{metrics['total_transactions']:,}")

with col4:
    st.metric("Fraud Count", f"{metrics['fraud_count']:,}")

# Merchant leaderboard
st.subheader("Top 10 Merchants by TPM")
df_merchants = get_merchant_leaderboard()
st.dataframe(df_merchants, use_container_width=True)

# Time series chart (mock data for demo)
st.subheader("TPM Over Time (Last 1 Hour)")
time_data = {
    'timestamp': pd.date_range(start=datetime.now() - timedelta(hours=1), periods=60, freq='1min'),
    'tpm': [8000 + i*100 + (i%10)*1000 for i in range(60)]
}
df_time = pd.DataFrame(time_data)

fig = px.line(df_time, x='timestamp', y='tpm', 
              title='Transactions Per Minute',
              labels={'tpm': 'TPM', 'timestamp': 'Time'})
st.plotly_chart(fig, use_container_width=True)

# Fraud rate over time
st.subheader("Fraud Rate Over Time")
fraud_data = {
    'timestamp': pd.date_range(start=datetime.now() - timedelta(hours=1), periods=60, freq='1min'),
    'fraud_rate': [0.02 + (0.01 if i%15 == 0 else 0) for i in range(60)]
}
df_fraud = pd.DataFrame(fraud_data)

fig_fraud = px.line(df_fraud, x='timestamp', y='fraud_rate',
                    title='Fraud Rate Over Time',
                    labels={'fraud_rate': 'Fraud Rate', 'timestamp': 'Time'})
fig_fraud.update_layout(yaxis=dict(tickformat=".2%"))
st.plotly_chart(fig_fraud, use_container_width=True)

# Refresh
st.write(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
```

### 2.6 Production Deployment

```yaml
# docker-compose.yml (Payments Platform Services)

version: '3.8'

services:
  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    depends_on:
      - zookeeper
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:29092,PLAINTEXT_HOST://kafka:9092
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --maxmemory 4gb --maxmemory-policy allkeys-lru

  payment-simulator:
    build:
      context: ./payments-data-platform
      dockerfile: docker/Dockerfile.simulator
    depends_on:
      - kafka
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      PAYMENT_RATE: "10000"  # TPS
    volumes:
      - ./data:/data

  stream-processor:
    build:
      context: ./payments-data-platform
      dockerfile: docker/Dockerfile.processor
    depends_on:
      - kafka
      - redis
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      REDIS_HOST: redis
      REDIS_PORT: 6379
    volumes:
      - ./data/checkpoint:/tmp/checkpoint

  dashboard:
    build:
      context: ./payments-data-platform/dashboard
      dockerfile: Dockerfile
    ports:
      - "8501:8501"
    depends_on:
      - redis
    environment:
      REDIS_HOST: redis
      REDIS_PORT: 6379

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
    depends_on:
      - prometheus
```

---

## COMPONENT 3: PAYMENT TRANSACTION LAKEHOUSE

### 3.1 Objective
Build a **scalable data lakehouse** that:
- Stores payment transaction history (bronze → gold)
- Maintains compliance & governance
- Serves analytics and ML
- Demonstrates data architecture maturity
- Shows cost optimization thinking

### 3.2 Medallion Architecture

```
LAKEHOUSE ARCHITECTURE (Medallion Pattern)

┌─────────────────────────────────────────────────────────────┐
│  BRONZE LAYER (Raw Data)                                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  /data/delta/bronze/payments/                              │
│  ├─ Contains: Raw transaction stream (as-is)               │
│  ├─ Partitioned by: date (YYYY-MM-DD)                      │
│  ├─ Schema:                                                │
│  │  ├─ transaction_id (PK)                                 │
│  │  ├─ customer_id                                         │
│  │  ├─ merchant_id                                         │
│  │  ├─ amount                                              │
│  │  ├─ currency                                            │
│  │  ├─ country                                             │
│  │  ├─ device_id                                           │
│  │  ├─ ip_address                                          │
│  │  ├─ timestamp                                           │
│  │  ├─ status                                              │
│  │  └─ _ingestion_timestamp                               │
│  │                                                         │
│  ├─ Format: Delta Lake (ACID transactions)                 │
│  ├─ Retention: 2 years (compliance)                        │
│  └─ Size: ~50GB/month (at 600M tx/day)                    │
│                                                             │
│  /data/delta/bronze/fraud_scores/                          │
│  ├─ Contains: Fraud detection scores                       │
│  ├─ Partitioned by: date                                   │
│  └─ Joined with transactions via transaction_id           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                          ↓ (cleaned + enriched)
┌─────────────────────────────────────────────────────────────┐
│  SILVER LAYER (Cleaned & Validated)                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  /data/delta/silver/transactions/                          │
│  ├─ Processing:                                            │
│  │  ├─ Removed duplicates                                  │
│  │  ├─ Validated data types & ranges                       │
│  │  ├─ Filled missing values (where appropriate)           │
│  │  ├─ Masked PII (last 4 of card, etc.)                  │
│  │  ├─ Added fraud_flag from fraud scores                 │
│  │  └─ Added quality metrics (data_quality_score)          │
│  │                                                         │
│  ├─ Schema (enhanced):                                     │
│  │  ├─ [all bronze fields]                                 │
│  │  ├─ fraud_score                                         │
│  │  ├─ fraud_flag (binary)                                 │
│  │  ├─ data_quality_score                                  │
│  │  ├─ has_pii                                             │
│  │  └─ _processed_timestamp                                │
│  │                                                         │
│  ├─ Partitioned: date + country (common queries)           │
│  ├─ Format: Delta Lake with Z-order clustering             │
│  │   └─ Z-order by: customer_id, merchant_id              │
│  └─ Size: ~45GB/month (after dedup & optimization)         │
│                                                             │
│  /data/delta/silver/customers/                             │
│  ├─ Slowly Changing Dimensions (SCD Type 2)               │
│  ├─ Tracks customer profile changes                        │
│  └─ Useful for customer lifetime value, segmentation       │
│                                                             │
│  /data/delta/silver/merchants/                             │
│  ├─ Merchant master data                                   │
│  └─ MCC codes, high-risk flags, categories                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                          ↓ (aggregated + enriched)
┌─────────────────────────────────────────────────────────────┐
│  GOLD LAYER (Analytics Ready)                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  /data/delta/gold/daily_metrics/                           │
│  ├─ Pre-aggregated daily metrics                           │
│  ├─ Partitioned: date                                      │
│  ├─ Columns:                                               │
│  │  ├─ date                                                │
│  │  ├─ total_transactions                                  │
│  │  ├─ total_volume                                        │
│  │  ├─ fraud_count                                         │
│  │  ├─ fraud_rate                                          │
│  │  ├─ unique_customers                                    │
│  │  ├─ unique_merchants                                    │
│  │  ├─ avg_transaction_amount                              │
│  │  └─ p99_transaction_amount                              │
│  │                                                         │
│  │  Size: ~5MB/month                                       │
│  │  Query latency: <1 second (pre-aggregated)              │
│  │                                                         │
│  ├─ /data/delta/gold/hourly_metrics/                       │
│  │  └─ Same but hourly (for dashboards)                    │
│  │                                                         │
│  ├─ /data/delta/gold/ml_features/                          │
│  │  ├─ Feature store for fraud detection                   │
│  │  ├─ Pre-computed customer aggregates                    │
│  │  │  ├─ transactions_7d                                  │
│  │  │  ├─ sum_amount_7d                                    │
│  │  │  ├─ avg_amount_7d                                    │
│  │  │  └─ fraud_rate_7d                                    │
│  │  │                                                      │
│  │  ├─ Pre-computed merchant aggregates                    │
│  │  └─ Partitioned: date, customer_id (point lookups)      │
│  │                                                         │
│  ├─ /data/delta/gold/customer_segment/                     │
│  │  ├─ Customer risk segments                              │
│  │  │  ├─ high_risk (many fraud transactions)              │
│  │  │  ├─ medium_risk                                      │
│  │  │  └─ low_risk                                         │
│  │  └─ Updated daily                                       │
│  │                                                         │
│  └─ /data/delta/gold/merchant_analytics/                   │
│     ├─ Merchant performance metrics                        │
│     ├─ Chargeback rates, fraud rates                       │
│     └─ Used by risk teams for onboarding decisions         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 Data Pipeline (ETL/ELT Jobs)

```python
# transaction-lakehouse/src/etl_pipeline.py

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, from_json, struct, to_json,
    current_timestamp, hash, md5,
    year, month, dayofmonth, window
)
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class LakehouseETL:
    def __init__(self, spark: SparkSession):
        self.spark = spark
        self.bronze_path = "/data/delta/bronze"
        self.silver_path = "/data/delta/silver"
        self.gold_path = "/data/delta/gold"
    
    def bronze_to_silver_transactions(self):
        """ETL: Bronze → Silver (Transactions)"""
        
        logger.info("Starting Bronze → Silver ETL for transactions")
        
        # Read from bronze
        df_bronze = self.spark.read.format("delta") \
            .load(f"{self.bronze_path}/payments")
        
        # Deduplication
        df_dedup = df_bronze.dropDuplicates(["transaction_id"])
        
        # Validation
        df_validated = df_dedup \
            .filter(col("amount") > 0) \
            .filter(col("customer_id").isNotNull()) \
            .filter(col("timestamp").isNotNull())
        
        # Masking PII
        from pyspark.sql.functions import regexp_replace
        df_masked = df_validated \
            .withColumn(
                "card_masked",
                regexp_replace(col("card_number"), r".{12}", "****")
            ) \
            .drop("card_number", "full_name", "email")  # Drop sensitive fields
        
        # Add quality metrics
        df_quality = df_masked \
            .withColumn("data_quality_score", 
                       (
                           (~col("amount").isNull()).cast("int") +
                           (~col("customer_id").isNull()).cast("int") +
                           (~col("merchant_id").isNull()).cast("int") +
                           (~col("timestamp").isNull()).cast("int")
                       ) / 4.0
            )
        
        # Add processing timestamp
        df_processed = df_quality \
            .withColumn("_processed_timestamp", current_timestamp()) \
            .withColumn("_etl_batch_id", 
                       lit(datetime.now().isoformat()))
        
        # Write to silver with partitioning
        df_processed.write.mode("append") \
            .format("delta") \
            .partitionBy("date", "country") \
            .option("delta.columnMapping.mode", "name") \
            .save(f"{self.silver_path}/transactions")
        
        logger.info(f"Wrote {df_processed.count()} records to silver layer")
    
    def silver_to_gold_daily_metrics(self):
        """ETL: Silver → Gold (Daily Metrics)"""
        
        logger.info("Starting Silver → Gold ETL for daily metrics")
        
        # Read silver
        df_silver = self.spark.read.format("delta") \
            .load(f"{self.silver_path}/transactions")
        
        # Aggregate by date
        df_daily = df_silver \
            .groupBy(
                col("date")
            ) \
            .agg(
                count("*").alias("total_transactions"),
                sum("amount").alias("total_volume"),
                sum(
                    (col("fraud_flag") == True).cast("int")
                ).alias("fraud_count"),
                (
                    sum((col("fraud_flag") == True).cast("int")) / 
                    count("*")
                ).alias("fraud_rate"),
                approx_count_distinct("customer_id").alias("unique_customers"),
                approx_count_distinct("merchant_id").alias("unique_merchants"),
                avg("amount").alias("avg_transaction_amount"),
                percentile_approx("amount", 0.99).alias("p99_transaction_amount")
            ) \
            .withColumn("_processed_timestamp", current_timestamp())
        
        # Write to gold
        df_daily.write.mode("overwrite") \
            .format("delta") \
            .partitionBy("date") \
            .save(f"{self.gold_path}/daily_metrics")
        
        logger.info("Completed daily metrics aggregation")
    
    def silver_to_gold_ml_features(self):
        """Create feature store for ML (customer aggregates)"""
        
        logger.info("Starting feature store creation")
        
        df_silver = self.spark.read.format("delta") \
            .load(f"{self.silver_path}/transactions")
        
        # 7-day window features
        window_7d = datetime.now() - timedelta(days=7)
        
        df_features = df_silver \
            .filter(col("timestamp") >= window_7d) \
            .groupBy("customer_id") \
            .agg(
                count("*").alias("transactions_7d"),
                sum("amount").alias("sum_amount_7d"),
                avg("amount").alias("avg_amount_7d"),
                sum(
                    (col("fraud_flag") == True).cast("int")
                ).alias("fraud_count_7d"),
                (
                    sum((col("fraud_flag") == True).cast("int")) / 
                    count("*")
                ).alias("fraud_rate_7d"),
                max("timestamp").alias("last_transaction_date"),
                approx_count_distinct("merchant_id").alias("unique_merchants_7d"),
                approx_count_distinct("country").alias("unique_countries_7d")
            ) \
            .withColumn("_feature_date", current_timestamp())
        
        # Write to gold with optimized partitioning
        df_features.write.mode("overwrite") \
            .format("delta") \
            .option("delta.dataSkippingNumIndexedCols", 2) \
            .save(f"{self.gold_path}/ml_features")
        
        # Create Z-order index for fast lookups
        self.spark.sql(f"""
            OPTIMIZE {self.gold_path}/ml_features
            ZORDER BY customer_id
        """)
        
        logger.info("Completed ML feature store")

def schedule_etl_jobs():
    """Airflow DAG for scheduling ETL"""
    
    from airflow import DAG
    from airflow.operators.python import PythonOperator
    from datetime import datetime, timedelta
    
    default_args = {
        'owner': 'payment-platform',
        'retries': 2,
        'retry_delay': timedelta(minutes=5),
    }
    
    dag = DAG(
        'lakehouse_etl_pipeline',
        default_args=default_args,
        description='Payment lakehouse ETL pipeline',
        schedule_interval='0 * * * *',  # Hourly
        start_date=datetime(2024, 8, 1),
        catchup=False,
    )
    
    # Task 1: Bronze → Silver
    def run_bronze_silver():
        spark = SparkSession.builder.appName("BronzeToSilver").getOrCreate()
        etl = LakehouseETL(spark)
        etl.bronze_to_silver_transactions()
    
    task_bronze_silver = PythonOperator(
        task_id='bronze_to_silver',
        python_callable=run_bronze_silver,
        dag=dag,
    )
    
    # Task 2: Silver → Gold Daily
    def run_silver_gold_daily():
        spark = SparkSession.builder.appName("SilverGoldDaily").getOrCreate()
        etl = LakehouseETL(spark)
        etl.silver_to_gold_daily_metrics()
    
    task_silver_gold_daily = PythonOperator(
        task_id='silver_to_gold_daily',
        python_callable=run_silver_gold_daily,
        dag=dag,
    )
    
    # Task 3: Feature store creation
    def run_feature_store():
        spark = SparkSession.builder.appName("FeatureStore").getOrCreate()
        etl = LakehouseETL(spark)
        etl.silver_to_gold_ml_features()
    
    task_feature_store = PythonOperator(
        task_id='create_ml_features',
        python_callable=run_feature_store,
        dag=dag,
    )
    
    # Dependencies
    task_bronze_silver >> [task_silver_gold_daily, task_feature_store]
    
    return dag
```

### 3.4 Data Governance & Compliance

```python
# transaction-lakehouse/src/governance.py

class DataGovernance:
    """
    Implements compliance & governance for payment data
    - PCI DSS (payment card industry)
    - GDPR (right to be forgotten)
    - SOX (audit trails)
    """
    
    def pii_detection_and_masking(self, df):
        """Detect and mask PII/PHI"""
        
        import re
        from pyspark.sql.functions import regexp_replace, when, col
        
        # Card number masking (PCI DSS requirement)
        df = df.withColumn(
            "card_number",
            regexp_replace(col("card_number"), r"(\d{4})\d{8}(\d{4})", "$1****$2")
        )
        
        # Email masking
        df = df.withColumn(
            "email",
            regexp_replace(col("email"), r"(\w{2})\w*(@.*)", "$1***$2")
        )
        
        # Phone masking
        df = df.withColumn(
            "phone",
            regexp_replace(col("phone"), r"(\d{3})\d{3}(\d{4})", "$1***$2")
        )
        
        return df
    
    def audit_logging(self, operation: str, table: str, record_count: int):
        """Log all data access for compliance"""
        
        from datetime import datetime
        
        audit_log = {
            'timestamp': datetime.now(),
            'operation': operation,  # CREATE, READ, UPDATE, DELETE
            'table': table,
            'record_count': record_count,
            'user': os.getenv('USER'),
            'hostname': socket.gethostname()
        }
        
        # Write to immutable audit log (append-only)
        self.spark.createDataFrame([audit_log]) \
            .write.format("delta") \
            .mode("append") \
            .save("/data/delta/audit_logs")
        
        logger.info(f"Audit log: {audit_log}")
    
    def data_retention_policy(self):
        """Implement retention policies for compliance"""
        
        # PCI DSS: Card data retention max 3 months after expiry
        # GDPR: Retain only what's necessary
        # SOX: 7-year retention for financial records
        
        policies = {
            'bronze/payments': {
                'retention_days': 730,  # 2 years (SOX)
                'masked_fields': ['card_number', 'email', 'ssn']
            },
            'silver/transactions': {
                'retention_days': 730,
                'delete_pii_after_days': 90
            },
            'gold/daily_metrics': {
                'retention_days': 2555,  # 7 years
                'aggregated': True  # No individual records
            }
        }
        
        return policies
    
    def data_lineage_tracking(self):
        """Track data lineage for compliance"""
        
        # Every delta table has _ingestion_timestamp and _processed_timestamp
        # This allows tracking: source → raw → processed → aggregated
        
        lineage = """
        Fraud Alerts → Bronze Payments
                    ↓
                   Silver Transactions (dedup, validate, mask)
                    ↓
        ML Features ← Gold (aggregates, features)
        Dashboards ←
        """
        
        return lineage
```

---

## COMPONENT 4: VERIFIABLE INTENT INTEGRATION (Optional)

### 4.1 Objective
Implement **Mastercard's Verifiable Intent framework** for safe agentic commerce.

### 4.2 Architecture

```
VERIFIABLE INTENT FLOW

┌─────────────────┐
│   User Request  │ "Buy me coffee"
└────────┬────────┘
         │
         ▼
┌──────────────────────────┐
│  AI Agent                │
│  (Interprets intent)     │
└────────┬─────────────────┘
         │
         ▼ (AI decides to make payment)
┌──────────────────────────────────────┐
│  Generate Verifiable Intent          │
│  ├─ Parse user intent                │
│  ├─ Create intent statement          │
│  ├─ Sign with user's key             │
│  └─ Embed cryptographic proof        │
└────────┬─────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│  Fraud Detection System              │
│  ├─ Verify cryptographic proof       │
│  ├─ Check user actually authorized   │
│  ├─ Score fraud probability          │
│  └─ Decision: approve/challenge/block│
└────────┬─────────────────────────────┘
         │
    ┌────┴────┐
    ▼         ▼
  APPROVE   CHALLENGE/BLOCK
    │         │
    ▼         ▼
 Payment    Notify User
 Completes
```

### 4.3 Implementation (Simplified)

```python
# verifiable-intent/src/verifiable_intent.py

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Tuple
import hashlib
import hmac
import json
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend

@dataclass
class IntentClaim:
    """Represents a user's cryptographically-signed intent"""
    
    user_id: str
    merchant_id: str
    amount: float
    currency: str
    timestamp: str
    expiry: str
    intent_description: str  # "Buy coffee at Starbucks"
    
    def to_json(self) -> str:
        return json.dumps({
            'user_id': self.user_id,
            'merchant_id': self.merchant_id,
            'amount': self.amount,
            'currency': self.currency,
            'timestamp': self.timestamp,
            'expiry': self.expiry,
            'intent_description': self.intent_description
        })

class VerifiableIntentManager:
    """
    Manages cryptographic proof of user intent for payments
    Based on Mastercard's Verifiable Intent framework
    """
    
    def __init__(self, key_size: int = 2048):
        # Generate RSA keypair
        self.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
            backend=default_backend()
        )
        self.public_key = self.private_key.public_key()
    
    def create_intent_claim(
        self,
        user_id: str,
        merchant_id: str,
        amount: float,
        currency: str = "USD",
        intent_description: str = "",
        validity_minutes: int = 5
    ) -> IntentClaim:
        """Create a signed intent claim"""
        
        now = datetime.utcnow()
        expiry = now + timedelta(minutes=validity_minutes)
        
        return IntentClaim(
            user_id=user_id,
            merchant_id=merchant_id,
            amount=amount,
            currency=currency,
            timestamp=now.isoformat(),
            expiry=expiry.isoformat(),
            intent_description=intent_description
        )
    
    def sign_intent(self, intent: IntentClaim) -> str:
        """Sign intent claim with user's private key"""
        
        claim_json = intent.to_json()
        
        signature = self.private_key.sign(
            claim_json.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        return signature.hex()
    
    def verify_intent(
        self,
        intent: IntentClaim,
        signature: str
    ) -> Tuple[bool, str]:
        """Verify intent signature using public key"""
        
        try:
            claim_json = intent.to_json()
            signature_bytes = bytes.fromhex(signature)
            
            self.public_key.verify(
                signature_bytes,
                claim_json.encode(),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            # Check expiry
            expiry = datetime.fromisoformat(intent.expiry)
            if datetime.utcnow() > expiry:
                return False, "Intent signature expired"
            
            return True, "Intent verified"
        
        except Exception as e:
            return False, f"Verification failed: {str(e)}"
    
    def create_verifiable_transaction(
        self,
        user_id: str,
        merchant_id: str,
        amount: float,
        intent_description: str
    ) -> Dict:
        """
        End-to-end: Create and sign a verifiable transaction
        Used by AI agents to safely initiate payments
        """
        
        # Create intent
        intent = self.create_intent_claim(
            user_id=user_id,
            merchant_id=merchant_id,
            amount=amount,
            intent_description=intent_description
        )
        
        # Sign it
        signature = self.sign_intent(intent)
        
        # Package for transmission
        verifiable_txn = {
            'intent': {
                'user_id': intent.user_id,
                'merchant_id': intent.merchant_id,
                'amount': intent.amount,
                'currency': intent.currency,
                'timestamp': intent.timestamp,
                'expiry': intent.expiry,
                'intent_description': intent.intent_description
            },
            'signature': signature,
            'verification_status': 'pending'
        }
        
        return verifiable_txn

class AgenticPaymentAuthorizer:
    """
    Uses Verifiable Intent to safely authorize AI agent payments
    
    Flow:
    1. AI Agent → Creates Verifiable Intent (cryptographically signed)
    2. Fraud Detection → Verifies signature + checks fraud score
    3. If both pass → Transaction authorized
    4. If either fails → Transaction blocked/challenged
    """
    
    def __init__(self, intent_manager: VerifiableIntentManager, fraud_predictor):
        self.intent_manager = intent_manager
        self.fraud_predictor = fraud_predictor
    
    def authorize_agentic_payment(
        self,
        verifiable_txn: Dict,
        ai_agent_id: str
    ) -> Dict:
        """Authorize payment from AI agent with verifiable intent"""
        
        # Step 1: Verify cryptographic proof
        intent = verifiable_txn['intent']
        signature = verifiable_txn['signature']
        
        intent_claim = IntentClaim(**intent)
        is_valid, message = self.intent_manager.verify_intent(
            intent_claim, signature
        )
        
        if not is_valid:
            return {
                'authorized': False,
                'reason': f'Intent verification failed: {message}',
                'fraud_score': 0.0  # N/A
            }
        
        # Step 2: Check fraud score
        fraud_score = self.fraud_predictor.predict_fraud_score({
            'customer_id': intent['user_id'],
            'merchant_id': intent['merchant_id'],
            'amount': intent['amount'],
            'ai_agent_initiated': 1  # Flag agentic commerce
        })
        
        # Step 3: Make decision
        if fraud_score < 0.2:
            decision = True
            reason = "Verifiable intent + low fraud score"
        elif fraud_score < 0.7:
            decision = False  # Challenge
            reason = "Verifiable intent valid, but medium fraud score"
        else:
            decision = False  # Block
            reason = "Verifiable intent valid, but high fraud score"
        
        return {
            'authorized': decision,
            'reason': reason,
            'fraud_score': float(fraud_score),
            'intent_verified': is_valid,
            'ai_agent_id': ai_agent_id,
            'transaction_id': intent['user_id'] + '_' + 
                            intent['merchant_id'] + '_' +
                            intent['timestamp']
        }

# FastAPI endpoint for agentic payments
@app.post("/authorize-agentic-payment")
async def authorize_agentic_payment(request: VerifiableTransactionRequest):
    """
    Endpoint for AI agents to request payment authorization
    with cryptographic proof of user intent
    """
    
    result = authorizer.authorize_agentic_payment(
        verifiable_txn=request.verifiable_txn,
        ai_agent_id=request.ai_agent_id
    )
    
    return result
```

---

## INTEGRATION ARCHITECTURE

### Complete Data Flow

```
┌──────────────┐
│ Payment Txn  │
└──────┬───────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  REAL-TIME FRAUD DETECTION                              │
│  ├─ Extract features (<50ms)                            │
│  ├─ Ensemble ML model (<10ms)                           │
│  ├─ Get SHAP explanation (if high risk)                │
│  └─ Decision: approve/challenge/block                   │
└──────┬────────────────────────────────────────────────┬─┘
       │                                                  │
       ▼                                                  ▼
┌──────────────────────────────────────────────────────────┐
│  REAL-TIME PAYMENTS PLATFORM                            │
│  ├─ Kafka ingestion (deduplication)                     │
│  ├─ Stream processing (aggregation)                     │
│  ├─ Redis state management (features, metrics)          │
│  ├─ Real-time dashboards (Streamlit/Grafana)           │
│  └─ Output to Kafka (fraud-alerts, metrics)             │
└──────┬────────────────────────────────────────────────┬─┘
       │                                                  │
       └──────────────────────┬───────────────────────────┘
                              │
                              ▼
                   ┌──────────────────────────┐
                   │  DELTA LAKE (Lakehouse)  │
                   │                          │
                   │  Bronze → Silver → Gold  │
                   │  (ingestion → processing)│
                   │                          │
                   │ Outputs:                 │
                   │ - Audit trail            │
                   │ - Analytics              │
                   │ - ML features            │
                   │ - Compliance data        │
                   └──────────────────────────┘
```

---

## DEPLOYMENT & INFRASTRUCTURE

### Local Development (Docker Compose)

```yaml
version: '3.8'

services:
  # Kafka & Zookeeper
  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    ports:
      - "2181:2181"
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    ports:
      - "9092:9092"
      - "9101:9101"
    depends_on:
      - zookeeper
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: 'zookeeper:2181'
      KAFKA_ADVERTISED_LISTENERS: 'PLAINTEXT://kafka:29092,PLAINTEXT_HOST://kafka:9092'
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: 'PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT'
      KAFKA_INTER_BROKER_LISTENER_NAME: 'PLAINTEXT'
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1

  # Redis
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru

  # Fraud Detection API
  fraud-detection:
    build:
      context: ./fraud-detection
      dockerfile: docker/Dockerfile
    ports:
      - "8000:8000"
    depends_on:
      - redis
    environment:
      REDIS_HOST: redis
      REDIS_PORT: 6379
    volumes:
      - ./models:/app/models

  # Payment Simulator
  payment-simulator:
    build:
      context: ./payments-data-platform
      dockerfile: docker/Dockerfile.simulator
    depends_on:
      - kafka
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      PAYMENT_RATE: "10000"  # TPS

  # Stream Processor
  stream-processor:
    build:
      context: ./payments-data-platform
      dockerfile: docker/Dockerfile.processor
    depends_on:
      - kafka
      - redis
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      REDIS_HOST: redis

  # Streamlit Dashboard
  dashboard:
    build:
      context: ./payments-data-platform/dashboard
    ports:
      - "8501:8501"
    depends_on:
      - redis
      - fraud-detection
    environment:
      REDIS_HOST: redis
      FRAUD_API: http://fraud-detection:8000

  # Prometheus
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml

  # Grafana
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    depends_on:
      - prometheus
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin

  # Spark Master (for lakehouse processing)
  spark-master:
    image: bitnami/spark:3.5.0
    ports:
      - "8080:8080"
      - "7077:7077"
    environment:
      SPARK_MODE: master

  # Spark Worker
  spark-worker:
    image: bitnami/spark:3.5.0
    depends_on:
      - spark-master
    environment:
      SPARK_MODE: worker
      SPARK_MASTER_URL: spark://spark-master:7077

  # Jupyter (for notebooks/development)
  jupyter:
    image: jupyter/pyspark-notebook
    ports:
      - "8888:8888"
    volumes:
      - ./notebooks:/home/jovyan/work
      - ./data:/data
```

### Production Deployment (Kubernetes)

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: payment-platform

---
# Fraud Detection Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fraud-detection-api
  namespace: payment-platform
spec:
  replicas: 3
  selector:
    matchLabels:
      app: fraud-detection
  template:
    metadata:
      labels:
        app: fraud-detection
    spec:
      containers:
      - name: fraud-detection
        image: payment-platform/fraud-detection:latest
        ports:
        - containerPort: 8000
        env:
        - name: REDIS_HOST
          value: redis-service
        - name: REDIS_PORT
          value: "6379"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            cpu: 1000m
            memory: 2Gi
          limits:
            cpu: 2000m
            memory: 4Gi

---
# Service for Fraud Detection
apiVersion: v1
kind: Service
metadata:
  name: fraud-detection-service
  namespace: payment-platform
spec:
  selector:
    app: fraud-detection
  ports:
  - protocol: TCP
    port: 8000
    targetPort: 8000
  type: LoadBalancer

---
# Redis StatefulSet (for persistence)
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis
  namespace: payment-platform
spec:
  serviceName: redis-service
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
        volumeMounts:
        - name: redis-storage
          mountPath: /data
  volumeClaimTemplates:
  - metadata:
      name: redis-storage
    spec:
      accessModes: [ "ReadWriteOnce" ]
      resources:
        requests:
          storage: 10Gi

---
# Service for Redis
apiVersion: v1
kind: Service
metadata:
  name: redis-service
  namespace: payment-platform
spec:
  clusterIP: None
  ports:
  - port: 6379
  selector:
    app: redis
```

---

## TESTING & QUALITY ASSURANCE

### Testing Strategy

```python
# fraud-detection/tests/test_fraud_detection.py

import pytest
from src.model_inference import EnsemblePredictor
from src.api import app
from fastapi.testclient import TestClient

client = TestClient(app)

@pytest.fixture
def predictor():
    return EnsemblePredictor(model_paths={
        'xgb': 'models/xgboost_v1.pkl',
        'lgb': 'models/lightgbm_v1.pkl',
        'nn': 'models/neural_net_v1.pt',
        'scaler': 'models/feature_scaler.pkl'
    })

def test_fraud_score_valid_range(predictor):
    """Fraud scores should be between 0 and 1"""
    features = {
        'amount': 100.0,
        'merchant_mcc': '5411',
        'txn_count_24h': 5,
        'txn_last_hour': 0
    }
    
    score = predictor.predict_fraud_score(features)
    
    assert 0.0 <= score <= 1.0

def test_high_velocity_increases_fraud_score(predictor):
    """High transaction velocity should increase fraud score"""
    
    features_low_velocity = {
        'amount': 100.0,
        'merchant_mcc': '5411',
        'txn_count_24h': 1,
        'txn_last_hour': 0
    }
    
    features_high_velocity = {
        'amount': 100.0,
        'merchant_mcc': '5411',
        'txn_count_24h': 50,
        'txn_last_hour': 15  # Many transactions in 1 hour
    }
    
    score_low = predictor.predict_fraud_score(features_low_velocity)
    score_high = predictor.predict_fraud_score(features_high_velocity)
    
    assert score_high > score_low

@pytest.mark.asyncio
async def test_fraud_detection_api():
    """Test the FastAPI endpoint"""
    
    payload = {
        "customer_id": "cust_001",
        "amount": 125.50,
        "merchant_id": "mer_789",
        "merchant_category": "5411",
        "country": "US",
        "device_id": "dev_xyz",
        "ip_address": "192.168.1.1"
    }
    
    response = client.post("/score", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert 'fraud_score' in data
    assert 'decision' in data
    assert data['decision'] in ['approve', 'challenge', 'block']

def test_end_to_end_fraud_detection():
    """Integration test: feature extraction → model → decision"""
    
    from src.feature_engineering import RealTimeFeatureExtractor
    import redis
    
    r = redis.Redis(decode_responses=True)
    extractor = RealTimeFeatureExtractor(r)
    
    # Simulate transaction
    transaction = {
        'customer_id': 'cust_001',
        'amount': 500.0,  # Large amount
        'merchant_category': '7995',  # Gambling (high risk)
        'country': 'US',
        'device_id': 'dev_new',  # New device
        'ip_address': '1.2.3.4'
    }
    
    features = extractor.extract_features(transaction)
    score = predictor.predict_fraud_score(features)
    
    # Should have elevated fraud score
    assert score > 0.5
```

### Load Testing

```python
# tests/load_test.py

from locust import HttpUser, task, between

class PaymentUser(HttpUser):
    wait_time = between(1, 3)
    
    @task
    def score_transaction(self):
        """Load test fraud detection endpoint"""
        
        payload = {
            "customer_id": "cust_001",
            "amount": 125.50,
            "merchant_id": "mer_789",
            "merchant_category": "5411",
            "country": "US",
            "device_id": "dev_xyz",
            "ip_address": "192.168.1.1"
        }
        
        self.client.post("/score", json=payload)

# Run with: locust -f tests/load_test.py -u 1000 -r 100 -t 10m
```

---

## MONITORING & OBSERVABILITY

### Key Metrics

```python
# fraud-detection/src/monitoring.py

from prometheus_client import Counter, Histogram, Gauge
import time

# Counters
inference_count = Counter(
    'fraud_detection_inferences_total',
    'Total fraud detection inferences'
)

fraud_decisions = Counter(
    'fraud_decisions_total',
    'Fraud decisions by type',
    ['decision_type']  # approve, challenge, block
)

# Histograms
inference_latency = Histogram(
    'fraud_detection_latency_seconds',
    'Fraud detection latency'
)

model_scores = Histogram(
    'fraud_model_scores',
    'Distribution of fraud scores'
)

# Gauges
model_drift = Gauge(
    'model_performance_drift',
    'Model performance drift vs baseline'
)

redis_latency = Gauge(
    'redis_lookup_latency_ms',
    'Redis feature lookup latency'
)

# Usage
def predict_with_monitoring(features):
    start = time.time()
    
    score = model.predict(features)
    
    latency = time.time() - start
    
    inference_latency.observe(latency)
    inference_count.inc()
    model_scores.observe(score)
    
    if score < 0.2:
        fraud_decisions.labels(decision_type='approve').inc()
    elif score < 0.7:
        fraud_decisions.labels(decision_type='challenge').inc()
    else:
        fraud_decisions.labels(decision_type='block').inc()
    
    return score
```

### Alerting Rules

```yaml
# monitoring/alert_rules.yml

groups:
  - name: fraud_detection
    rules:
      - alert: HighFraudRate
        expr: rate(fraud_decisions_total{decision_type="block"}[5m]) > 0.05
        for: 5m
        annotations:
          summary: "Fraud rate > 5%"
          
      - alert: HighLatency
        expr: histogram_quantile(0.99, fraud_detection_latency_seconds) > 0.1
        annotations:
          summary: "P99 latency > 100ms"
          
      - alert: ModelDrift
        expr: model_performance_drift > 0.1
        annotations:
          summary: "Model performance degraded by >10%"
```

---

## PROJECT TIMELINE & MILESTONES

### Phase 1: Fraud Detection (Weeks 1-3)

```
Week 1:
├─ Day 1-2: Setup project structure, data sources
├─ Day 3-4: Feature engineering implementation
├─ Day 5: Model training pipeline
└─ Week 1 deliverable: Basic model trained

Week 2:
├─ Day 1-2: Ensemble model integration
├─ Day 3-4: FastAPI endpoint development
├─ Day 5: SHAP explainability integration
└─ Week 2 deliverable: Fraud detection API running

Week 3:
├─ Day 1-2: Testing & edge cases
├─ Day 3: Docker containerization
├─ Day 4: Documentation & README
├─ Day 5: GitHub push
└─ Week 3 deliverable: Production-grade fraud detection shipped
```

### Phase 2: Payments Data Platform (Weeks 4-6)

```
Week 4:
├─ Day 1-2: Kafka setup & topic design
├─ Day 3-4: Payment simulator implementation
├─ Day 5: Spark Streaming setup
└─ Week 4 deliverable: Kafka + payment simulator running

Week 5:
├─ Day 1-2: Stream processing logic (dedup, validation)
├─ Day 3-4: Redis integration for state management
├─ Day 5: Aggregation logic (1-min, 5-min, 1-hour)
└─ Week 5 deliverable: Streaming pipeline end-to-end

Week 6:
├─ Day 1-2: Streamlit dashboard development
├─ Day 3-4: Grafana dashboards
├─ Day 5: Testing & documentation
└─ Week 6 deliverable: Real-time dashboards live
```

### Phase 3: Lakehouse (Weeks 7-9)

```
Week 7:
├─ Day 1-2: Delta Lake setup (bronze, silver, gold)
├─ Day 3-4: Data ingestion pipeline
├─ Day 5: Schema design & partitioning strategy
└─ Week 7 deliverable: Basic lakehouse structure

Week 8:
├─ Day 1-2: ETL jobs (bronze → silver → gold)
├─ Day 3-4: Data quality frameworks
├─ Day 5: Compliance layer (PII masking, audit logs)
└─ Week 8 deliverable: Full ETL pipeline operational

Week 9:
├─ Day 1-2: ML feature store creation
├─ Day 3-4: Optimization (Z-order, compression)
├─ Day 5: Documentation & governance docs
└─ Week 9 deliverable: Production lakehouse operational
```

### Phase 4: Verifiable Intent (Optional, Weeks 10-12)

```
Week 10:
├─ Day 1-2: Study Mastercard Verifiable Intent framework
├─ Day 3-4: RSA key generation & cryptography
├─ Day 5: Intent claim signing/verification
└─ Week 10 deliverable: Crypto foundation in place

Week 11:
├─ Day 1-2: Integration with fraud detection
├─ Day 3-4: FastAPI endpoint for agentic payments
├─ Day 5: Testing cryptographic flows
└─ Week 11 deliverable: Agentic payment authorization working

Week 12:
├─ Day 1-2: End-to-end integration testing
├─ Day 3-4: Documentation & example scenarios
├─ Day 5: GitHub final push
└─ Week 12 deliverable: Complete platform with Verifiable Intent
```

### Total Effort: 12 Weeks
- **Phase 1-3 (Core):** 9 weeks (high priority)
- **Phase 4 (Optional):** 3 weeks (if time permits)

---

## CONCLUSION

This guide is a component-level how-to. The canonical architecture is [`PAYMENT_PLATFORM.md`](./PAYMENT_PLATFORM.md): one platform, local-first, official Verifiable Intent, authorization × fraud × policy.

**Keys to execution:**
1. Ship working, tested code
2. Document architecture and how to run locally
3. Optimize for payment-system constraints (fraud latency, streaming, governance, agent intent)
4. Stay focused (Phases 1-3 are sufficient; skip Phase 4 if time-constrained)
5. Follow `PAYMENT_PLATFORM.md` wherever this file conflicts

**Next steps:**
1. Use the repository structure in `PAYMENT_PLATFORM.md`
2. Start Phase 1 on `develop`
3. Keep cloud deferred until Phase 12 is explicitly opened

---

Generated: August 2026
