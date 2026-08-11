"""Unit tests for MLflow experiment tracking and model promotion policy engine."""

import json
from pathlib import Path
from typing import Any, Dict

from mlflow.tracking import MlflowClient

from src.training.promotion import (
    compare_candidate_to_incumbent,
    load_promotion_policy,
    log_pipeline_run_to_mlflow,
    promote_model,
)


def test_load_promotion_policy() -> None:
    """Test loading promotion policy thresholds from JSON artifact."""
    policy = load_promotion_policy()
    assert "min_f1_improvement" in policy
    assert "max_precision_drop" in policy
    assert "max_recall_drop" in policy
    assert policy["min_f1_improvement"] == 0.01
    assert policy["max_precision_drop"] == 0.02
    assert policy["max_recall_drop"] == 0.0


def test_promotion_bootstrap_case() -> None:
    """Test initial model promotion when no incumbent Production model exists."""
    candidate_metrics = {
        "optimal_threshold_metrics": {
            "f1": 0.6416,
            "precision": 0.5598,
            "recall": 0.7513,
        }
    }

    result = compare_candidate_to_incumbent(candidate_metrics, incumbent_metrics=None)

    assert result["is_promoted"] is True
    assert result["is_bootstrap"] is True
    assert "no existing production model" in result["reason"]


def test_promotion_success_case() -> None:
    """Test successful promotion when candidate meets all Section 9 criteria."""
    incumbent_metrics = {
        "optimal_threshold_metrics": {
            "f1": 0.6000,
            "precision": 0.6500,
            "recall": 0.7000,
        }
    }
    candidate_metrics = {
        "optimal_threshold_metrics": {
            "f1": 0.6400,  # +0.0400 >= +0.0100
            "precision": 0.6400,  # drop = 0.0100 <= 0.0200
            "recall": 0.7200,  # drop = -0.0200 <= 0.0000
        }
    }

    result = compare_candidate_to_incumbent(
        candidate_metrics, incumbent_metrics=incumbent_metrics
    )

    assert result["is_promoted"] is True
    assert result["checks"]["f1_passed"] is True
    assert result["checks"]["precision_passed"] is True
    assert result["checks"]["recall_passed"] is True
    assert "Promoted:" in result["reason"]


def test_promotion_failure_f1_delta() -> None:
    """Test promotion rejection when F1 improvement is less than 1% (+0.01)."""
    incumbent_metrics = {
        "optimal_threshold_metrics": {
            "f1": 0.6400,
            "precision": 0.6000,
            "recall": 0.7000,
        }
    }
    candidate_metrics = {
        "optimal_threshold_metrics": {
            "f1": 0.6450,  # +0.0050 < +0.0100 (fails)
            "precision": 0.6000,
            "recall": 0.7000,
        }
    }

    result = compare_candidate_to_incumbent(
        candidate_metrics, incumbent_metrics=incumbent_metrics
    )

    assert result["is_promoted"] is False
    assert result["checks"]["f1_passed"] is False
    assert "F1 delta (+0.0050) < min required" in result["reason"]


def test_promotion_failure_precision_drop() -> None:
    """Test promotion rejection when precision drop exceeds 2% (0.02)."""
    incumbent_metrics = {
        "optimal_threshold_metrics": {
            "f1": 0.6000,
            "precision": 0.7000,
            "recall": 0.7000,
        }
    }
    candidate_metrics = {
        "optimal_threshold_metrics": {
            "f1": 0.6400,  # +0.0400 >= +0.0100
            "precision": 0.6500,  # drop = 0.0500 > 0.0200 (fails)
            "recall": 0.7000,
        }
    }

    result = compare_candidate_to_incumbent(
        candidate_metrics, incumbent_metrics=incumbent_metrics
    )

    assert result["is_promoted"] is False
    assert result["checks"]["precision_passed"] is False
    assert "Precision drop (0.0500) > max allowed" in result["reason"]


def test_promotion_failure_recall_decrease() -> None:
    """Test promotion rejection when recall decreases (recall drop > 0.0)."""
    incumbent_metrics = {
        "optimal_threshold_metrics": {
            "f1": 0.6000,
            "precision": 0.6500,
            "recall": 0.7500,
        }
    }
    candidate_metrics = {
        "optimal_threshold_metrics": {
            "f1": 0.6400,  # +0.0400 >= +0.0100
            "precision": 0.6500,
            "recall": 0.7000,  # drop = 0.0500 > 0.0000 (fails)
        }
    }

    result = compare_candidate_to_incumbent(
        candidate_metrics, incumbent_metrics=incumbent_metrics
    )

    assert result["is_promoted"] is False
    assert result["checks"]["recall_passed"] is False
    assert "Recall drop (0.0500) > max allowed" in result["reason"]


def test_promotion_edge_cases_exact_thresholds() -> None:
    """Test promotion decision when candidate matches threshold boundary values."""

    incumbent_metrics = {
        "optimal_threshold_metrics": {
            "f1": 0.6000,
            "precision": 0.6000,
            "recall": 0.7000,
        }
    }
    candidate_metrics = {
        "optimal_threshold_metrics": {
            "f1": 0.6100,  # +0.0100 == min_f1_improvement
            "precision": 0.5800,  # drop = 0.0200 == max_precision_drop
            "recall": 0.7000,  # drop = 0.0000 == max_recall_drop
        }
    }

    result = compare_candidate_to_incumbent(
        candidate_metrics, incumbent_metrics=incumbent_metrics
    )

    assert result["is_promoted"] is True
    assert result["checks"]["f1_passed"] is True
    assert result["checks"]["precision_passed"] is True
    assert result["checks"]["recall_passed"] is True


def test_registry_persistence_fresh_client(tmp_path: Path) -> None:
    """Test model registry persistence using a freshly instantiated MlflowClient.

    Verifies that model registration and stage transitions persist to the backing
    SQLite database without relying on in-memory object state.
    """
    db_file = tmp_path / "test_registry.db"
    tracking_uri = f"sqlite:///{db_file}"
    exp_name = "test-persistence-exp"
    model_name = "test-persistence-model"

    # Setup synthetic evaluation report JSON
    eval_data: Dict[str, Any] = {
        "model_algorithm": "XGBClassifier",
        "test_samples": 50,
        "metrics_at_threshold_0_5": {
            "roc_auc": 0.85,
            "f1": 0.60,
            "precision": 0.65,
            "recall": 0.55,
        },
        "optimal_threshold_metrics": {
            "optimal_threshold": 0.35,
            "f1": 0.64,
            "precision": 0.60,
            "recall": 0.70,
        },
        "brier_score": 0.12,
        "provenance": {"git_commit_hash": "test"},
    }
    eval_json = tmp_path / "evaluation_metrics.json"
    eval_json.write_text(json.dumps(eval_data), encoding="utf-8")

    # 1. First execution with client 1
    c1 = MlflowClient(tracking_uri=tracking_uri)
    res = promote_model(
        tracking_uri=tracking_uri,
        experiment_name=exp_name,
        model_name=model_name,
        eval_report_path=eval_json,
        client=c1,
    )
    assert res["is_promoted"] is True
    assert res["stage"] == "Production"

    # 2. Re-instantiate completely fresh client against local SQLite store
    fresh_client = MlflowClient(tracking_uri=tracking_uri)
    latest_versions = fresh_client.get_latest_versions(
        model_name, stages=["Production"]
    )

    assert len(latest_versions) == 1
    prod_version = latest_versions[0]
    assert str(prod_version.version) == "1"
    assert prod_version.current_stage == "Production"
    assert prod_version.tags.get("promotion_status") == "promoted"


def test_mlflow_logging_logistic_regression_metrics_only(tmp_path: Path) -> None:
    """Test that Logistic Regression is logged as a metrics-only historical child run.

    Verifies that no model artifact is logged for Logistic Regression and that it is
    tagged as a metrics-only historical baseline.
    """
    db_file = tmp_path / "test_logging.db"
    tracking_uri = f"sqlite:///{db_file}"
    exp_name = "test-logging-exp"

    eval_data: Dict[str, Any] = {
        "model_algorithm": "XGBClassifier",
        "test_samples": 50,
        "metrics_at_threshold_0_5": {
            "roc_auc": 0.85,
            "f1": 0.60,
            "precision": 0.65,
            "recall": 0.55,
        },
        "optimal_threshold_metrics": {
            "optimal_threshold": 0.35,
            "f1": 0.64,
            "precision": 0.60,
            "recall": 0.70,
        },
        "brier_score": 0.12,
        "provenance": {"git_commit_hash": "test"},
    }

    parent_id, child_id = log_pipeline_run_to_mlflow(
        eval_data, tracking_uri=tracking_uri, experiment_name=exp_name
    )

    assert parent_id != ""

    fresh_client = MlflowClient(tracking_uri=tracking_uri)
    if child_id:
        child_run = fresh_client.get_run(child_id)
        assert (
            child_run.data.tags.get("model_status")
            == "metrics_only_historical, no_persisted_estimator"
        )
        assert child_run.data.tags.get("candidate_family") == "LogisticRegression"

        # Verify ZERO model artifact logged for LR
        artifacts = fresh_client.list_artifacts(child_id)
        assert len(artifacts) == 0
