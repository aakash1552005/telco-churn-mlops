"""Unit tests for model evaluation and threshold optimization module."""

import json
from pathlib import Path
from typing import Any, Dict

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

from src.training.evaluate import (
    compute_calibration_metrics,
    evaluate_model,
    export_error_analysis,
    export_feature_importance,
    generate_evaluation_report,
    optimize_threshold,
)


def test_evaluate_model_metrics_calculation() -> None:
    """Test evaluate_model metric calculation against known input/output pairs."""
    y_true = np.array([0, 0, 1, 1, 1])
    y_prob = np.array([0.1, 0.4, 0.6, 0.8, 0.9])

    metrics = evaluate_model(y_true, y_prob, threshold=0.5)

    assert metrics["threshold"] == 0.5
    assert metrics["roc_auc"] == 1.0
    assert metrics["f1"] == 1.0
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["confusion_matrix"] == [[2, 0], [0, 3]]


def test_optimize_threshold_synthetic() -> None:
    """Test threshold optimization logic on synthetic prediction/label pair."""

    # Ground truth: 4 negatives, 4 positives
    y_true = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    # Probabilities where optimal threshold is around 0.35
    y_prob = np.array([0.1, 0.2, 0.3, 0.7, 0.4, 0.5, 0.8, 0.9])

    opt_results = optimize_threshold(y_true, y_prob)

    assert "optimal_threshold" in opt_results
    thresh = opt_results["optimal_threshold"]
    assert isinstance(thresh, float)
    assert 0.0 < thresh < 1.0
    assert opt_results["optimal_f1"] >= 0.80


def test_compute_calibration_metrics() -> None:
    """Test Brier score loss and calibration curve calculation."""
    y_true = np.array([0, 0, 1, 1])
    y_prob = np.array([0.1, 0.2, 0.8, 0.9])

    calib = compute_calibration_metrics(y_true, y_prob, n_bins=5)

    assert "brier_score" in calib
    assert isinstance(calib["brier_score"], float)
    assert calib["brier_score"] < 0.05
    assert "prob_true" in calib
    assert "prob_pred" in calib


def test_export_feature_importance_and_error_analysis(tmp_path: Path) -> None:
    """Test feature importance and error analysis CSV exports."""
    # Synthetic trained model
    X = pd.DataFrame({"f1": [1.0, 2.0, 3.0, 4.0], "f2": [0.5, 1.5, 2.5, 3.5]})
    y = np.array([0, 0, 1, 1])
    model = LogisticRegression().fit(X, y)

    imp_csv = tmp_path / "feature_importance.csv"
    df_imp = export_feature_importance(model, ["f1", "f2"], imp_csv)

    assert imp_csv.exists()
    assert list(df_imp.columns) == ["feature", "importance", "rank"]
    assert len(df_imp) == 2

    err_csv = tmp_path / "error_analysis.csv"
    customer_ids = np.array(["C01", "C02", "C03", "C04"])
    y_prob = model.predict_proba(X)[:, 1]
    df_err = export_error_analysis(customer_ids, y, y_prob, 0.5, err_path := err_csv)

    assert err_path.exists()
    assert "customerID" in df_err.columns
    assert len(df_err) == 4


@pytest.fixture
def synthetic_eval_dataset(tmp_path: Path) -> Dict[str, Any]:
    """Fixture creating synthetic trained model, test dataset, schema, and metadata."""
    proc_dir = tmp_path / "proc"
    models_dir = tmp_path / "models"
    reports_dir = tmp_path / "reports"
    plots_dir = reports_dir / "plots"

    proc_dir.mkdir(parents=True)
    models_dir.mkdir(parents=True)
    reports_dir.mkdir(parents=True)
    plots_dir.mkdir(parents=True)

    np.random.seed(42)
    X_mat = np.random.randn(50, 5)
    y_vec = np.random.choice([0, 1], size=50)

    feature_names = [f"feat_{i}" for i in range(5)]
    test_df = pd.DataFrame(X_mat, columns=feature_names)
    test_df["Churn"] = y_vec

    test_df.to_csv(proc_dir / "test.csv", index=False)

    schema_data = {
        "features": feature_names,
        "target": "Churn",
        "feature_count": 5,
    }
    with open(models_dir / "feature_schema.json", "w", encoding="utf-8") as f:
        json.dump(schema_data, f)

    meta_data = {
        "algorithm": "LogisticRegression",
        "random_seed": 42,
        "best_cv_score": 0.85,
        "git_commit_hash": "test_hash",
        "dataset_sha256": "test_sha",
        "feature_pipeline_sha256": "pipe_sha",
        "schema_version": "1.0.0",
    }
    with open(models_dir / "training_metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta_data, f)

    model = LogisticRegression(random_state=42).fit(X_mat, y_vec)
    joblib.dump(model, models_dir / "best_model.joblib")

    return {
        "proc_dir": proc_dir,
        "model_path": models_dir / "best_model.joblib",
        "schema_path": models_dir / "feature_schema.json",
        "metadata_path": models_dir / "training_metadata.json",
        "reports_dir": reports_dir,
        "plots_dir": plots_dir,
        "models_dir": models_dir,
    }


def test_generate_evaluation_report_artifacts(
    synthetic_eval_dataset: Dict[str, Any],
) -> None:
    """Test generate_evaluation_report creates all plots, JSONs, and CSVs."""
    ds = synthetic_eval_dataset

    results = generate_evaluation_report(
        processed_dir=ds["proc_dir"],
        model_path=ds["model_path"],
        schema_path=ds["schema_path"],
        metadata_path=ds["metadata_path"],
        output_dir=ds["reports_dir"],
        plots_dir=ds["plots_dir"],
    )

    assert "model_algorithm" in results
    assert "metrics_at_threshold_0_5" in results
    assert "optimal_threshold_metrics" in results
    assert "brier_score" in results

    # Verify JSON artifacts
    assert (ds["reports_dir"] / "evaluation_metrics.json").exists()
    assert (ds["reports_dir"] / "classification_report.json").exists()
    assert (ds["reports_dir"] / "calibration_metrics.json").exists()

    # Verify decision_threshold.json in models_dir if saved via settings or reports_dir
    thresh_file = ds["models_dir"] / "decision_threshold.json"
    if thresh_file.exists():
        with open(thresh_file, "r", encoding="utf-8") as f:
            t_data = json.load(f)
        assert "optimal_threshold" in t_data
        assert 0.0 < t_data["optimal_threshold"] < 1.0

    # Verify Plots
    p_dir = ds["plots_dir"]
    assert (p_dir / "confusion_matrix.png").exists()
    assert (p_dir / "feature_importance.png").exists()
    assert (p_dir / "roc_curve.png").exists()
    assert (p_dir / "precision_recall_curve.png").exists()
    assert (p_dir / "calibration_curve.png").exists()
    assert (p_dir / "prediction_distribution.png").exists()


def test_evaluation_reproducibility(synthetic_eval_dataset: Dict[str, Any]) -> None:
    """Test evaluation pipeline produces 100% identical metrics across multiple runs."""
    ds = synthetic_eval_dataset

    res1 = generate_evaluation_report(
        processed_dir=ds["proc_dir"],
        model_path=ds["model_path"],
        schema_path=ds["schema_path"],
        metadata_path=ds["metadata_path"],
        output_dir=ds["reports_dir"] / "run1",
        plots_dir=ds["plots_dir"] / "run1",
    )

    res2 = generate_evaluation_report(
        processed_dir=ds["proc_dir"],
        model_path=ds["model_path"],
        schema_path=ds["schema_path"],
        metadata_path=ds["metadata_path"],
        output_dir=ds["reports_dir"] / "run2",
        plots_dir=ds["plots_dir"] / "run2",
    )

    assert res1["metrics_at_threshold_0_5"] == res2["metrics_at_threshold_0_5"]
    assert res1["optimal_threshold_metrics"] == res2["optimal_threshold_metrics"]
    assert res1["brier_score"] == res2["brier_score"]
