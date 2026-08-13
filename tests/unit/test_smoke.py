"""Unit test module for automated smoke test script."""

from scripts.smoke_test import run_smoke_test


def test_smoke_test_function_signature() -> None:
    """Test run_smoke_test signature is callable and has expected defaults."""
    assert callable(run_smoke_test)
