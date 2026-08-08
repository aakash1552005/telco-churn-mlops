"""Structured Logging Utility for Telco Churn MLOps Platform.

USAGE:
    from src.core.logging import get_logger

    logger = get_logger(__name__)
    logger.info("Data ingestion started", extra={"dataset": "telco_churn"})
    logger.error("Validation failed", extra={"missing_columns": ["tenure"]})

LOGGING CONVENTIONS:
    - Every module MUST obtain a logger via `get_logger(__name__)`.
    - Do NOT use bare `print()` statements anywhere in `src/`.

LOG LEVELS GUIDANCE:
    - DEBUG   : Detailed diagnostic information for local debugging.
    - INFO    : General operational events (ingestion start/complete).
    - WARNING : Non-critical anomalies (e.g. missing optional fields).
    - ERROR   : Operative failures requiring attention (validation error).
    - CRITICAL: System-wide failures rendering service unavailable.

PII & SECURITY CONSTRAINTS (MANDATORY):
    - NEVER log entire customer records, raw database rows, or payloads.
    - NEVER log PII such as customer names, emails, phone numbers,
      street addresses, or payment details.
    - Future modules MUST explicitly select and sanitize fields to log.
    - Arbitrary `extra=` context is supported for non-PII identifiers.
"""

import json
import logging
import sys
from typing import Any, Dict, Optional

from src.core.config import get_settings

# Built-in attributes of logging.LogRecord to exclude from extra fields
STANDARD_LOG_RECORD_ATTRS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "taskName",
}


class JSONFormatter(logging.Formatter):
    """Formatter emitting single-line JSON log records with extra context."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger_name": record.name,
            "module": record.module,
            "message": record.getMessage(),
        }

        # Include exception info if present
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            log_data["exception"] = record.exc_text

        # Safely extract custom extra fields passed via extra={...}
        for key, val in record.__dict__.items():
            if key not in STANDARD_LOG_RECORD_ATTRS:
                try:
                    json.dumps(val)
                    log_data[key] = val
                except (TypeError, OverflowError):
                    log_data[key] = str(val)

        return json.dumps(log_data)


def get_logger(name: str, json_format: Optional[bool] = None) -> logging.Logger:
    """Factory function returning a configured Logger instance.

    Args:
        name: Name of the logger, typically `__name__`.
        json_format: Force JSON formatting if True, text if False.
                     Defaults to True for prod/staging, False for dev.

    Returns:
        Configured logging.Logger instance.
    """
    logger = logging.getLogger(name)

    # Avoid duplicate handlers if called multiple times for same module
    if logger.handlers:
        return logger

    settings = get_settings()
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(log_level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

    if json_format is None:
        json_format = settings.ENVIRONMENT.lower() in ("production", "staging")

    if json_format:
        formatter: logging.Formatter = JSONFormatter()
    else:
        fmt_str = "%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(message)s"
        formatter = logging.Formatter(fmt_str)

    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False

    return logger
