# 6. End-to-End Integration Testing Architecture and Isolation Contract

Date: 2026-08-17

## Status

Accepted

## Context

The Telco Customer Churn MLOps platform encompasses multiple decoupled subsystems spanning ingestion, schema validation, feature engineering, model training, evaluation, threshold tuning, MLflow model registry promotion, FastAPI serving, Prometheus metrics instrumentation, and drift monitoring.

While Phases 1–11 provide granular unit tests and Phase 18 proves live retrain-and-deploy loops against live Jenkins/Minikube infrastructure, CI gates require a fast, deterministic, end-to-end integration suite. This suite must exercise the real production functions and service endpoints together without incurring external cloud/cluster dependencies (AWS, ECR, EKS, Minikube) or risking contamination of the canonical production MLflow database, model registry, or DVC-tracked dataset artifacts.

## Decision

We implement a dedicated, hermetically isolated End-to-End Integration Test Suite (`tests/integration/test_end_to_end.py`) with the following architectural guarantees:

1. **Hermetic Workspace Isolation**:
   - All intermediate datasets (`data/raw/`, `data/processed/`), model artifacts (`models/`), evaluation/drift reports (`reports/`), and tracking databases are scoped strictly to ephemeral workspaces (`pytest tmp_path / integration_workspace`).
   - Canonical paths (`mlflow.db`, `models/`, `reports/`, `data/processed/`) are protected by assertion guards and remain 100% immutable throughout the run.

2. **Dedicated MLflow Registry & Tracking Store**:
   - Training, evaluation, promotion, and FastAPI inference load operations interact exclusively with a dedicated SQLite tracking store (`sqlite:///<tmp_path>/integration_mlflow.db`) and a dedicated registered model name (`telco-churn-integration-test`).
   - The candidate model is promoted to "Production" solely within the isolated integration registry, proving the promotion and registry-loading contract without touching the canonical Production model or run IDs.

3. **Fast, Deterministic CI Search Space (`n_iter=2`)**:
   - To keep integration runtimes under the CI target budget (< 1 minute), candidate hyperparameter search is parameterized to `n_iter=2` within the integration runner while preserving full cross-validation and evaluation logic.

4. **Real Component Contracts (No Mocks)**:
   - Exercises real production code paths across all 11 lifecycle stages:
     - `ingest_raw_data`
     - `validate_data`
     - `process_and_save_features`
     - `train_candidate_models`
     - `generate_evaluation_report`
     - `promote_model`
     - `prediction_service.load_production_model`
     - `/health/readiness`
     - `/predict`
     - `/metrics` (Prometheus gauge, counters, histogram, and counter incrementation)
     - `run_drift_pipeline` (synthetic shifted data detection with `trigger_retraining=False`)

5. **Docker Compose & Jenkins Integration**:
   - Encapsulated in `docker-compose.integration.yml` and `infra/docker/Dockerfile.integration`.
   - Added as an independent `Integration Test` stage in `Jenkinsfile` situated after unit tests and prior to canonical production validation and training stages.

## Consequences

### Positive
- **High Confidence**: Proves full pipeline compatibility across data, modeling, registry, API, metrics, and drift components in a single automated test run.
- **Strict Production Safety**: Zero risk of test runs promoting spurious models into the canonical production registry or corrupting production metrics/DVC state.
- **Fast Feedback Loop**: Executes in ~50 seconds, making it ideal as a mandatory blocking gate on every pull request and Jenkins build.
- **Zero External Infrastructure Dependency**: Runs completely offline without AWS, ECR, Minikube, or live Kubernetes clusters.

### Neutral / Trade-offs
- Model promotion is validated inside the temporary registry; live cluster promotion verification remains the responsibility of Phase 18 smoke tests.
- Requires maintaining `docker-compose.integration.yml` alongside the standard development compose configurations.
