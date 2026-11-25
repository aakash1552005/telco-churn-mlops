"""Bootstrap script to generate baseline production artifacts for container serving in CI.

Runs the minimal pipeline (ingest -> validate -> features -> train -> evaluate -> promote)
so that models/, mlruns/, and mlflow.db contain an active Production-stage model.
"""

import sys
from pathlib import Path

from src.core.config import get_settings
from src.core.logging import get_logger
from src.data.features import process_and_save_features
from src.data.ingestion import ingest_raw_data
from src.data.validation import validate_data
from src.training.evaluate import generate_evaluation_report
from src.training.promotion import promote_model
from src.training.train import train_candidate_models

logger = get_logger(__name__)


def bootstrap() -> None:
    """Execute minimal end-to-end artifact generation."""
    settings = get_settings()
    logger.info("Starting CI artifact bootstrap...")

    raw_path = Path(settings.RAW_DATA_PATH)
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Ingest
    if not raw_path.exists():
        logger.info(f"Ingesting raw dataset from '{settings.RAW_DATA_LOCATION}'...")
        ingest_raw_data(
            source_type=settings.RAW_DATA_SOURCE_TYPE,
            source_location=settings.RAW_DATA_LOCATION,
            target_path=raw_path,
        )

    import pandas as pd

    df_raw = pd.read_csv(raw_path)

    # 2. Validate
    schema_yaml = Path(settings.SCHEMA_FILE_PATH)
    val_report_path = Path(settings.VALIDATION_REPORT_PATH)
    val_report_path.parent.mkdir(parents=True, exist_ok=True)
    validate_data(df=df_raw, schema_path=schema_yaml, report_path=val_report_path)

    # 3. Features
    proc_dir = Path(settings.PROCESSED_DATA_DIR)
    pipe_path = Path(settings.FEATURE_PIPELINE_PATH)
    schema_path = Path(settings.FEATURE_SCHEMA_PATH)
    proc_dir.mkdir(parents=True, exist_ok=True)
    pipe_path.parent.mkdir(parents=True, exist_ok=True)

    process_and_save_features(
        raw_df=df_raw,
        processed_dir=proc_dir,
        pipeline_path=pipe_path,
        schema_output_path=schema_path,
        test_size=settings.TEST_SIZE,
        random_state=settings.RANDOM_STATE,
    )

    # 4. Train (n_iter=2 for rapid CI bootstrap)
    model_path = Path(settings.MODEL_OUTPUT_PATH)
    metrics_path = Path(settings.TRAINING_METRICS_PATH)
    cv_path = Path(settings.CV_RESULTS_PATH)
    meta_path = Path(settings.TRAINING_METADATA_PATH)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)

    train_candidate_models(
        processed_dir=proc_dir,
        schema_path=schema_path,
        pipeline_path=pipe_path,
        model_output_path=model_path,
        metrics_output_path=metrics_path,
        cv_results_output_path=cv_path,
        metadata_output_path=meta_path,
        random_state=settings.RANDOM_STATE,
        n_iter=2,
    )

    # 5. Evaluate
    reports_dir = Path("reports")
    plots_dir = reports_dir / "plots"
    thresh_path = Path(settings.DECISION_THRESHOLD_PATH)
    generate_evaluation_report(
        processed_dir=proc_dir,
        model_path=model_path,
        schema_path=schema_path,
        metadata_path=meta_path,
        output_dir=reports_dir,
        plots_dir=plots_dir,
        threshold_path=thresh_path,
    )

    # 6. Promote to Production
    promote_results = promote_model()
    logger.info(
        f"Bootstrap complete: Model '{promote_results['model_name']}' version "
        f"{promote_results['model_version']} promoted to stage '{promote_results['stage']}'."
    )


if __name__ == "__main__":
    try:
        bootstrap()
    except Exception as e:
        logger.error(f"Bootstrap failed: {e}", exc_info=True)
        sys.exit(1)
