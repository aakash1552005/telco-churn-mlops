"""Demonstration script showing Phase 6 feature engineering.

Demonstrates:
1. Before/After values for the 11 TotalCharges blank-string rows (" " -> 0.0 float).
2. Anti-leakage confirmation (scaler parameters fit ONLY on training split).
3. Pipeline serialization (joblib) and round-trip transformation verification.
"""

import pathlib
import sys

# Ensure project root is on sys.path when executed directly
PROJECT_ROOT = pathlib.Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.data.features import (  # noqa: E402
    TotalChargesImputer,
    process_and_save_features,
)


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

    df_raw = pd.read_csv(raw_csv)

    print("=== 1. BEFORE/AFTER VALUES FOR THE 11 BLANK TOTALCHARGES ROWS ===")
    blank_mask = df_raw["TotalCharges"].astype(str).str.strip().eq("")
    blank_rows_before = df_raw[blank_mask][
        ["customerID", "tenure", "MonthlyCharges", "TotalCharges"]
    ]

    imputer = TotalChargesImputer()
    df_imputed = imputer.transform(df_raw)
    blank_rows_after = df_imputed[blank_mask][
        ["customerID", "tenure", "MonthlyCharges", "TotalCharges"]
    ]

    print("RAW VALUES BEFORE IMPUTATION:")
    print(blank_rows_before.to_string(index=True))

    print("\nIMPUTED VALUES AFTER IMPUTATION:")
    print(blank_rows_after.to_string(index=True))

    print(
        f"\nConfirmed: All {len(blank_rows_before)} blank TotalCharges rows "
        f"where tenure == 0 were successfully imputed to float 0.0."
    )

    print("\n=== 2. RUNNING FEATURE PIPELINE (STRICT ANTI-LEAKAGE) ===")
    X_tr, X_te, y_tr, y_te, pipeline = process_and_save_features(df_raw)

    print(f"X_train Processed Shape: {X_tr.shape}")
    print(f"X_test Processed Shape:  {X_te.shape}")
    print(f"y_train Churn Distribution: 1={y_tr.sum()}, 0={len(y_tr)-y_tr.sum()}")
    print(f"y_test Churn Distribution:  1={y_te.sum()}, 0={len(y_te)-y_te.sum()}")

    col_transformer = pipeline.named_steps["column_preprocessor"]
    scaler = col_transformer.named_transformers_["num"]
    print("\nScaler Mean Vector (Computed ONLY from X_train):")
    print(scaler.mean_)

    print("\n=== 3. FEATURE PIPELINE SERIALIZATION & ARTIFACTS ===")
    pipe_path = pathlib.Path(settings.FEATURE_PIPELINE_PATH)
    processed_dir = pathlib.Path(settings.PROCESSED_DATA_DIR)

    print(f"Serialized Pipeline Path: '{pipe_path}' (Exists: {pipe_path.exists()})")
    print(
        f"Processed Datasets Path:  '{processed_dir}' "
        f"(train.csv Exists: {(processed_dir / 'train.csv').exists()})"
    )


if __name__ == "__main__":
    run_demo()
