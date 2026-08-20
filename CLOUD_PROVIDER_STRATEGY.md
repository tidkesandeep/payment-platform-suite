# Cloud Provider Strategy for Agentic Payment Platform
**Decision Framework: Mastercard Recruitment Signal + Technical Alignment**

---

## EXECUTIVE SUMMARY

**For Mastercard recruitment:**

| CSP | Score | Reason |
|-----|-------|--------|
| **Azure** | ⭐⭐⭐⭐ | You already use it (EY); Mastercard actively expanding |
| **AWS** | ⭐⭐⭐⭐⭐ | Market leader in fintech/payments; universal credibility |
| **GCP** | ⭐⭐⭐ | Strong data analytics; weaker fintech positioning |

**Recommendation: AWS**

Why:
- Payments infrastructure (AWS Payment Cryptography, PCI)
- Mastercard uses AWS heavily
- Strongest fintech ecosystem
- Maximum recruiter credibility
- But Azure is acceptable if budget-constrained

---

## COMPARISON: AWS vs AZURE vs GCP

### PAYMENTS DOMAIN SERVICES

#### AWS
```
Payments Infrastructure:
├─ AWS Payment Cryptography
├─ AWS Payment Cryptography Data Key
├─ PCI DSS Level 1 compliance
├─ Multi-regional deployment
├─ Fraud detection (via ML)
└─ KMS (encryption key management)

Fintech Market Position:
├─ #1 choice for payment processors
├─ Used by: JPMorgan, Goldman Sachs, Stripe, Square
├─ Strongest payment-specific services
└─ Largest fintech community

Risk Services:
├─ Amazon Fraud Detector
├─ Real-time anomaly detection
├─ Model training + inference
└─ SHAP explainability
```

#### Azure
```
Payments Infrastructure:
├─ Key Vault (encryption)
├─ Azure Dedicated HSM
├─ PCI DSS compliance possible
├─ Cosmos DB (global distribution)
└─ Limited payment-specific services

Fintech Market Position:
├─ Growing in enterprise banking
├─ Used by: HSBC, Barclays (legacy systems)
├─ Weaker payment ecosystem
└─ Smaller fintech community

Risk Services:
├─ Anomaly Detector
├─ Less specialized than AWS
└─ Good for general ML
```

#### GCP
```
Payments Infrastructure:
├─ Cloud KMS (encryption)
├─ BigQuery (analytics)
├─ Limited payment-specific services
└─ Good data warehouse capabilities

Fintech Market Position:
├─ Growing but smaller
├─ Used by: Citi (analytics), some fintechs
├─ Weaker payments ecosystem
└─ Strong in ML/data science

Risk Services:
├─ Vertex AI (general ML)
├─ Good but not payments-specific
└─ Excellent for analytics
```

---

## TECHNOLOGY STACK ALIGNMENT

### Your Blueprint Technology Stack

```
Layer 1: Event Streaming
├─ Kafka → AWS Kinesis preferred
├─ Event Hubs (Azure) → works but not native
└─ Pub/Sub (GCP) → works but less fintech-aligned

Layer 2: Stream Processing
├─ Spark → All three work equally
├─ Kinesis Firehose (AWS best)
└─ Event Hubs (Azure) → works

Layer 3: Data Storage
├─ Delta Lake on S3 (AWS) → ⭐⭐⭐⭐⭐
├─ Delta Lake on ADLS Gen2 (Azure) → ⭐⭐⭐⭐
├─ Delta Lake on GCS (GCP) → ⭐⭐⭐

Layer 4: Machine Learning
├─ SageMaker (AWS) → ⭐⭐⭐⭐⭐ fintech-grade
├─ Azure ML → ⭐⭐⭐⭐ good but less specialized
├─ Vertex AI (GCP) → ⭐⭐⭐⭐ excellent but not payments

Layer 5: Observability
├─ CloudWatch (AWS) → ⭐⭐⭐⭐⭐
├─ Azure Monitor → ⭐⭐⭐⭐
├─ Cloud Logging (GCP) → ⭐⭐⭐⭐

Layer 6: Cryptography (CRITICAL FOR VERIFIABLE INTENT)
├─ AWS KMS + Payment Cryptography → ⭐⭐⭐⭐⭐ BEST
├─ Azure Key Vault → ⭐⭐⭐⭐
└─ Cloud KMS (GCP) → ⭐⭐⭐
```

---

## MASTERCARD'S ACTUAL CLOUD USAGE

**Mastercard is multi-cloud but strategic choices:**

### AWS
```
Mastercard's primary cloud provider
├─ Open Banking APIs (AWS)
├─ AI/ML infrastructure
├─ Transaction processing (Kinesis)
├─ Multi-region deployment
└─ ~60-70% of public cloud spend (estimated)

Mastercard + AWS Joint Offerings:
├─ "Mastercard and AWS Collaboration"
├─ Joint fintech solutions
├─ Payment processing templates
└─ Recruiting emphasis: AWS expertise valued
```

### Azure
```
Secondary cloud provider
├─ Enterprise banking relationships
├─ Legacy system integration
├─ Some AI/ML workloads
└─ ~20-30% of public cloud spend (estimated)

Azure Experience:
├─ Valuable (you have it via EY)
├─ But not primary technical direction
└─ Recruiter sees it as "enterprise Microsoft shop" skill
```

### GCP
```
Emerging third option
├─ Data analytics focus (BigQuery)
├─ Emerging AI/ML initiatives
└─ ~10-20% of public cloud spend (estimated)

GCP Recruiting Signal:
├─ Interesting for ML
├─ But not payment infrastructure
└─ Weaker signal for Mastercard
```

---

## RECRUITER SIGNAL ANALYSIS

### AWS Choice
**Recruiter thinks:**
> "This engineer chose the payment industry standard.
> They understand Mastercard's technology direction.
> They can immediately contribute to our AWS payment infrastructure."

**Signal strength:** ⭐⭐⭐⭐⭐ Maximum

**Why it works:**
- AWS is where Mastercard's payments business lives
- Kinesis is their transaction streaming choice
- SageMaker is their ML platform
- KMS + Payment Crypto is their key management
- Demonstrates you know the industry standard

---

### Azure Choice
**Recruiter thinks:**
> "They have Azure experience (good).
> But they didn't choose the payment industry standard.
> Why Azure for a payment platform?"

**Signal strength:** ⭐⭐⭐⭐ Good but not optimal

**Why it's weaker:**
- You're already known to have Azure skills (EY contractor)
- Choosing Azure again doesn't prove new thinking
- Mastercard sees Azure as "enterprise legacy," not "cutting-edge payments"
- Doesn't demonstrate payment domain expertise

**When Azure makes sense:**
- If you're recruiting for enterprise banking roles (HSBC, Barclays, etc.)
- If you want to emphasize Azure certifications
- If building in Azure ecosystem is mandatory (organizational constraint)

---

### GCP Choice
**Recruiter thinks:**
> "Interesting ML choice.
> But this isn't a payment platform, it's a data science project."

**Signal strength:** ⭐⭐⭐ Weaker for payments

**Why it's misaligned:**
- GCP is data-science focused, not payments-focused
- Mastercard doesn't prioritize GCP for payment infrastructure
- Sends signal: "I'm a data person, not a payments person"
- Doesn't leverage Mastercard's existing infrastructure

---

## HYBRID APPROACH: MULTI-CLOUD STRATEGY

### Option 1: Primary AWS + Secondary Cloud
```
RECOMMENDED HYBRID

Primary Implementation: AWS
├─ Event Streaming: Kinesis (industry standard)
├─ Stream Processing: Kinesis Firehose + Spark
├─ Storage: S3 + Delta Lake
├─ ML: SageMaker
├─ Cryptography: KMS + Payment Cryptography
├─ Observability: CloudWatch
└─ Deployed in 2-3 regions

Secondary Deployment: Azure (optional)
├─ Same code, different infrastructure
├─ Event Hub instead of Kinesis
├─ ADLS Gen2 instead of S3
├─ Azure ML instead of SageMaker
├─ Key Vault instead of KMS
└─ For 1-2 regions

Recruiter Signal:
✅ "AWS-first (payments standard)"
✅ "Multi-cloud thinking (enterprise skill)"
✅ "Can work with Azure too (EY background)"
✅ "Understands cloud portability"

Implementation Effort:
- Start with AWS (8-10 weeks)
- Add Azure deployment (additional 2-3 weeks)
- Shows versatility without losing focus
```

### Option 2: AWS Primary Only
```
FASTEST IMPLEMENTATION

Primary Implementation: AWS Only
├─ All services in AWS
├─ Full depth (not spreading thin)
├─ Best recruiter signal (focused expertise)
└─ Timeline: 14-15 weeks (as planned)

Why This Works:
✅ Mastercard's actual infrastructure
✅ Demonstrates payment domain expertise
✅ Deeper implementation in one ecosystem
✅ Can mention "portable architecture" (implicit AWS → others)

Recruiter Signal:
⭐⭐⭐⭐⭐ Maximum (focused expertise)
```

---

## DETAILED AWS SERVICE MAPPING

### Phase 1: Foundation
```
Transaction API
├─ AWS Lambda (serverless)
├─ API Gateway (REST endpoint)
├─ RDS PostgreSQL (transaction store)
└─ VPC + IAM (networking + security)

Kafka Alternative: Amazon Kinesis
├─ Kinesis Data Streams (event streaming)
├─ Kinesis Firehose (delivery)
├─ Kinesis Analytics (real-time processing)
└─ ~$0.36/million records (vs Kafka managed: $1.2)

Cost: ~$50-100/month (starter tier)
```

### Phase 2: Streaming
```
Real-Time Processing
├─ Kinesis Data Streams
├─ Spark Streaming on EC2 or EMR
├─ Managed Apache Flink (emerging)
└─ Lambda (for lightweight processing)

Recommended: Kinesis + EMR
├─ Kinesis: $50-200/month
├─ EMR: $200-500/month (depending on cluster size)
└─ S3: $30-50/month (data storage)

Cost: ~$300-750/month
```

### Phase 3: Lakehouse
```
Delta Lake on S3
├─ S3 (object storage)
├─ AWS Glue Data Catalog (metadata)
├─ AWS Glue ETL (transformations)
├─ Athena (SQL queries)
└─ Lake Formation (governance)

Or: Databricks on AWS
├─ Databricks (managed Spark)
├─ Works natively with S3
├─ Built-in Delta Lake
├─ Simpler than raw EMR
└─ ~$0.50/DBU/hour

Cost: S3 $50-100/month OR Databricks $300-600/month
```

### Phase 4: Features
```
Online Features
├─ ElastiCache (Redis replacement)
├─ DynamoDB (low-latency KV store)
└─ ~$0.36/hour per node

Offline Features
├─ Glue ETL jobs
├─ Athena queries
├─ SageMaker Feature Store
└─ $2-10/day per pipeline

Cost: ~$50-150/month
```

### Phase 5: Fraud Engine
```
Model Training
├─ SageMaker (managed ML service)
├─ Can use XGBoost, LightGBM, TensorFlow
├─ AutoML capabilities
├─ Built-in feature store
└─ Notebook instances for development

Real-Time Inference
├─ SageMaker Endpoints
├─ <50ms latency SLA achievable
├─ Auto-scaling
└─ ~$0.36/hour per instance

Cost: ~$200-400/month (development + inference)
```

### Phase 6: Observability
```
Monitoring
├─ CloudWatch (native AWS)
├─ OpenTelemetry integration
├─ Custom metrics
└─ Dashboard + alarms

Cost Logs: ~$0.50/GB ingested
Metrics: ~$0.30/custom metric/month
Dashboards: Free
→ ~$100-200/month
```

### Phase 7: AI Services
```
Fraud Investigation Agent
├─ Bedrock (LLM access)
│  ├─ Claude 3.5 Sonnet
│  ├─ GPT-4, Llama, etc.
│  └─ Pay per token
│
├─ Lambda (agent logic)
├─ DynamoDB (RAG context store)
└─ S3 (document storage)

Cost: $0.03-0.15 per 1K input tokens
→ ~$50-150/month (moderate usage)
```

### Phase 8: Verifiable Intent
```
Cryptography
├─ AWS KMS (key management)
│  └─ ~$1/month per key + $0.03/10k requests
│
├─ AWS Payment Cryptography
│  └─ Purpose-built for payment crypto
│  └─ ~$1.60/hour per HSM
│
├─ Secrets Manager (credential storage)
│  └─ ~$0.40/secret + $0.05/rotation

Cost: ~$50-100/month for cryptographic operations
```

### Phase 9-12: Full Stack
```
TOTAL AWS MONTHLY COST ESTIMATE

Development Phase (Phases 1-8):
├─ Compute (EC2, Lambda): $200-400
├─ Storage (S3): $50-100
├─ Databases (RDS, DynamoDB): $100-200
├─ Data Processing (Kinesis, Glue): $200-400
├─ ML (SageMaker): $200-400
├─ Observability: $100-200
├─ Cryptography: $50-100
└─ TOTAL: ~$900-1800/month

Production Phase (with scale testing):
├─ Same services but larger instances
├─ Multi-region replication
├─ Higher throughput (100K+ TPS)
└─ TOTAL: ~$3000-6000/month

Cost Optimization:
✅ Use free tier (12 months for new accounts)
✅ Use spot instances for non-critical workloads
✅ Use reserved capacity
✅ Shutdown non-production resources nightly
→ Realistic cost for portfolio project: $300-500/month
```

---

## AWS PAYMENT-SPECIFIC ADVANTAGES

### AWS Payment Cryptography
```
Purpose-Built for Payments

What It Does:
├─ HSM-backed key management
├─ PCI DSS Level 1 compliance
├─ Payment-specific operations
├─ Cryptographic standards validation
└─ Audit logging

Why It Matters for Verifiable Intent:
├─ Official Mastercard spec uses ES256
├─ AWS Payment Cryptography supports ES256
├─ HSM protects private keys
├─ Audit trail for compliance
└─ Industry-standard approach

Example:
```
import boto3

kms_client = boto3.client('payment-cryptography')

# Generate signing key (HSM-backed)
response = kms_client.create_key(
    KeyAttributes={
        'KeyUsage': 'SIGN_VERIFY',
        'KeyClass': 'PRIVATE_KEY',
        'KeyAlgorithm': 'ECC_SM2'  # or ES256, etc.
    }
)

# Sign intent claim
signature = kms_client.sign(
    KeyIdentifier=key_id,
    Message=intent_claim,
    SigningAlgorithm='ES256'
)
```

This is exactly what you need for Verifiable Intent + Payment Cryptography integration.
```

### AWS Fraud Detector
```
Purpose-Built for Payments Fraud

What It Does:
├─ Detects fraud patterns
├─ Uses AutoML training
├─ Real-time scoring
├─ Explainability (model + rule-based)
└─ PCI DSS compliance

Integration with Your Fraud Engine:
├─ Use as secondary model (ensemble)
├─ OR use as baseline (replace your XGBoost)
├─ Gets you Mastercard's fraud ML approach
└─ Shows industry-standard thinking

Cost: $100-200/month for moderate usage
```

---

## ALTERNATIVE: RUN LOCALLY FIRST

### Development Approach
```
Month 1-2: LocalStack Development
├─ Run AWS services locally (Docker)
├─ LocalStack (open-source)
│  └─ Kinesis, Lambda, S3, DynamoDB, etc.
│
├─ Kafka locally (as-is)
├─ Postgres locally (as-is)
├─ Redis locally (as-is)
└─ Free and identical to AWS

Then Month 3: Deploy to AWS
├─ Move from LocalStack to AWS
├─ Docker Compose → CloudFormation/Terraform
├─ Minimal code changes
└─ Full cloud deployment

Advantages:
✅ No cloud costs during development
✅ Faster iteration loop (local is faster)
✅ Learn cloud deployment at end
✅ Can show both local + AWS deployment

Cost: $0 during development, $300-500 for Phase 9-12 deployment
```

---

## FINAL RECOMMENDATION

### PRIMARY RECOMMENDATION: AWS

```
Why:
1. Payment industry standard
2. Mastercard uses AWS heavily
3. Strongest fintech ecosystem
4. AWS Payment Cryptography + KMS for Verifiable Intent
5. SageMaker for fraud ML
6. Maximum recruiter credibility

Implementation:
├─ Phases 1-8: LocalStack (free)
├─ Phases 9-12: AWS cloud ($300-500/month)
└─ Total project cost: ~$1500-2000 USD

Timeline: 14-15 weeks (as planned)
Signal: ⭐⭐⭐⭐⭐ Maximum
```

### SECONDARY RECOMMENDATION: AWS Primary + Azure Secondary

```
Why:
1. AWS primary (payments expertise)
2. Azure secondary (enterprise thinking)
3. Shows multi-cloud understanding
4. Leverages your EY/Azure experience
5. Demonstrates portability

Implementation:
├─ Phases 1-8: AWS + LocalStack (free)
├─ Phases 9-12: 
│  ├─ AWS full deployment ($300-500/month)
│  └─ Azure equivalent infrastructure (additional $200-300/month)
└─ Total project cost: ~$2500-3000 USD

Timeline: 16-18 weeks (additional 2-3 weeks for Azure)
Signal: ⭐⭐⭐⭐⭐ Maximum + "multi-cloud architect"
```

### AVOID: GCP Primary

```
Why Not:
1. Weak payments positioning
2. Data science focus (misses payment architecture)
3. Mastercard not primary GCP customer
4. Doesn't leverage Mastercard + AWS relationship
5. Weaker recruiter signal for payments roles

Signal: ⭐⭐⭐ Good for general ML, but not payments-specific
```

### AVOID: Azure Primary

```
Why Not:
1. Recruiters expect you to choose AWS for payments
2. Choosing Azure again (after EY) = "no new thinking"
3. Azure seen as "enterprise legacy," not "payments innovation"
4. Mastercard's primary payment infrastructure is AWS
5. Signals: "data engineer who hasn't shifted to fintech thinking"

Signal: ⭐⭐⭐⭐ Acceptable, but suboptimal
```

---

## IMPLEMENTATION CHECKLIST

### If Going AWS Primary:

```
☐ Create AWS account (free tier: 12 months)
☐ Set up IAM roles + policies (security first)
☐ Create VPC (network isolation)
☐ Set up Terraform (infrastructure as code)
☐ Configure CloudWatch (observability)
☐ Set cost alerts ($50/month threshold)

☐ Phases 1-8: Use LocalStack (free, identical to AWS)
  ├─ Kinesis → LocalStack Kinesis
  ├─ S3 → LocalStack S3
  ├─ Lambda → LocalStack Lambda
  ├─ RDS → Local Postgres
  └─ DynamoDB → LocalStack DynamoDB

☐ Phase 9-12: Migrate to real AWS
  ├─ Push Docker images to ECR
  ├─ Deploy to ECS/EKS
  ├─ Enable CloudWatch dashboards
  ├─ Configure auto-scaling
  └─ Run load tests

☐ Document architecture (Terraform modules)
☐ Write cost optimization report
☐ Create deployment runbook
```

### If Going Hybrid (AWS + Azure):

```
All AWS steps above, PLUS:

☐ Create Azure account (free tier: 12 months)
☐ Set up Azure Resource Groups
☐ Set up Azure Terraform modules

☐ Create abstraction layer:
  ├─ Constants for cloud-specific services
  ├─ Cloud factory pattern
  └─ Provider-agnostic APIs where possible

☐ Phase 13-14: Deploy to Azure
  ├─ Event Hubs instead of Kinesis
  ├─ ADLS Gen2 instead of S3
  ├─ Azure ML instead of SageMaker
  ├─ Key Vault instead of KMS
  └─ Azure Container Apps instead of ECS

☐ Demonstrate parity:
  ├─ Same fraud model in both clouds
  ├─ Performance comparison
  ├─ Cost comparison
  └─ Operational complexity comparison

✅ This positions you as "cloud-agnostic architect"
```

---

## COST BREAKDOWN: AWS vs AZURE

### AWS (14-15 weeks)
```
Phase 1-8: Development (LocalStack)
├─ LocalStack: Free
├─ Local resources: Free
└─ Total: $0

Phase 9-12: Cloud Deployment
├─ Kinesis: $100-200/month
├─ S3: $50-100/month
├─ RDS/DynamoDB: $100-200/month
├─ EC2/Lambda: $200-400/month
├─ SageMaker: $200-400/month
├─ Other services: $100-200/month
└─ 2 months deployment: $1400-2000

Total AWS Project Cost: ~$1500-2000 USD
```

### Azure (16-18 weeks, hybrid)
```
Phase 1-8: Development (LocalStack)
├─ LocalStack: Free
└─ Total: $0

Phase 9-12: AWS Cloud Deployment
└─ Same as AWS: $1400-2000

Phase 13-14: Azure Cloud Deployment
├─ Event Hubs: $100-150/month
├─ ADLS Gen2: $50-100/month
├─ Azure SQL/Cosmos: $100-200/month
├─ Azure VMs: $200-400/month
├─ Azure ML: $150-300/month
├─ Other services: $100-150/month
└─ 2 months deployment: $1200-1800

Total Hybrid Project Cost: ~$2600-3800 USD
```

---

## FINAL ANSWER

### ✅ PRIMARY CHOICE: AWS

**Why:**
- Mastercard's primary cloud
- Payment-specific services (KMS, Payment Crypto)
- Strongest fintech ecosystem
- Maximum recruiter signal
- Industry standard for payments

**Implementation:**
- Phases 1-8: LocalStack (free)
- Phases 9-12: AWS cloud ($300-500/month)
- Total cost: ~$1500-2000

**Timeline:** 14-15 weeks (as planned)

**Recruiter Signal:** ⭐⭐⭐⭐⭐ Maximum

---

### ✅ SECONDARY CHOICE: Hybrid (AWS + Azure)

**Why:**
- AWS primary (payments)
- Azure secondary (enterprise)
- Shows multi-cloud thinking
- Leverages your Azure background

**Implementation:**
- Phases 1-8: LocalStack (free)
- Phases 9-12: AWS ($1.4-2K)
- Phases 13-14: Azure ($1.2-1.8K additional)
- Total cost: ~$2600-3800

**Timeline:** 16-18 weeks (2-3 weeks longer)

**Recruiter Signal:** ⭐⭐⭐⭐⭐ Maximum + "multi-cloud architect"

---

### ❌ AVOID: GCP or Azure Primary

Too much misalignment with Mastercard's actual technology direction.
