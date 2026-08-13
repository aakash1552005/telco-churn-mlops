"""Automated Container Smoke Test Script for CI/CD (Phase 11 / Phase 14).

Queries the running containerized prediction service endpoint, asserts
http 200 status, schema compliance, probability, decision, and exact
optimal decision threshold verification (threshold_used == 0.3254).
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, cast


def wait_for_readiness(base_url: str, max_retries: int = 10) -> None:
    """Poll readiness probe until service initializes."""
    url = f"{base_url.rstrip('/')}/health/readiness"
    print(f"Polling readiness probe at {url}...")
    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.getcode() == 200:
                    print(f"Service ready! (attempt {attempt}/{max_retries})")
                    return
        except Exception:
            time.sleep(2)
    print(f"WARNING: Service at {url} did not respond within {max_retries * 2}s.")


def run_smoke_test(
    base_url: str = "http://localhost:8001",
    api_key: str = "dev-secret-key-123",
) -> Dict[str, Any]:
    """Execute container smoke test against prediction endpoint."""
    wait_for_readiness(base_url)
    url = f"{base_url.rstrip('/')}/predict"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
    }
    payload = {
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

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status_code = resp.getcode()
            response_bytes = resp.read()
            data = json.loads(response_bytes.decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}")
        sys.exit(1)
    except Exception as e:
        print(f"Connection Error: {e}")
        sys.exit(1)

    print(f"HTTP Status: {status_code}")
    print(f"Response Payload: {json.dumps(data, indent=2)}")

    # Programmatic assertions
    assert status_code == 200, f"Expected 200 OK, got {status_code}"
    assert "probability" in data, "Missing 'probability' key"
    assert (
        0.0 <= data["probability"] <= 1.0
    ), f"Invalid probability: {data['probability']}"
    assert "decision" in data, "Missing 'decision' key"
    assert data["decision"] in [
        "Churn",
        "No Churn",
    ], f"Invalid decision: {data['decision']}"
    assert "churn_predicted" in data, "Missing 'churn_predicted' key"
    assert "threshold_used" in data, "Missing 'threshold_used' key"

    # Strict assertion for optimal threshold contract
    expected_threshold = 0.3254
    actual_threshold = float(data["threshold_used"])
    err_msg = (
        f"Threshold mismatch! Expected {expected_threshold}, got {actual_threshold}"
    )
    assert abs(actual_threshold - expected_threshold) < 1e-4, err_msg

    msg = (
        "SUCCESS: All smoke test assertions passed! "
        f"(threshold_used={actual_threshold})"
    )
    print(msg)
    return cast(Dict[str, Any], data)


if __name__ == "__main__":
    host_port = os.getenv("TEST_SERVICE_URL", "http://localhost:8001")
    api_key_val = os.getenv("API_KEY", "dev-secret-key-123")
    run_smoke_test(base_url=host_port, api_key=api_key_val)
