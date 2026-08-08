"""Data Ingestion Module for Telco Customer Churn Dataset.

Provides reliable, reproducible, and idempotent loading of the raw Telco
Customer Churn dataset into `data/raw/telco_churn.csv` tracked by DVC.
"""

import hashlib
import shutil
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


def calculate_md5(file_path: Path) -> str:
    """Calculate MD5 checksum of a file for DVC tracking verification.

    Args:
        file_path: Path to the target file.

    Returns:
        Hexadecimal MD5 hash string.
    """
    md5_hash = hashlib.md5()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            md5_hash.update(byte_block)
    return md5_hash.hexdigest()


def create_dvc_pointer_file(file_path: Path) -> Path:
    """Create or update DVC pointer file (.dvc) for target dataset file.

    Args:
        file_path: Path to the dataset file.

    Returns:
        Path to the created .dvc pointer file.
    """
    md5_val = calculate_md5(file_path)
    file_size = file_path.stat().st_size
    dvc_file_path = file_path.with_suffix(file_path.suffix + ".dvc")

    dvc_content = (
        f"outs:\n"
        f"- md5: {md5_val}\n"
        f"  size: {file_size}\n"
        f"  hash: md5\n"
        f"  path: {file_path.name}\n"
    )
    with open(dvc_file_path, "w", encoding="utf-8") as f:
        f.write(dvc_content)

    return dvc_file_path


def ingest_raw_data(
    source_type: Optional[str] = None,
    source_location: Optional[str] = None,
    target_path: Optional[Path] = None,
) -> Path:
    """Ingest raw Telco Churn dataset from URL or local path.

    Idempotent operation: re-running overwrites target file cleanly without
    data corruption and computes reproducible SHA-256 and MD5 dataset checksums.

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
    md5_checksum = calculate_md5(dst_path)

    df = pd.read_csv(dst_path)
    row_count = len(df)
    col_count = len(df.columns)
    columns_list = list(df.columns)

    # Create/update DVC tracking pointer file
    dvc_file = create_dvc_pointer_file(dst_path)

    logger.info(
        "Raw dataset ingestion and verification successful",
        extra={
            "target_path": str(dst_path),
            "sha256_checksum": sha256_checksum,
            "dvc_md5_hash": md5_checksum,
            "dvc_pointer_file": str(dvc_file),
            "row_count": row_count,
            "column_count": col_count,
            "columns": columns_list,
        },
    )

    logger.info("Data ingestion completed successfully")
    return dst_path


if __name__ == "__main__":
    ingest_raw_data()
