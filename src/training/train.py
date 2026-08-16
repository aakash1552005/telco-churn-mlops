"""Model Training Pipeline for Telco Customer Churn Platform.

Trains candidate models (Logistic Regression baseline + XGBoost Classifier)
using StratifiedKFold cross-validation and RandomizedSearchCV hyperparameter search
optimizing ROC-AUC. Validates processed feature schema alignment, logs class balance,
and persists full data provenance metadata and evaluation reports.
"""

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.base import BaseEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import RandomizedSearchCV, StratifiedKFold

from src.core.config import get_settings
from src.core.logging import get_logger
from src.data.validation import load_schema_config

logger = get_logger(__name__)

TARGET_COLUMN: str = "Churn"


def calculate_file_sha256(file_path: Path) -> str:
    """Calculate SHA-256 hex digest of a file on disk."""
    if not file_path.exists():
        return "not_found"
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_git_commit_hash() -> str:
    """Retrieve current Git HEAD commit hash via subprocess."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception as e:
        logger.warning(f"Failed to retrieve Git commit hash: {e}")
    return "unknown"


def validate_feature_schema(
    df: pd.DataFrame,
    schema_path: Optional[Path] = None,
    log_success: bool = True,
) -> List[str]:
    """Compare dataset columns against persisted models/feature_schema.json.

    Args:
        df: Input DataFrame to validate.
        schema_path: Optional path to feature_schema.json artifact.
        log_success: Whether to log success message.

    Returns:
        List of expected feature column names in exact order.

    Raises:
        FileNotFoundError: If feature_schema.json does not exist.
        ValueError: If feature count, names, or ordering mismatch schema.
    """
    path = schema_path or Path(get_settings().FEATURE_SCHEMA_PATH)
    if not path.exists():
        err_msg = (
            f"Feature schema artifact '{path}' not found. "
            f"Run Phase 6 feature engineering pipeline first."
        )
        logger.error(err_msg)
        raise FileNotFoundError(err_msg)

    with open(path, "r", encoding="utf-8") as f:
        schema_data = json.load(f)

    expected_features: List[str] = schema_data.get("features", [])
    actual_features: List[str] = [col for col in df.columns if col != TARGET_COLUMN]

    # Check 1: Feature Count Mismatch
    if len(actual_features) != len(expected_features):
        err_msg = (
            f"Feature schema count mismatch: expected {len(expected_features)}, "
            f"observed {len(actual_features)}."
        )
        logger.error(err_msg)
        raise ValueError(err_msg)

    # Check 2: Feature Set Difference
    expected_set = set(expected_features)
    actual_set = set(actual_features)
    if expected_set != actual_set:
        missing = sorted(list(expected_set - actual_set))
        extra = sorted(list(actual_set - expected_set))
        err_msg = f"Feature schema column mismatch: missing={missing}, extra={extra}"
        logger.error(err_msg)
        raise ValueError(err_msg)

    # Check 3: Feature Order Mismatch
    if actual_features != expected_features:
        err_msg = (
            "Feature schema column order mismatch. Silent column reordering detected."
        )
        logger.error(err_msg)
        raise ValueError(err_msg)

    if log_success:
        logger.info(
            f"Feature schema alignment validated successfully "
            f"({len(expected_features)} features)."
        )
    return expected_features


def log_class_balance(y: pd.Series) -> Dict[str, Any]:
    """Calculate and log target class distribution.

    Args:
        y: Target series (0 and 1 values).

    Returns:
        Dictionary containing class balance statistics.
    """
    total_samples = len(y)
    pos_count = int((y == 1).sum())
    neg_count = int((y == 0).sum())
    pos_pct = float((pos_count / total_samples) * 100) if total_samples > 0 else 0.0
    neg_pct = float((neg_count / total_samples) * 100) if total_samples > 0 else 0.0

    stats = {
        "total_samples": total_samples,
        "positive_count": pos_count,
        "positive_percent": round(pos_pct, 2),
        "negative_count": neg_count,
        "negative_percent": round(neg_pct, 2),
    }

    logger.info(
        "Target class balance before training",
        extra=stats,
    )
    return stats


def roc_auc_binary_scorer(estimator: Any, X: Any, y: Any) -> float:
    """Custom 1D binary ROC-AUC scorer for RandomizedSearchCV."""
    probs = estimator.predict_proba(X)
    if hasattr(probs, "ndim") and probs.ndim == 2 and probs.shape[1] == 2:
        probs = probs[:, 1]
    return float(roc_auc_score(y, probs))


def train_candidate_models(
    processed_dir: Optional[Path] = None,
    schema_path: Optional[Path] = None,
    model_output_path: Optional[Path] = None,
    metrics_output_path: Optional[Path] = None,
    cv_results_output_path: Optional[Path] = None,
    metadata_output_path: Optional[Path] = None,
    random_state: Optional[int] = None,
    n_iter: Optional[int] = None,
    n_jobs: int = -1,
) -> Tuple[BaseEstimator, Dict[str, Any], Dict[str, Any]]:
    """Train candidate models with StratifiedKFold CV and RandomizedSearchCV.

    Args:
        processed_dir: Path to processed train/test datasets directory.
        schema_path: Path to models/feature_schema.json artifact.
        model_output_path: Path to output serialized best model.
        metrics_output_path: Path to output training_metrics.json.
        cv_results_output_path: Path to output cv_results.csv.
        metadata_output_path: Path to output training_metadata.json.
        random_state: Random state seed.
        n_iter: Number of RandomizedSearchCV search iterations.

    Returns:
        Tuple of (winning_fitted_estimator, metrics_dict, metadata_dict).
    """
    settings = get_settings()
    data_dir = processed_dir or Path(settings.PROCESSED_DATA_DIR)
    sch_path = schema_path or Path(settings.FEATURE_SCHEMA_PATH)
    out_model_path = model_output_path or Path(settings.MODEL_OUTPUT_PATH)
    out_metrics_path = metrics_output_path or Path(settings.TRAINING_METRICS_PATH)
    out_cv_path = cv_results_output_path or Path(settings.CV_RESULTS_PATH)
    out_meta_path = metadata_output_path or Path(settings.TRAINING_METADATA_PATH)
    seed = random_state if random_state is not None else settings.RANDOM_STATE
    search_iter = n_iter if n_iter is not None else settings.MODEL_SEARCH_ITERATIONS

    # Fix all global randomness
    np.random.seed(seed)

    # 1. Load Processed Datasets Directly (Phase 7 does not re-derive features)
    train_csv = data_dir / "train.csv"
    test_csv = data_dir / "test.csv"
    if not train_csv.exists() or not test_csv.exists():
        err_msg = (
            f"Processed datasets not found in '{data_dir}'. "
            f"Run Phase 6 feature engineering pipeline first."
        )
        logger.error(err_msg)
        raise FileNotFoundError(err_msg)

    train_df = pd.read_csv(train_csv)
    test_df = pd.read_csv(test_csv)

    logger.info(
        f"Loaded processed datasets: train={train_df.shape}, test={test_df.shape}"
    )

    # 2. Compare train.csv Columns Against Persisted Feature Schema
    expected_features = validate_feature_schema(
        train_df, schema_path=sch_path, log_success=True
    )
    validate_feature_schema(test_df, schema_path=sch_path, log_success=False)

    X_train = train_df[expected_features]
    y_train = train_df[TARGET_COLUMN]

    X_test = test_df[expected_features]
    y_test = test_df[TARGET_COLUMN]

    # 3. Log Class Balance Before Training
    log_class_balance(y_train)

    # 4. StratifiedKFold Cross-Validation Setup
    cv_folds = settings.CV_FOLDS
    cv = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=seed)

    # 5. Define Candidate Models & Search Spaces
    if os.getenv("FORCE_DEGRADED_CANDIDATE") == "1":
        logger.warning(
            "FORCE_DEGRADED_CANDIDATE=1 detected: "
            "Training degraded candidate model for promotion gate testing."
        )
        candidates: Dict[str, Dict[str, Any]] = {
            "LogisticRegression": {
                "estimator": LogisticRegression(
                    random_state=seed, max_iter=5, C=0.0001
                ),
                "param_distributions": {"C": [0.0001]},
                "n_iter": 1,
            }
        }
    else:
        candidates = {
            "LogisticRegression": {
                "estimator": LogisticRegression(random_state=seed, max_iter=1000),
                "param_distributions": {
                    "C": [0.001, 0.01, 0.1, 1.0, 10.0, 100.0],
                    "solver": ["lbfgs"],
                },
                "n_iter": 6,  # 6 combinations total for C grid
            },
            "XGBClassifier": {
                "estimator": xgb.XGBClassifier(
                    random_state=seed, eval_metric="logloss"
                ),
                "param_distributions": {
                    "n_estimators": [50, 100, 150, 200, 250, 300],
                    "max_depth": [3, 4, 5, 6, 7, 8],
                    "learning_rate": [0.01, 0.03, 0.05, 0.1, 0.2],
                    "subsample": [0.6, 0.7, 0.8, 0.9, 1.0],
                    "colsample_bytree": [0.6, 0.7, 0.8, 0.9, 1.0],
                    "min_child_weight": [1, 3, 5, 7],
                    "gamma": [0.0, 0.1, 0.2, 0.3],
                },
                "n_iter": search_iter,
            },
        }

    results: Dict[str, Dict[str, Any]] = {}
    cv_results_frames: List[pd.DataFrame] = []

    best_winner_name: Optional[str] = None
    best_winner_score: float = -1.0
    best_winner_search: Optional[RandomizedSearchCV] = None

    logger.info("Starting hyperparameter search optimizing ROC-AUC...")

    for model_name, cfg in candidates.items():
        logger.info(f"Executing RandomizedSearchCV for '{model_name}'...")
        search = RandomizedSearchCV(
            estimator=cfg["estimator"],
            param_distributions=cfg["param_distributions"],
            n_iter=cfg["n_iter"],
            scoring=roc_auc_binary_scorer,
            cv=cv,
            random_state=seed,
            n_jobs=n_jobs,
            refit=True,
        )
        search.fit(X_train, y_train)

        cv_score = float(search.best_score_)
        logger.info(
            f"Completed RandomizedSearchCV for '{model_name}': "
            f"Best CV ROC-AUC = {cv_score:.4f}"
        )

        # Collect CV results table
        df_cv = pd.DataFrame(search.cv_results_)
        df_cv["model_name"] = model_name
        cv_results_frames.append(df_cv)

        # Record candidate results
        results[model_name] = {
            "best_cv_roc_auc": cv_score,
            "best_params": search.best_params_,
            "fitted_search": search,
        }

        if cv_score > best_winner_score:
            best_winner_score = cv_score
            best_winner_name = model_name
            best_winner_search = search

    assert best_winner_name is not None and best_winner_search is not None

    logger.info(
        f"Winning candidate model selected: '{best_winner_name}' "
        f"with Best CV ROC-AUC = {best_winner_score:.4f}"
    )

    winning_model: BaseEstimator = best_winner_search.best_estimator_

    # Verify Required Estimator Interface Constraints
    # (.predict, .predict_proba, .classes_)
    if not hasattr(winning_model, "predict"):
        raise AttributeError(f"Winning model '{best_winner_name}' lacks '.predict()'.")
    if not hasattr(winning_model, "predict_proba"):
        raise AttributeError(
            f"Winning model '{best_winner_name}' lacks '.predict_proba()'."
        )
    if not hasattr(winning_model, "classes_"):
        raise AttributeError(
            f"Winning model '{best_winner_name}' lacks '.classes_' attribute."
        )

    # 6. Evaluate Held-Out test.csv EXACTLY ONCE on Candidate Models
    # (test.csv is evaluated strictly after model selection)
    metrics_summary: Dict[str, Any] = {
        "winning_algorithm": best_winner_name,
        "best_cv_roc_auc": round(best_winner_score, 4),
        "candidates": {},
    }

    for model_name, res in results.items():
        estimator: BaseEstimator = res["fitted_search"].best_estimator_
        y_pred = estimator.predict(X_test)
        y_prob = estimator.predict_proba(X_test)[:, 1]

        test_roc_auc = float(roc_auc_score(y_test, y_prob))
        test_f1 = float(f1_score(y_test, y_pred))
        test_precision = float(precision_score(y_test, y_pred))
        test_recall = float(recall_score(y_test, y_pred))

        metrics_summary["candidates"][model_name] = {
            "cv_roc_auc": round(res["best_cv_roc_auc"], 4),
            "test_roc_auc": round(test_roc_auc, 4),
            "test_f1": round(test_f1, 4),
            "test_precision": round(test_precision, 4),
            "test_recall": round(test_recall, 4),
            "best_params": res["best_params"],
        }

        logger.info(
            f"Test Evaluation for '{model_name}': "
            f"ROC-AUC={test_roc_auc:.4f}, F1={test_f1:.4f}, "
            f"Precision={test_precision:.4f}, Recall={test_recall:.4f}"
        )

    # 7. Persist Output Artifacts
    # Artifact 1: models/best_model.joblib
    out_model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(winning_model, out_model_path)
    logger.info(f"Persisted winning model artifact to: '{out_model_path}'")

    # Artifact 2: reports/training_metrics.json
    out_metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics_summary, f, indent=2)
    logger.info(f"Persisted training metrics report to: '{out_metrics_path}'")

    # Artifact 3: reports/cv_results.csv
    out_cv_path.parent.mkdir(parents=True, exist_ok=True)
    df_combined_cv = pd.concat(cv_results_frames, ignore_index=True)
    df_combined_cv.to_csv(out_cv_path, index=False)
    logger.info(f"Persisted cross-validation search results to: '{out_cv_path}'")

    # Artifact 4: models/training_metadata.json (Full Provenance Chain)
    raw_path = Path(settings.RAW_DATA_PATH)
    dataset_sha256 = calculate_file_sha256(raw_path)
    feature_pipeline_sha256 = calculate_file_sha256(
        Path(settings.FEATURE_PIPELINE_PATH)
    )

    schema_config = load_schema_config(Path(settings.SCHEMA_FILE_PATH))
    schema_version = schema_config.get("schema_version", "1.0.0")

    metadata: Dict[str, Any] = {
        "algorithm": best_winner_name,
        "random_seed": seed,
        "cv_folds": cv_folds,
        "best_hyperparameters": best_winner_search.best_params_,
        "best_cv_score": round(best_winner_score, 4),
        "training_timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit_hash": get_git_commit_hash(),
        "feature_count": len(expected_features),
        "dataset_sha256": dataset_sha256,
        "feature_pipeline_sha256": feature_pipeline_sha256,
        "schema_version": schema_version,
    }

    out_meta_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"Persisted training metadata provenance to: '{out_meta_path}'")

    return winning_model, metrics_summary, metadata


if __name__ == "__main__":
    train_candidate_models()
