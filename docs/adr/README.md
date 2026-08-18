# Architecture Decision Records (ADR) Index

This directory maintains the historical log of all formal Architectural Decision Records (ADRs) for the Telco Customer Churn MLOps platform.

Each record captures the architectural context, design alternatives evaluated, decision rationale, and operational consequences for major technical milestones.

---

## Catalog of Architectural Decision Records

| ADR # | Title | Phase Made | Status | Summary of Decision |
|---|---|---|---|---|
| [ADR 0001](0001-use-tasks-py-over-makefile.md) | **Standardize Task Automation via tasks.py for Cross-Platform Portability** | Phase 1 | Accepted | Adopted a pure Python task runner script ([`tasks.py`](../../tasks.py)) utilizing Python standard library (`argparse`, `subprocess`) to eliminate non-portable GNU `make` dependencies on Windows while providing a uniform interface across Linux, macOS, and CI. |
| [ADR 0002](0002-configure-pydantic-mypy-plugin.md) | **Configure pydantic.mypy Plugin for Type Checking BaseSettings** | Phase 2 | Accepted | Configured the official Pydantic Mypy plugin (`pydantic.mypy`) in [`pyproject.toml`](../../pyproject.toml) to support dynamic runtime environment resolution without `# type: ignore` suppressions, preserving static type safety. |
| [ADR 0003](0003-model-training-and-hyperparameter-search-strategy.md) | **Model Training, Hyperparameter Search, and Metric Selection Strategy** | Phase 7 | Accepted | Selected `RandomizedSearchCV` (5-fold stratified CV, 20 iterations, `random_state=42`) for deterministic reproducibility and decoupled global search ranking (ROC-AUC) from threshold-specific operational business deployment gates (F1/Precision/Recall). |
| [ADR 0004](0004-model-evaluation-threshold-optimization-and-calibration.md) | **Model Evaluation, Threshold Optimization, and Calibration Strategy** | Phase 8 | Accepted | Restricted deep evaluation strictly to the winning estimator (`models/best_model.joblib`), conducted decision threshold optimization along the Precision-Recall curve ($\approx 0.3254$) boosting operational F1 from `0.5898` to `0.6416`, and validated probability calibration using Brier score loss. |
| [ADR 0005](0005-mlflow-tracking-and-model-promotion-policy.md) | **MLflow Tracking Backend, Model Registry, and Promotion Policy Architecture** | Phase 9 | Accepted | Adopted SQLite (`sqlite:///mlflow.db`) as the tracking backend store to enable local MLflow Model Registry stages (`Staging`, `Production`, `Archived`), operationalized promotion rules in `models/promotion_policy.json`, implemented bootstrap auto-promotion, and logged secondary candidates as metrics-only runs. |
| [ADR 0006](0006-end-to-end-integration-testing-and-isolation.md) | **End-to-End Integration Testing Architecture and Isolation Contract** | Phase 19 | Accepted | Implemented a dedicated integration test suite (`tests/integration/test_end_to_end.py`) exercising the entire 11-stage pipeline in an ephemeral workspace (`integration_mlflow.db`, `telco-churn-integration-test`) without touching canonical production artifacts or requiring cloud infrastructure. |

---

## ADR Template and Structure

New architectural decisions must follow the standard lightweight format:
1. **Title**: `ADR <Number>: <Title>`
2. **Status**: `Proposed` | `Accepted` | `Deprecated` | `Superseded by ADR XXXX`
3. **Context**: The business requirement or technical problem being solved.
4. **Decision**: The chosen technical architecture, implementation, and boundaries.
5. **Alternatives Considered**: Key options evaluated and reasons for rejection.
6. **Consequences**: Positive, negative, and neutral trade-offs resulting from the decision.
