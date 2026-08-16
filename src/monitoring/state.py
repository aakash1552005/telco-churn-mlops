"""Monitoring State Management Module.

Provides persistent state tracking for monitoring windows across distinct process
invocations or container lifecycle runs.
Tracks consecutive drift windows, window execution counters, and historical decisions.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_STATE_FILE_PATH = Path("reports/monitoring_state.json")


@dataclass
class WindowRecord:
    """Record of an individual monitoring window execution."""

    window_id: str
    timestamp: str
    drift_detected: bool
    triggering_criteria: List[str]
    consecutive_drift_count: int
    retraining_triggered: bool
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MonitoringState:
    """Persistent state container for drift monitoring."""

    total_windows_evaluated: int = 0
    consecutive_drift_windows: int = 0
    last_window_id: Optional[str] = None
    last_evaluated_at: Optional[str] = None
    last_retraining_triggered_at: Optional[str] = None
    history: List[Dict[str, Any]] = field(default_factory=list)


class MonitoringStateManager:
    """Manages reading, updating, and persisting drift monitoring state to disk."""

    def __init__(self, state_file_path: Optional[Path] = None) -> None:
        """Initialize state manager with file path."""
        self.state_file_path = state_file_path or DEFAULT_STATE_FILE_PATH

    def load_state(self) -> MonitoringState:
        """Load state from persistent JSON file, or return empty state if absent."""
        if not self.state_file_path.exists():
            logger.info(
                f"State file '{self.state_file_path}' not found."
                " Initializing fresh state."
            )
            return MonitoringState()

        try:
            with open(self.state_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return MonitoringState(
                total_windows_evaluated=data.get("total_windows_evaluated", 0),
                consecutive_drift_windows=data.get("consecutive_drift_windows", 0),
                last_window_id=data.get("last_window_id"),
                last_evaluated_at=data.get("last_evaluated_at"),
                last_retraining_triggered_at=data.get("last_retraining_triggered_at"),
                history=data.get("history", []),
            )
        except Exception as e:
            logger.warning(
                f"Failed to read state file "
                f"'{self.state_file_path}' ({e}). "
                "Reinitializing."
            )
            return MonitoringState()

    def record_window_result(
        self,
        window_id: str,
        drift_detected: bool,
        triggering_criteria: List[str],
        retraining_threshold: int = 3,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> tuple[int, bool]:
        """Update state with the result of a monitoring window.

        Args:
            window_id: Unique window identifier string.
            drift_detected: True if Section 10 drift threshold was breached.
            triggering_criteria: List of breached criteria names.
            retraining_threshold: Number of consecutive drift
                windows needed to trigger retraining.
            metadata: Additional provenance metadata for the window.

        Returns:
            Tuple of (new_consecutive_drift_count, should_trigger_retraining).
        """
        state = self.load_state()
        now_iso = datetime.now(timezone.utc).isoformat()

        if drift_detected:
            state.consecutive_drift_windows += 1
        else:
            state.consecutive_drift_windows = 0

        state.total_windows_evaluated += 1
        state.last_window_id = window_id
        state.last_evaluated_at = now_iso

        should_trigger = state.consecutive_drift_windows >= retraining_threshold

        if should_trigger:
            state.last_retraining_triggered_at = now_iso

        record = WindowRecord(
            window_id=window_id,
            timestamp=now_iso,
            drift_detected=drift_detected,
            triggering_criteria=triggering_criteria,
            consecutive_drift_count=state.consecutive_drift_windows,
            retraining_triggered=should_trigger,
            metadata=metadata or {},
        )

        # Keep last 50 window records in history
        state.history.append(asdict(record))
        if len(state.history) > 50:
            state.history = state.history[-50:]

        self.save_state(state)

        logger.info(
            f"Updated monitoring state for window '{window_id}': "
            f"drift={drift_detected}, "
            f"consecutive_count={state.consecutive_drift_windows}, "
            f"retrain_triggered={should_trigger}"
        )

        return state.consecutive_drift_windows, should_trigger

    def save_state(self, state: MonitoringState) -> None:
        """Persist state object to JSON on disk atomically."""
        self.state_file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_file_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(asdict(state), f, indent=2)
            temp_path.replace(self.state_file_path)
        except Exception as e:
            logger.error(f"Failed to persist state to '{self.state_file_path}': {e}")
            if temp_path.exists():
                temp_path.unlink()
            raise
