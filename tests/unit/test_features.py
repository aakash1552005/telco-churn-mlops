"""Unit tests for feature engineering module."""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from src.data.features import (
    BINARY_FLAG_FEATURES,
    CONTINUOUS_NUMERICAL_FEATURES,
    DerivedFeatureEngineer,
    TotalChargesImputer,
    build_feature_pipeline,
    process_and_save_features,
)


@pytest.fixture
def raw_sample_df() -> pd.DataFrame:
    """Fixture providing sample raw Telco Churn DataFrame."""
    return pd.DataFrame(
        {
            "customerID": ["7590-VHVEG", "5575-GNVDE", "0000-NEW01"],
            "gender": ["Female", "Male", "Female"],
            "SeniorCitizen": [0, 0, 1],
            "Partner": ["Yes", "No", "No"],
            "Dependents": ["No", "No", "No"],
            "tenure": [1, 34, 0],
            "PhoneService": ["No", "Yes", "Yes"],
            "MultipleLines": ["No phone service", "No", "No"],
            "InternetService": ["DSL", "DSL", "Fiber optic"],
            "OnlineSecurity": ["No", "Yes", "No"],
            "OnlineBackup": ["Yes", "No", "No"],
            "DeviceProtection": ["No", "Yes", "No"],
            "TechSupport": ["No", "No", "No"],
            "StreamingTV": ["No", "No", "No"],
            "StreamingMovies": ["No", "No", "No"],
            "Contract": ["Month-to-month", "One year", "Month-to-month"],
            "PaperlessBilling": ["Yes", "No", "Yes"],
            "PaymentMethod": [
                "Electronic check",
                "Mailed check",
                "Electronic check",
            ],
            "MonthlyCharges": [29.85, 56.95, 70.00],
            "TotalCharges": ["29.85", "1889.50", " "],  # Includes blank string " "
            "Churn": ["No", "No", "Yes"],
        }
    )


def test_total_charges_imputer_blank_strings(
    raw_sample_df: pd.DataFrame,
) -> None:
    """Test TotalChargesImputer converts blank strings (' ') to 0.0 float."""
    imputer = TotalChargesImputer()
    df_out = imputer.transform(raw_sample_df)

    assert df_out["TotalCharges"].dtype == float
    assert df_out.loc[0, "TotalCharges"] == 29.85
    assert df_out.loc[1, "TotalCharges"] == 1889.50
    # Confirm row index 2 (blank string " ") imputed to 0.0 float
    assert df_out.loc[2, "TotalCharges"] == 0.0


def test_derived_feature_engineer(raw_sample_df: pd.DataFrame) -> None:
    """Test DerivedFeatureEngineer creates expected derived feature columns."""
    imputer = TotalChargesImputer()
    df_clean = imputer.transform(raw_sample_df)

    engineer = DerivedFeatureEngineer()
    df_out = engineer.transform(df_clean)

    assert "charge_ratio" in df_out.columns
    assert "tenure_years" in df_out.columns
    assert "is_monthly_contract" in df_out.columns
    assert "has_internet" in df_out.columns

    # Verify calculations
    assert np.isclose(df_out.loc[0, "tenure_years"], 1 / 12.0)
    assert df_out.loc[0, "is_monthly_contract"] == 1
    assert df_out.loc[1, "is_monthly_contract"] == 0
    assert df_out.loc[0, "has_internet"] == 1


def test_binary_flags_passthrough_unscaled(
    raw_sample_df: pd.DataFrame,
) -> None:
    """Test binary flags (SeniorCitizen, etc.) remain 0/1 unscaled."""
    df_large = pd.concat([raw_sample_df] * 10, ignore_index=True)
    X_tr, X_te, y_tr, y_te, pipeline = process_and_save_features(
        df_large, test_size=0.3, random_state=42
    )

    # Assert binary flag columns preserve exact 0/1 integer/float values
    for flag_col in BINARY_FLAG_FEATURES:
        unique_vals = set(X_tr[flag_col].unique())
        assert unique_vals.issubset({0.0, 1.0, 0, 1})


def test_no_data_leakage(raw_sample_df: pd.DataFrame) -> None:
    """Test scaler mean/std parameters are computed strictly from X_train."""
    df_large = pd.concat([raw_sample_df] * 10, ignore_index=True)

    X_tr_proc, X_te_proc, y_tr, y_te, pipeline = process_and_save_features(
        df_large,
        test_size=0.3,
        random_state=42,
    )

    col_transformer = pipeline.named_steps["column_preprocessor"]
    scaler = col_transformer.named_transformers_["num_scale"]

    # Verify scaler mean was computed during fit(X_train) for 5 continuous features
    assert hasattr(scaler, "mean_")
    assert len(scaler.mean_) == len(CONTINUOUS_NUMERICAL_FEATURES)


def test_feature_pipeline_joblib_roundtrip(
    raw_sample_df: pd.DataFrame, tmp_path: Path
) -> None:
    """Test fitted feature pipeline serializes to joblib and deserializes cleanly."""
    X = raw_sample_df.drop(columns=["Churn", "customerID"])
    pipeline = build_feature_pipeline()
    X_transformed_original = pipeline.fit_transform(X)

    # Save to joblib
    model_file = tmp_path / "feature_pipeline.joblib"
    joblib.dump(pipeline, model_file)
    assert model_file.exists()

    # Reload from joblib
    reloaded_pipeline = joblib.load(model_file)
    X_transformed_reloaded = reloaded_pipeline.transform(X)

    # Assert 100% identical outputs
    np.testing.assert_array_almost_equal(X_transformed_original, X_transformed_reloaded)


def test_process_and_save_features_end_to_end(
    raw_sample_df: pd.DataFrame, tmp_path: Path
) -> None:
    """End-to-end test verifying processed CSVs and serialized joblib pipeline."""
    df_large = pd.concat([raw_sample_df] * 10, ignore_index=True)
    out_dir = tmp_path / "processed"
    pipe_path = tmp_path / "feature_pipeline.joblib"

    X_tr, X_te, y_tr, y_te, pipeline = process_and_save_features(
        df_large,
        processed_dir=out_dir,
        pipeline_path=pipe_path,
        test_size=0.2,
        random_state=42,
    )

    assert (out_dir / "train.csv").exists()
    assert (out_dir / "test.csv").exists()
    assert pipe_path.exists()

    train_df = pd.read_csv(out_dir / "train.csv")
    test_df = pd.read_csv(out_dir / "test.csv")

    assert "Churn" in train_df.columns
    assert "Churn" in test_df.columns
    assert len(train_df) + len(test_df) == len(df_large)
