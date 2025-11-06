import numpy as np
import pytest
from pytestqt.qtbot import QtBot
from unittest.mock import MagicMock, patch

from acq4.devices.MockStage import MockStage
from acq4.devices.Stage import Stage
from acq4.devices.Stage.calibration import (
    ManipulatorAxesCalibrationWindow,
    group_points_by_colinearity,
)

@pytest.fixture
def unlimited_manipulator() -> Stage:
    class MockDM:
        def __init__(self):
            self.sigAbortAll = MagicMock()

        def declareInterface(self, name, interfaces, obj):
            pass

        def getDevice(self, name):
            return None

        def readConfigFile(self, fn):
            return {}

    mock_dm = MockDM()
    config = {
        'driver': 'MockStage',
        'nAxes': 4,
        'imagingDevice': 'Cam',
    }
    with patch("acq4.Manager.Manager.single") as mock_get_manager:
        mock_get_manager.return_value = mock_dm
        yield MockStage(mock_dm, config, "Stage4")


def test_axis_calibration_4_axes(unlimited_manipulator, qtbot):
    cal_win = ManipulatorAxesCalibrationWindow(unlimited_manipulator)
    sqrt2 = np.sqrt(2)
    cal_win.calibration["points"] = [
        [[0, 0, 0, 0], [0, 0, 0]],
        [[1, 0, 0, 0], [1, 0, 0]],
        [[2, 0, 0, 0], [2, 0, 0]],
        [[3, 0, 0, 0], [3, 0, 0]],
        [[3, 1, 0, 0], [3, 1, 0]],
        [[3, 2, 0, 0], [3, 2, 0]],
        [[3, 3, 0, 0], [3, 3, 0]],
        [[3, 3, 1, 0], [3, 3, 1]],
        [[3, 3, 2, 0], [3, 3, 2]],
        [[3, 3, 3, 0], [3, 3, 3]],
        [[3, 3, 3, 1], [3 + sqrt2, 3, 3 + sqrt2]],
        [[3, 3, 3, 2], [3 + 2 * sqrt2, 3, 3 + 2 * sqrt2]],
        [[3, 3, 3, 3], [3 + 3 * sqrt2, 3, 3 + 3 * sqrt2]],
    ]
    cal_win.recalculate()

    angles = unlimited_manipulator.calculatedAxisOrientation('+d')
    assert angles['pitch'] == pytest.approx(45.0)
    assert angles['yaw'] == pytest.approx(0.0)
