"""Demonstration script showing text and JSON logging across log levels."""

import pathlib
import sys

# Ensure project root is on sys.path when executed directly
PROJECT_ROOT = pathlib.Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.logging import get_logger  # noqa: E402


def run_demo() -> None:
    print("=== PLAIN TEXT FORMATTER DEMO ===")
    text_logger = get_logger("demo.text", json_format=False)
    text_logger.setLevel("DEBUG")
    for h in text_logger.handlers:
        h.setLevel("DEBUG")

    text_logger.debug("Debugging data ingestion pipeline step 1")
    text_logger.info("Data ingestion completed successfully")
    text_logger.warning("Optional column 'TotalCharges' has 11 empty strings")
    text_logger.error("Database connection timeout after 3 retries")

    print("\n=== JSON FORMATTER DEMO ===")
    json_logger = get_logger("demo.json", json_format=True)
    json_logger.setLevel("DEBUG")
    for h in json_logger.handlers:
        h.setLevel("DEBUG")

    json_logger.debug("Checking cache status", extra={"cache_hit": False, "step": 1})
    json_logger.info("Dataset batch processed", extra={"rows": 7043, "columns": 21})
    json_logger.warning("High memory usage detected", extra={"memory_percent": 84.5})
    json_logger.error(
        "Model evaluation failed",
        extra={"error_code": "VAL_404", "model_version": "v1.2.0"},
    )


if __name__ == "__main__":
    run_demo()
