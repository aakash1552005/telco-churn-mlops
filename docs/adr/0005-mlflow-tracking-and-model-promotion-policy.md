# ADR 0005: MLflow Tracking Backend, Model Registry, and Promotion Policy Architecture

- **Status:** Accepted
- **Date:** 2026-08-11
- **Deciders:** MLOps Engineering Team

---

## Context

Phase 9 of the Telco Customer Churn MLOps platform requires integrating MLflow experiment tracking, model registration, and automated promotion policy enforcement per Master Contract Section 9.

Key technical requirements:
1. Enabling local MLflow Model Registry support (`Staging`, `Production`, `Archived` stage transitions).
2. Operationalizing Master Contract Section 9 promotion policy into code and versioned configuration.
3. Defining the metric basis for model promotion comparisons.
4. Handling the initial bootstrap deployment case when no production model exists.
5. Logging historical candidate runs (`LogisticRegression`) accurately without violating Phase 7/8 model persistence boundaries.

---

## Decisions

### 1. MLflow Tracking Backend (`sqlite:///mlflow.db`)

We select SQLite (`sqlite:///mlflow.db`) as the local MLflow tracking backend store.

**Rationale:**
- MLflow's Model Registry features (model registration, versioning, stage transitions between `Staging`, `Production`, and `Archived`) **strictly require a database-backed backend store** (SQLAlchemy URI). Plain file stores (`mlruns/` directories without a database URI) do NOT support the MLflow Model Registry API (MLflow raises `RestException: Model Registry functionality is unavailable when tracking to local file store`).
- Using SQLite provides local, zero-dependency, out-of-process registry persistence without requiring an external HTTP server daemon.
- **Gitignore Policy:** `mlflow.db`, `*.db`, and `mlruns/` are local runtime database artifacts and local tracking stores; they are gitignored and never committed to version control.

---

### 2. Operationalizing Promotion Policy via `models/promotion_policy.json`

To eliminate ambiguity between Master Contract Section 9 text and code implementation, `models/promotion_policy.json` serves as the versioned source of truth for all promotion policy threshold parameters:

```json
{
  "min_f1_improvement": 0.01,
  "max_precision_drop": 0.02,
  "max_recall_drop": 0.0
}
```

**Promotion Criteria (Evaluated against Incumbent Production Model):**
1. **F1 Score Improvement:** Candidate optimal-threshold F1 must improve over the incumbent Production model by at least +1.0% ($\ge +0.0100$).
2. **Precision Drop:** Candidate optimal-threshold Precision drop must not exceed 2.0% ($\le 0.0200$).
3. **Recall Drop:** Candidate optimal-threshold Recall must not decrease ($\le 0.0000$).

---

### 3. Metric Basis: Optimal-Threshold F1 Comparison

In alignment with Phase 8 established standards and `models/decision_threshold.json`, promotion comparisons use the **optimal-threshold F1 score** (`0.6416` for current XGBoost model) rather than the default 0.5 threshold F1 score (`0.5898`).

**Rationale:** Phase 8 established that decision threshold optimization (`0.3254`) reflects the model's true operational classification performance in production. Evaluating candidate promotion against default `0.5` metrics would misrepresent operational business utility.

---

### 4. Bootstrap Initial Promotion Policy

When evaluating a candidate model and no model currently exists in the `"Production"` stage in MLflow Model Registry (e.g. during initial deployment or fresh environment setup):

**Decision:**
- The initial candidate model is **auto-promoted** to `"Production"` with the logged reason: `"no existing production model — initial promotion"`.
- This ensures the pipeline does not stall or remain stuck in `"Staging"` indefinitely upon initial deployment.

---

### 5. Metrics-Only Historical Child Run Logging for Logistic Regression

In Phase 7, candidate evaluation logged search results to `reports/training_metrics.json` and `reports/cv_results.csv`, serializing only the winning estimator (`models/best_model.joblib`, `XGBClassifier`).

**Decision:**
- We do NOT retrain or refit Logistic Regression to populate an artificial model artifact for MLflow.
- Instead, `log_pipeline_run_to_mlflow()` logs `LogisticRegression` as a nested, metrics-only historical child run under the parent pipeline run.
- The child run logs all hyperparameter settings and test metrics from `reports/training_metrics.json`, carries **zero model artifact**, and is tagged explicitly:
  - `model_status: metrics_only_historical, no_persisted_estimator`
  - `candidate_family: LogisticRegression`

---

## Consequences

- **Positive:** MLflow Model Registry fully operationalized locally via SQLite (`sqlite:///mlflow.db`).
- **Positive:** Versioned, deterministic promotion policy engine (`src/training/promotion.py`, `models/promotion_policy.json`).
- **Positive:** Initial bootstrap auto-promotion handled cleanly.
- **Positive:** Preserved lean model artifact boundary without retraining discarded candidate models.
