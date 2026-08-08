"""Demonstration script showing Phase 5 data validation.

Runs validation against real ingested raw dataset and four corrupted fixtures:
- Real Dataset: Passes 100%
- Fixture A: Missing required column ('Churn') -> Fails
- Fixture B: Invalid domain value (tenure = -5) -> Fails
- Fixture C: Duplicate customerID -> Fails
- Fixture D: Extra/unknown column present ('ExtraUnknownCol') -> Fails
"""

import pathlib
import sys

# Ensure project root is on sys.path when executed directly
PROJECT_ROOT = pathlib.Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.data.ingestion import calculate_sha256  # noqa: E402
from src.data.validation import DataValidationError, validate_data  # noqa: E402


def run_demo() -> None:
    settings = get_settings()
    raw_csv = pathlib.Path(settings.RAW_DATA_PATH)

    if not raw_csv.exists():
        err_msg = (
            f"Raw dataset '{raw_csv}' not found. "
            f"Run 'py -3.12 tasks.py ingest' first."
        )
        print(err_msg)
        sys.exit(1)

    dataset_hash = calculate_sha256(raw_csv)
    real_df = pd.read_csv(raw_csv)

    print("=== 1. VALIDATING REAL INGESTED DATASET ===")
    report = validate_data(real_df, dataset_sha256=dataset_hash)
    summary = report["summary"]
    print(f"Result: {summary['validation_status']}")
    print(
        f"Rules Passed: {summary['rules_passed']} | "
        f"Rules Failed: {summary['rules_failed']}"
    )
    print(f"Dataset SHA-256: {summary['dataset_sha256']}")
    print(f"Schema Version: {summary['schema_version']}")

    print("\n=== 2. FIXTURE A: MISSING REQUIRED COLUMN ('Churn') ===")
    df_a = real_df.drop(columns=["Churn"])
    try:
        validate_data(df_a, dataset_sha256=dataset_hash)
    except DataValidationError as e:
        print(f"Caught expected DataValidationError: {e}")

    print("\n=== 3. FIXTURE B: INVALID DOMAIN VALUE (tenure = -5) ===")
    df_b = real_df.copy()
    df_b.loc[0, "tenure"] = -5
    try:
        validate_data(df_b, dataset_sha256=dataset_hash)
    except DataValidationError as e:
        print(f"Caught expected DataValidationError: {e}")

    print("\n=== 4. FIXTURE C: DUPLICATE customerID ===")
    df_c = real_df.copy()
    df_c.loc[1, "customerID"] = df_c.loc[0, "customerID"]
    # Change tenure to avoid triggering duplicate rows rule first
    df_c.loc[1, "tenure"] = 999
    try:
        validate_data(df_c, dataset_sha256=dataset_hash)
    except DataValidationError as e:
        print(f"Caught expected DataValidationError: {e}")

    print("\n=== 5. FIXTURE D: EXTRA / UNKNOWN COLUMN PRESENT ===")
    df_d = real_df.copy()
    df_d["ExtraUnknownCol"] = "unexpected_upstream_column"
    try:
        validate_data(df_d, dataset_sha256=dataset_hash)
    except DataValidationError as e:
        print(f"Caught expected DataValidationError: {e}")


if __name__ == "__main__":
    run_demo()
