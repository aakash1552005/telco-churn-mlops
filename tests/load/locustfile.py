"""Headless Locust load test suite for Telco Churn Prediction API (/predict).

Simulates concurrent customer evaluation traffic with realistic feature payloads.
"""

import os
import random
from locust import HttpUser, constant, task

CUSTOMER_PROFILES = [
    # Profile 1: High risk month-to-month DSL user
    {
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
    },
    # Profile 2: Low risk one-year contract loyal customer
    {
        "customerID": "5575-GNVDE",
        "gender": "Male",
        "SeniorCitizen": 0,
        "Partner": "No",
        "Dependents": "No",
        "tenure": 34,
        "PhoneService": "Yes",
        "MultipleLines": "No",
        "InternetService": "DSL",
        "OnlineSecurity": "Yes",
        "OnlineBackup": "No",
        "DeviceProtection": "Yes",
        "TechSupport": "No",
        "StreamingTV": "No",
        "StreamingMovies": "No",
        "Contract": "One year",
        "PaperlessBilling": "No",
        "PaymentMethod": "Mailed check",
        "MonthlyCharges": 56.95,
        "TotalCharges": "1889.5",
    },
    # Profile 3: Moderate risk month-to-month DSL user with backup
    {
        "customerID": "3668-QPYBK",
        "gender": "Male",
        "SeniorCitizen": 0,
        "Partner": "No",
        "Dependents": "No",
        "tenure": 2,
        "PhoneService": "Yes",
        "MultipleLines": "No",
        "InternetService": "DSL",
        "OnlineSecurity": "Yes",
        "OnlineBackup": "Yes",
        "DeviceProtection": "No",
        "TechSupport": "No",
        "StreamingTV": "No",
        "StreamingMovies": "No",
        "Contract": "Month-to-month",
        "PaperlessBilling": "Yes",
        "PaymentMethod": "Mailed check",
        "MonthlyCharges": 53.85,
        "TotalCharges": "108.15",
    },
    # Profile 4: Long tenure one-year contract DSL customer
    {
        "customerID": "7795-CFOCW",
        "gender": "Male",
        "SeniorCitizen": 0,
        "Partner": "No",
        "Dependents": "No",
        "tenure": 45,
        "PhoneService": "No",
        "MultipleLines": "No phone service",
        "InternetService": "DSL",
        "OnlineSecurity": "Yes",
        "OnlineBackup": "No",
        "DeviceProtection": "Yes",
        "TechSupport": "Yes",
        "StreamingTV": "No",
        "StreamingMovies": "No",
        "Contract": "One year",
        "PaperlessBilling": "No",
        "PaymentMethod": "Bank transfer (automatic)",
        "MonthlyCharges": 42.30,
        "TotalCharges": "1840.75",
    },
]


class TelcoChurnUser(HttpUser):
    """Simulated client performing churn predictions against FastAPI backend."""

    # Zero think time so measured throughput strictly reflects server processing capacity
    wait_time = constant(0)

    def on_start(self) -> None:
        """Initialize API key header from environment."""
        api_key = os.environ.get("API_KEY") or os.environ.get("X_API_KEY")
        if not api_key:
            raise ValueError(
                "API_KEY environment variable is required for load testing but was not set."
            )
        self.headers = {
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        }

    @task(10)
    def predict_churn(self) -> None:
        """Send prediction request to /predict endpoint."""
        payload = random.choice(CUSTOMER_PROFILES)
        with self.client.post(
            "/predict",
            json=payload,
            headers=self.headers,
            catch_response=True,
            name="/predict",
        ) as response:
            if response.status_code == 200:
                data = response.json()
                if "churn_probability" in data and "churn_prediction" in data:
                    response.success()
                else:
                    response.failure(f"Missing expected keys in response: {response.text}")
            else:
                response.failure(f"HTTP {response.status_code}: {response.text}")

    @task(1)
    def healthcheck(self) -> None:
        """Periodic readiness probe."""
        self.client.get("/health/readiness", name="/health/readiness")
