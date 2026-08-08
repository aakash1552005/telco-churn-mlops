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
| Phase 5 | Data Validation & Schema | Milestone 1 | Tier A | Completed | 2026-08-08 | `a01cfd0` |
| Phase 6 | DVC & Feature Engineering | Milestone 1 | Tier A | Pending | - | - |
| Phase 7 | Model Training Pipeline | Milestone 1 | Tier A | Pending | - | - |
| Phase 8 | Model Evaluation & Metrics | Milestone 1 | Tier A | Pending | - | - |
| Phase 9 | MLflow & Promotion Policy | Milestone 1 | Tier A | Pending | - | - |
| Phase 10 | FastAPI & Security Baseline | Milestone 1 | Tier A | Pending | - | - |
| Phase 11 | Docker Containerization | Milestone 1 | Tier A | Pending | - | - |
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
- **Commit:** `a01cfd0` (`feat: add data validation layer`)
- **Verification Evidence:**
  - Data-Driven Schema Config: [`src/data/schema.yaml`](file:///C:/Users/AAKASH.S.S/OneDrive/Desktop/Pipelines/src/data/schema.yaml) (`schema_version: "1.0.0"`, `allow_extra_columns: false`).
  - `py -3.12 tasks.py lint`: Stray `print()` check passed; `flake8`, `black`, `isort`, `mypy` passed clean across 11 source files.
  - `py -3.12 tasks.py test`: All 21 unit tests across `test_config.py`, `test_logging.py`, `test_ingestion.py`, and `test_validation.py` passed 100% clean in 6.12s.
  - `py -3.12 tasks.py validate`: Validated real raw dataset (`data/raw/telco_churn.csv`). Saved JSON report to `reports/validation_report.json` with matching dataset SHA-256 hash.
  - `py -3.12 scripts/demo_validation.py`: Confirmed real dataset passed (65 rules passed, 0 failed), and 4 corrupted fixtures (Missing Column, Invalid Domain Value, Duplicate customerID, Extra Unknown Column) failed loudly with exact `DataValidationError` exception details.
  - Pre-commit hooks: All 8 pre-commit hooks passed clean on `git commit`.
- **ADRs Created:** None for Phase 5.
- **Known Issues & Remaining Risks:**
  1. **Strict Unknown Column Rejection Policy:** `allow_extra_columns: false` enforces immediate failure if upstream data providers add unannounced columns. Adding legitimate new features to the raw dataset will require updating `schema.yaml` to bump `schema_version`.
  2. **TotalCharges String Encoding:** The raw dataset encodes `TotalCharges` as strings due to 11 empty space values (`" "`) for zero-tenure customers. Schema validation treats `TotalCharges` as string type; numerical casting and missing value imputation will occur in Phase 6 (Feature Engineering).
- **Next Phase:** Phase 6 (DVC & Feature Engineering)
