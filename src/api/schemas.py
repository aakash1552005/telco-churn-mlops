"""Pydantic schemas for FastAPI prediction service request and response validation.

Validates raw input fields against Phase 5 domain rules (e.g. tenure >= 0,
MonthlyCharges >= 0, categorical allowed values) and defines standardized
JSON output contracts.
"""

from typing import Any, Dict, Literal, Optional, Union

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    """Pydantic request payload schema validating raw Telco customer input fields."""

    customerID: Optional[str] = Field(
        default=None, description="Optional customer identifier string"
    )
    gender: Literal["Female", "Male"] = Field(
        ..., description="Customer gender: 'Female' or 'Male'"
    )
    SeniorCitizen: int = Field(
        ..., ge=0, le=1, description="Binary senior citizen indicator (0 or 1)"
    )
    Partner: Literal["Yes", "No"] = Field(
        ..., description="Whether customer has a partner ('Yes' or 'No')"
    )
    Dependents: Literal["Yes", "No"] = Field(
        ..., description="Whether customer has dependents ('Yes' or 'No')"
    )
    tenure: int = Field(
        ...,
        ge=0,
        description="Number of months customer has stayed with company (>= 0)",
    )
    PhoneService: Literal["Yes", "No"] = Field(
        ..., description="Whether customer has phone service ('Yes' or 'No')"
    )
    MultipleLines: Literal["Yes", "No", "No phone service"] = Field(
        ..., description="Multiple lines status"
    )
    InternetService: Literal["DSL", "Fiber optic", "No"] = Field(
        ..., description="Internet service provider option"
    )
    OnlineSecurity: Literal["Yes", "No", "No internet service"] = Field(
        ..., description="Online security add-on status"
    )
    OnlineBackup: Literal["Yes", "No", "No internet service"] = Field(
        ..., description="Online backup add-on status"
    )
    DeviceProtection: Literal["Yes", "No", "No internet service"] = Field(
        ..., description="Device protection add-on status"
    )
    TechSupport: Literal["Yes", "No", "No internet service"] = Field(
        ..., description="Tech support add-on status"
    )
    StreamingTV: Literal["Yes", "No", "No internet service"] = Field(
        ..., description="Streaming TV add-on status"
    )
    StreamingMovies: Literal["Yes", "No", "No internet service"] = Field(
        ..., description="Streaming movies add-on status"
    )
    Contract: Literal["Month-to-month", "One year", "Two year"] = Field(
        ..., description="Contract term duration"
    )
    PaperlessBilling: Literal["Yes", "No"] = Field(
        ..., description="Paperless billing option ('Yes' or 'No')"
    )
    PaymentMethod: Literal[
        "Electronic check",
        "Mailed check",
        "Bank transfer (automatic)",
        "Credit card (automatic)",
    ] = Field(..., description="Payment method category")
    MonthlyCharges: float = Field(
        ..., ge=0.0, description="Monthly charge amount (>= 0.0)"
    )
    TotalCharges: Union[str, float] = Field(
        ..., description="Total charges amount as string or float"
    )


class PredictResponse(BaseModel):
    """Pydantic response payload schema for churn prediction endpoints."""

    customerID: Optional[str] = Field(
        default=None, description="Customer ID if provided"
    )
    probability: float = Field(
        ..., ge=0.0, le=1.0, description="Raw predicted churn probability [0.0, 1.0]"
    )
    decision: str = Field(
        ..., description="Thresholded churn decision label ('Churn' or 'No Churn')"
    )
    churn_predicted: bool = Field(
        ..., description="Boolean decision flag (True if probability >= threshold)"
    )
    threshold_used: float = Field(..., description="Optimal decision threshold applied")
    model_version: str = Field(
        ..., description="MLflow Registry Production model version tag"
    )


class HealthResponse(BaseModel):
    """Health probe status response schema."""

    status: str = Field(..., description="Overall health status string ('healthy')")
    service: str = Field(..., description="Service identifier name")
    environment: str = Field(..., description="Active deployment environment")
    timestamp: str = Field(..., description="UTC ISO-8601 timestamp")
    model_loaded: bool = Field(
        ..., description="Whether model is initialized and ready"
    )
    model_version: str = Field(..., description="Active Production model version")


class VersionResponse(BaseModel):
    """API version info response schema."""

    version: str = Field(..., description="Semantic version string")
    project_name: str = Field(..., description="Project repository name")
    environment: str = Field(..., description="Deployment environment")


class ModelInfoResponse(BaseModel):
    """Production model metadata and provenance response schema."""

    model_name: str = Field(..., description="MLflow registered model name")
    model_version: str = Field(..., description="MLflow Production model version")
    run_id: str = Field(..., description="Parent MLflow run ID")
    algorithm: str = Field(..., description="Fitted estimator algorithm name")
    optimal_threshold: float = Field(
        ..., description="Active decision threshold applied for inference"
    )
    loaded_at: str = Field(..., description="ISO timestamp when model was loaded")
    provenance: Dict[str, Any] = Field(
        ..., description="Data, git commit, and feature pipeline provenance tags"
    )


class ReloadResponse(BaseModel):
    """Response schema for model reload endpoint."""

    status: str = Field(..., description="Status of reload operation ('success')")
    message: str = Field(..., description="Detailed description of reload outcome")
    model_version: str = Field(..., description="Newly loaded Production model version")
