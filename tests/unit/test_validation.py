"""Unit tests for data validation module."""

import json
from pathlib import Path

import pandas as pd
import pytest

from src.data.validation import DataValidationError, validate_data


@pytest.fixture
def valid_df() -> pd.DataFrame:
    """Fixture returning a valid single-row Telco Churn DataFrame."""
    return pd.DataFrame(
        {
            "customerID": ["7590-VHVEG"],
            "gender": ["Female"],
            "SeniorCitizen": [0],
            "Partner": ["Yes"],
            "Dependents": ["No"],
            "tenure": [1],
            "PhoneService": ["No"],
            "MultipleLines": ["No phone service"],
            "InternetService": ["DSL"],
            "OnlineSecurity": ["No"],
            "OnlineBackup": ["Yes"],
            "DeviceProtection": ["No"],
            "TechSupport": ["No"],
            "StreamingTV": ["No"],
            "StreamingMovies": ["No"],
            "Contract": ["Month-to-month"],
            "PaperlessBilling": ["Yes"],
            "PaymentMethod": ["Electronic check"],
            "MonthlyCharges": [29.85],
            "TotalCharges": ["29.85"],
            "Churn": ["No"],
        }
    )


def test_validate_data_valid_passes(valid_df: pd.DataFrame, tmp_path: Path) -> None:
    """Test valid dataset passes validation and outputs JSON report."""
    report_file = tmp_path / "validation_report.json"
    report = validate_data(
        valid_df,
        dataset_sha256="test_hash_123",
        report_path=report_file,
    )

    assert report["summary"]["validation_status"] == "PASSED"
    assert report["summary"]["rules_failed"] == 0
    assert report["summary"]["dataset_sha256"] == "test_hash_123"
    assert report_file.exists()


def test_validate_data_missing_column_fails(
    valid_df: pd.DataFrame, tmp_path: Path
) -> None:
    """Test missing required column raises DataValidationError."""
    corrupted_df = valid_df.drop(columns=["Churn"])
    report_file = tmp_path / "report_missing_col.json"

    with pytest.raises(DataValidationError) as exc_info:
        validate_data(
            corrupted_df,
            dataset_sha256="hash_missing",
            report_path=report_file,
        )

    err = exc_info.value
    assert err.rule_name == "required_column_present"
    assert err.affected_column == "Churn"


def test_validate_data_extra_unknown_column_fails(
    valid_df: pd.DataFrame, tmp_path: Path
) -> None:
    """Test extra/unknown column is rejected per schema policy."""
    corrupted_df = valid_df.copy()
    corrupted_df["ExtraUnknownCol"] = "unexpected_data"
    report_file = tmp_path / "report_extra_col.json"

    with pytest.raises(DataValidationError) as exc_info:
        validate_data(
            corrupted_df,
            dataset_sha256="hash_extra",
            report_path=report_file,
        )

    err = exc_info.value
    assert err.rule_name == "no_unknown_columns"
    assert "ExtraUnknownCol" in err.affected_column


def test_validate_data_duplicate_customer_id_fails(
    valid_df: pd.DataFrame, tmp_path: Path
) -> None:
    """Test duplicate customerID raises DataValidationError."""
    corrupted_df = pd.concat([valid_df, valid_df], ignore_index=True)
    # Give different tenure to avoid triggering no_duplicate_rows rule first
    corrupted_df.loc[1, "tenure"] = 5
    report_file = tmp_path / "report_dup_id.json"

    with pytest.raises(DataValidationError) as exc_info:
        validate_data(
            corrupted_df,
            dataset_sha256="hash_dup_id",
            report_path=report_file,
        )

    err = exc_info.value
    assert err.rule_name == "unique_column_values"
    assert err.affected_column == "customerID"


def test_validate_data_domain_min_value_fails(
    valid_df: pd.DataFrame, tmp_path: Path
) -> None:
    """Test negative tenure violates min_value domain rule."""
    corrupted_df = valid_df.copy()
    corrupted_df.loc[0, "tenure"] = -5
    report_file = tmp_path / "report_negative_tenure.json"

    with pytest.raises(DataValidationError) as exc_info:
        validate_data(
            corrupted_df,
            dataset_sha256="hash_domain_min",
            report_path=report_file,
        )

    err = exc_info.value
    assert err.rule_name == "domain_min_value"
    assert err.affected_column == "tenure"


def test_validate_data_domain_allowed_values_fails(
    valid_df: pd.DataFrame, tmp_path: Path
) -> None:
    """Test invalid Churn value violates allowed_values domain rule."""
    corrupted_df = valid_df.copy()
    corrupted_df.loc[0, "Churn"] = "Maybe"
    report_file = tmp_path / "report_invalid_churn.json"

    with pytest.raises(DataValidationError) as exc_info:
        validate_data(
            corrupted_df,
            dataset_sha256="hash_allowed_val",
            report_path=report_file,
        )

    err = exc_info.value
    assert err.rule_name == "domain_allowed_values"
    assert err.affected_column == "Churn"


def test_validation_report_json_structure(
    valid_df: pd.DataFrame, tmp_path: Path
) -> None:
    """Test output JSON report matches required summary structure."""
    report_file = tmp_path / "report_structure.json"
    validate_data(valid_df, dataset_sha256="sha_999", report_path=report_file)

    with open(report_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "summary" in data
    assert "failed_rules" in data
    summary = data["summary"]
    assert summary["validation_status"] == "PASSED"
    assert "rules_passed" in summary
    assert "rules_failed" in summary
    assert "schema_version" in summary
    assert summary["dataset_sha256"] == "sha_999"
    assert "timestamp" in summary
