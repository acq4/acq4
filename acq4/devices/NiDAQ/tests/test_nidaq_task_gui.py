"""NiDAQ task dock: saved states, including ones from before DAQ filtering was removed."""

import logging

import pytest

from acq4.devices.NiDAQ.taskGUI import NiDAQTask
from acq4.util import Qt


class _FakeTaskRunner(Qt.QObject):
    sigTaskSequenceStarted = Qt.Signal(object)
    sigTaskStarted = Qt.Signal(object)
    sigTaskFinished = Qt.Signal()
    sigTaskChanged = Qt.Signal(object, object)

    def getParam(self, name):
        assert name == 'duration'
        return 0.2


class _FakeManager:
    def listDevices(self):
        return []


class _FakeDev:
    dm = _FakeManager()

    def name(self):
        return 'DAQ'


OLD_STATE = {
    'rate': 50000.0,
    'downsample': 5,
    'triggerDevice': 'No Trigger',
    'denoiseMethod': 'Pointwise',
    'denoiseThreshold': 4.0,
    'denoiseWidth': 1,
    'filterMethod': 'Bessel',
    'besselCutoff': 2000.0,
    'besselOrder': 4,
    'besselBidirectional': True,
    'butterworthPassband': 20e3,
    'butterworthStopband': 40e3,
    'butterworthPassDB': 3.0,
    'butterworthStopDB': 40.0,
    'butterworthBidirectional': False,
}


@pytest.fixture
def gui(qtbot):
    runner = _FakeTaskRunner()
    gui = NiDAQTask(_FakeDev(), runner)
    qtbot.addWidget(gui)
    gui._runner = runner
    yield gui
    gui.quit()


def test_old_state_with_filter_keys_restores(gui, caplog):
    with caplog.at_level(logging.WARNING, logger='acq4'):
        gui.restoreState(dict(OLD_STATE))
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    cmd = gui.generateTask()
    assert cmd == {'rate': 50000.0, 'downsample': 5, 'numPts': 10000}
    assert set(gui.saveState()) == {'rate', 'downsample', 'triggerDevice'}


def test_generated_command_round_trips(gui):
    gui.restoreState({'rate': 20000.0, 'downsample': 2, 'triggerDevice': 'No Trigger'})
    assert gui.generateTask() == {'rate': 20000.0, 'downsample': 2, 'numPts': 4000}
    assert not any(hasattr(gui.ui, name) for name in ('filterCombo', 'denoiseCombo', 'besselCtrl'))
