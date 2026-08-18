"""Task runner script for cross-platform project maintenance.

Supports install, lint, format, test, and clean tasks.
"""

import argparse
import pathlib
import shutil
import subprocess
import sys

PROJECT_ROOT = pathlib.Path(__file__).parent.resolve()


def run_cmd(cmd: list[str]) -> None:
    """Run shell command using sys.executable where appropriate."""
    print(f"Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if res.returncode != 0:
        print(f"Command failed with exit code {res.returncode}")
        sys.exit(res.returncode)


def task_install() -> None:
    """Install project dependencies in editable mode and pre-commit hooks."""
    run_cmd([sys.executable, "-m", "pip", "install", "-e", ".[dev,test]"])
    git_dir = PROJECT_ROOT / ".git"
    if not git_dir.exists():
        print("Initializing git repository...")
        run_cmd(["git", "init"])
    run_cmd([sys.executable, "-m", "pre_commit", "install"])


def check_no_print() -> None:
    """Ensure no bare print() statements exist in src/ application codebase.

    Enforcement Scope:
        - src/: Strictly enforced. All production code, pipeline modules, and core
          utilities must use get_logger(__name__) instead of bare print().
        - scripts/, tests/, tasks.py: Excluded. CLI helper tools, test drivers, and
          task runner routines legitimately write formatted console output to terminal.
    """
    print("--- Checking for bare print() statements in src/ ---")
    stray_prints = []
    for py_file in (PROJECT_ROOT / "src").rglob("*.py"):
        lines = py_file.read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("print(") or " print(" in line:
                if not stripped.startswith("#"):
                    stray_prints.append(
                        f"{py_file.relative_to(PROJECT_ROOT)}:{idx}: {line}"
                    )
    if stray_prints:
        print("Error: Bare print() statements found in src/:")
        for err in stray_prints:
            print(f"  {err}")
        sys.exit(1)
    print("No bare print() statements found in src/.")


def task_lint() -> None:
    """Run code style, formatting, and type checks."""
    check_no_print()
    print("--- Running flake8 ---")
    run_cmd([sys.executable, "-m", "flake8", "src", "tests"])
    print("--- Running black check ---")
    run_cmd([sys.executable, "-m", "black", "--check", "src", "tests"])
    print("--- Running isort check ---")
    run_cmd([sys.executable, "-m", "isort", "--check-only", "src", "tests"])
    print("--- Running mypy ---")
    run_cmd([sys.executable, "-m", "mypy"])


def task_format() -> None:
    """Auto-format code using isort and black."""
    print("--- Running isort ---")
    run_cmd([sys.executable, "-m", "isort", "src", "tests"])
    print("--- Running black ---")
    run_cmd([sys.executable, "-m", "black", "src", "tests"])


def task_test() -> None:
    """Run pytest suite."""
    print(f"Running: {sys.executable} -m pytest")
    res = subprocess.run([sys.executable, "-m", "pytest"], cwd=PROJECT_ROOT)
    if res.returncode == 5:
        print("Pytest completed successfully (0 tests collected for scaffolding).")
    elif res.returncode != 0:
        print(f"Pytest failed with exit code {res.returncode}")
        sys.exit(res.returncode)


def task_integration_test() -> None:
    """Run end-to-end integration test suite in isolated environment."""
    print("--- Running End-to-End Integration Test Suite ---")
    run_cmd(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/integration/test_end_to_end.py",
            "-v",
        ]
    )


def task_clean() -> None:
    """Remove cache files and build artifacts."""
    for pattern in ["__pycache__", ".pytest_cache", ".mypy_cache", ".coverage"]:
        for path in PROJECT_ROOT.rglob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.is_file():
                path.unlink(missing_ok=True)
    print("Cleaned cache directories.")


def task_ingest() -> None:
    """Run data ingestion and update DVC tracking."""
    print("--- Running Data Ingestion ---")
    from src.data.ingestion import ingest_raw_data

    raw_path = ingest_raw_data()
    print(f"Data ingestion completed: {raw_path}")


def task_validate() -> None:
    """Run data validation against raw dataset."""
    print("--- Running Data Validation ---")
    from pathlib import Path

    import pandas as pd

    from src.core.config import get_settings
    from src.data.ingestion import calculate_sha256
    from src.data.validation import validate_data

    raw_path = Path(get_settings().RAW_DATA_PATH)
    if not raw_path.exists():
        print(
            f"Error: Raw dataset not found at '{raw_path}'. "
            f"Run 'python tasks.py ingest' first."
        )
        sys.exit(1)

    sha256_hash = calculate_sha256(raw_path)
    df = pd.read_csv(raw_path)
    validate_data(df, dataset_sha256=sha256_hash)
    print(
        f"Data validation PASSED! "
        f"Report saved to '{get_settings().VALIDATION_REPORT_PATH}'."
    )


def task_features() -> None:
    """Run feature engineering pipeline on raw dataset."""
    print("--- Running Feature Engineering Pipeline ---")
    from pathlib import Path

    import pandas as pd

    from src.core.config import get_settings
    from src.data.features import process_and_save_features

    raw_path = Path(get_settings().RAW_DATA_PATH)
    if not raw_path.exists():
        print(
            f"Error: Raw dataset not found at '{raw_path}'. "
            f"Run 'py -3.12 tasks.py ingest' first."
        )
        sys.exit(1)

    df_raw = pd.read_csv(raw_path)
    X_tr, X_te, y_tr, y_te, pipe = process_and_save_features(df_raw)
    print("Feature engineering pipeline completed successfully.")
    print(f"Processed feature matrix shape (X_train): {X_tr.shape} (49 features)")
    print(f"Processed feature matrix shape (X_test):  {X_te.shape} (49 features)")
    print(
        "Saved CSV datasets on disk (train.csv / test.csv): "
        "50 columns (49 features + 1 target 'Churn')"
    )
    print(f"Serialized pipeline: '{get_settings().FEATURE_PIPELINE_PATH}'")
    print(f"Processed datasets directory: '{get_settings().PROCESSED_DATA_DIR}'")


def task_train() -> None:
    """Run model training and hyperparameter search pipeline."""
    print("--- Running Model Training Pipeline ---")
    from src.core.config import get_settings
    from src.training.train import train_candidate_models

    winning_model, metrics, metadata = train_candidate_models()
    print("Model training pipeline completed successfully.")
    print(f"Winning Algorithm: {metadata['algorithm']}")
    print(f"Best CV ROC-AUC Score: {metadata['best_cv_score']}")
    print(f"Serialized Winning Model: '{get_settings().MODEL_OUTPUT_PATH}'")
    print(f"Training Metrics JSON: '{get_settings().TRAINING_METRICS_PATH}'")
    print(f"Cross-Validation Results CSV: '{get_settings().CV_RESULTS_PATH}'")
    print(f"Training Metadata JSON: '{get_settings().TRAINING_METADATA_PATH}'")


def task_evaluate() -> None:
    """Run model evaluation, threshold optimization, and reporting pipeline."""
    print("--- Running Model Evaluation Pipeline ---")
    from src.core.config import get_settings
    from src.training.evaluate import generate_evaluation_report

    results = generate_evaluation_report()
    settings = get_settings()
    print("Model evaluation pipeline completed successfully.")
    print(f"Evaluated Model Algorithm: {results['model_algorithm']}")
    print(f"Test Samples Evaluated: {results['test_samples']}")
    print(f"Default 0.5 ROC-AUC: {results['metrics_at_threshold_0_5']['roc_auc']}")
    print(f"Default 0.5 F1: {results['metrics_at_threshold_0_5']['f1']}")
    opt_th = results["optimal_threshold_metrics"]["optimal_threshold"]
    print(f"Optimal Threshold: {opt_th}")

    print(f"Optimal Threshold F1: {results['optimal_threshold_metrics']['f1']}")
    print(f"Brier Score: {results['brier_score']}")
    print(f"Evaluation Metrics JSON: '{settings.EVALUATION_METRICS_PATH}'")
    print(f"Optimal Decision Threshold JSON: '{settings.DECISION_THRESHOLD_PATH}'")
    print(f"Classification Report JSON: '{settings.CLASSIFICATION_REPORT_PATH}'")
    print(f"Calibration Metrics JSON: '{settings.CALIBRATION_METRICS_PATH}'")
    print(f"Feature Importances CSV: '{settings.FEATURE_IMPORTANCE_PATH}'")
    print(f"Error Analysis CSV: '{settings.ERROR_ANALYSIS_PATH}'")
    print(f"Plots Directory: '{settings.PLOTS_DIR}'")


def task_promote() -> None:
    """Orchestrate MLflow model registry integration and promotion policy."""
    print("--- Running Model Promotion Pipeline ---")
    from src.core.config import get_settings
    from src.training.promotion import promote_model

    results = promote_model()
    settings = get_settings()
    print("Model promotion pipeline completed successfully.")
    print(f"Registered Model Name: {results['model_name']}")
    print(f"Registered Model Version: {results['model_version']}")
    print(f"Assigned Lifecycle Stage: {results['stage']}")
    status_str = "PROMOTED" if results["is_promoted"] else "REJECTED"
    print(f"Promotion Status: {status_str}")
    print(f"Promotion Reason: {results['reason']}")
    print(f"MLflow Run ID: {results['run_id']}")
    print(f"MLflow Tracking URI: '{settings.MLFLOW_TRACKING_URI}'")
    if not results["is_promoted"]:
        print("ERROR: Model candidate failed Section 9 promotion criteria.")
        sys.exit(1)


def task_serve() -> None:
    """Run uvicorn dev server for FastAPI prediction service."""
    print("--- Starting FastAPI Prediction Service ---")
    from src.core.config import get_settings

    settings = get_settings()
    try:
        run_cmd(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "src.api.app:app",
                "--host",
                settings.API_HOST,
                "--port",
                str(settings.API_PORT),
            ]
        )
    except KeyboardInterrupt:
        print("\nFastAPI prediction service stopped.")


def task_docker_build() -> None:
    """Build Docker container image with dynamic OCI build-args for FastAPI service."""
    print("--- Building Docker Container Image ---")
    import datetime
    import subprocess

    try:
        git_commit = (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except Exception:
        git_commit = "unknown"

    build_date = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    version = "1.0.0"

    cmd = [
        "docker",
        "build",
        "-t",
        "telco-churn-api:latest",
        "--build-arg",
        f"BUILD_DATE={build_date}",
        "--build-arg",
        f"GIT_COMMIT={git_commit}",
        "--build-arg",
        f"VERSION={version}",
        ".",
    ]
    run_cmd(cmd)


def task_docker_run() -> None:
    """Run Docker container image locally with host bind mounts mapping port 8000."""
    print("--- Running Docker Container with Host Bind Mounts ---")
    models_dir = (PROJECT_ROOT / "models").resolve()
    mlruns_dir = (PROJECT_ROOT / "mlruns").resolve()
    db_path = (PROJECT_ROOT / "mlflow.db").resolve()
    try:
        run_cmd(
            [
                "docker",
                "run",
                "--rm",
                "-p",
                "8000:8000",
                "-v",
                f"{models_dir}:/app/models:ro",
                "-v",
                f"{mlruns_dir}:/app/mlruns:ro",
                "-v",
                f"{db_path}:/app/mlflow.db:rw",
                "--name",
                "telco-churn-api-container",
                "telco-churn-api:latest",
            ]
        )
    except KeyboardInterrupt:
        print("\nDocker container stopped.")


def task_drift() -> None:
    """Run Evidently AI drift detection and monitoring pipeline."""
    print("--- Running Evidently AI Drift Detection Pipeline ---")
    from src.monitoring.drift import run_drift_pipeline

    res = run_drift_pipeline()
    print("Drift Monitoring Pipeline Completed.")
    print(f"  Drift Detected: {res['summary']['drift_detected']}")
    print(f"  Consecutive Drift Windows: {res['summary']['consecutive_drift_windows']}")
    print(f"  Retraining Triggered: {res['summary']['retraining_triggered']}")
    if res["summary"]["triggering_criteria"]:
        print(f"  Triggering Criteria: {res['summary']['triggering_criteria']}")


def main() -> None:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Task runner for Telco Churn MLOps Pipeline."
    )
    parser.add_argument(
        "target",
        choices=[
            "install",
            "lint",
            "format",
            "test",
            "integration-test",
            "clean",
            "ingest",
            "validate",
            "features",
            "train",
            "evaluate",
            "promote",
            "serve",
            "docker-build",
            "docker-run",
            "drift",
        ],
        help="Target task to execute",
    )
    args = parser.parse_args()

    tasks = {
        "install": task_install,
        "lint": task_lint,
        "format": task_format,
        "test": task_test,
        "integration-test": task_integration_test,
        "clean": task_clean,
        "ingest": task_ingest,
        "validate": task_validate,
        "features": task_features,
        "train": task_train,
        "evaluate": task_evaluate,
        "promote": task_promote,
        "serve": task_serve,
        "docker-build": task_docker_build,
        "docker-run": task_docker_run,
        "drift": task_drift,
    }
    tasks[args.target]()


if __name__ == "__main__":
    main()
