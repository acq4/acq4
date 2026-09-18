"""Recording a stored location close to an axis limit succeeds, with a warning.

A home position recorded against an axis limit is reachable at the moment it is saved
and may not be later: an axis commanded to its own end of travel stops short, and on a
4-axis manipulator the stored global point does not say which device position produced
it, so the inverse kinematics can come back with the redundant axis parked on its bound.
Refusing to save would lose the position, so the save stands and the operator is warned.
"""

import logging

import pytest
from unittest.mock import patch

from acq4.devices.MockStage import MockStage
from acq4.panic import GlobalHalt


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
    """Build a MockStage reporting µm, with configurable axis limits."""
    made = []

    def factory(limits, nAxes=4, scale=None):
        config = {
            'driver': 'MockStage',
            'nAxes': nAxes,
            # device units of µm, as a Sensapex reports; the guard's 500 µm tolerance is
            # a real distance and has to be converted through this to compare to limits
            'scale': [1e-6] * nAxes if scale is None else scale,
            'limits': limits,
        }
        with patch("acq4.Manager.Manager.single") as single:
            single.return_value = _MockDM()
            dev = MockStage(_MockDM(), config, f"MockLimitStage{len(made)}")
        made.append(dev)

        # keep stored locations in memory; this test is about the warning, not the file
        dev._stored = {}
        dev.readConfigFile = lambda fn: dict(dev._stored)
        dev.writeConfigFile = lambda data, fn: dev._stored.update(data)
        return dev

    yield factory
    for dev in made:
        dev.quit()


# MockStage starts at 0 on every axis, so limits are written relative to that.
ROOMY = {'x': [-20000, 20000], 'y': [-20000, 20000], 'z': [-20000, 20000], 'd': [-20000, 20000]}


def test_position_with_room_saves_without_warning(make_stage, caplog):
    stage = make_stage(ROOMY)
    with caplog.at_level(logging.WARNING):
        stage.setHomePosition()
    assert 'home' in stage._stored
    assert not [r for r in caplog.records if 'limit' in r.getMessage()]


def test_position_against_a_limit_saves_and_warns(make_stage, caplog):
    # x sits exactly on its lower limit, the others have room.
    limits = dict(ROOMY, x=[0, 20000])
    stage = make_stage(limits)
    with caplog.at_level(logging.WARNING):
        stage.setHomePosition()

    assert 'home' in stage._stored, "the position must still be recorded"
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "'home'" in warnings[0]
    assert '500 µm' in warnings[0] or '500 um' in warnings[0]
    assert ' x ' in warnings[0] or 'x =' in warnings[0]


def test_fourth_axis_is_checked_too(make_stage):
    # The d axis is the one a stored *global* position cannot describe, and the one that
    # the inverse kinematics parks on its bound; the guard works in device coordinates
    # precisely so that it sees it.
    stage = make_stage(dict(ROOMY, d=[0, 20000]))
    near = stage.axesNearLimits()
    assert [ax for ax, _, _ in near] == ['d']


def test_tolerance_is_a_real_distance_not_device_units(make_stage):
    # 400 µm from the limit in device units (µm) is inside the 500 µm tolerance...
    stage = make_stage(dict(ROOMY, x=[-400, 20000]))
    assert [ax for ax, _, _ in stage.axesNearLimits()] == ['x']
    # ...but a stage reporting mm is 400 mm away from the same-looking limit.
    mm_stage = make_stage(dict(ROOMY, x=[-400, 20000]), scale=[1e-3] * 4)
    assert mm_stage.axesNearLimits() == []


def test_unset_limits_are_not_flagged(make_stage):
    stage = make_stage({'x': [None, None], 'y': [None, None], 'z': [None, None], 'd': [None, None]})
    assert stage.axesNearLimits() == []


def test_tolerance_is_overridable(make_stage):
    stage = make_stage(dict(ROOMY, x=[-1000, 20000]))
    assert stage.axesNearLimits() == []
    assert [ax for ax, _, _ in stage.axesNearLimits(tolerance=2000e-6)] == ['x']


def test_out_of_range_position_still_raises(make_stage):
    # The existing hard check comes first: a position outside the limits is refused
    # outright rather than saved with a warning.
    stage = make_stage(dict(ROOMY, x=[100, 20000]))
    with pytest.raises(ValueError):
        stage.setHomePosition()
    assert 'home' not in stage._stored
