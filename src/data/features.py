"""Feature Engineering Module for Telco Customer Churn Pipeline.

IMPORTANT SCOPE NOTE: This module operates strictly on already-validated data
produced by Phase 4 (Ingestion) and validated by Phase 5 (Validation).
It is NOT a general-purpose validator substitute.

This module constructs a deterministic, scikit-learn compatible feature engineering
pipeline that performs TotalCharges numeric conversion, blank string imputation,
derived feature engineering, categorical one-hot encoding, and numerical scaling.
"""

import subprocess
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple

import joblib
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)

# Define categorical and numerical feature groups
CATEGORICAL_FEATURES: List[str] = [
    "gender",
    "Partner",
    "Dependents",
    "PhoneService",
    "MultipleLines",
    "InternetService",
    "OnlineSecurity",
    "OnlineBackup",
    "DeviceProtection",
    "TechSupport",
    "StreamingTV",
    "StreamingMovies",
    "Contract",
    "PaperlessBilling",
    "PaymentMethod",
]

NUMERICAL_FEATURES: List[str] = [
    "SeniorCitizen",
    "tenure",
    "MonthlyCharges",
    "TotalCharges",
]

TARGET_COLUMN: str = "Churn"


class TotalChargesImputer(BaseEstimator, TransformerMixin):
    """Custom transformer to convert TotalCharges from string to float and impute.

    DOMAN REASONING FOR IMPUTATION:
    The raw IBM Telco Churn dataset contains 11 rows where TotalCharges is a blank
    string (" "). In all 11 cases, these customers have tenure == 0 (new customers
    who joined in the current billing cycle and have not completed their first month).
    Therefore, setting TotalCharges to 0.0 is the mathematically correct and
    domain-justified imputation value.
    """

    def fit(self, X: pd.DataFrame, y: Any = None) -> "TotalChargesImputer":
        """Fit method (stateless transformer)."""
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Clean and convert TotalCharges column to float64."""
        X_out = X.copy()
        if "TotalCharges" in X_out.columns:
            # Replace whitespace-only strings with "0.0" and convert to float
            total_charges_clean = (
                X_out["TotalCharges"].astype(str).str.strip().replace("", "0.0")
            )
            X_out["TotalCharges"] = total_charges_clean.astype(float)
        return X_out


class DerivedFeatureEngineer(BaseEstimator, TransformerMixin):
    """Transformer for constructing domain-specific derived features."""

    def fit(self, X: pd.DataFrame, y: Any = None) -> "DerivedFeatureEngineer":
        """Fit method (stateless transformer)."""
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Create derived ratio and indicator features."""
        X_out = X.copy()

        # Derived feature 1: Total-to-monthly charge ratio
        # (Measures effective tenure length represented by payments)
        if "TotalCharges" in X_out.columns and "MonthlyCharges" in X_out.columns:
            X_out["charge_ratio"] = X_out["TotalCharges"] / (
                X_out["MonthlyCharges"] + 1e-5
            )

        # Derived feature 2: Tenure in years
        if "tenure" in X_out.columns:
            X_out["tenure_years"] = X_out["tenure"] / 12.0

        # Derived feature 3: Month-to-month contract flag
        if "Contract" in X_out.columns:
            X_out["is_monthly_contract"] = (
                X_out["Contract"] == "Month-to-month"
            ).astype(int)

        # Derived feature 4: Internet service presence flag
        if "InternetService" in X_out.columns:
            X_out["has_internet"] = (X_out["InternetService"] != "No").astype(int)

        return X_out


def build_feature_pipeline() -> Pipeline:
    """Construct complete scikit-learn feature engineering Pipeline.

    Returns:
        Unfitted scikit-learn Pipeline object combining imputation, feature
        derivation, categorical encoding, and numerical scaling.
    """
    derived_num_cols = NUMERICAL_FEATURES + [
        "charge_ratio",
        "tenure_years",
        "is_monthly_contract",
        "has_internet",
    ]

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL_FEATURES,
            ),
            ("num", StandardScaler(), derived_num_cols),
        ]
    )

    pipeline = Pipeline(
        steps=[
            ("total_charges_imputer", TotalChargesImputer()),
            ("derived_feature_engineer", DerivedFeatureEngineer()),
            ("column_preprocessor", preprocessor),
        ]
    )
    return pipeline


def run_dvc_add_processed(processed_dir: Path) -> None:
    """Run real dvc add CLI subprocess to track data/processed/ directory."""
    logger.info("Executing real 'dvc add' CLI on processed dataset directory...")
    cmd = [sys.executable, "-m", "dvc", "add", str(processed_dir)]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        logger.warning(
            f"'dvc add' CLI returned exit code {res.returncode}. "
            f"Output: {res.stderr}"
        )
    else:
        logger.info(f"Successfully added '{processed_dir}' to DVC tracking.")


def process_and_save_features(
    raw_df: pd.DataFrame,
    processed_dir: Optional[Path] = None,
    pipeline_path: Optional[Path] = None,
    test_size: Optional[float] = None,
    random_state: Optional[int] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, Pipeline]:
    """Execute feature engineering pipeline with strict train-test split.

    Args:
        raw_df: Raw input DataFrame.
        processed_dir: Directory to store processed CSVs.
        pipeline_path: File path to serialize feature pipeline.
        test_size: Test split ratio.
        random_state: Random state seed.

    Returns:
        Tuple of (X_train_proc, X_test_proc, y_train, y_test, fitted_pipeline).
    """
    settings = get_settings()
    out_dir = processed_dir or Path(settings.PROCESSED_DATA_DIR)
    pipe_path = pipeline_path or Path(settings.FEATURE_PIPELINE_PATH)
    t_size = test_size or settings.TEST_SIZE
    r_state = random_state or settings.RANDOM_STATE

    logger.info(
        "Starting Feature Engineering Pipeline execution",
        extra={
            "total_rows": len(raw_df),
            "test_size": t_size,
            "random_state": r_state,
        },
    )

    # Separate target variable Churn (convert "Yes"/"No" to 1/0 binary numeric)
    X = raw_df.drop(columns=[TARGET_COLUMN, "customerID"], errors="ignore")
    y = (raw_df[TARGET_COLUMN] == "Yes").astype(int)

    # Train-Test Split BEFORE fitting any transformer (STRICT ANTI-LEAKAGE)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=t_size, random_state=r_state, stratify=y
    )

    logger.info(
        f"Train/Test split completed: X_train={len(X_train)} rows, "
        f"X_test={len(X_test)} rows"
    )

    # Build and FIT pipeline ONLY on X_train
    pipeline = build_feature_pipeline()
    logger.info("Fitting feature pipeline exclusively on X_train (anti-leakage)...")
    X_train_transformed = pipeline.fit_transform(X_train)

    # TRANSFORM X_test using fitted pipeline
    logger.info("Transforming X_test using fitted pipeline...")
    X_test_transformed = pipeline.transform(X_test)

    # Retrieve feature names from ColumnTransformer step
    col_transformer: ColumnTransformer = pipeline.named_steps["column_preprocessor"]
    cat_encoder: OneHotEncoder = col_transformer.named_transformers_["cat"]
    cat_feature_names = cat_encoder.get_feature_names_out(CATEGORICAL_FEATURES)
    num_feature_names = col_transformer.transformers[1][2]
    all_feature_names = list(cat_feature_names) + list(num_feature_names)

    X_train_proc = pd.DataFrame(
        X_train_transformed, columns=all_feature_names, index=X_train.index
    )
    X_test_proc = pd.DataFrame(
        X_test_transformed, columns=all_feature_names, index=X_test.index
    )

    # Add target column back for saved processed datasets
    train_out = X_train_proc.copy()
    train_out[TARGET_COLUMN] = y_train.values

    test_out = X_test_proc.copy()
    test_out[TARGET_COLUMN] = y_test.values

    # Save processed datasets
    out_dir.mkdir(parents=True, exist_ok=True)
    train_csv = out_dir / "train.csv"
    test_csv = out_dir / "test.csv"

    train_out.to_csv(train_csv, index=False)
    test_out.to_csv(test_csv, index=False)
    logger.info(f"Saved processed train dataset to: {train_csv}")
    logger.info(f"Saved processed test dataset to: {test_csv}")

    # Serialize feature pipeline using joblib
    pipe_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, pipe_path)
    logger.info(f"Serialized fitted feature pipeline artifact to: {pipe_path}")

    # Update DVC tracking on data/processed
    run_dvc_add_processed(out_dir)

    return X_train_proc, X_test_proc, y_train, y_test, pipeline


if __name__ == "__main__":
    raw_csv_path = Path(get_settings().RAW_DATA_PATH)
    if raw_csv_path.exists():
        df_raw = pd.read_csv(raw_csv_path)
        process_and_save_features(df_raw)
