"""Prometheus metrics registry and telemetry instrumentation for Telco Churn API.

Exposes Prometheus metrics matching Master Contract specifications:
- telco_request_duration_seconds: Histogram of HTTP request latency in seconds.
- telco_predictions_total: Counter of predictions segmented strictly by decision.
- telco_api_errors_total: Counter of HTTP 4xx and 5xx response error classes.
- telco_model_info: Gauge info-metric representing active Production model version.
- Process-level metrics (CPU, memory, garbage collection) via prometheus_client.
"""

from typing import Dict

from fastapi import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from src.core.logging import get_logger

logger = get_logger(__name__)

# 1. HTTP Request Latency Histogram
# Buckets tailored for REST API performance SLAs from 5ms to 10s
REQUEST_DURATION_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.075,
    0.1,
    0.25,
    0.5,
    0.75,
    1.0,
    2.5,
    5.0,
    7.5,
    10.0,
)

TELCO_REQUEST_DURATION_SECONDS = Histogram(
    "telco_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "endpoint", "status_code"],
    buckets=REQUEST_DURATION_BUCKETS,
)

# 2. Prediction Counter (strictly bounded categorical cardinality: Churn vs No Churn)
# NOTE: NO customerID or per-customer field is included to avoid cardinality explosion
TELCO_PREDICTIONS_TOTAL = Counter(
    "telco_predictions_total",
    "Total number of customer churn predictions executed.",
    ["decision"],
)

# 3. API Error Counter (status classes: 4xx, 5xx)
TELCO_API_ERRORS_TOTAL = Counter(
    "telco_api_errors_total",
    "Total number of API error responses returned to clients.",
    ["status_class"],
)

# 4. Active Model Version Gauge (info metric pattern with value 1.0)
TELCO_MODEL_INFO = Gauge(
    "telco_model_info",
    "Information about the active Production model version currently serving traffic.",
    ["version"],
)

# Track active version label to clear obsolete gauges on model reload
_ACTIVE_VERSION_GAUGES: Dict[str, bool] = {}


def update_model_info(version: str) -> None:
    """Update active model version in Prometheus gauge.

    Args:
        version: Model version identifier string (e.g. '1', '2').
    """
    # Clear prior gauge labels to ensure only 1 version gauge is active at a time
    for old_ver in list(_ACTIVE_VERSION_GAUGES.keys()):
        if old_ver != version:
            try:
                TELCO_MODEL_INFO.remove(old_ver)
            except KeyError:
                pass
            _ACTIVE_VERSION_GAUGES.pop(old_ver, None)

    TELCO_MODEL_INFO.labels(version=str(version)).set(1.0)
    _ACTIVE_VERSION_GAUGES[str(version)] = True
    logger.info(f"Prometheus telco_model_info updated to version='{version}'")


def record_prediction_metric(decision: str) -> None:
    """Record prediction decision in Prometheus counter.

    Args:
        decision: Decision outcome string ('Churn' or 'No Churn').
    """
    valid_decision = decision if decision in ("Churn", "No Churn") else "Unknown"
    TELCO_PREDICTIONS_TOTAL.labels(decision=valid_decision).inc()


def record_api_error_metric(status_code: int) -> None:
    """Record HTTP error in Prometheus error counter if 4xx or 5xx.

    Args:
        status_code: HTTP response status code.
    """
    if 400 <= status_code < 500:
        TELCO_API_ERRORS_TOTAL.labels(status_class="4xx").inc()
    elif 500 <= status_code < 600:
        TELCO_API_ERRORS_TOTAL.labels(status_class="5xx").inc()


def get_metrics_response() -> Response:
    """Generate Prometheus exposition format payload from default registry.

    Returns:
        FastAPI Response with text/plain exposition payload and latest format header.
    """
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )
