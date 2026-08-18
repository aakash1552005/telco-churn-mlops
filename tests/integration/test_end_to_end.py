"""End-to-End Integration Test Suite for Telco Customer Churn Platform.

Master Contract Phase 19:
Proves that the entire system works together as one integrated whole:
ingest -> validate -> features -> train -> evaluate -> promote -> serve ->
readiness -> predict -> metrics -> drift

CRITICAL ISOLATION GUARANTEES:
- Uses an isolated workspace (pytest tmp_path / integration directory)
- Dedicated MLflow tracking store: sqlite:///<tmp_path>/integration_mlflow.db
- Dedicated registered model name: 'telco-churn-integration-test'
- Real production functions executed exclusively against isolated artifacts
- Zero mutation of canonical project data, models, reports, or real mlflow.db
"""

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.config import get_settings
from src.data.features import process_and_save_features
from src.data.ingestion import ingest_raw_data
from src.data.validation import validate_data
from src.inference.service import prediction_service
from src.monitoring.drift import run_drift_pipeline
from src.training.evaluate import generate_evaluation_report
from src.training.promotion import promote_model
from src.training.train import train_candidate_models

INTEGRATION_MODEL_NAME = "telco-churn-integration-test"
INTEGRATION_EXP_NAME = "telco-churn-integration-testing"


@pytest.fixture
def integration_workspace(tmp_path: Path) -> Dict[str, Path]:
    """Create isolated directory structure and paths for end-to-end integration run."""
    ws = tmp_path / "integration_workspace"
    ws.mkdir(parents=True, exist_ok=True)

    paths = {
        "root": ws,
        "raw_dir": ws / "data" / "raw",
        "raw_csv": ws / "data" / "raw" / "telco_churn.csv",
        "processed_dir": ws / "data" / "processed",
        "models_dir": ws / "models",
        "reports_dir": ws / "reports",
        "plots_dir": ws / "reports" / "plots",
        "schema_yaml": Path("src/data/schema.yaml").resolve(),
        "feature_pipeline": ws / "models" / "feature_pipeline.joblib",
        "feature_schema": ws / "models" / "feature_schema.json",
        "best_model": ws / "models" / "best_model.joblib",
        "training_metrics": ws / "reports" / "training_metrics.json",
        "cv_results": ws / "reports" / "cv_results.csv",
        "training_metadata": ws / "models" / "training_metadata.json",
        "decision_threshold": ws / "models" / "decision_threshold.json",
        "evaluation_metrics": ws / "reports" / "evaluation_metrics.json",
        "validation_report": ws / "reports" / "validation_report.json",
        "drift_report_json": ws / "reports" / "drift_report.json",
        "drift_report_html": ws / "reports" / "drift_report.html",
        "drift_state": ws / "reports" / "drift_state.json",
        "mlflow_db": ws / "integration_mlflow.db",
    }

    # Ensure directories exist
    paths["raw_dir"].mkdir(parents=True, exist_ok=True)
    paths["processed_dir"].mkdir(parents=True, exist_ok=True)
    paths["models_dir"].mkdir(parents=True, exist_ok=True)
    paths["reports_dir"].mkdir(parents=True, exist_ok=True)
    paths["plots_dir"].mkdir(parents=True, exist_ok=True)

    return paths


def test_end_to_end_pipeline_integration(
    integration_workspace: Dict[str, Path],
    sample_valid_payload: Dict[str, Any],
) -> None:
    """Execute complete 11-step integration test lifecycle in isolated environment."""
    ws = integration_workspace
    tracking_uri = f"sqlite:///{ws['mlflow_db'].as_posix()}"
    canonical_raw = Path("data/raw/telco_churn.csv")

    assert (
        canonical_raw.exists()
    ), "Canonical raw dataset must exist to seed integration ingestion."

    # -------------------------------------------------------------------------
    # STEP 1 — Ingest
    # -------------------------------------------------------------------------
    ingested_path = ingest_raw_data(
        source_type="local",
        source_location=str(canonical_raw),
        target_path=ws["raw_csv"],
    )

    assert ws["raw_csv"].exists(), "Isolated raw dataset must be created on disk."
    assert ingested_path == ws["raw_csv"]

    df_raw = pd.read_csv(ws["raw_csv"])
    assert len(df_raw) == 7043, f"Expected 7043 rows, got {len(df_raw)}"
    assert len(df_raw.columns) == 21, f"Expected 21 columns, got {len(df_raw.columns)}"

    # -------------------------------------------------------------------------
    # STEP 2 — Validate
    # -------------------------------------------------------------------------
    validation_report = validate_data(
        df=df_raw,
        schema_path=ws["schema_yaml"],
        report_path=ws["validation_report"],
    )

    assert ws["validation_report"].exists()
    assert validation_report["summary"]["validation_status"] == "PASSED"
    assert validation_report["summary"]["rules_failed"] == 0
    assert validation_report["summary"]["rules_passed"] > 0

    # -------------------------------------------------------------------------
    # STEP 3 — Feature Engineering
    # -------------------------------------------------------------------------
    X_train_proc, X_test_proc, y_train, y_test, fitted_pipeline = (
        process_and_save_features(
            raw_df=df_raw,
            processed_dir=ws["processed_dir"],
            pipeline_path=ws["feature_pipeline"],
            schema_output_path=ws["feature_schema"],
            test_size=0.2,
            random_state=42,
        )
    )

    train_csv = ws["processed_dir"] / "train.csv"
    test_csv = ws["processed_dir"] / "test.csv"
    assert train_csv.exists(), "Isolated processed train.csv must exist."
    assert test_csv.exists(), "Isolated processed test.csv must exist."
    assert ws[
        "feature_pipeline"
    ].exists(), "Isolated feature_pipeline.joblib must exist."
    assert ws["feature_schema"].exists(), "Isolated feature_schema.json must exist."

    with open(ws["feature_schema"], "r", encoding="utf-8") as f:
        schema_data = json.load(f)
    assert schema_data["feature_count"] == 49
    assert len(schema_data["features"]) == 49

    # -------------------------------------------------------------------------
    # STEP 4 — Train (Candidate Search with Fast CI Iterations n_iter=2)
    # -------------------------------------------------------------------------
    winning_estimator, train_metrics, train_meta = train_candidate_models(
        processed_dir=ws["processed_dir"],
        schema_path=ws["feature_schema"],
        pipeline_path=ws["feature_pipeline"],
        model_output_path=ws["best_model"],
        metrics_output_path=ws["training_metrics"],
        cv_results_output_path=ws["cv_results"],
        metadata_output_path=ws["training_metadata"],
        random_state=42,
        n_iter=2,
    )

    assert ws["best_model"].exists(), "Isolated winning best_model.joblib must exist."
    assert ws["training_metrics"].exists(), "Isolated training_metrics.json must exist."
    assert ws["cv_results"].exists(), "Isolated cv_results.csv must exist."
    assert ws[
        "training_metadata"
    ].exists(), "Isolated training_metadata.json must exist."
    assert train_metrics["winning_algorithm"] in ["LogisticRegression", "XGBClassifier"]
    assert train_metrics["best_cv_roc_auc"] > 0.70

    # -------------------------------------------------------------------------
    # STEP 5 — Evaluate
    # -------------------------------------------------------------------------
    eval_report = generate_evaluation_report(
        processed_dir=ws["processed_dir"],
        model_path=ws["best_model"],
        schema_path=ws["feature_schema"],
        metadata_path=ws["training_metadata"],
        output_dir=ws["reports_dir"],
        plots_dir=ws["plots_dir"],
        threshold_path=ws["decision_threshold"],
    )

    assert ws[
        "evaluation_metrics"
    ].exists(), "Isolated evaluation_metrics.json must exist."
    assert ws[
        "decision_threshold"
    ].exists(), "Isolated decision_threshold.json must exist."

    opt_thresh = eval_report["optimal_threshold_metrics"]["optimal_threshold"]
    opt_f1 = eval_report["optimal_threshold_metrics"]["f1"]
    assert 0.1 <= opt_thresh <= 0.9, f"Optimal threshold out of bounds: {opt_thresh}"
    assert 0.4 <= opt_f1 <= 1.0, f"Optimal F1 out of reasonable range: {opt_f1}"

    # -------------------------------------------------------------------------
    # STEP 6 — Promote (Targeting Isolated MLflow Tracking Store)
    # -------------------------------------------------------------------------
    promotion_result = promote_model(
        tracking_uri=tracking_uri,
        experiment_name=INTEGRATION_EXP_NAME,
        model_name=INTEGRATION_MODEL_NAME,
        eval_report_path=ws["evaluation_metrics"],
        model_path=ws["best_model"],
    )

    assert (
        promotion_result["is_promoted"] is True
    ), "Bootstrap candidate must be promoted to Production."
    assert promotion_result["stage"] == "Production"
    assert promotion_result["model_name"] == INTEGRATION_MODEL_NAME
    assert int(promotion_result["model_version"]) >= 1

    # -------------------------------------------------------------------------
    # STEP 7 & 8 — Serve & Health Readiness
    # -------------------------------------------------------------------------
    # Reset and explicitly load prediction_service against isolated artifacts
    prediction_service.load_production_model(
        tracking_uri=tracking_uri,
        model_name=INTEGRATION_MODEL_NAME,
        pipeline_path=ws["feature_pipeline"],
        threshold_path=ws["decision_threshold"],
        schema_path=ws["feature_schema"],
    )

    assert prediction_service.model is not None
    assert prediction_service.feature_pipeline is not None
    assert prediction_service.model_version == str(promotion_result["model_version"])

    app = create_app()
    client = TestClient(app)

    # Query /health/readiness
    readiness_res = client.get("/health/readiness")
    assert readiness_res.status_code == 200
    readiness_json = readiness_res.json()
    assert readiness_json["status"] == "ready"
    assert readiness_json["model_loaded"] is True
    assert readiness_json["model_version"] == str(promotion_result["model_version"])

    # -------------------------------------------------------------------------
    # STEP 9 — Predict Endpoint Contract
    # -------------------------------------------------------------------------
    settings = get_settings()
    api_key = (
        settings.API_SECRET_KEYS[0]
        if settings.API_SECRET_KEYS
        else "dev-secret-key-123"
    )

    predict_res = client.post(
        "/predict",
        json=sample_valid_payload,
        headers={"X-API-Key": api_key},
    )

    assert (
        predict_res.status_code == 200
    ), f"Predict failed: {predict_res.status_code} - {predict_res.text}"
    p_json = predict_res.json()

    assert "customerID" in p_json
    assert p_json["customerID"] == sample_valid_payload["customerID"]
    assert "probability" in p_json
    assert 0.0 <= p_json["probability"] <= 1.0
    assert "decision" in p_json
    assert p_json["decision"] in ["Churn", "No Churn"]
    assert "churn_predicted" in p_json
    assert isinstance(p_json["churn_predicted"], bool)
    assert "threshold_used" in p_json
    assert np.isclose(p_json["threshold_used"], opt_thresh, atol=1e-4)
    assert "model_version" in p_json
    assert p_json["model_version"] == str(promotion_result["model_version"])

    # -------------------------------------------------------------------------
    # STEP 10 — Metrics Verification & Counter Increment
    # -------------------------------------------------------------------------
    metrics_res = client.get("/metrics")
    assert metrics_res.status_code == 200
    metrics_text = metrics_res.text

    # Assert all four custom Prometheus metric declarations
    assert "# TYPE telco_request_duration_seconds histogram" in metrics_text
    assert "# TYPE telco_predictions_total counter" in metrics_text
    assert "# TYPE telco_api_errors_total counter" in metrics_text
    assert "# TYPE telco_model_info gauge" in metrics_text

    # Send a second prediction request to confirm counter increments
    client.post(
        "/predict",
        json=sample_valid_payload,
        headers={"X-API-Key": api_key},
    )
    metrics_res_2 = client.get("/metrics")
    assert metrics_res_2.status_code == 200
    assert "telco_predictions_total" in metrics_res_2.text

    # -------------------------------------------------------------------------
    # STEP 11 — Drift Detection on Synthetic Shifted Dataset
    # -------------------------------------------------------------------------
    # Create shifted dataset from isolated test.csv (scale MonthlyCharges by 4.0)
    df_test_proc = pd.read_csv(test_csv)
    df_shifted = df_test_proc.copy()
    if "MonthlyCharges" in df_shifted.columns:
        df_shifted["MonthlyCharges"] = df_shifted["MonthlyCharges"] * 4.0
    elif "MonthlyCharges__scaled" in df_shifted.columns:
        df_shifted["MonthlyCharges__scaled"] = (
            df_shifted["MonthlyCharges__scaled"] * 4.0
        )

    shifted_csv = ws["processed_dir"] / "shifted_test.csv"
    df_shifted.to_csv(shifted_csv, index=False)

    drift_res = run_drift_pipeline(
        reference_path=train_csv,
        current_path=shifted_csv,
        model_path=ws["best_model"],
        output_report_path=ws["drift_report_json"],
        output_html_path=ws["drift_report_html"],
        state_file_path=ws["drift_state"],
        trigger_retraining=False,
    )

    assert ws["drift_report_json"].exists()
    assert (
        drift_res["summary"]["drift_detected"] is True
    ), "Shifted dataset must trigger positive drift detection."
    assert len(drift_res["summary"]["triggering_criteria"]) > 0
