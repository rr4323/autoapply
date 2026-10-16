# AgentOS Full-Stack Learning Roadmap

**Goal:** Build end-to-end system demonstrating agent architecture → data pipeline → K8s orchestration → observability → MLOps.

**Current State:** Phase A (M0) skeleton exists. Docker-compose with API, agents, PostgreSQL, Redis, MinIO. Need to complete Phase 1 and layer each subsequent phase.

---

## Core Evaluation Framework (Spans All Phases)

This roadmap emphasizes **three evaluation pillars** that run through every phase:

### 1. RAG Evaluation (Phase 2 onward)
**What:** Assessing quality of retrieved documents in context of the job description.

**Metrics:**
- `retrieval_relevance` (0.0-1.0): Are retrieved docs actually related to the JD? Use LLM to score.
- `retrieval_coverage` (0.0-1.0): Do docs collectively cover job responsibilities? Coverage of key skills, experience levels, etc.
- `retrieval_latency_ms`: How long does retrieval take?
- `num_docs_retrieved`: Document count (may be filtered by relevance threshold)

**Implementation:** `backend/agents/src/agentos_agents/retriever/evaluator.py`
- Takes: JD (query) + retrieved docs (results)
- Calls Claude to score relevance/coverage
- Returns: evaluation dict → published to Kafka topic `rag-evaluations`
- Storage: PostgreSQL table `rag_evaluation_results`

**Monitoring:** Phase 4 dashboard shows RAG relevance/coverage trends + alerts if dropping below threshold.

---

### 2. Agent Evaluation (Phase 2 onward)
**What:** Assessing how well each agent completed its task.

**Metrics per agent type:**
- `success_rate` (%): % of runs that succeeded
- `avg_latency` (ms): How long each agent takes
- `error_rate_by_type`: Breakdown of failures (timeout, API error, validation, etc.)
- `quality_score` (0.0-1.0): Output quality (e.g., for Generator: cover letter coherence, citation count, length)

**Implementation:** `backend/agents/src/agentos_agents/common/evaluator.py`
- Each agent publishes evaluation after completion
- Metrics calculated from agent logs + output inspection
- Published to Kafka topic `agent-evaluations`
- Storage: PostgreSQL table `agent_evaluation_results`

**Monitoring:** Phase 4 dashboard shows success rates per agent, error breakdown, quality trends + alerts if degrading.

---

### 3. Monitoring (Phase 2 → Phase 4 → Phase 5)
**What:** Real-time visibility into evaluation metrics + infrastructure health + automated response.

**Phase 2:** Kafka topics + PostgreSQL tables capture raw evaluation data.

**Phase 4:** 
- Prometheus scrapes evaluation metrics from applications
- Grafana dashboards visualize RAG + agent evaluation trends
- Alert rules: IF RAG relevance < 0.6 THEN warn / IF agent success rate < 85% THEN page oncall
- Query builder: SQL interface to slice evaluation data by date, agent type, JD source

**Phase 5:**
- Retraining pipeline reads evaluation metrics to decide: should we retrain?
- Model registry tracks evaluation baseline per model version
- MLflow links experiments to evaluation data for reproducibility

**Key insight:** Monitoring isn't just dashboards — it's the feedback loop that drives improvement.

---

## Data Architecture: OLTP, OLAP, Data Lake (Introduced in Phase 2)

Your system handles **three types of data workloads**, each requiring different tools:

### OLTP (Online Transactional Processing) — PostgreSQL
**Purpose:** Real-time operational data, freshest state.

**Use cases:**
- Current agent runs (did this run succeed?)
- Recent evaluation results (what's the latest RAG relevance score?)
- API queries (get details of a specific application)
- Transactions (update agent status, log new events)

**Characteristics:**
- Normalized schema (no redundancy)
- Fast writes + reads for small datasets
- Supports transactions (ACID)

**Tables in Phase 2:**
- `agent_runs` (transactional record of each agent execution)
- `rag_evaluation_results` (fresh evaluation scores per retrieval)
- `agent_evaluation_results` (fresh evaluation per agent)

---

### OLAP (Online Analytical Processing) — Pinot
**Purpose:** Fast analytics queries over large datasets, trending, aggregations.

**Use cases:**
- What's the average RAG relevance over the last 7 days?
- How does agent success rate compare day-over-day?
- Top 10 failure reasons by frequency?
- Dashboards (slicing data by date, agent type, source)

**Characteristics:**
- Pre-aggregated columns (ready for sums, averages, grouping)
- Columnar storage (compress similar values together)
- Fast queries for OLAP operations (slow for writes)
- Handles massive datasets efficiently

**Tables in Phase 2:**
- `rag_evaluation_metrics` (hourly aggregates: avg relevance, coverage, latency)
- `agent_evaluation_metrics` (hourly per-agent aggregates: success rate, latency p50/p95)

---

### Data Lake — S3 (Object Storage)
**Purpose:** Long-term raw event archive, compliance, retraining.

**Use cases:**
- Retrain models on 6 months of historical data
- Audit trail (what happened 3 months ago?)
- Compliance (keep all events for regulatory requirements)
- Machine learning (raw evaluation data → features for model training)

**Characteristics:**
- Immutable (once written, not changed)
- Partitioned for efficient querying (by date, topic, source)
- Parquet format (columnar, compressible)
- Infinitely scalable, cheap storage

**Buckets in Phase 2:**
- `agentos-raw-events/` (all Kafka events, partitioned by topic/date/hour)
- `agentos-evaluation-data/` (evaluation results in training format)
- `agentos-models/` (model checkpoints + artifacts)

---

### Why Three Layers?

```
Real-time transactions (PostgreSQL/OLTP)
         ↓
Analytical aggregations (Pinot/OLAP) ← Dashboards query this
         ↓
Long-term archive (S3/Data Lake) ← Retraining reads this
```

| Question | Use | Tool |
|----------|-----|------|
| Did this run succeed? (current) | Real-time status | PostgreSQL |
| What's avg relevance this week? | Trending, analytics | Pinot |
| Retrain on past 6 months? | Historical data, ML | S3 |

---

## Phase 1: Foundation (Agent + Scoring)
**Timeline:** 2-3 weeks  
**Learning:** Event-driven architecture, message passing, application flow  
**Deliverable:** Agent runs end-to-end, produces measurable outcomes, logs events to message bus

### Checklist

1. **Complete the agent pipeline** (backend/agents/src/agentos_agents/)
   - [ ] Scraper agent: fetch JD from job board → extract structured data
   - [ ] Retriever agent: take extracted JD → query internal vector DB → retrieve candidate context
   - [ ] Scoring agent: compare JD + candidate → output confidence score
   - [ ] Generator agent: create honest cover letter using scored data
   - [ ] Filler agent: fill ATS form with application data
   - [ ] Verifier agent: validate submission succeeded

2. **Add event production to each agent** (backend/agents/src/agentos_agents/common/publisher.py exists)
   - [ ] Each agent publishes to Redis (in-memory topic) at start/end/error
   - [ ] Events include: `{agent_id, run_id, timestamp, status, input_hash, output_hash, cost_estimate}`
   - [ ] Verify via Redis CLI: `redis-cli SUBSCRIBE agent-events`

3. **E2E test the full pipeline** (backend/agents/tests/test_e2e.py)
   - [ ] Mock job board (ats-fixtures already provides this)
   - [ ] Run all 6 agents in sequence
   - [ ] Verify output (application submitted + score confidence)
   - [ ] Check events landed in Redis

4. **Verify**
   - Run: `make test-e2e`
   - Expected: All agents succeed, confidence score 0.0-1.0, events logged to Redis

---

## Phase 2: Data Pipeline (Kafka + Flink + OLTP/OLAP/Data Lake)
**Timeline:** 4-5 weeks  
**Learning:** Message brokers, event streaming, stateful aggregation, OLTP vs OLAP architecture, data lake design  
**Deliverable:** Replace Redis with Kafka, add Flink jobs, set up PostgreSQL (OLTP), Pinot (OLAP), S3 (Data Lake)

### Checklist

1. **Add Kafka to docker-compose.yml**
   - [ ] Add Kafka service (bitnami/kafka)
   - [ ] Add Zookeeper dependency
   - [ ] Expose ports 9092 (broker), 29092 (internal)
   - [ ] Add healthcheck (kafka-broker-api-versions.sh)
   - [ ] Test: `docker compose up -d && docker compose exec kafka kafka-topics.sh --list --bootstrap-server localhost:9092`

2. **Create Kafka topics** (in docker-compose or init script)
   - [ ] `agent-events` (agent run lifecycle)
   - [ ] `rag-queries` (retriever queries + results)
   - [ ] `rag-evaluations` (relevance scores, coverage metrics)
   - [ ] `agent-evaluations` (agent output quality, success/failure analysis)
   - [ ] `scoring-results` (scoring confidence + rationale)
   - [ ] `applications-submitted` (final outcome)
   - Replication factor: 1 (dev), Partitions: 3

3. **Refactor publisher** (backend/agents/src/agentos_agents/common/publisher.py)
   - [ ] Create `KafkaPublisher` class (inherits from abstract `Publisher`)
   - [ ] Remove Redis publisher
   - [ ] Each agent uses KafkaPublisher to emit to appropriate topic
   - [ ] Test: publish event → `kafka-console-consumer.sh --topic agent-events`

4. **Add RAG Evaluation** (new: backend/agents/src/agentos_agents/retriever/evaluator.py)
   - [ ] Implement `RAGEvaluator` class:
     - Input: JD (query), retrieved docs (results)
     - Metrics:
       - `retrieval_relevance`: does each doc relate to JD requirements? (0.0-1.0)
       - `retrieval_coverage`: do docs collectively cover job responsibilities? (0.0-1.0)
       - `retrieval_latency_ms`: how long to fetch results
       - `num_docs_retrieved`: document count
     - Method: LLM-based evaluation (use Claude to score relevance + coverage)
   - [ ] Publish to `rag-evaluations` topic after retrieval completes
   - [ ] Store results in PostgreSQL table `rag_evaluation_results`

5. **Add Agent Evaluation** (new: backend/agents/src/agentos_agents/common/evaluator.py)
   - [ ] Implement `AgentEvaluator` class:
     - Tracks per-agent metrics:
       - `success_rate`: % of successful runs in sliding window
       - `avg_latency`: execution time
       - `error_rate`: failure causes (timeout, API error, validation error, etc.)
       - `quality_score`: based on output inspection (e.g., cover letter length, citation count)
   - [ ] Each agent publishes evaluation after completion
   - [ ] Publish to `agent-evaluations` topic
   - [ ] Store in PostgreSQL table `agent_evaluation_results`

6. **Add first Flink jobs** (new: backend/agents/flink/)
   - [ ] Create Maven project: `mvn archetype:generate` (flink-quickstart)
   - [ ] Job 1: `AggregateAgentMetrics` 
     - Read: `agent-events` topic
     - Window: 5-minute tumbling window
     - Aggregate: count succeeded, count failed, avg latency per agent type
     - Sink: PostgreSQL table `agent_metrics_5min`
   - [ ] Job 2: `AggregateRAGEvaluation`
     - Read: `rag-evaluations` topic
     - Window: hourly
     - Aggregate: avg relevance, avg coverage, p50/p95 latency
     - Sink: PostgreSQL table `rag_evaluation_metrics_hourly`
   - [ ] Job 3: `AggregateAgentEvaluation`
     - Read: `agent-evaluations` topic
     - Window: hourly per agent type
     - Aggregate: success rate, latency percentiles, quality scores
     - Sink: PostgreSQL table `agent_evaluation_metrics_hourly`
   - [ ] Deploy: `make build-flink` → `docker-compose up flink-jobmanager`

7. **Add Flink to docker-compose.yml**
   - [ ] Flink JobManager service
   - [ ] Flink TaskManager service (1 replica for dev)
   - [ ] Expose ports 8081 (UI), 6123 (taskmanager)

8. **Add OLAP layer (Pinot)** — real-time OLAP database for analytics queries
   - [ ] Add Pinot service to docker-compose.yml (Pinot Controller + Broker)
   - [ ] Configure Pinot table schemas:
     - Table: `rag_evaluation_metrics` (schema for RAG metrics)
       - Columns: timestamp, agent_id, retrieval_relevance, retrieval_coverage, latency_ms, num_docs
       - Time column: timestamp
       - Real-time ingestion from Kafka topic `rag-evaluations`
     - Table: `agent_evaluation_metrics` (schema for agent metrics)
       - Columns: timestamp, agent_type, success_count, failure_count, avg_latency, quality_score
       - Real-time ingestion from Kafka topic `agent-evaluations`
   - [ ] Create Pinot connectors: Kafka → Pinot (real-time tables)
   - [ ] Test: Query Pinot via PQL (Pinot Query Language)
     - `SELECT AVG(retrieval_relevance) FROM rag_evaluation_metrics WHERE timestamp > now() - 3600000`

9. **Add Data Lake (S3/MinIO)** — long-term raw data storage
   - [ ] MinIO already in docker-compose (storage backend)
   - [ ] Create S3 buckets:
     - Bucket: `agentos-raw-events` (all raw Kafka events, partitioned by date/topic)
     - Bucket: `agentos-evaluation-data` (raw evaluation results for retraining)
     - Bucket: `agentos-models` (model artifacts + checkpoints)
   - [ ] Add Flink sink to S3:
     - Job 4: `ArchiveToDataLake`
       - Read: all Kafka topics (agent-events, rag-evaluations, agent-evaluations, etc.)
       - Format: Parquet (columnar, compressible)
       - Path: `s3://agentos-raw-events/{topic}/{year}/{month}/{day}/{hour}/`
       - Sync to S3: every 1 hour
   - [ ] Verify: `aws s3 ls s3://agentos-raw-events/ --recursive` shows hourly partitions

10. **Setup OLTP → OLAP → Data Lake pipeline**
    - [ ] Kafka topics flow to 3 sinks in parallel:
      - **OLTP (PostgreSQL)**: Real-time transactional storage (operational queries)
        - Tables: agent_runs, rag_queries, evaluation_results (fresh, up-to-date)
        - Used by: API, agents, monitoring (current state)
      - **OLAP (Pinot)**: Analytical aggregations (trending, slicing)
        - Tables: hourly/daily aggregates, pre-computed metrics
        - Used by: Dashboards, reporting, business intelligence
      - **Data Lake (S3/Parquet)**: Raw event archive (retraining, compliance)
        - Format: Partitioned Parquet by date/topic
        - Used by: Retraining pipeline, offline analysis, audit
    - [ ] Diagram in code:
      ```
      Kafka topics
        ├─→ PostgreSQL (OLTP) → Real-time queries
        ├─→ Pinot (OLAP) → Analytics queries (pre-aggregated)
        └─→ S3 (Data Lake) → Raw archive (retraining, compliance)
      ```

11. **Add schema migration for OLAP**
    - [ ] Create database view: `rag_evaluation_summary` (aggregated stats)
    - [ ] Create database view: `agent_evaluation_summary` (per-agent stats)
    - [ ] These feed Grafana dashboards in Phase 4

12. **Verify**
    - Run agents → check all three layers:
      - **OLTP (PostgreSQL)**: `SELECT * FROM rag_evaluation_results ORDER BY created_at DESC LIMIT 5;` (fresh data)
      - **OLAP (Pinot)**: `SELECT AVG(retrieval_relevance) FROM rag_evaluation_metrics WHERE timestamp > now() - 3600000;` (aggregated)
      - **Data Lake (S3)**: `aws s3 ls s3://agentos-raw-events/rag-evaluations/` (partitioned Parquet files)
    - Expected: Data flowing through all three layers simultaneously

---

## Phase 3: K8s Orchestration
**Timeline:** 3-4 weeks  
**Learning:** Container orchestration, StatefulSets for stateful services, resource management  
**Deliverable:** Move Kafka + Flink from docker-compose to K8s

### Checklist

1. **Setup local K8s** (minikube)
   - [ ] Install minikube: `brew install minikube` (Mac) or `choco install minikube` (Windows)
   - [ ] Start cluster: `minikube start --cpus 4 --memory 8192`
   - [ ] Enable ingress addon: `minikube addons enable ingress`
   - [ ] Test: `kubectl get nodes`

2. **Create K8s manifests** (new: k8s/)
   - [ ] Namespace: `agentos-dev`
   - [ ] Kafka StatefulSet + Headless Service
     - Replicas: 1 (dev)
     - Persistence: PVC for /var/lib/kafka
     - Broker config: KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka-0.kafka:9092
   - [ ] Zookeeper Deployment + Service
   - [ ] PostgreSQL StatefulSet + PVC
   - [ ] Redis Deployment + Service

3. **Deploy to K8s**
   - [ ] Write Helm chart (optional, but better long-term)
     - Or: kubectl apply -f k8s/*.yaml
   - [ ] Verify Kafka is running: `kubectl logs -n agentos-dev kafka-0`
   - [ ] Test connectivity: `kubectl run -it --rm kafka-test --image=confluentinc/cp-kafka:latest --restart=Never -- kafka-console-producer --broker-list kafka:9092`

4. **Deploy Flink on K8s**
   - [ ] Flink JobManager StatefulSet
   - [ ] Flink TaskManager Deployment (3 replicas)
   - [ ] Service to expose JobManager UI (port 8081)
   - [ ] ConfigMap for flink-conf.yaml
   - [ ] Job submission: `kubectl port-forward -n agentos-dev svc/flink-jobmanager 8081:8081` → upload JAR via UI

5. **Deploy Pinot (OLAP) to K8s**
   - [ ] Pinot Controller StatefulSet
   - [ ] Pinot Broker Deployment (2 replicas)
   - [ ] Pinot Server StatefulSet (2 replicas)
   - [ ] Zookeeper Deployment (dependency for Pinot)
   - [ ] Service exposing Broker on port 8099 (Pinot UI)
   - [ ] ConfigMap: Pinot table schemas
   - [ ] Real-time ingestion: configure Kafka connectors in Pinot

6. **Migrate API + Agents to K8s**
   - [ ] Go API Deployment (3 replicas)
   - [ ] Python Agent Worker Deployment (5 replicas)
   - [ ] Service exposing API on port 8080
   - [ ] ConfigMaps for environment variables
   - [ ] Verify health: `kubectl get pods -n agentos-dev`

7. **Verify**
   - Run: `kubectl port-forward -n agentos-dev svc/api 8080:8080`
   - Hit: `curl localhost:8080/healthz` → 200 OK
   - Check Flink UI: http://localhost:8081 → jobs running
   - Check Pinot UI: http://localhost:8099 → tables ingesting data
   - Verify S3/MinIO access from Flink pods (data lake working)

---

## Phase 4: Monitoring & Observability (Prometheus + Grafana + Finops)
**Timeline:** 4-5 weeks  
**Learning:** Metrics scraping, time-series databases, alert rules, evaluation monitoring, cost tracking, dashboard design  
**Deliverable:** Full visibility into agent + RAG evaluation, infra health, cost tracking with budget alerts

### Checklist

1. **Add Prometheus scrape targets**
   - [ ] Add Prometheus service to K8s (Deployment)
   - [ ] ConfigMap: prometheus.yml
     - Scrape: API (port 8080/metrics)
     - Scrape: Kafka (port 9999/metrics - needs JMX exporter)
     - Scrape: Flink (port 8081/metrics)
     - Scrape: PostgreSQL (postgres-exporter sidecar)
   - [ ] PVC for Prometheus storage (15 days retention)

2. **Instrument applications with evaluation metrics**
   - [ ] Go API: Add Prometheus library
     - Metrics: `api_requests_total`, `api_request_duration_seconds`, `database_queries_total`
   - [ ] Python agents: Add Prometheus client
     - Metrics: `agent_runs_total`, `agent_duration_seconds`, `agent_success_rate`, `llm_token_usage`
   - [ ] RAG evaluator: Export to Prometheus
     - Metrics: `rag_retrieval_relevance`, `rag_retrieval_coverage`, `rag_query_latency`
   - [ ] Agent evaluator: Export to Prometheus
     - Metrics: `agent_quality_score`, `agent_error_rate_by_type`, `agent_latency_percentiles`
   - [ ] Test: `curl localhost:8080/metrics` → see Prometheus format

3. **Create evaluation-focused queries**
   - [ ] **OLTP (PostgreSQL)** queries for real-time data:
     - Query: Recent RAG evaluation scores (relevance + coverage trends)
     - Query: Agent success rates per agent type
     - Query: Quality score distribution (histogram)
     - Query: Error rate breakdown by failure type
     - Save as named views in PostgreSQL for Grafana
   - [ ] **OLAP (Pinot)** queries for analytics:
     - Query: AVG(retrieval_relevance) by hour (trending)
     - Query: P50/P95 latency per agent type (by date range)
     - Query: Top 10 error reasons (by frequency)
     - Query: Success rate over time (with date filtering)
     - Test queries via Pinot UI or `curl` to broker endpoint

4. **Add Grafana with evaluation dashboards**
   - [ ] Grafana Deployment in K8s
   - [ ] Persistent volume for dashboards
   - [ ] Add Prometheus datasource (http://prometheus:9090)
   - [ ] Add PostgreSQL datasource (for real-time OLTP queries)
   - [ ] Add Pinot datasource (for analytical OLAP queries)
   - [ ] Create 5 dashboards:
     - **RAG Evaluation** (uses Pinot OLAP): Retrieval relevance/coverage over time (hourly trends), latency p50/p95, top failure modes, heatmaps
     - **Agent Evaluation** (uses Pinot OLAP): Success rate per agent type (daily trending), quality score distribution, error breakdown (pie chart)
     - **Infrastructure** (uses Prometheus): Kafka lag, Flink parallelism, Pod CPU/Memory, Pinot query latency
     - **Pipeline Health** (uses both): Real-time event lag (PostgreSQL), end-to-end latency (Pinot), throughput (JDs processed/hour)
     - **Business** (uses Pinot OLAP): Applications submitted/day (bar chart), score distribution, cost per application, conversion rate trends

5. **Add Evaluation-based Alerting**
   - [ ] PrometheusRule CRD or alerting.rules in ConfigMap
   - [ ] Evaluation alerts:
     - `RAGRetrievalRelevance < 0.6` (5-min window) → warn (retrieved docs not relevant)
     - `RAGRetrievalCoverage < 0.5` (5-min window) → warn (docs don't cover JD)
     - `AgentSuccessRate < 90%` (1-hour window) → page oncall (agent degradation)
     - `AgentQualityScore < 0.7` (hourly) → investigate
   - [ ] Infrastructure alerts:
     - `AgentFailureRate > 5%` → page oncall
     - `KafkaConsumerLag > 10000` → warn
     - `FlinkTaskFailures > 0` → alert
   - [ ] Alertmanager for routing (email, Slack, etc.)

6. **Add Finops (Financial Operations) Monitoring**
   - [ ] Add cost tracking to events:
     - Each agent publishes: `llm_tokens_used`, `llm_cost_usd` (based on Claude pricing)
     - Each Flink job publishes: `compute_cost_usd` (estimated from task count + duration)
     - Storage cost tracking: S3/Pinot storage size → monthly cost estimate
   - [ ] Create Pinot table: `cost_metrics`
     - Columns: timestamp, agent_type, llm_tokens, llm_cost, compute_cost, total_cost_per_run
     - Real-time ingestion from Kafka topic `cost-events`
   - [ ] Add Grafana finops dashboard:
     - **Cost Breakdown**: pie chart (LLM % vs infrastructure % vs storage %)
     - **Cost Trends**: daily/weekly spending (bar chart, cumulative line)
     - **Cost per Application**: average cost to process one JD + application
     - **Cost per Agent**: which agents are most expensive?
     - **ROI**: cost per successful application vs. total applications
     - **Projections**: if current rate continues, monthly spend estimate
   - [ ] Finops alerts:
     - `DailySpendingExceeded(budget)` → warn if daily spend > $X
     - `CostPerApplicationAnomalous` → alert if cost/app spikes 50%+
     - `ExpensiveAgentRuntime` → warn if single run costs > $Y

7. **Add evaluation debugging/replay tools**
   - [ ] Query builder: filter evaluation results by date range, agent type, JD source
   - [ ] Replay pipeline: re-run evaluation on past agent runs
   - [ ] Export evaluations: download evaluation dataset for offline analysis (Python notebook)
   - [ ] Cost analyzer: which JD sources cost most? which agents waste the most?

8. **Verify**
   - Access Grafana: `kubectl port-forward -n agentos-dev svc/grafana 3000:3000`
   - Login: admin / admin
   - Check all 6 dashboards populate with real evaluation + finops data:
     - RAG Evaluation, Agent Evaluation, Infrastructure, Pipeline, Business, **Finops**
   - Run queries:
     - `SELECT avg(retrieval_relevance) FROM rag_evaluation_results WHERE created_at > now() - interval '1 hour';` (evaluation)
     - `SELECT sum(llm_cost) FROM cost_metrics WHERE timestamp > now() - 86400000;` (daily spend)
     - `SELECT avg(total_cost_per_run) FROM cost_metrics;` (avg cost per run)
   - Trigger evaluation alert → verify notification
   - Trigger cost alert (daily spend exceeds budget) → verify notification

---

## Phase 5: MLOps (MLflow + Evaluation-Driven Retraining)
**Timeline:** 3-4 weeks  
**Learning:** Model tracking, experiment management, reproducibility, evaluation-driven governance  
**Deliverable:** Full MLOps setup to track scoring agent performance + automated retraining based on evaluation metrics

### Checklist

1. **Add MLflow tracking server**
   - [ ] MLflow Deployment in K8s
   - [ ] Backend: PostgreSQL (tracking DB)
   - [ ] Artifact store: MinIO (s3-compatible)
   - [ ] Service exposed on port 5000
   - [ ] Test: `mlflow ui` → http://localhost:5000

2. **Instrument scoring agent for MLflow**
   - [ ] In `backend/agents/src/agentos_agents/generator/agent.py`:
     - Log params: model_name, temperature, max_tokens, retrieval_context_length
     - Log metrics: confidence_score, answer_length, citation_count, retrieved_doc_quality
     - Log artifacts: generated_answer, retrieved_docs (JSON)
   - [ ] Each run creates experiment in MLflow
   - [ ] Link evaluation metrics: pull RAG relevance + coverage scores from PostgreSQL
   - [ ] Verify: MLflow UI shows experiments + runs + linked evaluation data

3. **Add model registry**
   - [ ] Wrap scoring model in MLflow Model wrapper
   - [ ] Register versions: v1, v2, v3...
   - [ ] Transition versions: Staging → Production
   - [ ] Signature: input schema (JD, candidate) → output schema (confidence, rationale)
   - [ ] Store evaluation baseline for each version in model metadata

4. **Create evaluation-driven retraining pipeline**
   - [ ] Weekly batch job (K8s CronJob):
     - Trigger: IF (avg RAG relevance < 0.65 OR agent success rate < 85%) over past 7 days
     - Read: Parquet files from **Data Lake (S3)** for past 7-30 days
       - Path: `s3://agentos-evaluation-data/year=2025/month=01/day=15/`
       - Format: Parquet (columnar, efficient for ML pipelines)
     - Sample: 1000 recent scoring events with evaluation metrics
     - Prepare: convert to training format, include relevance/coverage as features
     - Train: new scoring model using evaluation metrics as ground truth
     - Evaluate: compare metrics vs. production model (confidence accuracy, latency)
     - If better: register new version + transition to Staging in model registry
     - If worse: investigate and alert (possible data quality issue)
   - [ ] Pipeline logs all metrics to MLflow for reproducibility

5. **Add evaluation-based governance + monitoring**
   - [ ] MLflow Model Registry view: version history + evaluation metrics per version
   - [ ] Grafana dashboard: Model metrics over time
     - Average confidence per model version
     - Model prediction latency
     - Retraining trigger conditions (RAG relevance, success rate)
     - Retraining success rate + frequency
     - Model A/B test results (if running canary deployment)
   - [ ] Alert: Model performance degradation > 5% (tied to evaluation metrics)
   - [ ] Audit trail: MLflow experiments linked to git commits + evaluation data
   - [ ] Validation gate: new model must match or exceed baseline evaluation metrics before promotion to Production

6. **Add canary deployment (optional advanced)**
   - [ ] Deploy new model version to 10% of traffic first
   - [ ] Monitor evaluation metrics: compare old vs. new model
   - [ ] If metrics improve → ramp to 100%
   - [ ] If metrics degrade → rollback to previous version

7. **Verify**
   - Run scoring agent 200+ times → MLflow shows 200+ runs with evaluation data
   - Check model registry: staging + production versions with evaluation baselines
   - Trigger retraining condition (lower RAG relevance scores) → watch job run
   - Verify new model registered with better evaluation metrics
   - Check Grafana: model version timeline with retraining events + evaluation trends

---

## Recommended Sequence

**Month 1:** Phase 1 + Phase 2 (Extended)
- Get agent pipeline solid (1 week)
- Add Kafka + Flink for event streaming (2 weeks)
- **Add OLTP/OLAP/Data Lake** (2 weeks)
  - PostgreSQL for transactional data (OLTP)
  - Pinot for analytics (OLAP)
  - S3 for raw event archive (Data Lake)

**Month 2:** Phase 3 + Phase 4
- Move all services to K8s (2 weeks)
- Add Prometheus + Grafana with both PostgreSQL + Pinot datasources (2 weeks)
- Get full observability (dashboards querying OLTP + OLAP)

**Month 3:** Phase 5
- Add MLflow (1 week)
- Instrument scoring agent (1 week)
- Build retraining pipeline reading from data lake (1 week)

---

## Key Learning Concepts by Phase

| Phase | Concepts | Technologies |
|-------|----------|---------------|
| 1 | Event-driven design, async messaging, error handling | Python, Pydantic, Redis |
| 2 | Message brokers, RAG + agent evaluation, OLTP/OLAP/Data Lake, stateful processing, windowing | Kafka, Flink/Dataflow, PostgreSQL (OLTP), Pinot (OLAP), S3/Parquet (Data Lake) |
| 3 | Container orchestration, StatefulSets, resource management, persistent storage | K8s, StatefulSets, Deployments, PVCs |
| 4 | Real-time + analytical dashboards, dual-datasource queries, cost tracking, alert design, finops | Prometheus, Grafana (PostgreSQL + Pinot datasources), evaluation + cost monitoring, alerting |
| 5 | Model governance, evaluation-driven retraining, data lake ML pipelines, reproducibility | MLflow, versioning, registries, Parquet data pipelines |

---

## Files You'll Create/Modify

### Phase 1
- `backend/agents/src/agentos_agents/common/publisher.py` (add event publishing)
- `backend/agents/src/agentos_agents/common/topics.py` (topic definitions)
- `backend/agents/tests/test_e2e.py` (full pipeline test)

### Phase 2
- `docker-compose.yml` (add Kafka + Zookeeper + Flink + Pinot)
- `backend/agents/src/agentos_agents/retriever/evaluator.py` (RAG evaluation logic)
- `backend/agents/src/agentos_agents/common/evaluator.py` (agent evaluation logic)
- `backend/agents/flink/` (new Maven project)
- `backend/agents/flink/src/main/java/com/agentos/AggregateAgentMetrics.java`
- `backend/agents/flink/src/main/java/com/agentos/AggregateRAGEvaluation.java`
- `backend/agents/flink/src/main/java/com/agentos/AggregateAgentEvaluation.java`
- `backend/agents/flink/src/main/java/com/agentos/ArchiveToDataLake.java` (S3 sink)
- `Makefile` (add Flink build targets)
- `backend/api/migrations/` (add tables: rag_evaluation_results, agent_evaluation_results, agent_runs)
- `pinot-config/rag_evaluation_metrics_table.json` (Pinot table schema)
- `pinot-config/agent_evaluation_metrics_table.json` (Pinot table schema)
- `tools/create_pinot_tables.sh` (schema initialization)

### Phase 3
- `k8s/namespace.yaml`
- `k8s/kafka-statefulset.yaml`
- `k8s/zookeeper-deployment.yaml`
- `k8s/pinot-controller-statefulset.yaml`
- `k8s/pinot-broker-deployment.yaml`
- `k8s/pinot-server-statefulset.yaml`
- `k8s/flink-deployment.yaml`
- `k8s/api-deployment.yaml`
- `k8s/agents-deployment.yaml`
- `k8s/storage-classes.yaml` (for PostgreSQL + Pinot PVCs)
- `helm/Chart.yaml` (optional but recommended)

### Phase 4
- `k8s/prometheus-deployment.yaml`
- `k8s/prometheus-config.yaml`
- `k8s/prometheus-rules.yaml` (evaluation + infrastructure + finops alert rules)
- `k8s/grafana-deployment.yaml`
- `k8s/grafana-datasources/` (PostgreSQL, Pinot, Prometheus datasource configs)
- `k8s/grafana-dashboards/` (6 dashboards: RAG Eval, Agent Eval, Infrastructure, Pipeline, Business, **Finops**)
- `k8s/alertmanager-deployment.yaml`
- `backend/api/metrics/` (Go Prometheus middleware)
- `backend/agents/metrics.py` (Python Prometheus client)
- `backend/agents/src/agentos_agents/common/prometheus_exporter.py` (evaluation metrics export)
- `backend/agents/src/agentos_agents/common/cost_tracker.py` (LLM cost + compute cost tracking)
- `backend/agents/flink/CostAggregation.java` (Flink job for cost aggregations)
- `pinot-config/cost_metrics_table.json` (Pinot cost metrics table schema)
- `tools/pinot_query_builder.py` (PQL query builder for Grafana)
- `tools/evaluation_query_builder.py` (SQL query builder for PostgreSQL in Grafana)
- `tools/cost_analyzer.py` (analyze cost trends, cost per agent, cost per JD source)
- `tools/replay_evaluation.py` (script to re-run evaluation on historical data from data lake)

### Phase 5
- `k8s/mlflow-deployment.yaml`
- `backend/agents/src/agentos_agents/generator/mlflow_tracking.py` (MLflow instrumentation)
- `backend/agents/flink/EvaluationDrivenRetraining.java` (evaluation-triggered retraining job)
- `backend/agents/src/agentos_agents/filler/evaluation_based_training.py` (training with evaluation metrics as labels)
- `k8s/retraining-cronjob.yaml` (weekly trigger)
- `tools/validate_model_promotion.py` (gate for model registry promotion)
- `k8s/grafana-dashboards/model-metrics.yaml` (model version + retraining dashboard)

---

## Success Criteria by Phase

- **Phase 1:** `make test-e2e` passes, all agents complete, events in Redis, agent outputs are correct

- **Phase 2:** 
  - Kafka topics populated with events
  - Flink jobs running, RAG evaluation scores flowing (0.0-1.0)
  - Agent evaluation metrics in PostgreSQL
  - **OLTP (PostgreSQL)**: evaluation_results tables populated with fresh data
  - **OLAP (Pinot)**: Pinot tables created, queries return aggregated metrics (e.g., AVG(retrieval_relevance))
  - **Data Lake (S3)**: Parquet files in S3 partitioned by date/hour, verifiable via `aws s3 ls`
  - All three layers (OLTP/OLAP/Data Lake) receiving data in parallel

- **Phase 3:** All services running in K8s (API, agents, Kafka, Flink, PostgreSQL, Pinot), accessible via kubectl port-forward, persistent volumes working, S3 integration working

- **Phase 4:** Grafana dashboards (6 total) populated with real evaluation + finops data (from PostgreSQL + Pinot), RAG relevance/coverage visible, agent success rates tracked, **cost per application tracked**, evaluation + cost alerts fire correctly, OLAP queries performant (<1s)

- **Phase 5:** MLflow tracks scoring experiments, model registry has versions, retraining runs weekly based on evaluation metrics from data lake, model performance trends visible in Grafana
