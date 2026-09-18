"""checkRangeOfMotion must distinguish "out of limits" from "the mapping failed".

It probes a position by nudging it toward each limit and asking whether the result is
still in range. Only an actual out-of-range answer says anything about the range of
motion; every other way the mapping can fail -- a missing previousPos on a 4-axis
inverse mapping, a degenerate transform -- is a fault, and reporting it as "this
position is near the x, y and z limits" is a confident wrong answer about a position
that may be nowhere near one.
"""

import numpy as np
import pytest
from unittest.mock import patch

from acq4.devices.MockStage import MockStage
from acq4.devices.Stage import OutOfLimitsError
from acq4.panic import GlobalHalt
from acq4.util.HelpfulException import HelpfulException


class _MockDM:
    def __init__(self):
        self.globalHalt = GlobalHalt()

    def declareInterface(self, name, interfaces, obj):
        pass

    def getDevice(self, name):
        return None

    def readConfigFile(self, fn):
        return {}


@pytest.fixture
def make_stage(qtbot):
    made = []

    def factory(limits, nAxes=3):
        config = {
            'driver': 'MockStage',
            'nAxes': nAxes,
            'scale': [1e-6] * nAxes,  # device units of µm
            'limits': limits,
        }
        with patch("acq4.Manager.Manager.single") as single:
            single.return_value = _MockDM()
            dev = MockStage(_MockDM(), config, f"MockRangeStage{len(made)}")
        made.append(dev)
        return dev

    yield factory
    for dev in made:
        dev.quit()


WIDE = {'x': [-50000, 50000], 'y': [-50000, 50000], 'z': [-50000, 50000]}


def test_out_of_limits_is_its_own_type():
    assert issubclass(OutOfLimitsError, ValueError)


def test_check_limits_raises_the_specific_type(make_stage):
    stage = make_stage(WIDE)
    with pytest.raises(OutOfLimitsError):
        stage.checkLimits([60000, 0, 0])


def test_position_with_room_passes(make_stage):
    # 10 mm from every limit, well outside the 500 µm tolerance.
    stage = make_stage(WIDE)
    stage.checkRangeOfMotion(np.array([0.0, 0.0, 0.0]), 'somewhere safe')


def test_position_near_a_limit_is_reported(make_stage):
    # x is 100 µm inside its limit; the probe steps 500 µm past it.
    stage = make_stage(dict(WIDE, x=[-100, 50000]))
    with pytest.raises(HelpfulException) as exc:
        stage.checkRangeOfMotion(np.array([0.0, 0.0, 0.0]), 'too close to x')
    assert 'x' in str(exc.value)


def test_mapping_faults_are_not_reported_as_limit_problems(make_stage):
    """A 4-axis stage cannot be probed this way, and must say so.

    mapGlobalToDevicePosition needs a previousPos for the inverse kinematics and is not
    given one here, so every probe raises. Before, that ValueError was caught and each
    of x, y and z was marked as near its limit -- so a 4-axis manipulator reported a
    range-of-motion problem for every position, including ones in the middle of its
    travel. Now the fault propagates.
    """
    stage = make_stage(dict(WIDE, d=[-50000, 50000]), nAxes=4)
    with pytest.raises(ValueError) as exc:
        stage.checkRangeOfMotion(np.array([0.0, 0.0, 0.0]), 'middle of nowhere')
    assert 'previousPos' in str(exc.value)
    assert not isinstance(exc.value, HelpfulException), (
        "a mapping fault must not be reported as a range-of-motion warning"
    )
