"""Data Ingestion Module for Telco Customer Churn Dataset.

Provides reliable, reproducible, and idempotent loading of the raw Telco
Customer Churn dataset into `data/raw/telco_churn.csv` tracked by DVC.
"""

import hashlib
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional

import pandas as pd

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)


def calculate_sha256(file_path: Path) -> str:
    """Calculate SHA-256 checksum of a file.

    Args:
        file_path: Path to the target file.

    Returns:
        Hexadecimal SHA-256 hash string.
    """
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def track_with_dvc(file_path: Path) -> None:
    """Invoke real `dvc add` command to generate and manage .dvc metadata.

    Args:
        file_path: Path to the dataset file to track with DVC.
    """
    dvc_exe = shutil.which("dvc") or "dvc"
    logger.info(
        "Executing real DVC CLI tracking", extra={"command": f"dvc add {file_path}"}
    )
    result = subprocess.run(
        [dvc_exe, "add", str(file_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logger.warning(
            "DVC add command returned non-zero exit code",
            extra={"stderr": result.stderr.strip()},
        )
    else:
        logger.info("DVC tracking updated successfully via real DVC CLI")


def ingest_raw_data(
    source_type: Optional[str] = None,
    source_location: Optional[str] = None,
    target_path: Optional[Path] = None,
) -> Path:
    """Ingest raw Telco Churn dataset from URL or local path.

    Idempotent operation: re-running overwrites target file cleanly without
    data corruption, logs dataset reproducibility metadata, and updates DVC.

    Args:
        source_type: 'url' or 'local' (defaults to Settings.RAW_DATA_SOURCE_TYPE).
        source_location: URL or local path (defaults to Settings.RAW_DATA_LOCATION).
        target_path: Path destination (defaults to Settings.RAW_DATA_PATH).

    Returns:
        Path to the saved raw CSV file.
    """
    settings = get_settings()

    src_type = (source_type or settings.RAW_DATA_SOURCE_TYPE).lower()
    src_loc = source_location or settings.RAW_DATA_LOCATION
    dst_path = target_path or Path(settings.RAW_DATA_PATH)

    logger.info(
        "Data ingestion process started",
        extra={
            "source_type": src_type,
            "source_location": src_loc,
            "target_path": str(dst_path),
        },
    )

    dst_path.parent.mkdir(parents=True, exist_ok=True)

    if src_type == "url":
        req = urllib.request.Request(src_loc, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as response:
            content = response.read()
            if not content:
                raise ValueError(f"Downloaded content from URL '{src_loc}' is empty.")
            with open(dst_path, "wb") as f:
                f.write(content)
    elif src_type == "local":
        src_file = Path(src_loc)
        if not src_file.exists():
            raise FileNotFoundError(f"Local source file not found: {src_file}")
        shutil.copyfile(src_file, dst_path)
    else:
        raise ValueError(
            f"Unsupported RAW_DATA_SOURCE_TYPE: '{src_type}'. Must be 'url' or 'local'."
        )

    # Verification & Reproducibility Analysis
    sha256_checksum = calculate_sha256(dst_path)

    df = pd.read_csv(dst_path)
    row_count = len(df)
    col_count = len(df.columns)
    columns_list = list(df.columns)

    # Detailed Dataset Verification Logging
    log_msg = (
        f"Raw dataset ingested and verified. Source: {src_loc} | "
        f"SHA-256: {sha256_checksum} | Rows: {row_count} | Cols: {col_count} | "
        f"Columns: {columns_list}"
    )
    logger.info(
        log_msg,
        extra={
            "source_url": src_loc,
            "target_path": str(dst_path),
            "sha256_checksum": sha256_checksum,
            "row_count": row_count,
            "column_count": col_count,
            "columns": columns_list,
        },
    )

    # Invoke real `dvc add` CLI tool
    track_with_dvc(dst_path)

    logger.info("Data ingestion completed successfully")
    return dst_path


if __name__ == "__main__":
    ingest_raw_data()
