# Final Human Acceptance & Verification Report

**Project Title**: Telco Customer Churn Prediction — Production-Grade MLOps Platform
**Phase**: Phase 20 — Final Documentation, Verification, Cost & Teardown
**Date**: 2026-08-17
**Author**: MLOps Engineering Team

---

## 1. Executive Summary & Architecture Overview

The Telco Customer Churn MLOps platform is a complete, production-grade machine learning system engineering lifecycle built to predict telecommunication customer churn, detect data/concept drift, and automate continuous integration, deployment, and retraining.

Following initial completion, an independent final technical audit across all 20 phases identified two integration defects (provenance hash workspace isolation and Kubernetes drift CronJob volume mount persistence). Both defects were remediated and re-verified end-to-end across the full 88-test suite and container/pod lifecycle runs.

### Key Architecture Components:
- **Local Kubernetes Cluster**: Single-node Minikube cluster executing containerized FastAPI services, PVC storage mounts (`telco-models-pvc`, `telco-mlflow-pvc`), and Prometheus/Grafana telemetry.
- **Continuous Integration / Continuous Deployment**: Jenkins LTS running in a containerized Docker runtime with pipeline stages for linting, testing, ingestion, validation, feature engineering, model training, evaluation, Section 9 promotion gating, Docker multi-stage builds, and Kubernetes rollouts.
- **Model Lifecycle & Registry**: 5-fold Stratified Cross-Validation training across XGBoost and Logistic Regression candidates, optimal decision threshold optimization along the Precision-Recall curve ($\approx 0.3254$, operational F1 = $0.6416$), and local SQLite-backed MLflow Model Registry (`sqlite:///mlflow.db`).
- **Cloud Image Registry**: AWS Elastic Container Registry (ECR) repository (`telco-churn-api` in `ap-south-1`) with immutable git-SHA digest tags.
- **Inference & Security**: FastAPI serving REST endpoints (`POST /predict`, `GET /health`, `GET /metrics`), API Key authentication (`X-API-Key`), SlowAPI rate limiting (60 req/min), CORS headers, and non-PII structured JSON logging.
- **Observability & Closed-Loop Retraining**: Prometheus metrics instrumentation, custom Grafana dashboards, Evidently AI drift monitoring with 3-consecutive-window dampening triggers via Jenkins REST API.

---

## 2. Final Repository Directory Structure

```
├── .dockerignore
├── .dvc/
├── .env.example
├── .flake8
├── .gitignore
├── .pre-commit-config.yaml
├── Dockerfile
├── Jenkinsfile
├── PROJECT_PROGRESS.md
├── README.md
├── data/
│   ├── raw/ (telco_churn.csv, .gitkeep)
│   └── processed/ (train.csv, test.csv, .gitignore)
├── docker-compose.integration.yml
├── docker-compose.yml
├── docs/
│   ├── COST_REPORT.md
│   ├── FINAL_ACCEPTANCE_REPORT.md
│   ├── TEARDOWN_GUIDE.md
│   ├── adr/
│   │   ├── README.md (ADR Catalog)
│   │   ├── 0001-use-tasks-py-over-makefile.md
│   │   ├── 0002-configure-pydantic-mypy-plugin.md
│   │   ├── 0003-model-training-and-hyperparameter-search-strategy.md
│   │   ├── 0004-model-evaluation-threshold-optimization-and-calibration.md
│   │   ├── 0005-mlflow-tracking-and-model-promotion-policy.md
│   │   └── 0006-end-to-end-integration-testing-and-isolation.md
│   └── diagrams/
│       ├── architecture.md
│       └── sequence.md
├── infra/
│   ├── aws/ (create_ecr_repo.ps1, push_to_ecr.ps1)
│   ├── docker/ (Dockerfile.integration)
│   ├── jenkins/ (Dockerfile, setup-jobs.groovy)
│   ├── k8s/ (configmap, secret, pvc-models, pvc-mlflow, deployment, service, drift-cronjob, hpa, pdb)
│   └── monitoring/ (prometheus-configmap, prometheus-deployment, prometheus-service, grafana-deployment, grafana-service, grafana-dashboard.json)
├── models/
│   ├── best_model.joblib
│   ├── decision_threshold.json
│   ├── feature_pipeline.joblib
│   ├── feature_schema.json
│   ├── promotion_policy.json
│   └── training_metadata.json
├── pyproject.toml
├── reports/
│   ├── calibration_metrics.json
│   ├── classification_report.json
│   ├── cv_results.csv
│   ├── error_analysis.csv
│   ├── evaluation_metrics.json
│   ├── feature_importance.csv
│   ├── training_metrics.json
│   └── plots/ (confusion_matrix, feature_importance, roc_curve, precision_recall_curve, calibration_curve, prediction_distribution)
├── scripts/ (demo scripts for logging, validation, features, drift, trigger)
├── src/
│   ├── api/ (app.py, routes.py, schemas.py, security.py, metrics.py)
│   ├── core/ (config.py, logging.py)
│   ├── data/ (ingestion.py, validation.py, features.py)
│   ├── inference/ (service.py)
│   ├── monitoring/ (drift.py, state.py, jenkins_trigger.py)
│   └── training/ (train.py, evaluate.py, promotion.py)
├── tasks.py
└── tests/
    ├── integration/ (test_end_to_end.py)
    └── unit/ (test_config, test_logging, test_ingestion, test_validation, test_features, test_training, test_evaluation, test_promotion, test_api, test_docker, test_metrics, test_drift, test_jenkins_trigger)
```

---

## 3. Reference to Key Artifacts & Documentation

- **System Architecture**: Detailed in [`docs/diagrams/architecture.md`](file:///c:/Users/AAKASH.S.S/OneDrive/Desktop/Pipelines/docs/diagrams/architecture.md)
- **Closed-Loop Retraining Flow**: Detailed in [`docs/diagrams/sequence.md`](file:///c:/Users/AAKASH.S.S/OneDrive/Desktop/Pipelines/docs/diagrams/sequence.md)
- **Architecture Decision Records**: Cataloged in [`docs/adr/README.md`](file:///c:/Users/AAKASH.S.S/OneDrive/Desktop/Pipelines/docs/adr/README.md)
- **AWS Cost Report**: Documented in [`docs/COST_REPORT.md`](file:///c:/Users/AAKASH.S.S/OneDrive/Desktop/Pipelines/docs/COST_REPORT.md)
- **Infrastructure Teardown Guide**: Documented in [`docs/TEARDOWN_GUIDE.md`](file:///c:/Users/AAKASH.S.S/OneDrive/Desktop/Pipelines/docs/TEARDOWN_GUIDE.md)

---

## 4. Known System Limitations

The following engineering limitations exist by design or reflect the scope of local development and single-node orchestration:

1. **Synthetic Current-Window Drift Detection**:
   - In offline development and automated CI testing, the current evaluation window is simulated using synthetic perturbation (`tenure * 0.1`, high `MonthlyCharges`) to deterministically trigger drift calculations. In a live multi-tenant enterprise system, live prediction payloads are streamed from real Kafka/Kinesis message queues.
2. **Local File-State Monitoring Persistence**:
   - Drift window counters and history are persisted locally to `reports/monitoring_state.json` via file locks and PVC mounts. In high-availability multi-replica cluster environments, drift state should be externalized to Redis or PostgreSQL to coordinate state across distributed workers.
3. **Grafana Development Credentials**:
   - The Grafana deployment in Minikube uses `admin`/`admin` basic auth for rapid local debugging. In enterprise environments, this must be integrated with OAuth2 / Okta / Azure AD SSO or HashiCorp Vault.
4. **Single-Node Minikube Runtime**:
   - Minikube operates as a single-node VM/container with `hostPath` storage. High availability, cross-availability-zone failover, and managed EBS/EFS CSI volume drivers are unavailable.
5. **Local SQLite MLflow Tracking**:
   - MLflow Model Registry uses a local SQLite database (`sqlite:///mlflow.db`) with file-backed artifact storage (`mlruns/`). SQLite does not support concurrent write transactions from distributed worker nodes.
6. **Local Development vs. Managed Cloud Kubernetes**:
   - Kubernetes services are exposed via `NodePort` rather than cloud `LoadBalancer` or Ingress controllers with TLS termination (e.g. AWS ALB Controller + Route53 + ACM).

---

## 5. Master Contract Section 13: Line-by-Line Acceptance Audit

The following matrix audits all acceptance criteria across every functional tier and lifecycle phase of the project:

| # | Master Contract Section / Criterion | Implementation & Verification Evidence | Status |
|---|---|---|---|
| **1** | **Section 1: Repository Architecture & Task Automation** | Standardized Python `tasks.py` (`install`, `lint`, `format`, `test`, `clean`), zero `make` dependency. | **PASS** |
| **2** | **Section 2: Configuration Management & Type Safety** | Pydantic v2 `BaseSettings` resolving `.env`, strict type hints, `pydantic.mypy` plugin configured with zero `# type: ignore` suppressions. | **PASS** |
| **3** | **Section 3: Structured Logging & Observability Baseline** | Structured JSON logging via standard library (`get_logger`), context binding, non-PII sanitization, zero raw `print()` statements in source modules. | **PASS** |
| **4** | **Section 4: Data Ingestion Pipeline & Versioning** | `src/data/ingestion.py` fetches raw Telco Churn CSV, verifies SHA-256 checksums, integrates with DVC (`data/processed.dvc`). | **PASS** |
| **5** | **Section 5: Schema Validation & Anomaly Detection** | `src/data/validation.py` validates 21 raw columns against schema rules, detects blank strings in `TotalCharges`, catches type anomalies with comprehensive validation reports. | **PASS** |
| **6** | **Section 6: Feature Pipeline & Anti-Leakage Guard** | `src/data/features.py` Scikit-Learn `ColumnTransformer` with `TotalChargesImputer` and `DerivedFeatureEngineer`, fit strictly on `X_train`, serialized to `models/feature_pipeline.joblib`. | **PASS** |
| **7** | **Section 7: Deterministic Model Training & CV** | `src/training/train.py` executes 5-fold stratified CV across XGBoost and Logistic Regression with `random_state=42`. Training is reproducible in hyperparameters, CV scores, metrics, and predictions under the fixed seed; serialized model files are not required to be byte-identical. Outputs `reports/training_metrics.json` and `reports/cv_results.csv`. | **PASS** |
| **8** | **Section 8: Model Evaluation & Threshold Tuning** | `src/training/evaluate.py` performs Precision-Recall threshold sweep ($\approx 0.3254$), reports operational F1 ($0.6416$), computes Brier score calibration, generates 6 visualization plots in `reports/plots/`. | **PASS** |
| **9** | **Section 9: MLflow Registry & Promotion Policy** | `src/training/promotion.py` operationalizes `models/promotion_policy.json` ($\Delta \text{F1} \ge 0.01, \Delta \text{Prec} \ge -0.02, \Delta \text{Rec} \ge 0$), logs metrics and artifacts to `sqlite:///mlflow.db`, auto-promotes initial bootstrap version 1 to Production. | **PASS** |
| **10** | **Section 10: Drift Monitoring & Automated Trigger** | `src/monitoring/drift.py` evaluates PSI and Wasserstein drift using Evidently, maintains 3-consecutive-window dampening in `state.py`, mounts persistent `/app/reports` storage, and triggers Jenkins via `jenkins_trigger.py`. | **PASS** |
| **11** | **Section 11: FastAPI Serving & Security Baseline** | `src/api/app.py` exposes `/predict`, `/health/liveness`, `/health/readiness`, `/metrics`, enforces `X-API-Key` auth, SlowAPI rate limiting (60/min), and CORS headers. | **PASS** |
| **12** | **Section 12: Docker Multi-Stage Containerization** | Multi-stage `Dockerfile` (`python:3.12-slim`), non-root `appuser` (UID 10001), Docker `HEALTHCHECK`, digest pinned in CI. | **PASS** |
| **13** | **Section 12b: AWS ECR Provisioning & Push Pipeline** | `infra/aws/push_to_ecr.ps1` pushed 9 image tags to ECR `telco-churn-api` with manifest digests verified. Teardown deletion verified via `RepositoryNotFoundException`. | **PASS** |
| **14** | **Section 13: Kubernetes Manifests & Orchestration** | Manifests in `infra/k8s/` (`deployment`, `service`, `configmap`, `secret`, `pvc`, `hpa`, `pdb`, `drift-cronjob`) deployed and verified on Minikube. Teardown verified via `minikube delete`. | **PASS** |
| **15** | **Section 14: Jenkins CI/CD Declarative Pipeline** | `Jenkinsfile` runs lint, unit tests, integration tests, ingestion, validation, features, training, evaluation, promotion gate, Docker build, and K8s rollout. | **PASS** |
| **16** | **Section 15: Prometheus Telemetry Instrumentation** | Prometheus scrapes FastAPI `/metrics` (`telco_predictions_total`, latency histogram, drift gauges). | **PASS** |
| **17** | **Section 16: Grafana Dashboards & Visualizations** | Custom dashboard auto-provisioned in Grafana (`http://<minikube-ip>:30091`) displaying real-time latency, throughput, and model health. | **PASS** |
| **18** | **Section 18: Closed-Loop Automated Retraining** | Retraining webhook triggers Jenkins job with parameters, re-evaluates promotion gate, and conditionally redeploys to Minikube. | **PASS** |
| **19** | **Section 19: End-to-End Hermetic Integration Suite** | `tests/integration/test_end_to_end.py` runs all 11 lifecycle stages end-to-end in isolated tmp workspace. Provenance pipeline SHA-256 calculated from effective pipeline path. Clean 100% pass across all 88 unit and integration tests. | **PASS** |
| **20** | **Section 20: Cost Reporting, Teardown & Documentation** | `README.md`, `COST_REPORT.md` (exact CLI error output, ₹2 INR pre-auth, ₹15k AutoPay ceiling, manual console guide), `TEARDOWN_GUIDE.md` (executed and verified). | **PASS** |

---

## 6. Independent Final Audit & Confirmed Defect Remediations

An independent technical audit conducted across all 20 phases identified 2 confirmed defects requiring remediation:

### Defect 1: Feature Pipeline Provenance Hash Workspace Isolation
- **Component**: `src/training/train.py` & `tests/integration/test_end_to_end.py`
- **Root Cause**: `train_candidate_models()` computed `feature_pipeline_sha256` using the static default `settings.FEATURE_PIPELINE_PATH` regardless of whether callers passed custom isolated paths. In hermetic integration test environments (`tmp_path`), this caused a hash mismatch against the dynamically fitted pipeline.
- **Remediation**: Added `pipeline_path: Optional[Path] = None` to `train_candidate_models()`, defaulting to `settings.FEATURE_PIPELINE_PATH` for production backwards compatibility. Used the effective `pipe_path` when computing `calculate_file_sha256(pipe_path)`. Updated `tests/integration/test_end_to_end.py` to pass `pipeline_path=ws["feature_pipeline"]`.
- **Verification**: `pytest tests/integration/test_end_to_end.py -v` passed cleanly with 0 provenance mismatches.

### Defect 2: Drift Monitoring State Persistence in Kubernetes CronJob
- **Component**: `infra/k8s/drift-cronjob.yaml`
- **Root Cause**: `src/monitoring/drift.py` persists the 3-consecutive-window dampening state to `/app/reports/monitoring_state.json`. In the original `drift-cronjob.yaml`, only `/app/models` (readOnly), `/app/mlruns`, and `/app/mlflow.db` were mounted; `/app/reports` was unmounted, causing ephemeral pods to discard window counts between scheduled runs.
- **Remediation**: Added volume mount for `/app/reports` in `infra/k8s/drift-cronjob.yaml` utilizing `telco-mlflow-pvc` with `subPath: reports` (`readOnly: false`).
- **Verification**: Executed multi-pod lifecycle simulation demonstrating state persistence across independent container executions: Run 1 recorded `consecutive_drift_windows = 1` and persisted to volume; Run 2 restored `consecutive_drift_windows = 1` from the mounted persistent storage and incremented count to `2`.

---

## 7. Remaining Risks & Operational Recommendations

1. **ECR Token Expiry in K8s Secret**:
   - AWS ECR authorization tokens expire after 12 hours. For long-running clusters using Option B (ECR pull secret), an automated CronJob or AWS IAM Roles for Service Accounts (IRSA on EKS) is recommended.
2. **Database Backup Strategy**:
   - Currently, `mlflow.db` resides on a single PVC. For production deployment, configure automated EBS snapshots or migrate MLflow backend store to managed Amazon RDS PostgreSQL.
3. **Data Ingestion Volume Growth**:
   - As dataset sizes grow beyond millions of rows, transition feature preprocessing from in-memory Scikit-Learn pipelines to distributed PySpark / AWS Glue transformations.
