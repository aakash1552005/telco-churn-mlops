"""Centralized typed configuration using Pydantic Settings."""

from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.example"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # Core & Logging Settings
    PROJECT_NAME: str = "telco-churn-mlops"
    ENVIRONMENT: str = Field(
        ...,
        description=("Deployment environment: 'development', 'staging', 'production'"),
    )
    LOG_LEVEL: str = Field(
        default="INFO", description="Logging level: DEBUG, INFO, WARNING, ERROR"
    )

    # Data Ingestion Settings (Master Contract Section 4)
    RAW_DATA_SOURCE_TYPE: str = Field(
        default="url",
        description="Source type for raw dataset: 'url' or 'local'",
    )
    RAW_DATA_LOCATION: str = Field(
        default=(
            "https://raw.githubusercontent.com/IBM/"
            "telco-customer-churn-on-icp4d/master/data/Telco-Customer-Churn.csv"
        ),
        description="Source URL or local path for raw dataset",
    )
    RAW_DATA_PATH: str = Field(
        default="data/raw/telco_churn.csv",
        description="Target destination path for raw dataset CSV",
    )

    # Data Validation Settings (Master Contract Section 5)
    SCHEMA_FILE_PATH: str = Field(
        default="src/data/schema.yaml",
        description="Path to validation schema YAML configuration file",
    )
    VALIDATION_REPORT_PATH: str = Field(
        default="reports/validation_report.json",
        description="Destination path for JSON validation report artifact",
    )

    # Feature Engineering Settings (Master Contract Section 6)
    PROCESSED_DATA_DIR: str = Field(
        default="data/processed",
        description="Directory path for storing processed train/test datasets",
    )
    FEATURE_PIPELINE_PATH: str = Field(
        default="models/feature_pipeline.joblib",
        description="Destination path for serialized feature pipeline artifact",
    )
    TEST_SIZE: float = Field(
        default=0.2,
        description="Test split ratio for train/test dataset splitting",
    )
    RANDOM_STATE: int = Field(
        default=42,
        description="Random seed for deterministic data splitting",
    )

    # Model Training Settings (Master Contract Section 7)
    FEATURE_SCHEMA_PATH: str = Field(
        default="models/feature_schema.json",
        description="Destination path for ordered feature schema JSON artifact",
    )
    MODEL_OUTPUT_PATH: str = Field(
        default="models/best_model.joblib",
        description="Destination path for serialized winning model artifact",
    )
    TRAINING_METRICS_PATH: str = Field(
        default="reports/training_metrics.json",
        description="Destination path for model training evaluation metrics report",
    )
    CV_RESULTS_PATH: str = Field(
        default="reports/cv_results.csv",
        description="Destination path for cross-validation search results CSV",
    )
    TRAINING_METADATA_PATH: str = Field(
        default="models/training_metadata.json",
        description="Destination path for training provenance metadata JSON artifact",
    )
    CV_FOLDS: int = Field(
        default=5,
        description="Number of folds for StratifiedKFold cross-validation",
    )
    MODEL_SEARCH_ITERATIONS: int = Field(
        default=20,
        description="Number of parameter settings sampled in RandomizedSearchCV",
    )

    # Phase 8 — Model Evaluation Settings
    EVALUATION_METRICS_PATH: str = Field(
        default="reports/evaluation_metrics.json",
        description=(
            "Destination path for consolidated model evaluation metrics report JSON"
        ),
    )
    DECISION_THRESHOLD_PATH: str = Field(
        default="models/decision_threshold.json",
        description="Destination path for optimal decision threshold JSON artifact",
    )
    CLASSIFICATION_REPORT_PATH: str = Field(
        default="reports/classification_report.json",
        description="Destination path for detailed classification report JSON artifact",
    )
    CALIBRATION_METRICS_PATH: str = Field(
        default="reports/calibration_metrics.json",
        description="Destination path for model calibration metrics JSON artifact",
    )
    FEATURE_IMPORTANCE_PATH: str = Field(
        default="reports/feature_importance.csv",
        description="Destination path for feature importances CSV artifact",
    )
    ERROR_ANALYSIS_PATH: str = Field(
        default="reports/error_analysis.csv",
        description="Destination path for error analysis CSV artifact",
    )
    PLOTS_DIR: str = Field(
        default="reports/plots",
        description="Destination directory for model evaluation visualization plots",
    )

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
    MLFLOW_TRACKING_URI: str = "sqlite:///mlflow.db"
    MLFLOW_EXPERIMENT_NAME: str = "telco-churn-prediction"
    MLFLOW_MODEL_NAME: str = "telco-churn-model"
    PROMOTION_POLICY_PATH: str = Field(
        default="models/promotion_policy.json",
        description="Path to versioned model promotion policy JSON artifact",
    )

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
