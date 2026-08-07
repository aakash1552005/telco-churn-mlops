"""Centralized typed configuration using Pydantic Settings."""

from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # Core & Logging Settings
    PROJECT_NAME: str = "telco-churn-mlops"
    ENVIRONMENT: str = Field(
        ...,
        description=(
            "Application environment (e.g. development, staging, production)."
        ),
    )
    LOG_LEVEL: str = "INFO"

    # API & Security Settings (Section 11)
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_SECRET_KEYS: List[str] = Field(default_factory=lambda: ["dev-secret-key-123"])
    RATE_LIMIT_PER_MINUTE: str = "60/minute"
    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:8000",
        ]
    )

    # MLflow & Model Registry Settings
    MLFLOW_TRACKING_URI: str = "http://localhost:5000"
    MLFLOW_EXPERIMENT_NAME: str = "telco-churn-prediction"
    MLFLOW_MODEL_NAME: str = "telco-churn-model"

    # DVC Data Versioning Settings
    DVC_REMOTE_NAME: str = "local_remote"
    DVC_REMOTE_URL: str = "data/dvc_remote"

    # AWS Cloud & ECR Settings
    AWS_REGION: str = "us-east-1"
    ECR_REPOSITORY_NAME: str = "telco-churn-api"

    # Promotion Policy Thresholds (Master Contract Section 9)
    PROMOTION_MIN_F1_DELTA: float = 0.01
    PROMOTION_MAX_PRECISION_DROP: float = 0.02
    PROMOTION_ALLOW_RECALL_DECREASE: bool = False

    # Drift & Retraining Policy Thresholds (Master Contract Section 10)
    DRIFT_FEATURE_PSI_THRESHOLD: float = 0.2
    DRIFT_EVIDENTLY_SCORE_THRESHOLD: float = 0.15
    DRIFT_CONFIDENCE_THRESHOLD: float = 0.75
    DRIFT_CONSECUTIVE_WINDOWS: int = 3


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Singleton getter for application settings."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
