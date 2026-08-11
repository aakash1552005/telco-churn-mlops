# ADR 0003: Model Training, Hyperparameter Search, and Metric Selection Strategy

- **Status:** Accepted
- **Date:** 2026-08-10
- **Deciders:** MLOps Engineering Team

---

## Context

Phase 7 of the Telco Customer Churn MLOps platform requires training candidate machine learning models (Logistic Regression baseline and XGBoost classifier) using 5-fold stratified cross-validation (`StratifiedKFold(n_splits=5, shuffle=True, random_state=42)`).

Key technical design choices include:
1. Selecting the hyperparameter optimization engine.
2. Aligning optimization search criteria with downstream production promotion policies.
3. Defining explicit hyperparameter search spaces.

## Decisions

### 1. RandomizedSearchCV over Optuna for Hyperparameter Optimization

We adopt scikit-learn's standard `RandomizedSearchCV` rather than `Optuna` or Bayesian search frameworks for Phase 7 model training.

**Rationale:**
- **Deterministic Reproducibility:** `RandomizedSearchCV` combined with fixed numpy and scikit-learn random seeds (`random_state=42`) guarantees exact repeatability across training runs.
- **Zero Heavy External Dependencies:** Integrates directly with scikit-learn's native estimators and `xgboost.XGBClassifier` without requiring external trial databases, Optuna storage backends, or complex stateful samplers.
- **Standardized Audit Artifacts:** Exposes `cv_results_` directly, enabling transparent serialization of cross-validation search statistics to [`reports/cv_results.csv`](file:///c:/Users/AAKASH.S.S/OneDrive/Desktop/Pipelines/reports/cv_results.csv).
- **Search Space Efficiency:** On tabular datasets of this scale (~5,634 training rows and 49 features), 20 randomized search iterations across 5 stratified folds provide ample hyperparameter coverage with fast execution times (< 15 seconds).

### 2. Metric Separation: ROC-AUC for Search Signal vs F1/Precision/Recall for Promotion Gate

We intentionally decouple the optimization metric used during hyperparameter search from the threshold-specific metric evaluated during production promotion (Phase 9).

**Explicit Separation of Concerns:**
- **ROC-AUC (Hyperparameter Search Criterion):** ROC-AUC measures a model's threshold-independent ability to rank positive (churn) instances higher than negative (non-churn) instances across all possible probability thresholds. It provides a smooth, continuous, rank-order optimization signal that is resilient to class imbalance and avoids overfitting to an arbitrary decision threshold during hyperparameter search.
- **F1 / Precision / Recall (Production Promotion Gate - Master Contract Section 9):** Evaluates operational performance at a specific decision boundary (e.g., probability threshold = 0.5) against business constraints (e.g., maximum allowable precision drop $\le 2\%$, F1 improvement $\ge 0.01$, and non-decreasing recall).

**Empirical Training Outcome & Divergence Analysis (Phase 7 Run):**
- **Search Selection Winner:** `XGBClassifier` won candidate selection with **Best CV ROC-AUC = 0.8497** compared to `LogisticRegression` (**0.8460**).
- **Held-Out Test Set Metrics (1,409 rows):**
  - **`XGBClassifier`:** Test ROC-AUC = **0.8469**, Precision = **0.6701**, Recall = **0.5267**, F1 = **0.5898**
  - **`LogisticRegression`:** Test ROC-AUC = **0.8422**, Precision = **0.6552**, Recall = **0.5588**, F1 = **0.6032**
- **Empirical Insight:** `XGBClassifier` provides superior overall ranking power across probability thresholds (ROC-AUC 0.8497 vs 0.8460). However, at the default `0.5` decision boundary, `LogisticRegression` produces a higher test F1 score (0.6032 vs 0.5898) due to higher recall (0.5588 vs 0.5267). This empirical divergence validates our two-tier strategy: `RandomizedSearchCV` optimizes global ranking capacity (ROC-AUC) to select the best probability estimator, while Phase 9's production promotion gate evaluates threshold-specific operational metrics (F1/Precision/Recall) before deployment.

**Key Takeaway:** Search signal (finding the best overall probability estimator) and deployment gate (validating operational business threshold safety) serve fundamentally different purposes in the model lifecycle.


---

## Search Space Definitions

### Logistic Regression Baseline
- `C`: Log-uniform distribution / discrete search grid: `[0.001, 0.01, 0.1, 1.0, 10.0, 100.0]`
- `penalty`: `['l2']`
- `solver`: `['lbfgs']`
- `max_iter`: `1000`
- `random_state`: `42`

### XGBoost Classifier (`xgb.XGBClassifier`)
- `n_estimators`: `[50, 100, 150, 200, 250, 300]`
- `max_depth`: `[3, 4, 5, 6, 7, 8]`
- `learning_rate`: `[0.01, 0.03, 0.05, 0.1, 0.2]`
- `subsample`: `[0.6, 0.7, 0.8, 0.9, 1.0]`
- `colsample_bytree`: `[0.6, 0.7, 0.8, 0.9, 1.0]`
- `min_child_weight`: `[1, 3, 5, 7]`
- `gamma`: `[0.0, 0.1, 0.2, 0.3]`
- `eval_metric`: `"logloss"`
- `random_state`: `42`

---

## Alternatives Considered

1. **Optuna / Hyperopt:** Provides adaptive TPE (Tree-structured Parzen Estimator) sampling, but introduces extra dependencies, non-trivial trial database management, and potential non-determinism across different OS environments.
2. **GridSearchCV:** Exhaustive search across the full XGBoost parameter grid produces $> 20,000$ combinations, causing unnecessary compute overhead without material metric improvement compared to randomized sampling.

---

## Consequences

- **Positive:** Guaranteed 100% deterministic model training and metrics across identical random seeds.
- **Positive:** Transparent export of full cross-validation history to CSV.
- **Positive:** Clean separation between model capacity optimization (ROC-AUC) and business policy validation (F1/Precision/Recall).
