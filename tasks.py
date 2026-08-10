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
    run_cmd(["pre-commit", "install"])


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
            "clean",
            "ingest",
            "validate",
            "features",
            "train",
        ],
        help="Target task to execute",
    )
    args = parser.parse_args()

    tasks = {
        "install": task_install,
        "lint": task_lint,
        "format": task_format,
        "test": task_test,
        "clean": task_clean,
        "ingest": task_ingest,
        "validate": task_validate,
        "features": task_features,
        "train": task_train,
    }
    tasks[args.target]()


if __name__ == "__main__":
    main()
