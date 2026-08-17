"""Model promotion and MLflow experiment tracking engine.

Enforces Master Contract Section 9 promotion policy and operationalizes
models/promotion_policy.json as the versioned source of truth.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import mlflow
import mlflow.sklearn
from mlflow.tracking import MlflowClient

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)


def load_promotion_policy(
    policy_path: Optional[Path] = None,
) -> Dict[str, float]:
    """Load model promotion policy thresholds from versioned JSON artifact.

    Args:
        policy_path: Path to promotion_policy.json artifact.

    Returns:
        Dict containing min_f1_improvement, max_precision_drop, max_recall_drop.
    """
    settings = get_settings()
    p_path = policy_path or Path(settings.PROMOTION_POLICY_PATH)

    if p_path.exists():
        with open(p_path, "r", encoding="utf-8") as f:
            policy_data: Dict[str, float] = json.load(f)
            logger.info(f"Loaded promotion policy from '{p_path}'")
            return policy_data

    # Fallback default seeding from settings / Section 9
    logger.warning(
        f"Promotion policy file not found at '{p_path}'. Using Section 9 defaults."
    )
    return {
        "min_f1_improvement": settings.PROMOTION_MIN_F1_DELTA,
        "max_precision_drop": settings.PROMOTION_MAX_PRECISION_DROP,
        "max_recall_drop": 0.0,
    }


def compare_candidate_to_incumbent(
    candidate_metrics: Dict[str, Any],
    incumbent_metrics: Optional[Dict[str, Any]] = None,
    policy: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Compare candidate model against incumbent Production model using optimal F1.

    Args:
        candidate_metrics: Dict of candidate model evaluation metrics.
        incumbent_metrics: Dict of incumbent Production model metrics
            (None if initial bootstrap).
        policy: Dict of policy thresholds.

    Returns:
        Dict containing is_promoted, reason, f1_delta, precision_drop, recall_drop.
    """

    active_policy = policy or load_promotion_policy()
    min_f1_imp = active_policy.get("min_f1_improvement", 0.01)
    max_prec_drop = active_policy.get("max_precision_drop", 0.02)
    max_rec_drop = active_policy.get("max_recall_drop", 0.0)

    # Bootstrap Case: No existing Production model
    if incumbent_metrics is None or not incumbent_metrics:
        reason = "no existing production model — initial promotion"
        logger.info(f"Promotion check result: PROMOTED (Bootstrap) - {reason}")
        return {
            "is_promoted": True,
            "reason": reason,
            "is_bootstrap": True,
            "f1_delta": 0.0,
            "precision_drop": 0.0,
            "recall_drop": 0.0,
            "checks": {
                "f1_passed": True,
                "precision_passed": True,
                "recall_passed": True,
            },
        }

    # Extract optimal threshold metrics per Phase 8 standard
    c_opt = candidate_metrics.get(
        "optimal_threshold_metrics",
        candidate_metrics.get("metrics_at_threshold_0_5", {}),
    )
    i_opt = incumbent_metrics.get(
        "optimal_threshold_metrics",
        incumbent_metrics.get("metrics_at_threshold_0_5", {}),
    )

    c_f1 = float(c_opt.get("f1", 0.0))
    c_prec = float(c_opt.get("precision", 0.0))
    c_rec = float(c_opt.get("recall", 0.0))

    i_f1 = float(i_opt.get("f1", 0.0))
    i_prec = float(i_opt.get("precision", 0.0))
    i_rec = float(i_opt.get("recall", 0.0))

    # Calculate metric deltas
    f1_delta = round(c_f1 - i_f1, 4)
    precision_drop = round(i_prec - c_prec, 4)
    recall_drop = round(i_rec - c_rec, 4)

    # Rule 1: F1 Improvement >= min_f1_improvement
    f1_passed = f1_delta >= min_f1_imp

    # Rule 2: Precision Drop <= max_precision_drop
    precision_passed = precision_drop <= max_prec_drop

    # Rule 3: Recall Decrease <= max_recall_drop (0.0)
    recall_passed = recall_drop <= max_rec_drop

    all_passed = f1_passed and precision_passed and recall_passed

    if all_passed:
        reason = (
            f"Promoted: F1 improved by {f1_delta:+.4f} (>= {min_f1_imp:+.4f}), "
            f"Precision drop {precision_drop:.4f} (<= {max_prec_drop:.4f}), "
            f"Recall drop {recall_drop:.4f} (<= {max_rec_drop:.4f})"
        )
        logger.info(f"Promotion check result: PROMOTED - {reason}")
    else:
        failed_reasons = []
        if not f1_passed:
            failed_reasons.append(
                f"F1 delta ({f1_delta:+.4f}) < min required ({min_f1_imp:+.4f})"
            )
        if not precision_passed:
            p_drop_str = f"{precision_drop:.4f}"
            p_max_str = f"{max_prec_drop:.4f}"
            failed_reasons.append(
                f"Precision drop ({p_drop_str}) > max allowed ({p_max_str})"
            )
        if not recall_passed:
            r_drop_str = f"{recall_drop:.4f}"
            r_max_str = f"{max_rec_drop:.4f}"
            failed_reasons.append(
                f"Recall drop ({r_drop_str}) > max allowed ({r_max_str})"
            )

        reason = "Rejected: " + "; ".join(failed_reasons)
        logger.warning(f"Promotion check result: REJECTED - {reason}")

    return {
        "is_promoted": all_passed,
        "reason": reason,
        "is_bootstrap": False,
        "f1_delta": f1_delta,
        "precision_drop": precision_drop,
        "recall_drop": recall_drop,
        "checks": {
            "f1_passed": f1_passed,
            "precision_passed": precision_passed,
            "recall_passed": recall_passed,
        },
    }


def log_pipeline_run_to_mlflow(
    eval_report: Dict[str, Any],
    tracking_uri: Optional[str] = None,
    experiment_name: Optional[str] = None,
) -> Tuple[str, str]:
    """Log model training/evaluation pipeline run artifacts to MLflow.

    Args:
        eval_report: Dict containing Phase 8 generate_evaluation_report output.
        tracking_uri: Optional tracking URI override.
        experiment_name: Optional experiment name override.

    Returns:
        Tuple of (parent_run_id, child_run_id).
    """
    settings = get_settings()
    t_uri = tracking_uri or settings.MLFLOW_TRACKING_URI
    exp_name = experiment_name or settings.MLFLOW_EXPERIMENT_NAME

    mlflow.set_tracking_uri(t_uri)
    mlflow.set_experiment(exp_name)

    provenance = eval_report.get("provenance", {})
    m_default = eval_report.get("metrics_at_threshold_0_5", {})
    m_optimal = eval_report.get("optimal_threshold_metrics", {})
    algorithm = eval_report.get("model_algorithm", "XGBClassifier")

    # 1. Start Parent Pipeline Run
    with mlflow.start_run(run_name=f"Pipeline_Run_{algorithm}") as parent_run:
        parent_id = parent_run.info.run_id
        logger.info(f"Started MLflow parent run ID: {parent_id}")

        # Log parameters
        mlflow.log_params(
            {
                "algorithm": algorithm,
                "test_samples": eval_report.get("test_samples", 1409),
                "git_commit_hash": provenance.get("git_commit_hash", "unknown"),
                "dataset_sha256": provenance.get("dataset_sha256", "unknown"),
                "feature_pipeline_sha256": provenance.get(
                    "feature_pipeline_sha256", "unknown"
                ),
                "schema_version": provenance.get("schema_version", "1.0.0"),
            }
        )

        # Log metrics (Default 0.5 and Optimal Threshold)
        mlflow.log_metrics(
            {
                "test_roc_auc_default_0_5": float(m_default.get("roc_auc", 0.0)),
                "test_f1_default_0_5": float(m_default.get("f1", 0.0)),
                "test_precision_default_0_5": float(m_default.get("precision", 0.0)),
                "test_recall_default_0_5": float(m_default.get("recall", 0.0)),
                "test_optimal_threshold": float(
                    m_optimal.get("optimal_threshold", 0.5)
                ),
                "test_f1_optimal": float(m_optimal.get("f1", 0.0)),
                "test_precision_optimal": float(m_optimal.get("precision", 0.0)),
                "test_recall_optimal": float(m_optimal.get("recall", 0.0)),
                "brier_score_loss": float(eval_report.get("brier_score", 0.0)),
            }
        )

        # Log Report Artifacts
        reports_dir = Path(settings.EVALUATION_METRICS_PATH).parent
        models_dir = Path(settings.MODEL_OUTPUT_PATH).parent
        plots_dir = Path(settings.PLOTS_DIR)

        for p_file in [
            reports_dir / "evaluation_metrics.json",
            reports_dir / "classification_report.json",
            reports_dir / "calibration_metrics.json",
            reports_dir / "feature_importance.csv",
            reports_dir / "error_analysis.csv",
            models_dir / "decision_threshold.json",
        ]:
            if p_file.exists():
                mlflow.log_artifact(str(p_file), artifact_path="reports")

        if plots_dir.exists():
            mlflow.log_artifacts(str(plots_dir), artifact_path="plots")

        # Log Model Artifact
        model_path = Path(settings.MODEL_OUTPUT_PATH)
        if model_path.exists():
            mlflow.log_artifact(str(model_path), artifact_path="model")

        # 2. Log Nested Child Run for Historical LR Candidate
        # Metrics-only historical run; no model artifact and zero refitting
        child_id = ""
        train_meta_path = Path(settings.TRAINING_METRICS_PATH)
        if train_meta_path.exists():
            try:
                with open(train_meta_path, "r", encoding="utf-8") as f:
                    t_data = json.load(f)
                candidates = t_data.get("candidates", {})
                lr_cand = candidates.get("LogisticRegression", {})
                if lr_cand:
                    with mlflow.start_run(
                        run_name="historical_candidate_logistic_regression",
                        nested=True,
                    ) as child_run:
                        child_id = child_run.info.run_id
                        mlflow.set_tags(
                            {
                                "model_status": (
                                    "metrics_only_historical, no_persisted_estimator"
                                ),
                                "candidate_family": "LogisticRegression",
                            }
                        )
                        mlflow.log_params(
                            {
                                "algorithm": "LogisticRegression",
                                "note": "Historical metric baseline from Phase 7",
                            }
                        )
                        mlflow.log_metrics(
                            {
                                "cv_roc_auc": float(lr_cand.get("cv_roc_auc", 0.0)),
                                "test_roc_auc": float(lr_cand.get("test_roc_auc", 0.0)),
                                "test_f1": float(lr_cand.get("test_f1", 0.0)),
                                "test_precision": float(
                                    lr_cand.get("test_precision", 0.0)
                                ),
                                "test_recall": float(lr_cand.get("test_recall", 0.0)),
                            }
                        )
                        logger.info(f"Logged LR child run (ID: {child_id})")
            except Exception as e:
                logger.warning(f"Could not log LR child run to MLflow: {e}")

    return parent_id, child_id


def promote_model(
    tracking_uri: Optional[str] = None,
    experiment_name: Optional[str] = None,
    model_name: Optional[str] = None,
    eval_report_path: Optional[Path] = None,
    model_path: Optional[Path] = None,
    policy_path: Optional[Path] = None,
    client: Optional[MlflowClient] = None,
) -> Dict[str, Any]:
    """Orchestrate MLflow model registration and promotion policy evaluation.

    Args:
        tracking_uri: Optional MLflow tracking URI override.
        experiment_name: Optional MLflow experiment name override.
        model_name: Optional registered model name override.
        eval_report_path: Optional path to evaluation_metrics.json artifact.
        model_path: Optional path to serialized best_model.joblib artifact.
        policy_path: Optional path to promotion_policy.json.
        client: Optional pre-configured MlflowClient instance.

    Returns:
        Dict containing promotion results, model version, and lifecycle details.
    """
    settings = get_settings()
    t_uri = tracking_uri or settings.MLFLOW_TRACKING_URI
    exp_name = experiment_name or settings.MLFLOW_EXPERIMENT_NAME
    m_name = model_name or settings.MLFLOW_MODEL_NAME
    e_path = eval_report_path or Path(settings.EVALUATION_METRICS_PATH)
    m_path = model_path or Path(settings.MODEL_OUTPUT_PATH)
    p_path = policy_path or Path(settings.PROMOTION_POLICY_PATH)

    # Use passed client or instantiate new MlflowClient against tracking URI
    m_client = client or MlflowClient(tracking_uri=t_uri)

    if not e_path.exists():
        err_msg = f"Evaluation metrics report not found at '{e_path}'."
        logger.error(err_msg)
        raise FileNotFoundError(err_msg)

    with open(e_path, "r", encoding="utf-8") as f:
        candidate_metrics: Dict[str, Any] = json.load(f)

    # 1. Log Run to MLflow Tracking
    parent_run_id, _ = log_pipeline_run_to_mlflow(
        candidate_metrics, tracking_uri=t_uri, experiment_name=exp_name
    )

    # 2. Register Candidate Model in Model Registry
    try:
        m_client.create_registered_model(m_name)
        logger.info(f"Created registered model '{m_name}' in MLflow Registry.")
    except Exception:
        # Registered model container already exists
        pass

    model_version = m_client.create_model_version(
        name=m_name,
        source=str(m_path.resolve()),
        run_id=parent_run_id,
        description=f"Model candidate from run {parent_run_id}",
    )
    v_num = model_version.version
    logger.info(f"Registered model candidate '{m_name}' version {v_num}.")

    # 3. Retrieve Current Production Model Version & Metrics
    incumbent_metrics: Optional[Dict[str, Any]] = None
    latest_prod_versions = m_client.get_latest_versions(m_name, stages=["Production"])

    if latest_prod_versions:
        prod_ver = latest_prod_versions[0]
        tags = prod_ver.tags or {}
        if "optimal_f1" in tags and tags.get("optimal_f1"):
            incumbent_metrics = {
                "optimal_threshold_metrics": {
                    "f1": float(tags.get("optimal_f1", 0.0)),
                    "precision": float(tags.get("optimal_precision", 0.0)),
                    "recall": float(tags.get("optimal_recall", 0.0)),
                }
            }
            logger.info(
                f"Retrieved incumbent Production model (v{prod_ver.version}) "
                "benchmark metrics from version tags."
            )
        else:
            # Retrieve incumbent metrics from version tags or run metrics
            try:
                prod_run = m_client.get_run(prod_ver.run_id)
                incumbent_metrics = {
                    "optimal_threshold_metrics": {
                        "f1": prod_run.data.metrics.get(
                            "test_f1_optimal",
                            prod_run.data.metrics.get("test_f1_default_0_5", 0.0),
                        ),
                        "precision": prod_run.data.metrics.get(
                            "test_precision_optimal",
                            prod_run.data.metrics.get(
                                "test_precision_default_0_5", 0.0
                            ),
                        ),
                        "recall": prod_run.data.metrics.get(
                            "test_recall_optimal",
                            prod_run.data.metrics.get("test_recall_default_0_5", 0.0),
                        ),
                    }
                }
                logger.info(
                    f"Retrieved incumbent Production model (v{prod_ver.version}) "
                    "metrics from run."
                )
            except Exception as e:
                logger.warning(f"Could not load Production run metrics: {e}.")

    # 4. Compare Candidate against Incumbent
    active_policy = load_promotion_policy(p_path) if p_path.exists() else None
    promotion_result = compare_candidate_to_incumbent(
        candidate_metrics, incumbent_metrics=incumbent_metrics, policy=active_policy
    )
    is_promoted = promotion_result["is_promoted"]
    reason = promotion_result["reason"]

    # 5. Transition Stage & Tag Model Version
    if is_promoted:
        target_stage = "Production"
        m_client.transition_model_version_stage(
            name=m_name,
            version=v_num,
            stage=target_stage,
            archive_existing_versions=True,
        )
        m_client.set_model_version_tag(m_name, v_num, "promotion_status", "promoted")
        m_client.set_model_version_tag(m_name, v_num, "promotion_reason", reason)
        c_opt = candidate_metrics.get("optimal_threshold_metrics", {})
        m_client.set_model_version_tag(
            m_name, v_num, "optimal_f1", str(c_opt.get("f1", ""))
        )
        m_client.set_model_version_tag(
            m_name, v_num, "optimal_precision", str(c_opt.get("precision", ""))
        )
        m_client.set_model_version_tag(
            m_name, v_num, "optimal_recall", str(c_opt.get("recall", ""))
        )
        logger.info(f"Successfully PROMOTED '{m_name}' v{v_num} to Production stage.")
    else:
        target_stage = "Staging"
        m_client.transition_model_version_stage(
            name=m_name,
            version=v_num,
            stage=target_stage,
            archive_existing_versions=False,
        )
        m_client.set_model_version_tag(m_name, v_num, "promotion_status", "rejected")
        m_client.set_model_version_tag(m_name, v_num, "promotion_reason", reason)
        logger.info(
            f"REJECTED '{m_name}' v{v_num} for Production; retained in Staging."
        )

    return {
        "model_name": m_name,
        "model_version": v_num,
        "stage": target_stage,
        "is_promoted": is_promoted,
        "reason": reason,
        "run_id": parent_run_id,
        "metrics": promotion_result,
    }
