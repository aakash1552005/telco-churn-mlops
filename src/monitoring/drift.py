"""Evidently AI Drift Detection and Retraining Policy Module.

Implements Master Contract Section 10 Drift Policy:
- Feature PSI Threshold: PSI > 0.20
- Evidently Data Drift Score Threshold:
  Dataset drift score (share of drifted features) > 0.15
- Prediction Confidence Threshold: Mean prediction confidence < 0.75
- Consecutive Window State Machine:
  3 consecutive drift windows required to trigger retraining.

Current-Window Data Strategy: Option (B) Synthetic Current
Window (held-out slice of test.csv).
Note: Results are explicitly tagged as synthetic/pre-production
as persistent request logging is not yet active.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from evidently.legacy.metric_preset import DataDriftPreset
from evidently.legacy.report import Report

from src.core.config import Settings, get_settings
from src.core.logging import get_logger
from src.monitoring.jenkins_trigger import trigger_jenkins_retraining
from src.monitoring.state import MonitoringStateManager

logger = get_logger(__name__)

# Default artifact paths
DEFAULT_REFERENCE_PATH = Path("data/processed/train.csv")
DEFAULT_CURRENT_PATH = Path("data/processed/test.csv")
DEFAULT_SCHEMA_PATH = Path("models/feature_schema.json")
DEFAULT_MODEL_PATH = Path("models/best_model.joblib")
DEFAULT_PIPELINE_PATH = Path("models/feature_pipeline.joblib")
DEFAULT_REPORT_JSON_PATH = Path("reports/drift_report.json")
DEFAULT_REPORT_HTML_PATH = Path("reports/drift_report.html")


def calculate_psi(
    ref: pd.Series,
    curr: pd.Series,
    num_bins: int = 10,
    epsilon: float = 1e-4,
) -> float:
    """Calculate Population Stability Index (PSI) between reference and current series.

    Args:
        ref: Reference distribution series.
        curr: Current monitoring distribution series.
        num_bins: Number of quantiles for continuous variables (default: 10).
        epsilon: Smoothing epsilon to prevent log(0) or division by zero.

    Returns:
        Float PSI value.
    """
    ref_clean = ref.dropna()
    curr_clean = curr.dropna()

    if len(ref_clean) == 0 or len(curr_clean) == 0:
        return 0.0

    unique_vals = np.union1d(ref_clean.unique(), curr_clean.unique())

    # Categorical or low-cardinality discrete feature (<= 10 unique values)
    if len(unique_vals) <= 10:
        ref_counts = ref_clean.value_counts(normalize=True)
        curr_counts = curr_clean.value_counts(normalize=True)
        psi = 0.0
        for val in unique_vals:
            p = ref_counts.get(val, 0.0) + epsilon
            q = curr_counts.get(val, 0.0) + epsilon
            psi += (q - p) * np.log(q / p)
        return float(max(0.0, psi))

    # Continuous / high-cardinality numerical feature: bin based on reference quantiles
    try:
        quantiles = np.linspace(0, 1, num_bins + 1)
        bins = np.percentile(ref_clean, quantiles * 100)
        bins = np.unique(bins)
        if len(bins) < 2:
            return 0.0
        bins[0] = -np.inf
        bins[-1] = np.inf

        ref_binned = pd.cut(ref_clean, bins=bins, include_lowest=True)
        curr_binned = pd.cut(curr_clean, bins=bins, include_lowest=True)

        ref_pct = ref_binned.value_counts(normalize=True).sort_index() + epsilon
        curr_pct = curr_binned.value_counts(normalize=True).sort_index() + epsilon

        ref_pct = ref_pct / ref_pct.sum()
        curr_pct = curr_pct / curr_pct.sum()

        psi_val = np.sum((curr_pct - ref_pct) * np.log(curr_pct / ref_pct))
        return float(max(0.0, psi_val))
    except Exception as e:
        logger.warning(f"Error computing PSI for continuous feature: {e}")
        return 0.0


def calculate_feature_psis(
    ref_df: pd.DataFrame,
    curr_df: pd.DataFrame,
    features: List[str],
) -> Dict[str, float]:
    """Calculate PSI for all listed features.

    Args:
        ref_df: Reference DataFrame.
        curr_df: Current monitoring DataFrame.
        features: List of feature column names.

    Returns:
        Dict mapping feature name to its PSI value.
    """
    psi_dict: Dict[str, float] = {}
    for feat in features:
        if feat in ref_df.columns and feat in curr_df.columns:
            psi_dict[feat] = round(calculate_psi(ref_df[feat], curr_df[feat]), 6)
    return psi_dict


def run_evidently_drift_report(
    ref_df: pd.DataFrame,
    curr_df: pd.DataFrame,
    features: List[str],
    save_html_path: Optional[Path] = None,
) -> Tuple[float, Dict[str, Any]]:
    """Execute Evidently DataDriftPreset report and extract drift scores.

    Args:
        ref_df: Reference feature DataFrame.
        curr_df: Current monitoring feature DataFrame.
        features: Target features to evaluate.
        save_html_path: Optional path to persist rendered HTML dashboard.

    Returns:
        Tuple of (dataset_drift_share, detailed_results_dict).
    """
    ref_eval = ref_df[features].copy()
    curr_eval = curr_df[features].copy()

    report = Report(metrics=[DataDriftPreset()])
    report.run(reference_data=ref_eval, current_data=curr_eval)

    report_dict = report.as_dict()
    metrics_list = report_dict.get("metrics", [])

    dataset_drift_share = 0.0
    detailed_results: Dict[str, Any] = {
        "share_of_drifted_columns": 0.0,
        "number_of_drifted_columns": 0,
        "number_of_columns": len(features),
        "dataset_drift": False,
        "column_drift": {},
    }

    for m in metrics_list:
        metric_name = m.get("metric")
        res = m.get("result", {})
        if metric_name == "DatasetDriftMetric":
            dataset_drift_share = float(res.get("share_of_drifted_columns", 0.0))
            detailed_results["share_of_drifted_columns"] = round(dataset_drift_share, 4)
            detailed_results["number_of_drifted_columns"] = res.get(
                "number_of_drifted_columns", 0
            )
            detailed_results["number_of_columns"] = res.get(
                "number_of_columns", len(features)
            )
            detailed_results["dataset_drift"] = res.get("dataset_drift", False)
        elif metric_name == "DataDriftTable":
            drift_by_columns = res.get("drift_by_columns", {})
            detailed_results["column_drift"] = {
                col: {
                    "drift_score": round(data.get("drift_score", 0.0), 6),
                    "drift_detected": data.get("drift_detected", False),
                    "stat_test": data.get("stat_test_name", "unknown"),
                }
                for col, data in drift_by_columns.items()
            }

    if save_html_path:
        try:
            save_html_path.parent.mkdir(parents=True, exist_ok=True)
            report.save_html(str(save_html_path))
            logger.info(f"Persisted Evidently HTML report to: '{save_html_path}'")
        except Exception as e:
            logger.warning(f"Failed to persist Evidently HTML report: {e}")

    return dataset_drift_share, detailed_results


def calculate_prediction_confidence(
    curr_df: pd.DataFrame,
    model: Any = None,
    model_path: Optional[Path] = None,
    features: Optional[List[str]] = None,
) -> Tuple[float, np.ndarray]:
    """Compute model prediction probabilities and mean confidence.

    Runs on current monitoring data.

    Confidence for binary classification: max(p, 1 - p).

    Args:
        curr_df: Current monitoring dataset (processed feature columns).
        model: Pre-loaded model estimator.
        model_path: Path to best_model.joblib if model is not pre-loaded.
        features: Optional list of features to subset.

    Returns:
        Tuple of (mean_prediction_confidence, array_of_probabilities).
    """
    if model is None:
        m_path = model_path or DEFAULT_MODEL_PATH
        if not m_path.exists():
            logger.warning(
                f"Model file '{m_path}' not found. Returning default confidence 1.0"
            )
            return 1.0, np.array([])
        model = joblib.load(m_path)

    eval_data = curr_df[features] if features else curr_df
    # Drop target if present
    if "Churn" in eval_data.columns:
        eval_data = eval_data.drop(columns=["Churn"])

    if hasattr(model, "predict_proba"):
        probs = model.predict_proba(eval_data)[:, 1]
    elif hasattr(model, "predict"):
        probs = model.predict(eval_data).astype(float)
    else:
        return 1.0, np.array([])

    confidences = np.maximum(probs, 1.0 - probs)
    mean_conf = float(np.mean(confidences))
    return round(mean_conf, 6), probs


def evaluate_drift_criteria(
    psis: Dict[str, float],
    evidently_score: float,
    mean_confidence: float,
    settings: Optional[Settings] = None,
) -> Tuple[bool, Dict[str, Any], List[str]]:
    """Evaluate Master Contract Section 10 threshold rules strictly.

    Rules:
    - Feature PSI > DRIFT_FEATURE_PSI_THRESHOLD (0.20)
    - Evidently data drift score > DRIFT_EVIDENTLY_SCORE_THRESHOLD (0.15)
    - Mean prediction confidence < DRIFT_CONFIDENCE_THRESHOLD (0.75)

    Args:
        psis: Dict of per-feature PSI values.
        evidently_score: Dataset drift score (share of drifted columns).
        mean_confidence: Mean prediction confidence across monitoring batch.
        settings: Application settings containing Section 10 thresholds.

    Returns:
        Tuple of (is_drift_detected, criteria_breakdown_dict,
        list_of_triggering_criteria).
    """
    cfg = settings or get_settings()

    psi_threshold = cfg.DRIFT_FEATURE_PSI_THRESHOLD
    evidently_threshold = cfg.DRIFT_EVIDENTLY_SCORE_THRESHOLD
    confidence_threshold = cfg.DRIFT_CONFIDENCE_THRESHOLD

    # 1. Feature PSI Criterion (strict >)
    drifted_psi_features = {
        feat: psi for feat, psi in psis.items() if psi > psi_threshold
    }
    psi_breached = len(drifted_psi_features) > 0
    max_psi = max(psis.values()) if psis else 0.0

    # 2. Evidently Data Drift Score Criterion (strict >)
    evidently_breached = evidently_score > evidently_threshold

    # 3. Mean Prediction Confidence Criterion (strict <)
    confidence_breached = mean_confidence < confidence_threshold

    triggering_criteria: List[str] = []
    if psi_breached:
        triggering_criteria.append(
            f"feature_psi (max_psi={max_psi:.4f} > {psi_threshold})"
        )
    if evidently_breached:
        triggering_criteria.append(
            f"evidently_drift_score ({evidently_score:.4f} > {evidently_threshold})"
        )
    if confidence_breached:
        triggering_criteria.append(
            f"mean_confidence ({mean_confidence:.4f} < {confidence_threshold})"
        )

    is_drift_detected = psi_breached or evidently_breached or confidence_breached

    criteria_summary: Dict[str, Any] = {
        "psi_criterion": {
            "threshold": psi_threshold,
            "max_psi": round(max_psi, 6),
            "drifted_features_count": len(drifted_psi_features),
            "drifted_features": drifted_psi_features,
            "breached": psi_breached,
        },
        "evidently_criterion": {
            "threshold": evidently_threshold,
            "dataset_drift_score": round(evidently_score, 4),
            "breached": evidently_breached,
        },
        "confidence_criterion": {
            "threshold": confidence_threshold,
            "mean_confidence": round(mean_confidence, 6),
            "breached": confidence_breached,
        },
        "drift_detected": is_drift_detected,
        "triggering_criteria": triggering_criteria,
    }

    return is_drift_detected, criteria_summary, triggering_criteria


def run_drift_pipeline(
    reference_path: Optional[Path] = None,
    current_path: Optional[Path] = None,
    window_id: Optional[str] = None,
    state_file_path: Optional[Path] = None,
    output_report_path: Optional[Path] = None,
    output_html_path: Optional[Path] = None,
    trigger_retraining: bool = True,
    settings: Optional[Settings] = None,
    jenkins_parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute the full end-to-end drift monitoring workflow.

    1. Ingests reference dataset and current monitoring window.
    2. Computes per-feature PSI, Evidently Data Drift, and Model Confidence.
    3. Evaluates Section 10 drift threshold rules.
    4. Updates persistent monitoring state machine (3-consecutive-windows rule).
    5. Updates Prometheus metrics.
    6. Dispatches Jenkins retraining trigger on 3rd consecutive drift window.
    7. Persists structured JSON report and HTML summary.

    Returns:
        Structured drift report dictionary.
    """
    cfg = settings or get_settings()
    ref_p = reference_path or DEFAULT_REFERENCE_PATH
    curr_p = current_path or DEFAULT_CURRENT_PATH
    w_id = window_id or f"win-{uuid.uuid4().hex[:8]}"

    logger.info(
        f"Starting drift monitoring pipeline for window '{w_id}' "
        f"[ref='{ref_p}', curr='{curr_p}']"
    )

    if not ref_p.exists():
        raise FileNotFoundError(f"Reference dataset not found at: '{ref_p}'")
    if not curr_p.exists():
        raise FileNotFoundError(f"Current monitoring dataset not found at: '{curr_p}'")

    ref_df = pd.read_csv(ref_p)
    curr_df = pd.read_csv(curr_p)

    # Resolve features (exclude target 'Churn')
    features = [c for c in ref_df.columns if c != "Churn" and c in curr_df.columns]

    # 1. Compute per-feature PSI
    psis = calculate_feature_psis(ref_df, curr_df, features)

    # 2. Compute Evidently Data Drift
    html_out = output_html_path or DEFAULT_REPORT_HTML_PATH
    evidently_score, evidently_details = run_evidently_drift_report(
        ref_df, curr_df, features, save_html_path=html_out
    )

    # 3. Compute Prediction Confidence
    mean_conf, _ = calculate_prediction_confidence(curr_df, features=features)

    # 4. Evaluate Section 10 Drift Criteria
    is_drift, criteria_summary, triggering_reasons = evaluate_drift_criteria(
        psis, evidently_score, mean_conf, settings=cfg
    )

    # 5. Update Persistent State Machine
    state_mgr = MonitoringStateManager(state_file_path=state_file_path)
    consecutive_count, should_retrain = state_mgr.record_window_result(
        window_id=w_id,
        drift_detected=is_drift,
        triggering_criteria=triggering_reasons,
        retraining_threshold=cfg.DRIFT_CONSECUTIVE_WINDOWS,
        metadata={
            "reference_source": str(ref_p),
            "current_window_source": str(curr_p),
            "synthetic_current_window": True,
            "evidently_drift_score": evidently_score,
            "mean_confidence": mean_conf,
        },
    )

    # 6. Update Prometheus Metrics (if metrics module available)
    try:
        from src.api.metrics import update_drift_metrics

        update_drift_metrics(
            score=evidently_score,
            detected=is_drift,
            consecutive_windows=consecutive_count,
        )
    except Exception as e:
        logger.debug(f"Prometheus metric update skipped: {e}")

    # 7. Retraining Trigger Execution (if 3 consecutive windows reached)
    jenkins_trigger_result: Optional[Dict[str, Any]] = None
    if should_retrain and trigger_retraining:
        logger.warning(
            "DRIFT TRIGGER ACTIVATED: Reached "
            f"{consecutive_count} consecutive drift windows! "
            f"Triggering Jenkins retraining pipeline."
        )
        try:
            jenkins_trigger_result = trigger_jenkins_retraining(
                reason=triggering_reasons,
                parameters=jenkins_parameters,
            )
        except Exception as e:
            logger.error(f"Failed to trigger Jenkins retraining pipeline: {e}")
            jenkins_trigger_result = {"status": "failed", "error": str(e)}

    # 8. Assemble and persist structured drift report
    report: Dict[str, Any] = {
        "window_id": w_id,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "reference_source": str(ref_p),
            "current_window_source": str(curr_p),
            "synthetic_current_window": True,
            "feature_count": len(features),
            "reference_rows": len(ref_df),
            "current_window_rows": len(curr_df),
        },
        "summary": {
            "drift_detected": is_drift,
            "consecutive_drift_windows": consecutive_count,
            "retraining_triggered": should_retrain,
            "triggering_criteria": triggering_reasons,
            "evidently_dataset_drift_score": evidently_score,
            "mean_prediction_confidence": mean_conf,
            "max_feature_psi": max(psis.values()) if psis else 0.0,
        },
        "criteria_breakdown": criteria_summary,
        "feature_psis": psis,
        "evidently_details": evidently_details,
        "jenkins_trigger": jenkins_trigger_result,
    }

    out_p = output_report_path or DEFAULT_REPORT_JSON_PATH
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Persisted drift report JSON to: '{out_p}'")

    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run Evidently AI Drift Detection & Monitoring Pipeline"
    )
    parser.add_argument(
        "--reference",
        type=Path,
        default=DEFAULT_REFERENCE_PATH,
        help="Path to reference dataset (default: data/processed/train.csv)",
    )
    parser.add_argument(
        "--current",
        type=Path,
        default=DEFAULT_CURRENT_PATH,
        help="Path to current monitoring window (default: data/processed/test.csv)",
    )
    parser.add_argument(
        "--window-id",
        type=str,
        default=None,
        help="Identifier for this monitoring window",
    )
    parser.add_argument(
        "--no-trigger",
        action="store_true",
        help="Disable automated Jenkins retraining trigger execution",
    )
    args = parser.parse_args()

    res = run_drift_pipeline(
        reference_path=args.reference,
        current_path=args.current,
        window_id=args.window_id,
        trigger_retraining=not args.no_trigger,
    )
    logger.info(
        "Drift Monitoring Completed: "
        f"drift_detected={res['summary']['drift_detected']}, "
        f"consecutive_windows={res['summary']['consecutive_drift_windows']}, "
        f"retraining_triggered={res['summary']['retraining_triggered']}"
    )
