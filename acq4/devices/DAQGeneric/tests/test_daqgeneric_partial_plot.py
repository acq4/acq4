"""Live curves in the DAQGeneric task dock, driven by hand-built partial results."""

import numpy as np
import pytest

from acq4.devices.DAQGeneric.taskGUI import DAQGenericTaskGui
from acq4.util import Qt
from acq4.util.partial_results import TaskResultArray

N = 1000
RATE = 10e3


class _FakeTaskRunner(Qt.QObject):
    sigTaskSequenceStarted = Qt.Signal(object)
    sigTaskStarted = Qt.Signal(object)
    sigTaskFinished = Qt.Signal()

    def getDevice(self, name):
        return None


class _FakeDev:
    def __init__(self, config):
        self._DGConfig = config

    def name(self):
        return 'FakeDAQGeneric'

    def getDAQName(self, ch):
        return 'DAQ'


def _makeResult(channels, seed=0):
    rng = np.random.default_rng(seed)
    data = rng.normal(size=(len(channels), N))
    info = [
        {'name': 'Channel', 'cols': [{'name': ch, 'units': 'V'} for ch in channels]},
        {'name': 'Time', 'units': 's', 'values': np.arange(N) / RATE},
        {'DAQ': {}},
    ]
    result = TaskResultArray(data, info=info)
    result._initSettlement(channels)
    return result


def _curves(chGui):
    return chGui.plot.getPlotItem().listDataItems()


@pytest.fixture
def dock(qtbot):
    runner = _FakeTaskRunner()
    dev = _FakeDev({'In0': {'type': 'ai', 'units': 'V'}, 'In1': {'type': 'ai', 'units': 'V'}})
    gui = DAQGenericTaskGui(dev, runner)
    qtbot.addWidget(gui)
    gui._runner = runner  # keep alive; the channels hold weak references
    yield gui
    gui.quit()


def _waitPainted(qtbot, gui):
    qtbot.waitUntil(lambda: not gui._partialRepaint.isPending(), timeout=1000)


def test_live_curve_shows_settled_prefix(qtbot, dock):
    result = _makeResult(['In0', 'In1'])
    result._setSettled('In0', 100)
    result._setSettled('In1', 40)
    dock.handlePartialResult(result, {})
    _waitPainted(qtbot, dock)

    for ch, n in [('In0', 100), ('In1', 40)]:
        chGui = dock.channels[ch]
        assert _curves(chGui) == [chGui.liveCurve]
        x, y = chGui.liveCurve.getOriginalDataset()
        np.testing.assert_array_equal(x, result.xvals('Time')[:n])
        np.testing.assert_array_equal(y, result[ch].view(np.ndarray)[:n])


def test_settlement_read_at_paint_time(qtbot, dock):
    result = _makeResult(['In0', 'In1'])
    result._setSettled('In0', 100)
    dock.handlePartialResult(result, {})
    result._setSettled('In0', 300)  # advances before the coalesced repaint runs
    _waitPainted(qtbot, dock)
    x, y = dock.channels['In0'].liveCurve.getOriginalDataset()
    assert len(y) == 300


def test_live_curve_updates_in_place_then_final_replaces_it(qtbot, dock):
    result = _makeResult(['In0', 'In1'])
    chGui = dock.channels['In0']
    for n in (100, 500, 900):
        result._setSettled('In0', n)
        dock.handlePartialResult(result, {})
        _waitPainted(qtbot, dock)
        assert _curves(chGui) == [chGui.liveCurve]
        assert len(chGui.liveCurve.getOriginalDataset()[1]) == n
    assert chGui.liveCurve.opts['autoDownsample'] is True
    assert chGui.liveCurve.opts['downsampleMethod'] == 'peak'
    assert chGui.liveCurve.opts['clipToView'] is True

    result._setSettled('In0', N)
    result._setComplete()
    dock.handleResult(result, {})
    assert chGui.liveCurve is None
    curves = _curves(chGui)
    assert len(curves) == 1
    np.testing.assert_array_equal(curves[0].getOriginalDataset()[1], result['In0'].view(np.ndarray))


def test_final_cancels_pending_partial_repaint(qtbot, dock):
    result = _makeResult(['In0', 'In1'])
    result._setSettled('In0', 100)
    dock.handlePartialResult(result, {})
    assert dock._partialRepaint.isPending()
    dock.handleResult(result, {})
    assert not dock._partialRepaint.isPending()
    qtbot.wait(150)
    chGui = dock.channels['In0']
    assert chGui.liveCurve is None
    assert len(_curves(chGui)) == 1


def test_sequence_overlays(qtbot, dock):
    chGui = dock.channels['In0']
    old = _makeResult(['In0', 'In1'], seed=1)
    dock.handleResult(old, {})
    assert len(_curves(chGui)) == 1

    dock.taskSequenceStarted()
    for run in range(2):
        result = _makeResult(['In0', 'In1'], seed=10 + run)
        result._setSettled('In0', 200)
        dock.handlePartialResult(result, {})
        _waitPainted(qtbot, dock)
        # first partial of the sequence cleared the earlier plot; later runs overlay
        assert len(_curves(chGui)) == run + 1
        assert chGui.liveCurve in _curves(chGui)
        dock.handleResult(result, {})
        assert len(_curves(chGui)) == run + 1
        assert chGui.liveCurve is None

    dock.taskSequenceStarted()
    result = _makeResult(['In0', 'In1'], seed=20)
    result._setSettled('In0', 200)
    dock.handlePartialResult(result, {})
    _waitPainted(qtbot, dock)
    assert _curves(chGui) == [chGui.liveCurve]


def test_display_check_off_skips_live_curve(qtbot, dock):
    chGui = dock.channels['In0']
    chGui.ui.displayCheck.setChecked(False)
    result = _makeResult(['In0', 'In1'])
    result._setSettled('In0', 100)
    dock.handlePartialResult(result, {})
    _waitPainted(qtbot, dock)
    assert chGui.liveCurve is None
    assert _curves(chGui) == []
    assert dock.channels['In1'].liveCurve is not None


def test_channel_missing_from_result_is_skipped(qtbot, dock):
    result = _makeResult(['In0'])
    result._setSettled('In0', 100)
    dock.handlePartialResult(result, {})
    _waitPainted(qtbot, dock)
    assert dock.channels['In0'].liveCurve is not None
    assert dock.channels['In1'].liveCurve is None


def test_many_partials_bounded_repaints(qtbot, dock, monkeypatch):
    chGui = dock.channels['In0']
    paints = []
    original = type(chGui).handlePartialResult

    def counting(self, result, nSettled, params):
        paints.append(nSettled)
        return original(self, result, nSettled, params)

    monkeypatch.setattr(type(chGui), 'handlePartialResult', counting)
    result = _makeResult(['In0'])
    for n in range(1, 201):
        result._setSettled('In0', n)
        dock.handlePartialResult(result, {})
    _waitPainted(qtbot, dock)
    qtbot.wait(100)
    assert paints == [200]
