"""Unit tests for model training pipeline."""

import json
from pathlib import Path
from typing import Tuple

import joblib
import numpy as np
import pandas as pd
import pytest

from src.training.train import (
    log_class_balance,
    train_candidate_models,
    validate_feature_schema,
)


@pytest.fixture
def synthetic_processed_dataset(tmp_path: Path) -> Tuple[Path, Path, Path]:
    """Fixture producing synthetic train.csv, test.csv, and feature_schema.json."""
    np.random.seed(42)
    n_samples = 100
    n_features = 10

    feature_names = [f"feature_{i}" for i in range(n_features)]
    X_data = np.random.randn(n_samples, n_features)
    y_data = np.random.choice([0, 1], size=n_samples, p=[0.7, 0.3])

    df = pd.DataFrame(X_data, columns=feature_names)
    df["Churn"] = y_data

    train_df = df.iloc[:80].copy()
    test_df = df.iloc[80:].copy()

    processed_dir = tmp_path / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    train_csv = processed_dir / "train.csv"
    test_csv = processed_dir / "test.csv"
    train_df.to_csv(train_csv, index=False)
    test_df.to_csv(test_csv, index=False)

    # Save feature_schema.json
    schema_path = tmp_path / "feature_schema.json"
    schema_payload = {
        "features": feature_names,
        "target": "Churn",
        "feature_count": n_features,
    }
    with open(schema_path, "w", encoding="utf-8") as f:
        json.dump(schema_payload, f, indent=2)

    # Create dummy feature_pipeline.joblib for metadata hash check
    pipeline_path = tmp_path / "feature_pipeline.joblib"
    joblib.dump({"dummy": "pipeline"}, pipeline_path)

    return processed_dir, schema_path, pipeline_path


def test_log_class_balance() -> None:
    """Test log_class_balance calculates correct counts and percentages."""
    y = pd.Series([0, 0, 0, 1, 1])
    stats = log_class_balance(y)

    assert stats["total_samples"] == 5
    assert stats["positive_count"] == 2
    assert stats["negative_count"] == 3
    assert stats["positive_percent"] == 40.0
    assert stats["negative_percent"] == 60.0


def test_validate_feature_schema_success(
    synthetic_processed_dataset: Tuple[Path, Path, Path],
) -> None:
    """Test validate_feature_schema passes on valid matching columns."""
    processed_dir, schema_path, _ = synthetic_processed_dataset
    train_df = pd.read_csv(processed_dir / "train.csv")

    features = validate_feature_schema(train_df, schema_path=schema_path)
    assert len(features) == 10
    assert features[0] == "feature_0"


def test_validate_feature_schema_count_mismatch(
    synthetic_processed_dataset: Tuple[Path, Path, Path],
) -> None:
    """Test validate_feature_schema raises ValueError on missing columns."""
    processed_dir, schema_path, _ = synthetic_processed_dataset
    train_df = pd.read_csv(processed_dir / "train.csv")
    df_missing = train_df.drop(columns=["feature_0"])

    with pytest.raises(ValueError, match="Feature schema count mismatch"):
        validate_feature_schema(df_missing, schema_path=schema_path)


def test_validate_feature_schema_order_mismatch(
    synthetic_processed_dataset: Tuple[Path, Path, Path],
) -> None:
    """Test validate_feature_schema raises ValueError on reordered columns."""
    processed_dir, schema_path, _ = synthetic_processed_dataset
    train_df = pd.read_csv(processed_dir / "train.csv")

    # Reverse feature columns order
    cols = list(train_df.columns)
    cols.reverse()
    df_reordered = train_df[cols]

    with pytest.raises(ValueError, match="Feature schema column order mismatch"):
        validate_feature_schema(df_reordered, schema_path=schema_path)


def test_train_candidate_models_tiny_dataset(
    synthetic_processed_dataset: Tuple[Path, Path, Path], tmp_path: Path
) -> None:
    """Test train_candidate_models runs on tiny synthetic dataset."""
    processed_dir, schema_path, pipeline_path = synthetic_processed_dataset

    out_model = tmp_path / "best_model.joblib"
    out_metrics = tmp_path / "training_metrics.json"
    out_cv = tmp_path / "cv_results.csv"
    out_meta = tmp_path / "training_metadata.json"

    winning_model, metrics, metadata = train_candidate_models(
        processed_dir=processed_dir,
        schema_path=schema_path,
        model_output_path=out_model,
        metrics_output_path=out_metrics,
        cv_results_output_path=out_cv,
        metadata_output_path=out_meta,
        random_state=42,
        n_iter=2,
        n_jobs=1,
    )

    # 1. Check Fitted Estimator Interface Constraints
    # (.predict, .predict_proba, .classes_)
    assert hasattr(winning_model, "predict")
    assert hasattr(winning_model, "predict_proba")
    assert hasattr(winning_model, "classes_")

    # Test predictions capability on sample data
    sample_X = np.random.randn(5, 10)
    preds = winning_model.predict(sample_X)
    probs = winning_model.predict_proba(sample_X)

    assert preds.shape == (5,)
    assert probs.shape == (5, 2)
    assert set(winning_model.classes_) == {0, 1}

    # 2. Check Artifact Persistence
    assert out_model.exists()
    assert out_metrics.exists()
    assert out_cv.exists()
    assert out_meta.exists()

    # 3. Check Metadata Content
    with open(out_meta, "r", encoding="utf-8") as f:
        meta_json = json.load(f)

    assert "algorithm" in meta_json
    assert meta_json["random_seed"] == 42
    assert meta_json["cv_folds"] == 5
    assert "best_hyperparameters" in meta_json
    assert "best_cv_score" in meta_json
    assert meta_json["feature_count"] == 10


def test_train_models_reproducibility(
    synthetic_processed_dataset: Tuple[Path, Path, Path], tmp_path: Path
) -> None:
    """Test re-running training twice with identical seed yields identical metrics."""
    processed_dir, schema_path, _ = synthetic_processed_dataset

    run1_dir = tmp_path / "run1"
    run2_dir = tmp_path / "run2"

    m1, metrics1, meta1 = train_candidate_models(
        processed_dir=processed_dir,
        schema_path=schema_path,
        model_output_path=run1_dir / "model.joblib",
        metrics_output_path=run1_dir / "metrics.json",
        cv_results_output_path=run1_dir / "cv.csv",
        metadata_output_path=run1_dir / "meta.json",
        random_state=42,
        n_iter=3,
        n_jobs=1,
    )

    m2, metrics2, meta2 = train_candidate_models(
        processed_dir=processed_dir,
        schema_path=schema_path,
        model_output_path=run2_dir / "model.joblib",
        metrics_output_path=run2_dir / "metrics.json",
        cv_results_output_path=run2_dir / "cv.csv",
        metadata_output_path=run2_dir / "meta.json",
        random_state=42,
        n_iter=3,
        n_jobs=1,
    )

    assert meta1["algorithm"] == meta2["algorithm"]
    assert meta1["best_hyperparameters"] == meta2["best_hyperparameters"]
    assert meta1["best_cv_score"] == meta2["best_cv_score"]
    assert metrics1["candidates"] == metrics2["candidates"]
