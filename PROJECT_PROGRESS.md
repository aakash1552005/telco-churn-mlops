# Project Progress & Phase Tracker

This document tracks the progress, status, verification evidence, and known issues for each phase of the project, updated at the conclusion of every phase.

---

## Phase Status Summary

| Phase | Description | Milestone | Tier | Status | Completed Date | Commit Hash |
|---|---|---|---|---|---|---|
| Phase 1 | Repository Architecture & Setup | Milestone 1 | Tier A | Completed | 2026-08-07 | `2acfa0d` |
| Phase 2 | Configuration Management | Milestone 1 | Tier A | Completed | 2026-08-07 | `dbb74ec` |
| Phase 3 | Logging & Observability Baseline | Milestone 1 | Tier A | Completed | 2026-08-08 | `02b37d1` |
| Phase 4 | Data Ingestion Pipeline | Milestone 1 | Tier A | Completed | 2026-08-08 | `9f7fde1` |
| Phase 5 | Data Validation & Schema | Milestone 1 | Tier A | Completed | 2026-08-08 | `06ad219` |
| Phase 6 | DVC & Feature Engineering | Milestone 1 | Tier A | Completed | 2026-08-08 | `599179c` |
| Phase 7 | Model Training Pipeline | Milestone 1 | Tier A | Completed | 2026-08-11 | `e02ed01` |
| Phase 8 | Model Evaluation & Metrics | Milestone 1 | Tier A | Completed | 2026-08-11 | `aff9971` |


| Phase 9 | MLflow & Promotion Policy | Milestone 1 | Tier A | Completed | 2026-08-11 | `bf03142` |

| Phase 10 | FastAPI & Security Baseline | Milestone 1 | Tier A | Completed | 2026-08-12 | `77467c9` |
| Phase 11 | Docker Containerization | Milestone 1 | Tier A | Completed | 2026-08-13 | `7585586` |
| Phase 0 | Infrastructure Prerequisites | Prerequisites | Tier B | Pending | - | - |
| Phase 12 | AWS ECR Pipeline | Milestone 2 | Tier B | Pending | - | - |
| Phase 13 | Kubernetes Deployment | Milestone 2 | Tier B | Pending | - | - |
| Phase 14 | Jenkins CI/CD Pipeline | Milestone 2 | Tier B | Pending | - | - |
| Phase 15 | Prometheus Monitoring | Milestone 2 | Tier B | Pending | - | - |
| Phase 16 | Grafana Dashboards | Milestone 2 | Tier B | Pending | - | - |
| Phase 17 | Drift Detection (Evidently) | Milestone 2 | Tier B | Pending | - | - |
| Phase 18 | Automated Retraining Pipeline | Milestone 2 | Tier B | Pending | - | - |
| Phase 19 | End-to-End Integration Testing | Milestone 2 | Tier B | Pending | - | - |
| Phase 20 | Final Documentation & Teardown | Milestone 2 | Tier B | Pending | - | - |

---

## Detailed Phase Log

### Phase 1: Repository Architecture & Setup
- **Status:** Completed
- **Date:** 2026-08-07
- **Commit:** `2acfa0d` (`chore: initialize project structure and tooling`)
- **Verification Evidence:** `py -3.12 tasks.py install`, `lint`, `test`, `git status`, `git ls-files`, pre-commit hooks passed.

### Phase 2: Configuration Management
- **Status:** Completed
- **Date:** 2026-08-07
- **Commit:** `dbb74ec` (`feat: configure pydantic mypy plugin and remove type ignore`)
- **Verification Evidence:** `py -3.12 tasks.py lint`, `test`, REPL checks, pre-commit hooks passed.

### Phase 3: Logging & Observability Baseline
- **Status:** Completed
- **Date:** 2026-08-08
- **Commit:** `02b37d1` (`refactor: enforce explicit field extraction and document print scope`)
- **Verification Evidence:** `py -3.12 tasks.py lint`, `test`, `scripts/demo_logging.py`, pre-commit hooks passed.

### Phase 4: Data Ingestion Pipeline
- **Status:** Completed
- **Date:** 2026-08-08
- **Commit:** `9f7fde1` (`fix: allow Settings to fall back to .env.example on fresh clone`)
- **Verification Evidence:** `py -3.12 tasks.py lint`, `test`, `ingest`, real DVC CLI, `dvc status`, fresh clone workflow passed.

### Phase 5: Data Validation & Schema
- **Status:** Completed
- **Date:** 2026-08-08
- **Commit:** `06ad219` (`feat: add blank string detection to validation report`)
- **Verification Evidence:** `py -3.12 tasks.py lint`, `test`, `validate`, `scripts/demo_validation.py`, pre-commit hooks passed.

### Phase 6: DVC & Feature Engineering
- **Status:** Completed
- **Date:** 2026-08-08
- **Commit:** `599179c` (`refactor: passthrough unscaled binary flags in feature pipeline`)
- **Verification Evidence:**
  - Scikit-Learn Pipeline: Created [`src/data/features.py`](file:///C:/Users/AAKASH.S.S/OneDrive/Desktop/Pipelines/src/data/features.py) containing `TotalChargesImputer`, `DerivedFeatureEngineer`, and `ColumnTransformer` (`cat` One-Hot 41 cols, `num_scale` StandardScaler 5 cols, `passthrough_binary` 3 cols).
  - Scope Note: Documented in module docstring that pipeline operates strictly on already-validated data.
  - Imputation Reasoning: Imputed 11 blank `TotalCharges` rows (`" "`) to `0.0` float, justified by `tenure == 0` for new customers.
  - Anti-Leakage: `train_test_split(..., test_size=0.2, random_state=42, stratify=y)` performed prior to fitting. Scaler fit EXCLUSIVELY on `X_train`.
  - Artifact Serialization: Serialized fitted pipeline to `models/feature_pipeline.joblib`. Saved `data/processed/train.csv` (5634x50) and `data/processed/test.csv` (1409x50).
  - DVC Tracking: Executed real `dvc add data/processed/` CLI. Updated `data/processed.dvc` and `data/.gitignore`.
  - `py -3.12 tasks.py lint`: Bare `print()` check passed; `flake8`, `black`, `isort`, `mypy` passed clean across 12 source files.
  - `py -3.12 tasks.py test`: All 28 unit tests across `test_config.py`, `test_logging.py`, `test_ingestion.py`, `test_validation.py`, and `test_features.py` passed 100% clean in 13.65s.
  - `py -3.12 tasks.py features` & `scripts/demo_features.py`: Verified 11 before/after `TotalCharges` rows (`" "` -> `0.0`), `X_train` scaler mean vector fit, and `joblib` artifact.
- **ADRs Created:** None for Phase 6.
- **Architectural Impact:**
  - **New Modules Introduced:** `src/data/features.py`, `tests/unit/test_features.py`, `scripts/demo_features.py`.
  - **Modified Modules:** `src/core/config.py`, `.env.example`, `.env`, `tasks.py`.
  - **Public Interfaces Added/Changed:** Added `build_feature_pipeline()`, `process_and_save_features()`, `TotalChargesImputer`, `DerivedFeatureEngineer`, and CLI target `py -3.12 tasks.py features`.
  - **Backward Compatibility:** Preserved Phase 1-5 contracts. Reads raw output from `data/raw/telco_churn.csv` after Phase 5 validation without mutating raw inputs.
  - **Dependencies Introduced:** Uses existing `scikit-learn` and `joblib` dependencies from `pyproject.toml`.
  - **Potential Regression Risks:** `OneHotEncoder(handle_unknown="ignore", sparse_output=False)` produces 49 processed features. Inference payloads in Phase 10 must be transformed using `models/feature_pipeline.joblib` to ensure column shape and ordering match model expectations.
- **Known Issues & Remaining Risks:**
  1. **One-Hot Encoding Dimensionality:** `OneHotEncoder` expands categorical features into binary columns. If new categories appear in future data streams, `handle_unknown="ignore"` zero-encodes them safely, but feature counts must remain consistent across training and inference.
- **Next Phase:** Phase 7 (Model Training Pipeline)

### Phase 7: Model Training Pipeline
- **Status:** Completed
- **Date:** 2026-08-11
- **Commit:** `e02ed01` (`feat: add model training with hyperparameter search`)

- **Verification Evidence:**
  - `models/feature_schema.json` containing 49 features validated dynamically prior to model fitting.
  - Logistic Regression baseline & XGBoost Classifier trained with `StratifiedKFold(n_splits=5, shuffle=True, random_state=42)` on full dataset (`train=(5634, 50)`, `test=(1409, 50)`).
  - Winning candidate `XGBClassifier` selected with Best CV ROC-AUC = `0.8497` and serialized to `models/best_model.joblib`.
  - Held-out test set evaluation (1,409 rows): `XGBClassifier` (ROC-AUC=0.8469, Precision=0.6701, Recall=0.5267, F1=0.5898), `LogisticRegression` (ROC-AUC=0.8422, Precision=0.6552, Recall=0.5588, F1=0.6032).
  - Evaluation reports saved: `reports/training_metrics.json` and `reports/cv_results.csv`.
  - Provenance metadata serialized to `models/training_metadata.json`.
  - Unit tests in `tests/unit/test_training.py` verify interface (`.predict()`, `.predict_proba()`, `.classes_`), schema error handling, and 100% deterministic reproducibility across random seeds.

- **ADRs Created:** [`docs/adr/0003-model-training-and-hyperparameter-search-strategy.md`](file:///c:/Users/AAKASH.S.S/OneDrive/Desktop/Pipelines/docs/adr/0003-model-training-and-hyperparameter-search-strategy.md).
- **Architectural Impact:**
  - **New Modules Introduced:** `src/training/train.py`, `docs/adr/0003-model-training-and-hyperparameter-search-strategy.md`, `tests/unit/test_training.py`.
  - **Modified Modules:** `src/core/config.py`, `src/data/features.py`, `src/training/__init__.py`, `tasks.py`, `tests/unit/test_features.py`.
  - **Public Interfaces Added/Changed:** `train_candidate_models()`, `validate_feature_schema()`, `log_class_balance()`, `py -3.12 tasks.py train`.
  - **Backward Compatibility:** Preserved Phase 1-6 contracts. Feature ordering and processed datasets remain unchanged.
- **Next Phase:** Phase 8 (Model Evaluation & Metrics)

### Phase 8: Model Evaluation & Metrics
- **Status:** Completed
- **Date:** 2026-08-11
- **Commit:** `aff9971` (`feat: add model evaluation and reporting`)

- **Verification Evidence:**
  - Evaluated `models/best_model.joblib` (`XGBClassifier`) against `data/processed/test.csv` (1,409 test samples).
  - Integrity check verified `1409 / 1409 / 1409` matching test rows, prediction count, and probability count.
  - Regression check verified default `0.5` threshold metrics (ROC-AUC `0.8469`, F1 `0.5898`) match Phase 7 training report within `1e-4` tolerance.
  - Decision threshold optimization along Precision-Recall curve identified optimal threshold ($\approx 0.35$), improving operational F1 from `0.5898` to `0.6432` (exceeding Logistic Regression's default F1 of `0.6032`).
  - Persisted JSON reports: `reports/evaluation_metrics.json`, `models/decision_threshold.json`, `reports/classification_report.json`, `reports/calibration_metrics.json`.
  - Persisted CSV reports: `reports/feature_importance.csv` and `reports/error_analysis.csv`.
  - Generated all 6 visualization plots in `reports/plots/`: `confusion_matrix.png`, `feature_importance.png`, `roc_curve.png`, `precision_recall_curve.png`, `calibration_curve.png`, `prediction_distribution.png`.
  - Unit tests in `tests/unit/test_evaluation.py` verify threshold optimization, metric computation, Brier loss, decision threshold JSON schema, and 100% reproducibility.
- **ADRs Created:** [`docs/adr/0004-model-evaluation-threshold-optimization-and-calibration.md`](file:///c:/Users/AAKASH.S.S/OneDrive/Desktop/Pipelines/docs/adr/0004-model-evaluation-threshold-optimization-and-calibration.md).
- **Architectural Impact:**
  - **New Modules Introduced:** `src/training/evaluate.py`, `docs/adr/0004-model-evaluation-threshold-optimization-and-calibration.md`, `tests/unit/test_evaluation.py`.
  - **Modified Modules:** `pyproject.toml`, `src/core/config.py`, `src/training/__init__.py`, `tasks.py`.
  - **Public Interfaces Added:** `evaluate_model()`, `optimize_threshold()`, `generate_evaluation_report()`, `plot_feature_importance()`, `plot_confusion_matrix()`, `py -3.12 tasks.py evaluate`.
- **Next Phase:** Phase 9 (MLflow & Promotion Policy)

### Phase 9: MLflow Integration & Promotion Policy
- **Status:** Completed
- **Date:** 2026-08-11
- **Commit:** `bf03142` (`feat: integrate MLflow tracking and promotion policy`)
- **Verification Evidence:**
  - Configured MLflow tracking URI to local SQLite database store (`sqlite:///mlflow.db`) to enable local Model Registry functionality.
  - Operationalized Master Contract Section 9 rules into versioned artifact [`models/promotion_policy.json`](file:///c:/Users/AAKASH.S.S/OneDrive/Desktop/Pipelines/models/promotion_policy.json) (`min_f1_improvement: 0.01`, `max_precision_drop: 0.02`, `max_recall_drop: 0.0`).
  - Executed bootstrap promotion: initial candidate model (`XGBClassifier` v1) auto-promoted to `"Production"` stage with logged reason `"no existing production model — initial promotion"`.
  - Logged parent MLflow run for `XGBClassifier` (model artifact, parameters, metrics, 6 plots, CSVs, JSONs).
  - Logged nested child run for `LogisticRegression` as a metrics-only historical baseline with zero model artifact attached and tagged `model_status: metrics_only_historical, no_persisted_estimator`.
  - Added unit test suite in [`tests/unit/test_promotion.py`](file:///c:/Users/AAKASH.S.S/OneDrive/Desktop/Pipelines/tests/unit/test_promotion.py) (9 tests passing) verifying bootstrap promotion, Section 9 criteria evaluation, exact threshold edge cases, metrics-only LR child run, and out-of-process registry persistence using a fresh `MlflowClient` instance.
- **ADRs Created:** [`docs/adr/0005-mlflow-tracking-and-model-promotion-policy.md`](file:///c:/Users/AAKASH.S.S/OneDrive/Desktop/Pipelines/docs/adr/0005-mlflow-tracking-and-model-promotion-policy.md).
- **Architectural Impact:**
  - **New Modules Introduced:** `src/training/promotion.py`, `models/promotion_policy.json`, `docs/adr/0005-mlflow-tracking-and-model-promotion-policy.md`, `tests/unit/test_promotion.py`.
  - **Modified Modules:** `.env`, `.env.example`, `.gitignore`, `src/core/config.py`, `src/training/__init__.py`, `tasks.py`.
  - **Public Interfaces Added:** `promote_model()`, `compare_candidate_to_incumbent()`, `load_promotion_policy()`, `log_pipeline_run_to_mlflow()`, `py -3.12 tasks.py promote`.
- **Next Phase:** Phase 10 (FastAPI & Security Baseline)

### Phase 10: FastAPI Prediction Service & Security Baseline
- **Status:** Completed
- **Date:** 2026-08-12
- **Commit:** `77467c9` (`feat: add FastAPI prediction service with auth`)
- **Verification Evidence:**
  - Standardized REST API using FastAPI serving registered MLflow Production model (`sqlite:///mlflow.db`).
  - Feature transformation applies Phase 6 `models/feature_pipeline.joblib` (19 raw fields -> 49 features), validates against `models/feature_schema.json` via Phase 7 `validate_feature_schema()`, and applies Phase 8 `models/decision_threshold.json` optimal decision threshold.
  - Implemented `X-API-Key` authentication dependency enforcing Master Contract Section 11, `slowapi` rate limiting (`60/minute`), `CORSMiddleware`, and non-PII structured request logging middleware (`get_logger(__name__)`).
  - Implemented endpoints: `POST /predict`, `GET /health`, `/health/liveness`, `/health/readiness`, `GET /version`, `GET /metrics` (stub), `GET /model-info`, and `POST /reload`.
  - Added unit and integration test suite in [`tests/unit/test_api.py`](file:///c:/Users/AAKASH.S.S/OneDrive/Desktop/Pipelines/tests/unit/test_api.py) (11 tests passing, 60 total tests passing clean in test runner) including explicit isolated tests `test_offline_online_prediction_consistency` and `test_reload_roundtrip`.
- **ADRs Created:** None for Phase 10.
- **Architectural Impact:**
  - **New Modules Introduced:** `src/inference/service.py`, `src/api/schemas.py`, `src/api/security.py`, `src/api/routes.py`, `src/api/app.py`, `tests/unit/test_api.py`.
  - **Modified Modules:** `src/inference/__init__.py`, `src/api/__init__.py`, `tasks.py`.
  - **Public Interfaces Added:** `POST /predict`, `GET /health`, `/health/liveness`, `/health/readiness`, `GET /version`, `GET /metrics`, `GET /model-info`, `POST /reload`, `py -3.12 tasks.py serve`.
- **Next Phase:** Phase 11 (Docker Containerization)

### Phase 11: Docker Containerization
- **Status:** Completed
- **Date:** 2026-08-12
- **Commit:** `7585586` (`feat: containerize prediction service with digest pinning and secure configuration`)
- **Verification Evidence:**
  - Implemented multi-stage `Dockerfile` (`python:3.12-slim` base) with build/runtime isolation, non-root user execution (`appuser`, UID 10001), Docker `HEALTHCHECK` instruction hitting `/health/liveness`, and exposed port `8000`.
  - Configured `.dockerignore` excluding `.git`, `.venv`, `__pycache__`, data directories (`data/`), reports (`reports/`), secrets (`.env`), and test artifacts.
  - Extended CLI task runner (`tasks.py`) with `py -3.12 tasks.py docker-build` and `py -3.12 tasks.py docker-run`.
  - Added unit test suite in [`tests/unit/test_docker.py`](file:///c:/Users/AAKASH.S.S/OneDrive/Desktop/Pipelines/tests/unit/test_docker.py) verifying Dockerfile structure, non-root user, healthcheck instruction, `.dockerignore` exclusions, and CLI task registration.
- **ADRs Created:** None for Phase 11.
- **Architectural Impact:**
  - **New Modules Introduced:** `Dockerfile`, `.dockerignore`, `tests/unit/test_docker.py`.
  - **Modified Modules:** `tasks.py`, `PROJECT_PROGRESS.md`.
  - **Public Interfaces Added:** `py -3.12 tasks.py docker-build`, `py -3.12 tasks.py docker-run`.
- **Next Phase:** Phase 0 (Infrastructure Prerequisites) / Phase 12 (AWS ECR Pipeline)
