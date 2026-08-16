"""Unit tests for drift detection, Section 10 thresholds, state.

Tests PSI computation, boundary comparisons, consecutive-window state persistence,
and retraining trigger logic.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.core.config import Settings
from src.monitoring.drift import (
    calculate_feature_psis,
    calculate_psi,
    evaluate_drift_criteria,
    run_drift_pipeline,
)
from src.monitoring.jenkins_trigger import trigger_jenkins_retraining
from src.monitoring.state import MonitoringStateManager


@pytest.fixture
def custom_settings() -> Settings:
    """Fixture providing isolated Settings with Section 10 thresholds."""
    return Settings(
        DRIFT_FEATURE_PSI_THRESHOLD=0.20,
        DRIFT_EVIDENTLY_SCORE_THRESHOLD=0.15,
        DRIFT_CONFIDENCE_THRESHOLD=0.75,
        DRIFT_CONSECUTIVE_WINDOWS=3,
    )


# ==============================================================================
# 1. PSI Calculation Tests
# ==============================================================================


def test_psi_identical_distributions() -> None:
    """PSI for identical distributions must be ~0.0."""
    np.random.seed(42)
    ref = pd.Series(np.random.normal(0, 1, 1000))
    curr = ref.copy()
    psi_val = calculate_psi(ref, curr)
    assert psi_val == pytest.approx(0.0, abs=1e-3)


def test_psi_shifted_distribution() -> None:
    """PSI for significantly shifted distributions must be > 0.20."""
    np.random.seed(42)
    ref = pd.Series(np.random.normal(0, 1, 1000))
    curr = pd.Series(np.random.normal(3, 1, 1000))  # Large mean shift
    psi_val = calculate_psi(ref, curr)
    assert psi_val > 0.20


def test_psi_discrete_categories() -> None:
    """PSI handles categorical / discrete low-cardinality features properly."""
    ref = pd.Series(["A"] * 500 + ["B"] * 500)
    curr_same = pd.Series(["A"] * 500 + ["B"] * 500)
    curr_shifted = pd.Series(["A"] * 900 + ["B"] * 100)

    psi_same = calculate_psi(ref, curr_same)
    psi_shifted = calculate_psi(ref, curr_shifted)

    assert psi_same == pytest.approx(0.0, abs=1e-3)
    assert psi_shifted > 0.20


def test_calculate_feature_psis() -> None:
    """calculate_feature_psis computes a dict of PSIs across specified features."""
    ref_df = pd.DataFrame(
        {
            "feat_a": [1.0, 2.0, 3.0, 4.0, 5.0] * 100,
            "feat_b": [0, 1] * 250,
            "target": [0, 1] * 250,
        }
    )
    curr_df = ref_df.copy()
    psis = calculate_feature_psis(ref_df, curr_df, ["feat_a", "feat_b"])
    assert "feat_a" in psis
    assert "feat_b" in psis
    assert "target" not in psis
    assert psis["feat_a"] == pytest.approx(0.0, abs=1e-3)
    assert psis["feat_b"] == pytest.approx(0.0, abs=1e-3)


# ==============================================================================
# 2. Section 10 Threshold Boundary & Criterion Evaluation Tests
# ==============================================================================


def test_evaluate_drift_criteria_no_drift(custom_settings: Settings) -> None:
    """When all metrics are within normal ranges, drift must be False."""
    psis = {"f1": 0.05, "f2": 0.12}
    evidently_score = 0.08
    mean_confidence = 0.85

    is_drift, summary, reasons = evaluate_drift_criteria(
        psis, evidently_score, mean_confidence, settings=custom_settings
    )

    assert is_drift is False
    assert len(reasons) == 0
    assert summary["drift_detected"] is False
    assert summary["psi_criterion"]["breached"] is False
    assert summary["evidently_criterion"]["breached"] is False
    assert summary["confidence_criterion"]["breached"] is False


def test_evaluate_drift_criteria_psi_only_drift(
    custom_settings: Settings,
) -> None:
    """When any feature PSI > 0.20, drift must be True."""
    psis = {"f1": 0.05, "f2": 0.25}  # f2 > 0.20
    evidently_score = 0.05
    mean_confidence = 0.85

    is_drift, summary, reasons = evaluate_drift_criteria(
        psis, evidently_score, mean_confidence, settings=custom_settings
    )

    assert is_drift is True
    assert len(reasons) == 1
    assert "feature_psi" in reasons[0]
    assert summary["psi_criterion"]["breached"] is True
    assert summary["evidently_criterion"]["breached"] is False
    assert summary["confidence_criterion"]["breached"] is False


def test_evaluate_drift_criteria_evidently_only_drift(
    custom_settings: Settings,
) -> None:
    """When Evidently drift score > 0.15, drift must be True."""
    psis = {"f1": 0.05, "f2": 0.10}
    evidently_score = 0.22  # > 0.15
    mean_confidence = 0.80

    is_drift, summary, reasons = evaluate_drift_criteria(
        psis, evidently_score, mean_confidence, settings=custom_settings
    )

    assert is_drift is True
    assert len(reasons) == 1
    assert "evidently_drift_score" in reasons[0]
    assert summary["evidently_criterion"]["breached"] is True


def test_evaluate_drift_criteria_confidence_only_drift(
    custom_settings: Settings,
) -> None:
    """When mean prediction confidence < 0.75, drift must be True."""
    psis = {"f1": 0.05, "f2": 0.10}
    evidently_score = 0.05
    mean_confidence = 0.68  # < 0.75

    is_drift, summary, reasons = evaluate_drift_criteria(
        psis, evidently_score, mean_confidence, settings=custom_settings
    )

    assert is_drift is True
    assert len(reasons) == 1
    assert "mean_confidence" in reasons[0]
    assert summary["confidence_criterion"]["breached"] is True


def test_evaluate_drift_criteria_multiple_criteria(
    custom_settings: Settings,
) -> None:
    """When multiple criteria breach, all reasons must be listed."""
    psis = {"f1": 0.35, "f2": 0.10}
    evidently_score = 0.25
    mean_confidence = 0.60

    is_drift, _, reasons = evaluate_drift_criteria(
        psis, evidently_score, mean_confidence, settings=custom_settings
    )

    assert is_drift is True
    assert len(reasons) == 3


def test_strict_boundary_psi(custom_settings: Settings) -> None:
    """PSI = 0.20 must NOT breach (strict >); PSI = 0.2001 MUST breach."""
    psis_exact = {"f1": 0.20}
    is_drift_exact, _, _ = evaluate_drift_criteria(
        psis_exact, 0.0, 0.90, settings=custom_settings
    )
    assert is_drift_exact is False

    psis_over = {"f1": 0.2001}
    is_drift_over, _, _ = evaluate_drift_criteria(
        psis_over, 0.0, 0.90, settings=custom_settings
    )
    assert is_drift_over is True


def test_strict_boundary_evidently_score(custom_settings: Settings) -> None:
    """Evidently score = 0.15 must NOT breach; score = 0.1501 MUST breach."""
    is_drift_exact, _, _ = evaluate_drift_criteria(
        {"f1": 0.05}, 0.15, 0.90, settings=custom_settings
    )
    assert is_drift_exact is False

    is_drift_over, _, _ = evaluate_drift_criteria(
        {"f1": 0.05}, 0.1501, 0.90, settings=custom_settings
    )
    assert is_drift_over is True


def test_strict_boundary_confidence(custom_settings: Settings) -> None:
    """Confidence=0.75 must NOT breach; 0.7499 MUST breach."""
    is_drift_exact, _, _ = evaluate_drift_criteria(
        {"f1": 0.05}, 0.0, 0.75, settings=custom_settings
    )
    assert is_drift_exact is False

    is_drift_under, _, _ = evaluate_drift_criteria(
        {"f1": 0.05}, 0.0, 0.7499, settings=custom_settings
    )
    assert is_drift_under is True


# ==============================================================================
# 3. 3-Consecutive-Window State Machine Tests
# ==============================================================================


def test_state_machine_3_consecutive_windows_and_reset(tmp_path: Path) -> None:
    """Verify 3 consecutive drift windows trigger retraining.

    Resets on a clean window.
    """
    state_file = tmp_path / "test_monitoring_state.json"
    mgr = MonitoringStateManager(state_file_path=state_file)

    # Window 1: Drift -> count=1, should_retrain=False
    count_1, retrain_1 = mgr.record_window_result(
        "win-1", drift_detected=True, triggering_criteria=["feature_psi"]
    )
    assert count_1 == 1
    assert retrain_1 is False

    # Window 2: Drift -> count=2, should_retrain=False
    count_2, retrain_2 = mgr.record_window_result(
        "win-2", drift_detected=True, triggering_criteria=["feature_psi"]
    )
    assert count_2 == 2
    assert retrain_2 is False

    # Window 3: Drift -> count=3, should_retrain=True
    count_3, retrain_3 = mgr.record_window_result(
        "win-3", drift_detected=True, triggering_criteria=["feature_psi"]
    )
    assert count_3 == 3
    assert retrain_3 is True

    # Window 4: Clean -> count=0, should_retrain=False
    count_4, retrain_4 = mgr.record_window_result(
        "win-4", drift_detected=False, triggering_criteria=[]
    )
    assert count_4 == 0
    assert retrain_4 is False

    # State file must persist and reload accurately
    reloaded_state = mgr.load_state()
    assert reloaded_state.consecutive_drift_windows == 0
    assert reloaded_state.total_windows_evaluated == 4
    assert len(reloaded_state.history) == 4


# ==============================================================================
# 4. End-to-End Pipeline & Synthetic Window Tests
# ==============================================================================


def test_run_drift_pipeline_unshifted(tmp_path: Path) -> None:
    """Running pipeline on unshifted splits produces no drift."""
    train_csv = Path("data/processed/train.csv")
    test_csv = Path("data/processed/test.csv")
    if not train_csv.exists() or not test_csv.exists():
        pytest.skip("Processed dataset artifacts not found for pipeline test.")

    state_file = tmp_path / "state_unshifted.json"
    report_file = tmp_path / "report_unshifted.json"

    # Compare train against first 500 rows of train (identical distribution)
    df_train = pd.read_csv(train_csv)
    ref_file = tmp_path / "ref.csv"
    curr_file = tmp_path / "curr.csv"
    df_train.head(500).to_csv(ref_file, index=False)
    df_train.head(500).to_csv(curr_file, index=False)

    report = run_drift_pipeline(
        reference_path=ref_file,
        current_path=curr_file,
        window_id="win-unshifted",
        state_file_path=state_file,
        output_report_path=report_file,
        model_path=tmp_path / "dummy.joblib",
        trigger_retraining=False,
    )

    assert report["summary"]["drift_detected"] is False
    assert report["summary"]["consecutive_drift_windows"] == 0
    assert report["summary"]["retraining_triggered"] is False
    assert report["summary"]["evidently_dataset_drift_score"] == pytest.approx(
        0.0, abs=1e-3
    )


def test_run_drift_pipeline_shifted(tmp_path: Path) -> None:
    """Shifted synthetic current window detects drift."""
    train_csv = Path("data/processed/train.csv")
    if not train_csv.exists():
        pytest.skip("Processed train dataset not found for pipeline test.")

    df_train = pd.read_csv(train_csv)
    ref_file = tmp_path / "ref.csv"
    df_train.head(500).to_csv(ref_file, index=False)

    # Create deliberately shifted synthetic dataset
    # (e.g. shift tenure and MonthlyCharges heavily)
    df_shifted = df_train.head(500).copy()
    if "tenure" in df_shifted.columns:
        df_shifted["tenure"] = df_shifted["tenure"] + 10.0
    if "MonthlyCharges" in df_shifted.columns:
        df_shifted["MonthlyCharges"] = df_shifted["MonthlyCharges"] + 15.0

    curr_file = tmp_path / "shifted_curr.csv"
    df_shifted.to_csv(curr_file, index=False)

    state_file = tmp_path / "state_shifted.json"
    report_file = tmp_path / "report_shifted.json"

    report = run_drift_pipeline(
        reference_path=ref_file,
        current_path=curr_file,
        window_id="win-shifted",
        state_file_path=state_file,
        output_report_path=report_file,
        model_path=tmp_path / "dummy.joblib",
        trigger_retraining=False,
    )

    assert report["summary"]["drift_detected"] is True
    assert report["summary"]["consecutive_drift_windows"] == 1
    assert len(report["summary"]["triggering_criteria"]) > 0


# ==============================================================================
# 5. Jenkins Retraining Trigger Tests
# ==============================================================================


@patch("urllib.request.urlopen")
def test_jenkins_trigger_mocked_success(mock_urlopen: MagicMock) -> None:
    """trigger_jenkins_retraining successfully acquires crumb and dispatches POST."""
    # Mock crumb response
    mock_crumb_resp = MagicMock()
    mock_crumb_resp.read.return_value = b"Jenkins-Crumb:abc123crumb"
    mock_crumb_resp.__enter__.return_value = mock_crumb_resp

    # Mock build response
    mock_build_resp = MagicMock()
    mock_build_resp.status = 201
    mock_build_resp.headers = {"Location": "http://localhost:8080/queue/item/42/"}
    mock_build_resp.__enter__.return_value = mock_build_resp

    mock_urlopen.side_effect = [mock_crumb_resp, mock_build_resp]

    result = trigger_jenkins_retraining(
        job_name="telco-churn-pipeline",
        reason=["feature_psi"],
        jenkins_url="http://localhost:8080",
        auth_credentials="admin:test-token",
    )

    assert result["status"] == "success"
    assert result["status_code"] == 201
    assert result["job_name"] == "telco-churn-pipeline"
    assert "queue/item/42/" in result["queue_location"]


def test_jenkins_trigger_missing_auth_raises() -> None:
    """trigger_jenkins_retraining raises RuntimeError when auth is empty."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(RuntimeError, match="No authentication credentials"):
            trigger_jenkins_retraining(
                auth_credentials="",
            )
