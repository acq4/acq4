"""checkRangeOfMotion must distinguish "out of limits" from "the mapping failed".

It probes a position by nudging it toward each limit and asking whether the result is
still in range. Only an actual out-of-range answer says anything about the range of
motion; every other way the mapping can fail -- a degenerate transform, a driver fault
-- is a fault, and reporting it as "this position is near the x, y and z limits" is a
confident wrong answer about a position that may be nowhere near one. The probes supply
the previousPos a 4-axis inverse mapping needs, so a 4-axis stage can be probed at all.
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
    """Only an out-of-limits answer says anything about the range of motion.

    Any other way the mapping can fail -- a degenerate transform, a driver fault -- is
    not evidence that the position is near a limit. Reporting one as "this position is
    near the x, y and z limits" is a confident wrong answer, so it propagates instead.
    """
    stage = make_stage(WIDE)
    fault = RuntimeError("the transform is degenerate")
    with patch.object(stage, 'mapGlobalToDevicePosition', side_effect=fault):
        with pytest.raises(RuntimeError) as exc:
            stage.checkRangeOfMotion(np.array([0.0, 0.0, 0.0]), 'middle of nowhere')
    assert exc.value is fault
    assert not isinstance(exc.value, HelpfulException), (
        "a mapping fault must not be reported as a range-of-motion warning"
    )


def test_a_four_axis_stage_in_open_travel_passes(make_stage):
    """The probe supplies the previousPos the 4-axis inverse kinematics needs.

    Without it every probe raised, so saving a position on a uMp -- which goes through
    checkRangeOfMotion with tolerance=0 -- failed for every position, including ones in
    the middle of the manipulator's travel.
    """
    stage = make_stage(dict(WIDE, d=[-50000, 50000]), nAxes=4)
    stage.checkRangeOfMotion(np.array([0.0, 0.0, 0.0]), 'middle of nowhere')


@pytest.mark.xfail(
    strict=True,
    reason="known gap: on >3 axes a probe outside the reachable set raises out of the "
           "inverse kinematics before checkLimits can call it an OutOfLimitsError, so "
           "the range-of-motion warning is never reached. If this starts passing, the "
           "previousPos warning in Stage.checkRangeOfMotion can go.",
)
def test_a_four_axis_stage_near_a_limit_is_reported_as_a_range_problem(make_stage):
    # x is 100 µm inside its limit and the probe steps 500 µm past it. On 3 axes that is
    # an OutOfLimitsError and the axis is named; on 4 it is a bare ValueError out of
    # minimum_displacement_inverse_kinematics, which checkRangeOfMotion rightly treats as
    # a fault rather than as evidence about the range of motion.
    stage = make_stage(dict(WIDE, x=[-100, 50000], d=[-50000, 50000]), nAxes=4)
    with pytest.raises(HelpfulException) as exc:
        stage.checkRangeOfMotion(np.array([0.0, 0.0, 0.0]), 'too close to x')
    assert 'x' in str(exc.value)
