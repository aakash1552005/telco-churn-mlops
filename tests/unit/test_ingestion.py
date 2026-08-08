"""Unit tests for data ingestion module."""

from pathlib import Path

import pandas as pd
import pytest

from src.data.ingestion import calculate_md5, calculate_sha256, ingest_raw_data


@pytest.fixture
def sample_csv_path(tmp_path: Path) -> Path:
    """Fixture creating a sample Telco Churn CSV for unit testing."""
    sample_data = {
        "customerID": ["7590-VHVEG", "5575-GNVDE"],
        "gender": ["Female", "Male"],
        "SeniorCitizen": [0, 0],
        "Partner": ["Yes", "No"],
        "Dependents": ["No", "No"],
        "tenure": [1, 34],
        "PhoneService": ["No", "Yes"],
        "MultipleLines": ["No phone service", "No"],
        "InternetService": ["DSL", "DSL"],
        "OnlineSecurity": ["No", "Yes"],
        "OnlineBackup": ["Yes", "No"],
        "DeviceProtection": ["No", "Yes"],
        "TechSupport": ["No", "No"],
        "StreamingTV": ["No", "No"],
        "StreamingMovies": ["No", "No"],
        "Contract": ["Month-to-month", "One year"],
        "PaperlessBilling": ["Yes", "No"],
        "PaymentMethod": ["Electronic check", "Mailed check"],
        "MonthlyCharges": [29.85, 56.95],
        "TotalCharges": ["29.85", "1889.5"],
        "Churn": ["No", "No"],
    }
    df = pd.DataFrame(sample_data)
    csv_file = tmp_path / "sample_input.csv"
    df.to_csv(csv_file, index=False)
    return csv_file


def test_ingest_raw_data_local_source(sample_csv_path: Path, tmp_path: Path) -> None:
    """Test ingestion from local file source."""
    target_csv = tmp_path / "data" / "raw" / "telco_churn.csv"
    result_path = ingest_raw_data(
        source_type="local",
        source_location=str(sample_csv_path),
        target_path=target_csv,
    )

    assert result_path.exists()
    assert result_path == target_csv


def test_ingest_raw_data_schema_and_dtypes(
    sample_csv_path: Path, tmp_path: Path
) -> None:
    """Test ingested dataset schema, row count, column names, and dtypes."""
    target_csv = tmp_path / "data" / "raw" / "telco_churn.csv"
    ingest_raw_data(
        source_type="local",
        source_location=str(sample_csv_path),
        target_path=target_csv,
    )

    df = pd.read_csv(target_csv)
    assert len(df) == 2
    assert len(df.columns) == 21
    assert "customerID" in df.columns
    assert "Churn" in df.columns
    assert df["tenure"].dtype == "int64"
    assert df["MonthlyCharges"].dtype == "float64"


def test_ingest_raw_data_dvc_pointer_file(
    sample_csv_path: Path, tmp_path: Path
) -> None:
    """Test creation of DVC pointer file (.dvc) matching dataset MD5."""
    target_csv = tmp_path / "data" / "raw" / "telco_churn.csv"
    ingest_raw_data(
        source_type="local",
        source_location=str(sample_csv_path),
        target_path=target_csv,
    )

    dvc_file = target_csv.with_suffix(".csv.dvc")
    assert dvc_file.exists()

    dvc_content = dvc_file.read_text(encoding="utf-8")
    expected_md5 = calculate_md5(target_csv)
    assert expected_md5 in dvc_content


def test_ingest_raw_data_idempotency(sample_csv_path: Path, tmp_path: Path) -> None:
    """Test re-running ingestion produces identical SHA-256 hash."""
    target_csv = tmp_path / "data" / "raw" / "telco_churn.csv"

    # First run
    ingest_raw_data(
        source_type="local",
        source_location=str(sample_csv_path),
        target_path=target_csv,
    )
    hash_1 = calculate_sha256(target_csv)

    # Second run (re-ingestion)
    ingest_raw_data(
        source_type="local",
        source_location=str(sample_csv_path),
        target_path=target_csv,
    )
    hash_2 = calculate_sha256(target_csv)

    assert hash_1 == hash_2


def test_ingest_raw_data_invalid_source_type(tmp_path: Path) -> None:
    """Test invalid source type raises ValueError."""
    target_csv = tmp_path / "data" / "raw" / "telco_churn.csv"
    with pytest.raises(ValueError, match="Unsupported RAW_DATA_SOURCE_TYPE"):
        ingest_raw_data(
            source_type="ftp",
            source_location="ftp://example.com/data.csv",
            target_path=target_csv,
        )
