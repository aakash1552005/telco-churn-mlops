"""FastAPI route handlers for Telco Customer Churn Prediction Service."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse

from src.api.schemas import (
    HealthResponse,
    ModelInfoResponse,
    PredictRequest,
    PredictResponse,
    ReloadResponse,
    VersionResponse,
)
from src.api.security import verify_api_key
from src.core.config import get_settings
from src.core.logging import get_logger
from src.inference.service import prediction_service

logger = get_logger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["Health"])
def get_health() -> HealthResponse:
    """Overall service health status probe."""
    settings = get_settings()
    is_loaded = (
        prediction_service.model is not None
        and prediction_service.feature_pipeline is not None
    )
    return HealthResponse(
        status="healthy" if is_loaded else "degraded",
        service=settings.PROJECT_NAME,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.now(timezone.utc).isoformat(),
        model_loaded=is_loaded,
        model_version=prediction_service.model_version,
    )


@router.get("/health/liveness", tags=["Health"])
def get_liveness() -> dict[str, str]:
    """Liveness probe (returns 200 if process is running)."""
    return {"status": "alive"}


@router.get("/health/readiness", tags=["Health"])
def get_readiness() -> Response:
    """Readiness probe (returns 200 if model & pipeline are loaded, 503 otherwise)."""
    is_ready = (
        prediction_service.model is not None
        and prediction_service.feature_pipeline is not None
    )
    if is_ready:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "ready",
                "model_loaded": True,
                "model_version": prediction_service.model_version,
            },
        )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "not_ready",
            "model_loaded": False,
            "detail": "Prediction service model is not loaded.",
        },
    )


@router.get("/version", response_model=VersionResponse, tags=["System"])
def get_version() -> VersionResponse:
    """Return API version information."""
    settings = get_settings()
    return VersionResponse(
        version="0.1.0",
        project_name=settings.PROJECT_NAME,
        environment=settings.ENVIRONMENT,
    )


@router.get("/metrics", tags=["Observability"])
def get_metrics() -> Response:
    """Prometheus metrics endpoint stub (Phase 15 integration placeholder)."""
    metrics_stub = (
        "# HELP telco_churn_predictions_total Total churn predictions executed.\n"
        "# TYPE telco_churn_predictions_total counter\n"
        'telco_churn_predictions_total{status="success"} 0\n'
        "# HELP telco_churn_model_info Active model version info.\n"
        "# TYPE telco_churn_model_info gauge\n"
        f'telco_churn_model_info{{version="{prediction_service.model_version}"}} 1\n'
    )
    return PlainTextResponse(content=metrics_stub, media_type="text/plain")


@router.post(
    "/predict",
    response_model=PredictResponse,
    tags=["Inference"],
    dependencies=[Depends(verify_api_key)],
)
def predict_churn(
    payload: PredictRequest,
    request: Request,
) -> PredictResponse:
    """Execute customer churn prediction for a raw Telco customer record.

    Validates raw input fields against domain constraints, transforms features using
    models/feature_pipeline.joblib, and applies models/decision_threshold.json.
    """
    try:
        raw_dict = payload.model_dump()
        result = prediction_service.predict(raw_dict)

        # Log prediction outcome metadata (NO PII — no customer field values)
        logger.info(
            "Executed prediction request",
            extra={
                "customerID": result.get("customerID"),
                "probability": result["probability"],
                "decision": result["decision"],
                "model_version": result["model_version"],
                "threshold_used": result["threshold_used"],
            },
        )

        return PredictResponse(
            customerID=result.get("customerID"),
            probability=result["probability"],
            decision=result["decision"],
            churn_predicted=result["churn_predicted"],
            threshold_used=result["threshold_used"],
            model_version=result["model_version"],
        )

    except Exception as e:
        logger.error(f"Prediction execution error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction error: {str(e)}",
        )


@router.get(
    "/model-info",
    response_model=ModelInfoResponse,
    tags=["Model Management"],
    dependencies=[Depends(verify_api_key)],
)
def get_model_info() -> ModelInfoResponse:
    """Return active Production model metadata and provenance."""
    settings = get_settings()
    if prediction_service.model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No Production model currently loaded.",
        )

    return ModelInfoResponse(
        model_name=settings.MLFLOW_MODEL_NAME,
        model_version=prediction_service.model_version,
        run_id=prediction_service.run_id,
        algorithm=prediction_service.algorithm,
        optimal_threshold=prediction_service.optimal_threshold,
        loaded_at=prediction_service.loaded_at,
        provenance=prediction_service.provenance,
    )


@router.post(
    "/reload",
    response_model=ReloadResponse,
    tags=["Model Management"],
    dependencies=[Depends(verify_api_key)],
)
def reload_model() -> ReloadResponse:
    """Reload Production model and threshold without process restart."""
    try:
        prediction_service.reload()
        return ReloadResponse(
            status="success",
            message=(
                f"Successfully reloaded Production model version "
                f"{prediction_service.model_version}."
            ),
            model_version=prediction_service.model_version,
        )
    except Exception as e:
        logger.error(f"Model reload failure: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model reload failed: {str(e)}",
        )
