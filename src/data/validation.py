"""Data Validation Module for Telco Customer Churn Pipeline.

Provides lightweight, explicit, data-driven validation against a YAML schema
covering Schema, Completeness, Integrity, and Domain rules.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

import pandas as pd
import yaml

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class DataValidationError(Exception):
    """Custom exception raised when data validation rules fail."""

    def __init__(
        self,
        rule_name: str,
        affected_column: str,
        observed_value: Any,
        expected_constraint: str,
        message: Optional[str] = None,
    ):
        self.rule_name = rule_name
        self.affected_column = affected_column
        self.observed_value = observed_value
        self.expected_constraint = expected_constraint
        default_msg = (
            f"Validation rule '{rule_name}' failed on column "
            f"'{affected_column}'. Observed: '{observed_value}'. "
            f"Expected constraint: '{expected_constraint}'."
        )
        full_msg = message or default_msg
        super().__init__(full_msg)


def load_schema_config(schema_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load and parse the YAML schema configuration file."""
    settings = get_settings()
    path = schema_path or Path(settings.SCHEMA_FILE_PATH)
    if not path.exists():
        err_msg = f"Schema configuration file not found at: {path}"
        raise FileNotFoundError(err_msg)

    with open(path, "r", encoding="utf-8") as f:
        schema = yaml.safe_load(f)

    if not isinstance(schema, dict):
        err_msg = f"Invalid schema file '{path}'. Expected dictionary content."
        raise ValueError(err_msg)

    if "schema_version" not in schema:
        err_msg = (
            f"Schema file '{path}' is missing required " f"'schema_version' field."
        )
        raise ValueError(err_msg)

    return cast(Dict[str, Any], schema)


def validate_data(
    df: pd.DataFrame,
    dataset_sha256: str = "",
    schema_path: Optional[Path] = None,
    report_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Validate DataFrame against configured schema and save run report.

    Args:
        df: Input DataFrame to validate.
        dataset_sha256: SHA-256 checksum of raw dataset for traceability.
        schema_path: Path to schema.yaml.
        report_path: Path to output JSON report.

    Returns:
        Validation report dictionary.

    Raises:
        DataValidationError: If any validation rule fails.
    """
    settings = get_settings()
    target_report_path = report_path or Path(settings.VALIDATION_REPORT_PATH)
    schema = load_schema_config(schema_path)

    schema_version = schema.get("schema_version", "1.0.0")
    allow_extra_cols = schema.get("allow_extra_columns", False)
    schema_cols_dict = schema.get("columns", {})
    expected_cols = set(schema_cols_dict.keys())
    actual_cols = set(df.columns)

    logger.info(
        "Data validation process started",
        extra={
            "schema_version": schema_version,
            "row_count": len(df),
            "col_count": len(df.columns),
            "dataset_sha256": dataset_sha256,
        },
    )

    failed_rules: List[Dict[str, Any]] = []
    rules_passed = 0

    # -------------------------------------------------------------------------
    # 1. SCHEMA VALIDATION
    # -------------------------------------------------------------------------
    # Rule 1.1: Missing required columns
    missing_cols = expected_cols - actual_cols
    if missing_cols:
        for col in sorted(missing_cols):
            failed_rules.append(
                {
                    "rule_name": "required_column_present",
                    "affected_column": col,
                    "failure_count": 1,
                    "observed_value": "Column missing from dataset",
                    "expected_constraint": "Column must be present in schema",
                }
            )
    else:
        rules_passed += 1

    # Rule 1.2: Unknown / extra columns
    extra_cols = actual_cols - expected_cols
    if not allow_extra_cols and extra_cols:
        extra_list = sorted(list(extra_cols))
        failed_rules.append(
            {
                "rule_name": "no_unknown_columns",
                "affected_column": ", ".join(extra_list),
                "failure_count": len(extra_list),
                "observed_value": f"Extra columns present: {extra_list}",
                "expected_constraint": (
                    "Reject unknown columns (allow_extra_columns=false)"
                ),
            }
        )
    elif not allow_extra_cols:
        rules_passed += 1

    # Rule 1.3: Column Data Types
    for col, col_rules in schema_cols_dict.items():
        if col not in df.columns:
            continue
        expected_type = col_rules.get("type")
        actual_dtype = str(df[col].dtype)

        type_failed = False
        if expected_type == "int":
            if not pd.api.types.is_integer_dtype(df[col]):
                type_failed = True
        elif expected_type == "float":
            is_flt = pd.api.types.is_float_dtype(df[col])
            is_int = pd.api.types.is_integer_dtype(df[col])
            if not is_flt and not is_int:
                type_failed = True
        elif expected_type == "string":
            is_obj = pd.api.types.is_object_dtype(df[col])
            is_str = pd.api.types.is_string_dtype(df[col])
            if not is_obj and not is_str:
                type_failed = True

        if type_failed:
            failed_rules.append(
                {
                    "rule_name": "correct_data_type",
                    "affected_column": col,
                    "failure_count": 1,
                    "observed_value": f"dtype={actual_dtype}",
                    "expected_constraint": (f"Compatible with type '{expected_type}'"),
                }
            )
        else:
            rules_passed += 1

    # -------------------------------------------------------------------------
    # 2. COMPLETENESS VALIDATION
    # -------------------------------------------------------------------------
    for col, col_rules in schema_cols_dict.items():
        if col not in df.columns:
            continue
        max_null_rate = col_rules.get("max_null_rate", 0.0)
        null_count = int(df[col].isnull().sum())
        null_rate = float(null_count / len(df)) if len(df) > 0 else 0.0

        if null_rate > max_null_rate:
            failed_rules.append(
                {
                    "rule_name": "completeness_max_null_rate",
                    "affected_column": col,
                    "failure_count": null_count,
                    "observed_value": (
                        f"null_rate={null_rate:.4f} ({null_count} nulls)"
                    ),
                    "expected_constraint": f"max_null_rate <= {max_null_rate}",
                }
            )
        else:
            rules_passed += 1

    # -------------------------------------------------------------------------
    # 3. INTEGRITY VALIDATION
    # -------------------------------------------------------------------------
    # Rule 3.1: Duplicate rows
    if schema.get("integrity_rules", {}).get("no_duplicate_rows", True):
        dup_rows_count = int(df.duplicated().sum())
        if dup_rows_count > 0:
            failed_rules.append(
                {
                    "rule_name": "no_duplicate_rows",
                    "affected_column": "ALL_COLUMNS",
                    "failure_count": dup_rows_count,
                    "observed_value": f"{dup_rows_count} duplicate rows found",
                    "expected_constraint": "0 duplicate rows",
                }
            )
        else:
            rules_passed += 1

    # Rule 3.2: Unique columns (e.g. customerID)
    for col, col_rules in schema_cols_dict.items():
        if col not in df.columns:
            continue
        if col_rules.get("unique", False):
            dup_id_count = int(df[col].duplicated().sum())
            if dup_id_count > 0:
                failed_rules.append(
                    {
                        "rule_name": "unique_column_values",
                        "affected_column": col,
                        "failure_count": dup_id_count,
                        "observed_value": (
                            f"{dup_id_count} duplicate values in '{col}'"
                        ),
                        "expected_constraint": (
                            f"All values in '{col}' must be unique"
                        ),
                    }
                )
            else:
                rules_passed += 1

    # -------------------------------------------------------------------------
    # 4. DOMAIN RULES VALIDATION
    # -------------------------------------------------------------------------
    for col, col_rules in schema_cols_dict.items():
        if col not in df.columns:
            continue

        # Min value check (e.g. tenure >= 0, MonthlyCharges >= 0)
        if "min_value" in col_rules:
            min_val = col_rules["min_value"]
            numeric_series = pd.to_numeric(df[col], errors="coerce")
            invalid_min_count = int((numeric_series < min_val).sum())
            if invalid_min_count > 0:
                failed_rules.append(
                    {
                        "rule_name": "domain_min_value",
                        "affected_column": col,
                        "failure_count": invalid_min_count,
                        "observed_value": f"{invalid_min_count} values < {min_val}",
                        "expected_constraint": f"Value >= {min_val}",
                    }
                )
            else:
                rules_passed += 1

        # Allowed values check (e.g. Churn in {Yes, No})
        if "allowed_values" in col_rules:
            allowed = set(col_rules["allowed_values"])
            invalid_mask = ~df[col].isin(allowed) & df[col].notnull()
            invalid_allowed_count = int(invalid_mask.sum())
            if invalid_allowed_count > 0:
                samples = list(df[col][invalid_mask].unique()[:3])
                failed_rules.append(
                    {
                        "rule_name": "domain_allowed_values",
                        "affected_column": col,
                        "failure_count": invalid_allowed_count,
                        "observed_value": (
                            f"{invalid_allowed_count} invalid values "
                            f"(e.g. {samples})"
                        ),
                        "expected_constraint": (
                            f"Value must be in {sorted(list(allowed))}"
                        ),
                    }
                )
            else:
                rules_passed += 1

    # -------------------------------------------------------------------------
    # SUMMARY & REPORT GENERATION
    # -------------------------------------------------------------------------
    status = "FAILED" if failed_rules else "PASSED"
    now_iso = datetime.now(timezone.utc).isoformat()

    report: Dict[str, Any] = {
        "summary": {
            "validation_status": status,
            "rules_passed": rules_passed,
            "rules_failed": len(failed_rules),
            "schema_version": schema_version,
            "dataset_sha256": dataset_sha256,
            "timestamp": now_iso,
        },
        "failed_rules": failed_rules,
    }

    # Save JSON Report
    target_report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    # Logging Stage Execution
    if failed_rules:
        for failure in failed_rules:
            logger.error(
                "Data validation rule failed",
                extra={
                    "rule_name": failure["rule_name"],
                    "affected_column": failure["affected_column"],
                    "failure_count": failure["failure_count"],
                    "observed_value": failure["observed_value"],
                    "expected_constraint": failure["expected_constraint"],
                },
            )

    logger.info(
        "Data validation summary completed",
        extra={
            "validation_status": status,
            "rules_passed": rules_passed,
            "rules_failed": len(failed_rules),
            "schema_version": schema_version,
            "report_path": str(target_report_path),
        },
    )

    if failed_rules:
        first_fail = failed_rules[0]
        raise DataValidationError(
            rule_name=first_fail["rule_name"],
            affected_column=first_fail["affected_column"],
            observed_value=first_fail["observed_value"],
            expected_constraint=first_fail["expected_constraint"],
        )

    logger.info("Data validation passed successfully")
    return report


if __name__ == "__main__":
    raw_csv = Path(get_settings().RAW_DATA_PATH)
    if raw_csv.exists():
        df_raw = pd.read_csv(raw_csv)
        validate_data(df_raw)
