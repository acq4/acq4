"""A stage's ``scale:`` must give exactly one entry per axis, checked when it loads.

scale is metres per device unit, and everything that turns device coordinates into a
distance indexes it by axis. A scale with fewer entries than the device has axes drops
the axes off the end: a 4-axis uMp given a 3-entry scale scores a pure-d move as zero
distance, so MoveFuture.expectedDuration returns 0.0 for a retraction that physically
takes a quarter of an hour. Failing once at startup beats failing deep inside a
duration calculation on a rig with a pipette in tissue.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

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
    made = []

    def factory(nAxes, scale=None, name='ScaleStage'):
        config = {'driver': 'MockStage', 'nAxes': nAxes}
        if scale is not None:
            config['scale'] = scale
        with patch("acq4.Manager.Manager.single") as single:
            single.return_value = _MockDM()
            dev = MockStage(_MockDM(), config, f"{name}{len(made)}")
        made.append(dev)
        return dev

    yield factory
    for dev in made:
        dev.quit()


def test_a_scale_with_one_entry_per_axis_loads(make_stage):
    stage = make_stage(4, [1e-6, 1e-6, -1e-6, 1e-6])
    assert len(stage.getAxisScale()) == 4


def test_no_scale_at_all_still_loads(make_stage):
    # getAxisScale() defaults to 1 per axis, which is already the right length.
    stage = make_stage(3)
    assert len(stage.getAxisScale()) == 3


def test_a_scale_shorter_than_the_axes_is_refused(make_stage):
    with pytest.raises(ValueError) as exc:
        make_stage(4, [1e-9, 1e-9, -1e-9], name='ShortScale')
    message = str(exc.value)
    assert 'ShortScale' in message, "the message must name the device"
    assert '4' in message and '3' in message, "and both counts"
    assert 'scale' in message


def test_a_scale_longer_than_the_axes_is_refused(make_stage):
    with pytest.raises(ValueError) as exc:
        make_stage(3, [1e-6, 1e-6, 1e-6, 1e-6], name='LongScale')
    message = str(exc.value)
    assert 'LongScale' in message
    assert 'scale' in message
