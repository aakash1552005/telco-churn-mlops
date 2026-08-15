"""Unit tests for configuration management via Pydantic Settings."""

import os
from unittest import mock

import pytest
from pydantic import ValidationError

from src.core.config import Settings, get_settings


def test_settings_loads_valid_config() -> None:
    """Test loading valid settings from environment variables."""
    env_vars = {
        "ENVIRONMENT": "testing",
        "LOG_LEVEL": "DEBUG",
        "MLFLOW_TRACKING_URI": "http://test-mlflow:5000",
        "AWS_REGION": "us-west-2",
    }
    with mock.patch.dict(os.environ, env_vars, clear=True):
        settings = Settings(_env_file=None)
        assert settings.ENVIRONMENT == "BROKEN_TEST_INTENTIONAL"  # Deliberate failure gate test
        assert settings.LOG_LEVEL == "DEBUG"
        assert settings.MLFLOW_TRACKING_URI == "http://test-mlflow:5000"
        assert settings.AWS_REGION == "us-west-2"


def test_missing_required_environment_fails_fast() -> None:
    """Test that missing required 'ENVIRONMENT' variable raises ValidationError."""
    with mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None)
        errors = exc_info.value.errors()
        assert any(err["loc"] == ("ENVIRONMENT",) for err in errors)


def test_promotion_policy_thresholds() -> None:
    """Test that Section 9 promotion policy thresholds are defined correctly."""
    with mock.patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
        settings = Settings(_env_file=None)
        assert settings.PROMOTION_MIN_F1_DELTA == 0.01
        assert settings.PROMOTION_MAX_PRECISION_DROP == 0.02
        assert settings.PROMOTION_ALLOW_RECALL_DECREASE is False


def test_drift_policy_thresholds() -> None:
    """Test that Section 10 drift detection thresholds are defined correctly."""
    with mock.patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
        settings = Settings(_env_file=None)
        assert settings.DRIFT_FEATURE_PSI_THRESHOLD == 0.2
        assert settings.DRIFT_EVIDENTLY_SCORE_THRESHOLD == 0.15
        assert settings.DRIFT_CONFIDENCE_THRESHOLD == 0.75
        assert settings.DRIFT_CONSECUTIVE_WINDOWS == 3


def test_get_settings_singleton() -> None:
    """Test get_settings() returns a Settings instance."""
    with mock.patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=True):
        settings = get_settings()
        assert isinstance(settings, Settings)
        assert settings.ENVIRONMENT == "development"
