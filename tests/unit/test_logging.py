"""Unit tests for structured logging utility."""

import json
import logging
from io import StringIO

from src.core.logging import JSONFormatter, get_logger


def test_json_formatter_emits_required_fields() -> None:
    """Assert JSON log records emit required fields.

    Fields required: timestamp, level, logger_name, module, message.
    """
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="src/core/test_mod.py",
        lineno=42,
        msg="Test log message",
        args=(),
        exc_info=None,
    )
    formatted_output = formatter.format(record)
    log_dict = json.loads(formatted_output)

    assert "timestamp" in log_dict
    assert log_dict["level"] == "INFO"
    assert log_dict["logger_name"] == "test_logger"
    assert log_dict["module"] == "test_mod"
    assert log_dict["message"] == "Test log message"


def test_json_formatter_includes_extra_context() -> None:
    """Assert custom primitive extra fields passed to logger are included."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.WARNING,
        pathname="src/data/ingest.py",
        lineno=10,
        msg="Ingestion warning",
        args=(),
        exc_info=None,
    )
    record.dataset_name = "telco_churn"  # type: ignore[attr-defined]
    record.row_count = 7043  # type: ignore[attr-defined]

    formatted_output = formatter.format(record)
    log_dict = json.loads(formatted_output)

    assert log_dict["dataset_name"] == "telco_churn"
    assert log_dict["row_count"] == 7043


def test_json_formatter_ignores_complex_unallowed_objects() -> None:
    """Assert complex arbitrary objects in extra fields are filtered out."""

    class RawCustomerPayload:
        pass

    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="src/data/ingest.py",
        lineno=15,
        msg="Processing customer payload",
        args=(),
        exc_info=None,
    )
    record.raw_payload = RawCustomerPayload()  # type: ignore[attr-defined]
    record.safe_id = "cust-99"  # type: ignore[attr-defined]

    formatted_output = formatter.format(record)
    log_dict = json.loads(formatted_output)

    assert "raw_payload" not in log_dict
    assert log_dict["safe_id"] == "cust-99"


def test_logger_factory_returns_configured_logger() -> None:
    """Test get_logger returns a Logger with correct name and handler."""
    logger = get_logger("unit_test_logger", json_format=False)
    assert logger.name == "unit_test_logger"
    assert len(logger.handlers) > 0


def test_logger_emits_json_to_stream() -> None:
    """Test logger writes structured JSON output to stream."""
    stream = StringIO()
    logger = logging.getLogger("stream_test_logger")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)

    logger.info("Stream test message", extra={"request_id": "req-123"})
    output = stream.getvalue()

    log_dict = json.loads(output)
    assert log_dict["message"] == "Stream test message"
    assert log_dict["request_id"] == "req-123"
    assert log_dict["level"] == "INFO"
