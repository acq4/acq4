"""Live primary-signal curve in the MultiClamp task dock, driven by hand-built partial results."""

import numpy as np
import pytest

from acq4.devices.MultiClamp.taskGUI import MultiClampTaskGui
from acq4.util import Qt
from acq4.util.partial_results import TaskResultArray

N = 1000
RATE = 10e3


class _FakeDaqGui(Qt.QObject):
    sigChanged = Qt.Signal(object)

    def currentState(self):
        return {'rate': RATE, 'numPts': N}


class _FakeTaskRunner(Qt.QObject):
    sigTaskSequenceStarted = Qt.Signal(object)
    sigTaskStarted = Qt.Signal(object)
    sigTaskFinished = Qt.Signal()

    def __init__(self):
        Qt.QObject.__init__(self)
        self.daqGui = _FakeDaqGui()

    def getDevice(self, name):
        return self.daqGui


class _FakeClamp(Qt.QObject):
    sigStateChanged = Qt.Signal(object)
    sigHoldingChanged = Qt.Signal(object, object)

    def name(self):
        return 'FakeClamp'

    def getDAQName(self, channel):
        return 'DAQ'

    def listSignals(self, mode):
        return (['MembranePotential'], ['MembraneCurrent'])

    def getLastState(self, mode):
        return {
            'holding': 0.0, 'primaryGain': 1, 'secondaryGain': 1,
            'primarySignal': 'MembranePotential', 'secondarySignal': 'MembraneCurrent',
        }


def _makeResult(seed=0):
    rng = np.random.default_rng(seed)
    cols = ['primary', 'secondary', 'command']
    info = [
        {'name': 'Channel', 'cols': [{'name': c} for c in cols]},
        {'name': 'Time', 'units': 's', 'values': np.arange(N) / RATE},
        {'ClampState': {}, 'DAQ': {}},
    ]
    result = TaskResultArray(rng.normal(size=(3, N)), info=info)
    result._initSettlement(['primary', 'secondary', 'command'])
    return result


@pytest.fixture
def dock(qtbot):
    runner = _FakeTaskRunner()
    dev = _FakeClamp()
    gui = MultiClampTaskGui(dev, runner)
    qtbot.addWidget(gui)
    gui._fakes = (runner, dev)
    yield gui
    gui.quit()


def _curves(gui):
    return gui.ui.topPlotWidget.getPlotItem().listDataItems()


def _waitPainted(qtbot, gui):
    qtbot.waitUntil(lambda: not gui._partialRepaint.isPending(), timeout=1000)


def test_live_curve_shows_settled_primary_prefix(qtbot, dock):
    result = _makeResult()
    result._setSettled('primary', 250)
    result._setSettled('secondary', 900)
    dock.handlePartialResult(result, {})
    result._setSettled('primary', 300)  # read at paint time
    _waitPainted(qtbot, dock)

    assert _curves(dock) == [dock.liveCurve]
    x, y = dock.liveCurve.getOriginalDataset()
    np.testing.assert_array_equal(x, result.xvals('Time')[:300])
    np.testing.assert_array_equal(y, result['primary'].view(np.ndarray)[:300])
    assert dock.liveCurve.opts['autoDownsample'] is True
    assert dock.liveCurve.opts['downsampleMethod'] == 'peak'
    assert dock.liveCurve.opts['clipToView'] is True


def test_final_replaces_live_curve_and_cancels_pending(qtbot, dock):
    result = _makeResult()
    result._setSettled('primary', 100)
    dock.handlePartialResult(result, {})
    _waitPainted(qtbot, dock)
    result._setSettled('primary', 200)
    dock.handlePartialResult(result, {})  # still pending when the final arrives
    dock.handleResult(result, {})
    qtbot.wait(150)

    assert dock.liveCurve is None
    curves = _curves(dock)
    assert len(curves) == 1
    np.testing.assert_array_equal(curves[0].getOriginalDataset()[1], result['primary'].view(np.ndarray))


def test_reset_inp_plots_honoured(qtbot, dock):
    dock.handleResult(_makeResult(seed=1), {})
    assert len(_curves(dock)) == 1

    dock.taskSequenceStarted()
    for run in range(2):
        result = _makeResult(seed=10 + run)
        result._setSettled('primary', 100)
        dock.handlePartialResult(result, {})
        _waitPainted(qtbot, dock)
        assert len(_curves(dock)) == run + 1
        dock.handleResult(result, {})
        assert len(_curves(dock)) == run + 1
