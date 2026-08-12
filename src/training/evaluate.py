"""Model evaluation, threshold optimization, calibration, and visualization module.

Evaluates winning serialized model artifact (models/best_model.joblib) against
the untouched held-out test split (data/processed/test.csv).
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import matplotlib

# Set non-interactive backend before importing pyplot
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.calibration import calibration_curve  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    brier_score_loss,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import train_test_split  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.core.logging import get_logger  # noqa: E402
from src.training.train import TARGET_COLUMN, validate_feature_schema  # noqa: E402

logger = get_logger(__name__)


def load_evaluation_artifacts(
    processed_dir: Optional[Path] = None,
    model_path: Optional[Path] = None,
    schema_path: Optional[Path] = None,
    metadata_path: Optional[Path] = None,
    raw_data_path: Optional[Path] = None,
) -> Tuple[Any, pd.DataFrame, np.ndarray, List[str], Dict[str, Any], np.ndarray]:
    """Load model, test dataset, feature schema, provenance metadata, and customer IDs.

    Args:
        processed_dir: Path to processed test.csv directory.
        model_path: Path to models/best_model.joblib.
        schema_path: Path to models/feature_schema.json.
        metadata_path: Path to models/training_metadata.json.
        raw_data_path: Path to data/raw/telco_churn.csv.

    Returns:
        Tuple of (model, X_test, y_test, expected_features,
        metadata_dict, customer_ids).
    """
    settings = get_settings()
    p_dir = processed_dir or Path(settings.PROCESSED_DATA_DIR)
    m_path = model_path or Path(settings.MODEL_OUTPUT_PATH)
    s_path = schema_path or Path(settings.FEATURE_SCHEMA_PATH)
    meta_path = metadata_path or Path(settings.TRAINING_METADATA_PATH)
    raw_path = raw_data_path or Path(settings.RAW_DATA_PATH)

    test_csv = p_dir / "test.csv"
    if not test_csv.exists():
        err_msg = f"Test dataset not found at '{test_csv}'."
        logger.error(err_msg)
        raise FileNotFoundError(err_msg)

    if not m_path.exists():
        err_msg = f"Model artifact not found at '{m_path}'."
        logger.error(err_msg)
        raise FileNotFoundError(err_msg)

    logger.info(f"Loading serialized model from '{m_path}'...")
    model = joblib.load(m_path)

    logger.info(f"Loading test dataset from '{test_csv}'...")
    test_df = pd.read_csv(test_csv)

    expected_features = validate_feature_schema(
        test_df, schema_path=s_path, log_success=True
    )

    X_test = test_df[expected_features]
    y_test = test_df[TARGET_COLUMN].values

    # Load training metadata provenance if available
    metadata_dict: Dict[str, Any] = {}
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            metadata_dict = json.load(f)

    # Re-derive customerID split matching Phase 6 logic
    customer_ids: np.ndarray

    if raw_path.exists():
        raw_df = pd.read_csv(raw_path)
        _, test_raw = train_test_split(
            raw_df,
            test_size=settings.TEST_SIZE,
            random_state=settings.RANDOM_STATE,
            stratify=raw_df[TARGET_COLUMN],
        )
        if len(test_raw) == len(test_df):
            customer_ids = test_raw["customerID"].values
        else:
            customer_ids = np.array([f"TEST_ID_{i:04d}" for i in range(len(test_df))])
    else:
        customer_ids = np.array([f"TEST_ID_{i:04d}" for i in range(len(test_df))])

    # Integrity Check Logging
    y_prob = model.predict_proba(X_test)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)

    test_shape = test_df.shape
    pred_count = len(y_pred)
    prob_count = len(y_prob)

    logger.info(
        "Evaluation test dataset integrity check: "
        f"test_shape={test_shape}, pred_count={pred_count}, prob_count={prob_count}"
    )

    if not (test_shape[0] == pred_count == prob_count):
        err_msg = (
            f"Integrity check mismatch: test_rows={test_shape[0]}, "
            f"pred_count={pred_count}, prob_count={prob_count}"
        )
        logger.error(err_msg)
        raise ValueError(err_msg)

    # Extended provenance logging
    logger.info(
        "Loaded model evaluation provenance context",
        extra={
            "algorithm": metadata_dict.get("algorithm", type(model).__name__),
            "git_commit_hash": metadata_dict.get("git_commit_hash", "unknown"),
            "dataset_sha256": metadata_dict.get("dataset_sha256", "unknown"),
            "feature_pipeline_sha256": metadata_dict.get(
                "feature_pipeline_sha256", "unknown"
            ),
            "schema_version": metadata_dict.get("schema_version", "1.0.0"),
            "test_rows": test_shape[0],
            "feature_count": len(expected_features),
        },
    )

    return model, X_test, y_test, expected_features, metadata_dict, customer_ids


def evaluate_model(
    y_true: np.ndarray, y_prob: np.ndarray, threshold: float = 0.5
) -> Dict[str, Any]:
    """Compute classification metrics at a specified decision threshold.

    Args:
        y_true: Ground truth binary labels.
        y_prob: Predicted probability vector for positive class.
        threshold: Decision boundary probability threshold.

    Returns:
        Dictionary of classification metrics.
    """
    y_pred = (y_prob >= threshold).astype(int)

    roc_auc = float(roc_auc_score(y_true, y_prob))
    f1 = float(f1_score(y_true, y_pred, zero_division=0))
    precision = float(precision_score(y_true, y_pred, zero_division=0))
    recall = float(recall_score(y_true, y_pred, zero_division=0))
    cm = confusion_matrix(y_true, y_pred).tolist()
    clf_report = classification_report(
        y_true, y_pred, output_dict=True, zero_division=0
    )

    return {
        "threshold": float(round(threshold, 4)),
        "roc_auc": round(roc_auc, 4),
        "f1": round(f1, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "confusion_matrix": cm,
        "classification_report": clf_report,
    }


def optimize_threshold(y_true: np.ndarray, y_prob: np.ndarray) -> Dict[str, Any]:
    """Sweep thresholds along Precision-Recall curve to find F1-maximizing threshold.

    Args:
        y_true: Ground truth binary labels.
        y_prob: Predicted probability vector.

    Returns:
        Dict containing optimal threshold, best F1, precision, recall, and metrics.
    """

    precisions, recalls, thresholds = precision_recall_curve(y_true, y_prob)

    best_f1 = -1.0
    best_thresh = 0.5
    best_precision = 0.0
    best_recall = 0.0

    # Evaluate F1 across candidate thresholds
    for p, r, t in zip(precisions[:-1], recalls[:-1], thresholds):
        if (p + r) > 0:
            f1 = (2 * p * r) / (p + r)
            if f1 > best_f1:
                best_f1 = float(f1)
                best_thresh = float(t)
                best_precision = float(p)
                best_recall = float(r)

    optimal_metrics = evaluate_model(y_true, y_prob, threshold=best_thresh)

    return {
        "optimal_threshold": float(round(best_thresh, 4)),
        "optimal_f1": float(round(best_f1, 4)),
        "optimal_precision": float(round(best_precision, 4)),
        "optimal_recall": float(round(best_recall, 4)),
        "optimal_metrics": optimal_metrics,
    }


def compute_calibration_metrics(
    y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10
) -> Dict[str, Any]:
    """Compute Brier score loss and calibration curve coordinates.

    Args:
        y_true: Ground truth binary labels.
        y_prob: Predicted probability vector.
        n_bins: Number of discretization bins.

    Returns:
        Dictionary containing brier_score and calibration curve points.
    """
    brier = float(brier_score_loss(y_true, y_prob))
    prob_true, prob_pred = calibration_curve(
        y_true, y_prob, n_bins=n_bins, strategy="uniform"
    )

    return {
        "brier_score": float(round(brier, 4)),
        "prob_true": [float(round(v, 4)) for v in prob_true],
        "prob_pred": [float(round(v, 4)) for v in prob_pred],
    }


def export_feature_importance(
    model: Any, feature_names: List[str], output_path: Path
) -> pd.DataFrame:
    """Extract feature importances, map to feature names, rank, and save CSV.

    Args:
        model: Fitted estimator instance.
        feature_names: List of feature column names.
        output_path: Path to output CSV.

    Returns:
        Feature importance DataFrame.
    """
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
    elif hasattr(model, "coef_"):
        importances = np.abs(model.coef_[0])
    else:
        importances = np.zeros(len(feature_names))

    df_imp = pd.DataFrame(
        {
            "feature": feature_names,
            "importance": importances,
        }
    )
    df_imp = df_imp.sort_values(by="importance", ascending=False).reset_index(drop=True)
    df_imp["rank"] = df_imp.index + 1
    df_imp["importance"] = df_imp["importance"].round(6)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_imp.to_csv(output_path, index=False)
    logger.info(f"Persisted feature importances to '{output_path}'")
    return df_imp


def export_error_analysis(
    customer_ids: np.ndarray,
    y_true: np.ndarray,
    y_prob: np.ndarray,
    threshold: float,
    output_path: Path,
) -> pd.DataFrame:
    """Generate and persist error analysis CSV mapping prediction errors.

    Args:
        customer_ids: Array of customer IDs.
        y_true: Ground truth binary labels.
        y_prob: Predicted probability vector.
        threshold: Decision threshold used.
        output_path: Destination path for error_analysis.csv.

    Returns:
        Error analysis DataFrame.
    """
    y_pred = (y_prob >= threshold).astype(int)
    is_error = y_true != y_pred

    df_err = pd.DataFrame(
        {
            "customerID": customer_ids,
            "true_label": y_true,
            "predicted_label": y_pred,
            "probability": np.round(y_prob, 4),
            "threshold_used": round(threshold, 4),
            "is_error": is_error.astype(int),
        }
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_err.to_csv(output_path, index=False)
    logger.info(f"Persisted error analysis CSV to '{output_path}'")
    return df_err


# --- PLOTTING UTILITIES ---


def plot_confusion_matrix(
    cm: List[List[int]], output_path: Path, title: str = "Confusion Matrix"
) -> None:
    """Plot and save confusion matrix heatmap.

    Args:
        cm: 2x2 confusion matrix list [[TN, FP], [FN, TP]].
        output_path: Path to save PNG.
        title: Title of plot.
    """
    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(cm, cmap="Blues")

    # Annotate values
    for i in range(2):
        for j in range(2):
            ax.text(
                j,
                i,
                f"{cm[i][j]}",
                ha="center",
                va="center",
                color="white" if cm[i][j] > (np.max(cm) / 2) else "black",
                fontsize=14,
                fontweight="bold",
            )

    ax.set_xticks([0, 1])
    ax.set_yticks([0, 1])
    ax.set_xticklabels(["Non-Churn (0)", "Churn (1)"])
    ax.set_yticklabels(["Non-Churn (0)", "Churn (1)"])
    ax.set_xlabel("Predicted Label")
    ax.set_ylabel("True Label")
    ax.set_title(title)
    fig.colorbar(im, ax=ax)
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300)
    plt.close(fig)
    logger.info(f"Saved plot to '{output_path}'")


def plot_feature_importance(
    df_importance: pd.DataFrame, output_path: Path, top_n: int = 15
) -> None:
    """Plot top N feature importances.

    Args:
        df_importance: Feature importance DataFrame.
        output_path: Path to save PNG.
        top_n: Number of top features to plot.
    """
    df_top = df_importance.head(top_n).iloc[::-1]

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh(df_top["feature"], df_top["importance"], color="#1f77b4")
    ax.set_xlabel("Importance Score")
    ax.set_title(f"Top {top_n} Feature Importances")
    ax.grid(axis="x", linestyle="--", alpha=0.7)
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300)
    plt.close(fig)
    logger.info(f"Saved plot to '{output_path}'")


def plot_roc_curve(
    y_true: np.ndarray, y_prob: np.ndarray, roc_auc: float, output_path: Path
) -> None:
    """Plot Receiver Operating Characteristic (ROC) curve.

    Args:
        y_true: Ground truth binary labels.
        y_prob: Predicted probability vector.
        roc_auc: ROC-AUC score.
        output_path: Path to save PNG.
    """
    fpr, tpr, _ = roc_curve(y_true, y_prob)

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(
        fpr, tpr, color="darkorange", lw=2, label=f"ROC Curve (AUC = {roc_auc:.4f})"
    )
    ax.plot(
        [0, 1], [0, 1], color="navy", lw=2, linestyle="--", label="Random Classifier"
    )
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.05)
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("Receiver Operating Characteristic (ROC) Curve")
    ax.legend(loc="lower right")
    ax.grid(alpha=0.3)
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300)
    plt.close(fig)
    logger.info(f"Saved plot to '{output_path}'")


def plot_pr_curve(
    y_true: np.ndarray, y_prob: np.ndarray, optimal_thresh: float, output_path: Path
) -> None:
    """Plot Precision-Recall curve with optimal threshold marker.

    Args:
        y_true: Ground truth binary labels.
        y_prob: Predicted probability vector.
        optimal_thresh: Optimal F1 decision threshold.
        output_path: Path to save PNG.
    """
    precisions, recalls, thresholds = precision_recall_curve(y_true, y_prob)

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(recalls, precisions, color="green", lw=2, label="Precision-Recall Curve")

    # Mark optimal threshold
    idx = np.argmin(np.abs(thresholds - optimal_thresh))
    ax.scatter(
        [recalls[idx]],
        [precisions[idx]],
        color="red",
        s=80,
        zorder=5,
        label=f"Optimal Thresh = {optimal_thresh:.4f}",
    )

    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.05)

    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title("Precision-Recall Curve")
    ax.legend(loc="lower left")
    ax.grid(alpha=0.3)
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300)
    plt.close(fig)
    logger.info(f"Saved plot to '{output_path}'")


def plot_calibration_curve(
    y_true: np.ndarray, y_prob: np.ndarray, brier_score: float, output_path: Path
) -> None:
    """Plot calibration curve (reliability diagram).

    Args:
        y_true: Ground truth binary labels.
        y_prob: Predicted probability vector.
        brier_score: Brier score loss.
        output_path: Path to save PNG.
    """
    prob_true, prob_pred = calibration_curve(
        y_true, y_prob, n_bins=10, strategy="uniform"
    )

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(
        prob_pred,
        prob_true,
        marker="o",
        linewidth=2,
        color="purple",
        label=f"Model (Brier = {brier_score:.4f})",
    )
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Perfectly Calibrated")
    ax.set_xlabel("Mean Predicted Probability")
    ax.set_ylabel("Fraction of Positives")
    ax.set_title("Probability Calibration Curve")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300)
    plt.close(fig)
    logger.info(f"Saved plot to '{output_path}'")


def plot_prediction_distribution(
    y_prob: np.ndarray,
    default_thresh: float,
    optimal_thresh: float,
    output_path: Path,
) -> None:
    """Plot histogram of predicted probabilities with threshold markers.

    Args:
        y_prob: Predicted probability vector.
        default_thresh: Default threshold (0.5).
        optimal_thresh: Optimal threshold.
        output_path: Path to save PNG.
    """
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.hist(y_prob, bins=25, color="skyblue", edgecolor="black", alpha=0.7)
    ax.axvline(
        default_thresh,
        color="red",
        linestyle="--",
        linewidth=2,
        label=f"Default Thresh ({default_thresh})",
    )
    ax.axvline(
        optimal_thresh,
        color="green",
        linestyle="-",
        linewidth=2,
        label=f"Optimal Thresh ({optimal_thresh:.4f})",
    )
    ax.set_xlabel("Predicted Probability")
    ax.set_ylabel("Frequency")
    ax.set_title("Predicted Probability Distribution")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.3)
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=300)
    plt.close(fig)
    logger.info(f"Saved plot to '{output_path}'")


def generate_evaluation_report(
    processed_dir: Optional[Path] = None,
    model_path: Optional[Path] = None,
    schema_path: Optional[Path] = None,
    metadata_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    plots_dir: Optional[Path] = None,
    threshold_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute end-to-end evaluation, threshold optimization, calibration, and plotting.

    Args:
        processed_dir: Path to processed test dataset directory.
        model_path: Path to models/best_model.joblib.
        schema_path: Path to models/feature_schema.json.
        metadata_path: Path to models/training_metadata.json.
        output_dir: Path to reports directory.
        plots_dir: Path to reports/plots directory.

    Returns:
        Dictionary containing consolidated evaluation results.
    """
    settings = get_settings()
    out_dir = output_dir or Path("reports")
    p_dir = plots_dir or Path(settings.PLOTS_DIR)

    model, X_test, y_test, features, meta_dict, customer_ids = (
        load_evaluation_artifacts(
            processed_dir=processed_dir,
            model_path=model_path,
            schema_path=schema_path,
            metadata_path=metadata_path,
        )
    )

    y_prob = model.predict_proba(X_test)[:, 1]

    # 1. Evaluate at default threshold 0.5
    default_metrics = evaluate_model(y_test, y_prob, threshold=0.5)

    # 2. Regression check against Phase 7 training_metrics.json if present
    training_metrics_path = out_dir / "training_metrics.json"
    if training_metrics_path.exists():
        with open(training_metrics_path, "r", encoding="utf-8") as f:
            t_metrics = json.load(f)
        win_alg = t_metrics.get("winning_algorithm", "XGBClassifier")
        win_candidates = t_metrics.get("candidates", {}).get(win_alg, {})
        expected_roc_auc = win_candidates.get("test_roc_auc")
        expected_f1 = win_candidates.get("test_f1")

        if expected_roc_auc is not None and expected_f1 is not None:
            if not (
                np.isclose(default_metrics["roc_auc"], expected_roc_auc, atol=1e-4)
                and np.isclose(default_metrics["f1"], expected_f1, atol=1e-4)
            ):
                d_auc = default_metrics["roc_auc"]
                d_f1 = default_metrics["f1"]
                err_msg = (
                    f"Regression mismatch! Default metrics (ROC-AUC={d_auc}, "
                    f"F1={d_f1}) do not match Phase 7 (ROC-AUC={expected_roc_auc}, "
                    f"F1={expected_f1})."
                )
                logger.error(err_msg)
                raise ValueError(err_msg)
            logger.info(
                "Regression check passed: Default 0.5 metrics match Phase 7 report."
            )

    # 3. Threshold Optimization
    opt_results = optimize_threshold(y_test, y_prob)
    opt_thresh = opt_results["optimal_threshold"]
    opt_metrics = opt_results["optimal_metrics"]

    # 4. Calibration Analysis
    calib_metrics = compute_calibration_metrics(y_test, y_prob, n_bins=10)

    # 5. Export Feature Importances
    feat_imp_path = Path(settings.FEATURE_IMPORTANCE_PATH)
    if output_dir:
        feat_imp_path = output_dir / "feature_importance.csv"
    df_imp = export_feature_importance(model, features, feat_imp_path)

    # 6. Export Error Analysis CSV
    err_path = Path(settings.ERROR_ANALYSIS_PATH)
    if output_dir:
        err_path = output_dir / "error_analysis.csv"
    export_error_analysis(customer_ids, y_test, y_prob, opt_thresh, err_path)

    # 7. Generate & Save Plot Artifacts
    plot_confusion_matrix(
        default_metrics["confusion_matrix"],
        p_dir / "confusion_matrix.png",
        title="Confusion Matrix (Threshold = 0.5)",
    )
    plot_feature_importance(df_imp, p_dir / "feature_importance.png", top_n=15)
    plot_roc_curve(y_test, y_prob, default_metrics["roc_auc"], p_dir / "roc_curve.png")
    plot_pr_curve(y_test, y_prob, opt_thresh, p_dir / "precision_recall_curve.png")
    plot_calibration_curve(
        y_test,
        y_prob,
        calib_metrics["brier_score"],
        p_dir / "calibration_curve.png",
    )
    plot_prediction_distribution(
        y_prob, 0.5, opt_thresh, p_dir / "prediction_distribution.png"
    )

    # 8. Persist JSON Artifacts
    # a. decision_threshold.json
    thresh_payload = {
        "optimal_threshold": opt_thresh,
        "optimal_f1": opt_results["optimal_f1"],
        "optimal_precision": opt_results["optimal_precision"],
        "optimal_recall": opt_results["optimal_recall"],
        "default_metrics_at_0_5": {
            "roc_auc": default_metrics["roc_auc"],
            "f1": default_metrics["f1"],
            "precision": default_metrics["precision"],
            "recall": default_metrics["recall"],
        },
    }
    thresh_file = threshold_path or Path(settings.DECISION_THRESHOLD_PATH)
    if output_dir and not threshold_path:
        thresh_file = output_dir / "decision_threshold.json"
    thresh_file.parent.mkdir(parents=True, exist_ok=True)
    with open(thresh_file, "w", encoding="utf-8") as f:
        json.dump(thresh_payload, f, indent=2)
    logger.info(f"Persisted optimal decision threshold to '{thresh_file}'")

    # b. classification_report.json
    report_file = Path(settings.CLASSIFICATION_REPORT_PATH)
    if output_dir:
        report_file = output_dir / "classification_report.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(default_metrics["classification_report"], f, indent=2)
    logger.info(f"Persisted classification report to '{report_file}'")

    # c. calibration_metrics.json
    calib_file = Path(settings.CALIBRATION_METRICS_PATH)
    if output_dir:
        calib_file = output_dir / "calibration_metrics.json"
    calib_file.parent.mkdir(parents=True, exist_ok=True)
    with open(calib_file, "w", encoding="utf-8") as f:
        json.dump(calib_metrics, f, indent=2)
    logger.info(f"Persisted calibration metrics to '{calib_file}'")

    # d. evaluation_metrics.json (Consolidated Report)
    eval_summary = {
        "model_algorithm": meta_dict.get("algorithm", type(model).__name__),
        "test_samples": len(y_test),
        "metrics_at_threshold_0_5": {
            "roc_auc": default_metrics["roc_auc"],
            "f1": default_metrics["f1"],
            "precision": default_metrics["precision"],
            "recall": default_metrics["recall"],
            "confusion_matrix": default_metrics["confusion_matrix"],
        },
        "optimal_threshold_metrics": {
            "optimal_threshold": opt_thresh,
            "f1": opt_metrics["f1"],
            "precision": opt_metrics["precision"],
            "recall": opt_metrics["recall"],
            "confusion_matrix": opt_metrics["confusion_matrix"],
        },
        "brier_score": calib_metrics["brier_score"],
        "provenance": {
            "git_commit_hash": meta_dict.get("git_commit_hash", "unknown"),
            "dataset_sha256": meta_dict.get("dataset_sha256", "unknown"),
            "feature_pipeline_sha256": meta_dict.get(
                "feature_pipeline_sha256", "unknown"
            ),
            "schema_version": meta_dict.get("schema_version", "1.0.0"),
        },
    }

    eval_summary_file = Path(settings.EVALUATION_METRICS_PATH)
    if output_dir:
        eval_summary_file = output_dir / "evaluation_metrics.json"
    eval_summary_file.parent.mkdir(parents=True, exist_ok=True)
    with open(eval_summary_file, "w", encoding="utf-8") as f:
        json.dump(eval_summary, f, indent=2)
    logger.info(f"Persisted evaluation metrics report to '{eval_summary_file}'")

    return eval_summary
