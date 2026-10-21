"""Tests that DefaultMotionPlanner._safe_path reports only OutOfLimitsError as a limits
error and re-raises other exceptions from checkGlobalLimits unchanged."""
from __future__ import annotations

import numpy as np
import pytest

from acq4.devices.Stage import OutOfLimitsError
from acq4.motion.tests.conftest import MockPipette


def make_planner():
    """A DefaultMotionPlanner that records _on_path_error instead of driving Visualize3D."""
    from acq4.motion.default_planner import DefaultMotionPlanner

    class _RecordingPlanner(DefaultMotionPlanner):
        def __init__(self):
            super().__init__()
            self.path_errors = []

        def _on_path_computed(self, pip, full_path):
            pass

        def _on_path_error(self, pip, full_path, failed_at):
            self.path_errors.append(failed_at)

    return _RecordingPlanner()


def _refusing_pipette(error):
    pip = MockPipette("pip1", global_pos=(0.0, 0.0, 1e-3))

    def refuse(pos, linear=False):
        raise error

    pip.parentStage.checkGlobalLimits = refuse
    return pip


def test_a_limit_violation_is_reported_as_a_limit_violation():
    planner = make_planner()
    pip = _refusing_pipette(OutOfLimitsError("x axis > 1000"))

    with pytest.raises(ValueError) as exc:
        planner._safe_path(pip, np.array([0.0, 0.0, 1e-3]), np.array([1e-3, 0.0, 1e-3]), "fast")

    assert "beyond the limits of its manipulator" in str(exc.value)
    assert "x axis > 1000" in str(exc.value)
    assert planner.path_errors, "the visualizer must still be told where the path failed"


def test_a_mapping_fault_is_not_reported_as_a_limit_violation():
    planner = make_planner()
    fault = RuntimeError("Transform is degenerate; cannot compute inverse kinematics")
    pip = _refusing_pipette(fault)

    with pytest.raises(RuntimeError) as exc:
        planner._safe_path(pip, np.array([0.0, 0.0, 1e-3]), np.array([1e-3, 0.0, 1e-3]), "fast")

    assert exc.value is fault, "the original exception must propagate unchanged"
    assert "beyond the limits" not in str(exc.value)
    assert planner.path_errors, "the visualizer must still be told where the path failed"


def test_a_value_error_that_is_not_about_limits_also_propagates():
    # OutOfLimitsError subclasses ValueError; a plain ValueError must still propagate as is.
    planner = make_planner()
    fault = ValueError("No valid position within bounds")
    pip = _refusing_pipette(fault)

    with pytest.raises(ValueError) as exc:
        planner._safe_path(pip, np.array([0.0, 0.0, 1e-3]), np.array([1e-3, 0.0, 1e-3]), "fast")

    assert exc.value is fault
    assert "beyond the limits" not in str(exc.value)
