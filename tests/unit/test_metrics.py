"""Unit tests for Prometheus metrics collection and exposition."""

import re
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.config import get_settings
from src.inference.service import prediction_service

settings = get_settings()
TEST_API_KEY = "dev-secret-key-12345"


@pytest.fixture(scope="module", autouse=True)
def ensure_production_model_loaded() -> None:
    """Ensure prediction service has loaded real Production model prior to tests."""
    try:
        prediction_service.load_production_model()
    except Exception as e:
        pytest.skip(
            f"Skipping metrics tests: Production model not available in MLflow: {e}"
        )


def test_metrics_endpoint_exposition_format() -> None:
    """Verify /metrics returns 200 with valid Prometheus exposition types."""
    app = create_app()
    with TestClient(app) as client:
        # Trigger at least one request so request histogram observations exist
        client.get("/health")

        res = client.get("/metrics")
        assert res.status_code == 200
        assert "text/plain" in res.headers["content-type"]
        body = res.text

        # Verify exact required # TYPE declarations
        assert "# TYPE telco_predictions_total counter" in body
        assert "# TYPE telco_api_errors_total counter" in body
        assert "# TYPE telco_request_duration_seconds histogram" in body
        assert "# TYPE telco_model_info gauge" in body
        assert "# TYPE telco_drift_score gauge" in body
        assert "# TYPE telco_drift_detected gauge" in body
        assert "# TYPE telco_drift_consecutive_windows gauge" in body

        # Verify histogram series structure (_bucket, _sum, _count)
        assert "telco_request_duration_seconds_bucket{" in body
        assert "telco_request_duration_seconds_sum{" in body
        assert "telco_request_duration_seconds_count{" in body

        # Verify process/Python metrics are exposed
        assert (
            "process_cpu_seconds_total" in body
            or "python_gc_objects_collected_total" in body
            or "process_resident_memory_bytes" in body
        )


def test_drift_metrics_exposed_as_gauge() -> None:
    """Verify update_drift_metrics updates all drift gauges."""
    from src.api.metrics import update_drift_metrics

    update_drift_metrics(score=0.1845, detected=True, consecutive_windows=2)

    app = create_app()
    with TestClient(app) as client:
        res = client.get("/metrics")
        assert res.status_code == 200
        body = res.text

        assert "telco_drift_score 0.1845" in body
        assert "telco_drift_detected 1.0" in body
        assert "telco_drift_consecutive_windows 2.0" in body


def test_predictions_metric_increments_on_predict(
    sample_valid_payload: Dict[str, Any],
) -> None:
    """Verify /predict increments telco_predictions_total with bounded label."""
    app = create_app()
    with TestClient(app) as client:
        # Get baseline metrics
        res_before = client.get("/metrics")
        assert res_before.status_code == 200

        # Execute prediction
        headers = {"X-API-Key": TEST_API_KEY}
        res_pred = client.post("/predict", json=sample_valid_payload, headers=headers)
        assert res_pred.status_code == 200
        decision = res_pred.json()["decision"]
        assert decision in ("Churn", "No Churn")

        # Get updated metrics
        res_after = client.get("/metrics")
        assert res_after.status_code == 200
        body_after = res_after.text

        # Assert counter incremented for the specific decision
        expected_metric = f'telco_predictions_total{{decision="{decision}"}}'
        assert expected_metric in body_after

        # Strict check: ensure customerID is NOT a label (cardinality protection)
        assert 'customerID="' not in body_after
        assert "7590-VHVEG" not in body_after


def test_api_errors_metric_increments_on_4xx() -> None:
    """Verify 4xx responses increment telco_api_errors_total{status_class='4xx'}."""
    app = create_app()
    with TestClient(app) as client:
        # Trigger 401 Unauthorized
        res_unauth = client.post("/predict", json={}, headers={"X-API-Key": "invalid"})
        assert res_unauth.status_code == 401

        # Check metrics
        res_metrics = client.get("/metrics")
        assert res_metrics.status_code == 200
        assert 'telco_api_errors_total{status_class="4xx"}' in res_metrics.text


def test_model_info_metric_matches_production_version() -> None:
    """Verify telco_model_info gauge reflects active Production model version."""
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/metrics")
        assert res.status_code == 200
        active_ver = prediction_service.model_version

        # Info metric gauge pattern: telco_model_info{version="<ver>"} 1.0
        expected_gauge_pattern = rf'telco_model_info{{version="{active_ver}"}}\s+1\.0'
        assert re.search(expected_gauge_pattern, res.text) is not None
