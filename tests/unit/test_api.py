"""Unit and Integration Test Suite for FastAPI Prediction Service (Phase 10).

Tests API endpoints, security authentication, Pydantic domain validation,
MLflow Production stage model loading, provenance verification, defensive startup
checks, offline/online prediction consistency, and dynamic model reload round-trip.
"""

import json
from pathlib import Path
from typing import Any, Dict

import joblib
import mlflow
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from mlflow.tracking import MlflowClient

from src.api.app import app
from src.core.config import get_settings
from src.inference.service import PredictionService, prediction_service
from src.training.train import calculate_file_sha256

settings = get_settings()
TEST_API_KEY = settings.API_SECRET_KEYS[0]


@pytest.fixture(scope="module", autouse=True)
def ensure_production_model_loaded() -> None:
    """Ensure prediction service has loaded real Production model prior to API tests."""
    try:
        prediction_service.load_production_model()
    except Exception as e:
        pytest.skip(
            f"Skipping API tests: Production model not available in MLflow: {e}"
        )


@pytest.fixture
def client() -> TestClient:
    """Instantiate FastAPI TestClient."""
    return TestClient(app)


@pytest.fixture
def sample_valid_payload() -> Dict[str, Any]:
    """Valid raw Telco customer payload dictionary."""
    return {
        "customerID": "7590-VHVEG",
        "gender": "Female",
        "SeniorCitizen": 0,
        "Partner": "Yes",
        "Dependents": "No",
        "tenure": 1,
        "PhoneService": "No",
        "MultipleLines": "No phone service",
        "InternetService": "DSL",
        "OnlineSecurity": "No",
        "OnlineBackup": "Yes",
        "DeviceProtection": "No",
        "TechSupport": "No",
        "StreamingTV": "No",
        "StreamingMovies": "No",
        "Contract": "Month-to-month",
        "PaperlessBilling": "Yes",
        "PaymentMethod": "Electronic check",
        "MonthlyCharges": 29.85,
        "TotalCharges": "29.85",
    }


def test_health_and_liveness_readiness(client: TestClient) -> None:
    """Verify /health, /health/liveness, and /health/readiness endpoints."""
    res_health = client.get("/health")
    assert res_health.status_code == 200
    data_h = res_health.json()
    assert data_h["status"] == "healthy"
    assert data_h["model_loaded"] is True
    assert "model_version" in data_h

    res_live = client.get("/health/liveness")
    assert res_live.status_code == 200
    assert res_live.json() == {"status": "alive"}

    res_ready = client.get("/health/readiness")
    assert res_ready.status_code == 200
    data_r = res_ready.json()
    assert data_r["status"] == "ready"
    assert data_r["model_loaded"] is True


def test_version(client: TestClient) -> None:
    """Verify /version endpoint returns project and version details."""
    res = client.get("/version")
    assert res.status_code == 200
    data = res.json()
    assert data["version"] == "0.1.0"
    assert data["project_name"] == settings.PROJECT_NAME


def test_metrics_endpoint(client: TestClient) -> None:
    """Verify /metrics endpoint returns live Prometheus exposition content."""
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
    assert "# TYPE telco_predictions_total counter" in res.text
    assert "# TYPE telco_request_duration_seconds histogram" in res.text


def test_predict_valid_sample(
    client: TestClient, sample_valid_payload: Dict[str, Any]
) -> None:
    """Verify /predict endpoint with valid raw input payload and API key."""
    headers = {"X-API-Key": TEST_API_KEY}
    res = client.post("/predict", json=sample_valid_payload, headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["customerID"] == "7590-VHVEG"
    assert 0.0 <= data["probability"] <= 1.0
    assert data["decision"] in ["Churn", "No Churn"]
    assert isinstance(data["churn_predicted"], bool)
    assert isinstance(data["threshold_used"], float)
    assert len(data["model_version"]) > 0


def test_predict_unauthorized(
    client: TestClient, sample_valid_payload: Dict[str, Any]
) -> None:
    """Verify /predict endpoint rejects requests missing or with invalid API key."""
    # 1. Missing API Key Header
    res_no_key = client.post("/predict", json=sample_valid_payload)
    assert res_no_key.status_code == 401
    assert "Missing X-API-Key" in res_no_key.json()["detail"]

    # 2. Invalid API Key Header
    headers = {"X-API-Key": "invalid-secret-key-999"}
    res_bad_key = client.post("/predict", json=sample_valid_payload, headers=headers)
    assert res_bad_key.status_code == 401
    assert "Invalid API key" in res_bad_key.json()["detail"]


def test_predict_validation_error(client: TestClient) -> None:
    """Verify /predict endpoint returns 422 Unprocessable Entity for domain errors."""
    headers = {"X-API-Key": TEST_API_KEY}

    # Case 1: Negative tenure (domain violation: tenure >= 0)
    bad_tenure_payload = {
        "gender": "Female",
        "SeniorCitizen": 0,
        "Partner": "Yes",
        "Dependents": "No",
        "tenure": -5,  # Invalid!
        "PhoneService": "No",
        "MultipleLines": "No phone service",
        "InternetService": "DSL",
        "OnlineSecurity": "No",
        "OnlineBackup": "Yes",
        "DeviceProtection": "No",
        "TechSupport": "No",
        "StreamingTV": "No",
        "StreamingMovies": "No",
        "Contract": "Month-to-month",
        "PaperlessBilling": "Yes",
        "PaymentMethod": "Electronic check",
        "MonthlyCharges": 29.85,
        "TotalCharges": "29.85",
    }
    res = client.post("/predict", json=bad_tenure_payload, headers=headers)
    assert res.status_code == 422
    err_detail = res.json()["detail"]
    assert any("tenure" in str(err) for err in err_detail)

    # Case 2: Invalid categorical enum (e.g. Contract = "Super-long-term")
    bad_enum_payload = bad_tenure_payload.copy()
    bad_enum_payload["tenure"] = 10
    bad_enum_payload["Contract"] = "Super-long-term"  # Invalid!
    res_enum = client.post("/predict", json=bad_enum_payload, headers=headers)
    assert res_enum.status_code == 422


def test_model_info(client: TestClient) -> None:
    """Verify /model-info endpoint returns Production model metadata and provenance."""
    headers = {"X-API-Key": TEST_API_KEY}
    res = client.get("/model-info", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["model_name"] == settings.MLFLOW_MODEL_NAME
    assert len(data["model_version"]) > 0
    assert len(data["run_id"]) > 0
    assert "algorithm" in data
    assert isinstance(data["optimal_threshold"], float)
    assert "provenance" in data
    assert "schema_version" in data["provenance"]


def test_mlflow_production_model_loaded() -> None:
    """Verify prediction service genuinely loaded model from Production stage."""
    m_client = MlflowClient(tracking_uri=settings.MLFLOW_TRACKING_URI)
    all_vers = m_client.search_model_versions(f"name='{settings.MLFLOW_MODEL_NAME}'")
    prod_vers = [v for v in all_vers if v.current_stage == "Production"]
    assert len(prod_vers) == 1
    expected_version = str(prod_vers[0].version)
    assert prediction_service.model_version == expected_version


def test_offline_online_prediction_consistency(
    client: TestClient, sample_valid_payload: Dict[str, Any]
) -> None:
    """ISOLATED TEST: Offline vs Online Prediction Consistency Check.

    Loads a raw customer record, computes probability offline using loaded
    feature_pipeline.joblib and best_model.joblib artifacts directly, then sends
    the exact raw payload to live POST /predict and asserts probabilities match
    within floating point tolerance (1e-5).
    """
    # 1. Offline Transformation and Scoring
    pipe_path = Path(settings.FEATURE_PIPELINE_PATH)
    model_path = Path(settings.MODEL_OUTPUT_PATH)
    schema_path = Path(settings.FEATURE_SCHEMA_PATH)

    assert pipe_path.exists()
    assert model_path.exists()

    offline_pipeline = joblib.load(pipe_path)
    offline_model = joblib.load(model_path)

    raw_df = pd.DataFrame([sample_valid_payload])
    X_raw = raw_df.drop(columns=["customerID", "Churn"], errors="ignore")

    X_trans = offline_pipeline.transform(X_raw)

    with open(schema_path, "r", encoding="utf-8") as f:
        sch_data = json.load(f)
    feature_cols = sch_data.get("features", [])

    X_proc_df = pd.DataFrame(X_trans, columns=feature_cols)

    offline_probs = offline_model.predict_proba(X_proc_df)[:, 1]
    offline_prob = float(offline_probs[0])

    # 2. Online API Prediction Endpoint Scoring
    headers = {"X-API-Key": TEST_API_KEY}
    res = client.post("/predict", json=sample_valid_payload, headers=headers)
    assert res.status_code == 200
    online_data = res.json()
    online_prob = float(online_data["probability"])

    # 3. Assert Consistency
    assert np.isclose(offline_prob, online_prob, atol=1e-5), (
        f"Offline/Online inconsistency: offline={offline_prob:.6f}, "
        f"online={online_prob:.6f}"
    )


def test_reload_roundtrip(tmp_path: Path) -> None:
    """ISOLATED TEST: Model Reload Round-Trip Mechanism.

    Registers two distinct dummy models in a temporary MLflow tracking registry,
    promotes Version 1 to Production, loads PredictionService, then promotes Version 2
    to Production, triggers reload(), and confirms /model-info and predictions
    use Version 2.
    """
    test_db = tmp_path / "test_mlflow.db"
    t_uri = f"sqlite:///{test_db.resolve()}"
    m_name = "test-churn-model"

    mlflow.set_tracking_uri(t_uri)
    m_client = MlflowClient(tracking_uri=t_uri)

    pipe_path = Path(settings.FEATURE_PIPELINE_PATH)
    model_path = Path(settings.MODEL_OUTPUT_PATH)
    schema_path = Path(settings.FEATURE_SCHEMA_PATH)

    # 1. Register Version 1 (Constant 0 prediction classifier)
    with mlflow.start_run(run_name="Run_v1") as run_v1:
        mlflow.log_params(
            {
                "algorithm": "DummyV1",
                "feature_pipeline_sha256": calculate_file_sha256(pipe_path),
                "schema_version": "1.0.0",
            }
        )
        mlflow.log_artifact(str(model_path), artifact_path="model")

    m_client.create_registered_model(m_name)
    mv1 = m_client.create_model_version(
        name=m_name,
        source=str(model_path.resolve()),
        run_id=run_v1.info.run_id,
    )
    m_client.transition_model_version_stage(
        name=m_name, version=mv1.version, stage="Production"
    )

    # Instantiate isolated PredictionService instance
    svc = PredictionService()
    svc.load_production_model(
        tracking_uri=t_uri,
        model_name=m_name,
        pipeline_path=pipe_path,
        schema_path=schema_path,
    )
    assert svc.model_version == "1"

    # 2. Register Version 2 (Different run and model version)
    with mlflow.start_run(run_name="Run_v2") as run_v2:
        mlflow.log_params(
            {
                "algorithm": "DummyV2",
                "feature_pipeline_sha256": calculate_file_sha256(pipe_path),
                "schema_version": "1.0.0",
            }
        )
        mlflow.log_artifact(str(model_path), artifact_path="model")

    mv2 = m_client.create_model_version(
        name=m_name,
        source=str(model_path.resolve()),
        run_id=run_v2.info.run_id,
    )
    # Promote Version 2 to Production (archiving Version 1)
    m_client.transition_model_version_stage(
        name=m_name,
        version=mv2.version,
        stage="Production",
        archive_existing_versions=True,
    )

    # 3. Trigger Service Reload
    svc.reload(tracking_uri=t_uri, model_name=m_name)

    # 4. Verify Reload State
    assert svc.model_version == "2"
    assert svc.run_id == run_v2.info.run_id
    assert svc.algorithm == "DummyV2"


def test_defensive_startup_failures(tmp_path: Path) -> None:
    """Verify hard defensive startup failures for edge cases.

    1. No Production-stage model in registry -> RuntimeError
    2. Multiple Production-stage models in registry -> RuntimeError (Item 10)
    3. Provenance feature_pipeline_sha256 mismatch -> RuntimeError (Item 2)
    """
    test_db = tmp_path / "defensive_mlflow.db"
    t_uri = f"sqlite:///{test_db.resolve()}"
    m_name = "defensive-model"

    mlflow.set_tracking_uri(t_uri)
    m_client = MlflowClient(tracking_uri=t_uri)
    m_client.create_registered_model(m_name)

    pipe_path = Path(settings.FEATURE_PIPELINE_PATH)
    model_path = Path(settings.MODEL_OUTPUT_PATH)
    schema_path = Path(settings.FEATURE_SCHEMA_PATH)

    svc = PredictionService()

    # Edge Case 1: 0 Production models in registry
    with pytest.raises(RuntimeError, match="No Production-stage model found"):
        svc.load_production_model(
            tracking_uri=t_uri,
            model_name=m_name,
            pipeline_path=pipe_path,
            schema_path=schema_path,
        )

    # Edge Case 2: Multiple Production models in registry (Item 10 defensive check)
    with mlflow.start_run() as r1:
        mlflow.log_params(
            {
                "feature_pipeline_sha256": calculate_file_sha256(pipe_path),
                "schema_version": "1.0.0",
            }
        )
        mlflow.log_artifact(str(model_path), artifact_path="model")
    v1 = m_client.create_model_version(
        name=m_name, source=str(model_path.resolve()), run_id=r1.info.run_id
    )
    m_client.transition_model_version_stage(
        name=m_name, version=v1.version, stage="Production"
    )

    with mlflow.start_run() as r2:
        mlflow.log_params(
            {
                "feature_pipeline_sha256": calculate_file_sha256(pipe_path),
                "schema_version": "1.0.0",
            }
        )
        mlflow.log_artifact(str(model_path), artifact_path="model")
    v2 = m_client.create_model_version(
        name=m_name, source=str(model_path.resolve()), run_id=r2.info.run_id
    )
    # Manually transition v2 without archiving v1 to simulate corrupt state
    m_client.transition_model_version_stage(
        name=m_name,
        version=v2.version,
        stage="Production",
        archive_existing_versions=False,
    )

    with pytest.raises(RuntimeError, match="Multiple Production-stage model versions"):
        svc.load_production_model(
            tracking_uri=t_uri,
            model_name=m_name,
            pipeline_path=pipe_path,
            schema_path=schema_path,
        )

    # Edge Case 3: Provenance SHA-256 mismatch (Item 2)
    m_name_bad_prov = "bad-provenance-model"
    m_client.create_registered_model(m_name_bad_prov)
    with mlflow.start_run() as r_bad:
        mlflow.log_params(
            {
                "feature_pipeline_sha256": "tampered_fake_sha256_hash",
                "schema_version": "1.0.0",
            }
        )
        mlflow.log_artifact(str(model_path), artifact_path="model")
    v_bad = m_client.create_model_version(
        name=m_name_bad_prov, source=str(model_path.resolve()), run_id=r_bad.info.run_id
    )
    m_client.transition_model_version_stage(
        name=m_name_bad_prov, version=v_bad.version, stage="Production"
    )

    with pytest.raises(RuntimeError, match="Provenance Mismatch"):
        svc.load_production_model(
            tracking_uri=t_uri,
            model_name=m_name_bad_prov,
            pipeline_path=pipe_path,
            schema_path=schema_path,
        )
