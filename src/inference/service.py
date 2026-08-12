"""Prediction Service for Telco Customer Churn Platform.

Loads Production-stage model from MLflow Model Registry, verifies data and schema
provenance, executes Phase 6 feature pipeline transformation, and applies Phase 8
optimal decision threshold.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

import joblib
import mlflow
import mlflow.artifacts
import pandas as pd
from mlflow.tracking import MlflowClient

from src.core.config import get_settings
from src.core.logging import get_logger
from src.data.validation import load_schema_config
from src.training.train import calculate_file_sha256, validate_feature_schema

logger = get_logger(__name__)


class PredictionService:
    """Singleton service for loading Production model and executing inference."""

    def __init__(self) -> None:
        self.model: Any = None
        self.feature_pipeline: Any = None
        self.optimal_threshold: float = 0.5
        self.model_version: str = "unknown"
        self.run_id: str = "unknown"
        self.algorithm: str = "unknown"
        self.loaded_at: str = ""
        self.provenance: Dict[str, Any] = {}
        self.expected_features: list[str] = []

    def load_production_model(
        self,
        tracking_uri: Optional[str] = None,
        model_name: Optional[str] = None,
        pipeline_path: Optional[Path] = None,
        threshold_path: Optional[Path] = None,
        schema_path: Optional[Path] = None,
    ) -> None:
        """Load Production-stage model from MLflow Registry with hard defensive checks.

        Args:
            tracking_uri: Optional MLflow tracking URI override.
            model_name: Optional registered model name override.
            pipeline_path: Optional path to feature_pipeline.joblib.
            threshold_path: Optional path to decision_threshold.json.
            schema_path: Optional path to feature_schema.json.

        Raises:
            RuntimeError: If 0 Production models exist, >1 Production models exist,
                or if provenance SHA-256/version checks fail.
        """
        settings = get_settings()
        t_uri = tracking_uri or settings.MLFLOW_TRACKING_URI
        m_name = model_name or settings.MLFLOW_MODEL_NAME
        pipe_path = pipeline_path or Path(settings.FEATURE_PIPELINE_PATH)
        thresh_path = threshold_path or Path(settings.DECISION_THRESHOLD_PATH)
        sch_path = schema_path or Path(settings.FEATURE_SCHEMA_PATH)

        logger.info(
            f"Initializing Production model load from MLflow Registry "
            f"(URI='{t_uri}', model='{m_name}')..."
        )

        # 1. Query MLflow Registry for Production Stage Versions
        mlflow.set_tracking_uri(t_uri)
        m_client = MlflowClient(tracking_uri=t_uri)

        try:
            all_versions = m_client.search_model_versions(f"name='{m_name}'")
            prod_versions = [v for v in all_versions if v.current_stage == "Production"]
        except Exception as e:
            err_msg = (
                f"Failed to query MLflow Registry for model '{m_name}' "
                f"at URI '{t_uri}': {e}"
            )
            logger.error(err_msg)
            raise RuntimeError(err_msg) from e

        # Defensive Check 1: Must find at least 1 Production model
        if not prod_versions:
            err_msg = (
                f"Hard Failure: No Production-stage model found in MLflow Registry "
                f"for registered model '{m_name}'."
            )
            logger.error(err_msg)
            raise RuntimeError(err_msg)

        # Defensive Check 2 (Item 10): Must NOT find multiple Production models
        if len(prod_versions) > 1:
            ver_list = [v.version for v in prod_versions]
            err_msg = (
                f"Hard Failure: Multiple Production-stage model versions detected in "
                f"MLflow Registry for '{m_name}': versions {ver_list}."
            )
            logger.error(err_msg)
            raise RuntimeError(err_msg)

        prod_ver = prod_versions[0]
        v_num = str(prod_ver.version)
        r_id = str(prod_ver.run_id or "")

        logger.info(f"Found Production model version {v_num} (MLflow run ID: {r_id}).")

        # 2. Retrieve MLflow Run Parameters for Provenance Verification
        try:
            run = m_client.get_run(r_id)
            run_params = run.data.params or {}
        except Exception as e:
            err_msg = f"Failed to fetch MLflow run data for run_id '{r_id}': {e}"
            logger.error(err_msg)
            raise RuntimeError(err_msg) from e

        # Provenance Check (Item 2 Clarification):
        # Compare MLflow run params (logged in Phase 9) against local environment
        mlflow_pipe_sha = run_params.get("feature_pipeline_sha256", "")
        mlflow_schema_ver = run_params.get("schema_version", "")

        local_pipe_sha = calculate_file_sha256(pipe_path)
        schema_cfg = load_schema_config(Path(settings.SCHEMA_FILE_PATH))
        local_schema_ver = schema_cfg.get("schema_version", "1.0.0")

        if mlflow_pipe_sha and local_pipe_sha != "not_found":
            if mlflow_pipe_sha != local_pipe_sha:
                err_msg = (
                    f"Provenance Mismatch! MLflow Production model (v{v_num}) "
                    f"was trained with feature_pipeline_sha256='{mlflow_pipe_sha}', "
                    f"but local '{pipe_path}' has SHA-256='{local_pipe_sha}'."
                )
                logger.error(err_msg)
                raise RuntimeError(err_msg)

        if mlflow_schema_ver:
            if mlflow_schema_ver != local_schema_ver:
                err_msg = (
                    f"Provenance Mismatch! MLflow Production model (v{v_num}) "
                    f"was trained with schema_version='{mlflow_schema_ver}', "
                    f"but local schema has version='{local_schema_ver}'."
                )
                logger.error(err_msg)
                raise RuntimeError(err_msg)

        logger.info("Provenance consistency checks passed successfully.")

        # 3. Download / Load Model Artifact
        local_model_path = Path(settings.MODEL_OUTPUT_PATH)
        if not local_model_path.exists():
            try:
                downloaded_dir = mlflow.artifacts.download_artifacts(
                    run_id=r_id,
                    artifact_path="model",
                    tracking_uri=t_uri,
                )
                local_model_path = Path(downloaded_dir) / "best_model.joblib"
            except Exception as e:
                logger.warning(
                    f"Could not download model artifact from MLflow: {e}. "
                    f"Checking default fallback."
                )

        if not local_model_path.exists():
            err_msg = (
                f"Hard Failure: Model file not found at '{local_model_path}' "
                f"for Production model version {v_num}."
            )
            logger.error(err_msg)
            raise RuntimeError(err_msg)

        try:
            self.model = joblib.load(local_model_path)
            logger.info(f"Loaded estimator artifact from '{local_model_path}'.")
        except Exception as e:
            err_msg = (
                f"Failed to load joblib estimator model from '{local_model_path}': {e}"
            )
            logger.error(err_msg)
            raise RuntimeError(err_msg) from e

        # 4. Load Feature Pipeline Artifact
        if not pipe_path.exists():
            err_msg = (
                f"Hard Failure: Feature pipeline artifact not found at '{pipe_path}'."
            )
            logger.error(err_msg)
            raise RuntimeError(err_msg)

        try:
            self.feature_pipeline = joblib.load(pipe_path)
            logger.info(f"Loaded feature pipeline artifact from '{pipe_path}'.")
        except Exception as e:
            err_msg = f"Failed to load feature pipeline from '{pipe_path}': {e}"
            logger.error(err_msg)
            raise RuntimeError(err_msg) from e

        # 5. Load Decision Threshold Artifact (Phase 8 optimal threshold)
        opt_threshold = 0.5
        if thresh_path.exists():
            try:
                with open(thresh_path, "r", encoding="utf-8") as f:
                    t_data = json.load(f)
                opt_threshold = float(t_data.get("optimal_threshold", 0.5))
                logger.info(
                    f"Loaded optimal decision threshold {opt_threshold} "
                    f"from '{thresh_path}'."
                )
            except Exception as e:
                logger.warning(
                    f"Could not read decision threshold from '{thresh_path}': {e}. "
                    f"Falling back to default 0.5."
                )

        self.optimal_threshold = opt_threshold

        # 6. Load Feature Schema expected column order
        if sch_path.exists():
            with open(sch_path, "r", encoding="utf-8") as f:
                sch_data = json.load(f)
            self.expected_features = sch_data.get("features", [])

        # Store metadata state
        self.model_version = v_num
        self.run_id = r_id
        self.algorithm = run_params.get("algorithm", type(self.model).__name__)
        self.loaded_at = datetime.now(timezone.utc).isoformat()
        self.provenance = {
            "git_commit_hash": run_params.get("git_commit_hash", "unknown"),
            "dataset_sha256": run_params.get("dataset_sha256", "unknown"),
            "feature_pipeline_sha256": mlflow_pipe_sha or local_pipe_sha,
            "schema_version": mlflow_schema_ver or local_schema_ver,
        }

        logger.info(
            f"Production Prediction Service successfully ready! "
            f"(Model Version: {self.model_version}, Algorithm: {self.algorithm}, "
            f"Threshold: {self.optimal_threshold})"
        )

    def predict(self, raw_input: Union[Dict[str, Any], pd.DataFrame]) -> Dict[str, Any]:
        """Execute feature engineering transformation and churn prediction.

        Args:
            raw_input: Raw Telco customer fields as dict or 1-row DataFrame.

        Returns:
            Dict containing probability, decision, threshold_used, model_version.

        Raises:
            RuntimeError: If service is not initialized or model is missing.
            ValueError: If feature schema validation fails.
        """
        if self.model is None or self.feature_pipeline is None:
            raise RuntimeError("PredictionService is not initialized with a model.")

        if isinstance(raw_input, dict):
            df_raw = pd.DataFrame([raw_input])
        else:
            df_raw = raw_input.copy()

        # Remove non-feature columns if present
        customer_id = (
            df_raw.get("customerID", [None])[0] if "customerID" in df_raw else None
        )
        X_raw = df_raw.drop(columns=["customerID", "Churn"], errors="ignore")

        # 1. Transform raw 19 fields through Phase 6 feature pipeline
        X_transformed = self.feature_pipeline.transform(X_raw)

        # 2. Build processed DataFrame with schema column names
        if (
            self.expected_features
            and len(self.expected_features) == X_transformed.shape[1]
        ):
            feature_cols = self.expected_features
        else:
            # Fallback to column preprocessor output names
            col_trans = self.feature_pipeline.named_steps["column_preprocessor"]
            cat_enc = col_trans.named_transformers_["cat"]
            cat_names = list(cat_enc.get_feature_names_out())
            num_names = list(col_trans.transformers[1][2])
            bin_names = list(col_trans.transformers[2][2])
            feature_cols = cat_names + num_names + bin_names

        X_proc_df = pd.DataFrame(X_transformed, columns=feature_cols)

        # 3. Validate against models/feature_schema.json (Reuse Phase 7's function)
        validate_feature_schema(
            X_proc_df,
            schema_path=Path(get_settings().FEATURE_SCHEMA_PATH),
            log_success=False,
        )

        # 4. Score probabilities with model
        probs = self.model.predict_proba(X_proc_df)[:, 1]
        prob = float(probs[0])

        # 5. Apply optimal threshold
        churn_bool = prob >= self.optimal_threshold
        decision_str = "Churn" if churn_bool else "No Churn"

        return {
            "customerID": customer_id,
            "probability": round(prob, 6),
            "decision": decision_str,
            "churn_predicted": churn_bool,
            "threshold_used": round(self.optimal_threshold, 4),
            "model_version": self.model_version,
        }

    def reload(
        self,
        tracking_uri: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        """Dynamic reload mechanism for Production model without process restart."""
        logger.info("Executing Production model reload...")
        self.load_production_model(tracking_uri=tracking_uri, model_name=model_name)


# Global singleton prediction service instance
prediction_service = PredictionService()
