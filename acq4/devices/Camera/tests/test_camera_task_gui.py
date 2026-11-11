"""Live image in the camera task dock, driven by hand-built partial results."""
import warnings

import numpy as np
import pytest

from acq4.devices.Camera.Camera import CameraTaskResult
from acq4.devices.Camera.taskGUI import CameraTaskGui
from acq4.devices.Camera.tests.camera_fakes import NORMAL, NPTS, FakeFuture, SyntheticDaq, makeFrames, makeTask
from acq4.util import Qt


class _FakeTaskRunner(Qt.QObject):
    sigTaskSequenceStarted = Qt.Signal(object)
    sigTaskStarted = Qt.Signal(object)
    sigTaskFinished = Qt.Signal()
    sigTaskPaused = Qt.Signal()

    def getDevice(self, name):
        return None


class _FakeCameraDev:
    _DGConfig = {'exposure': {'type': 'ai', 'units': 'V', 'device': 'DAQ', 'channel': '/Dev1/ai0'}}

    def name(self):
        return 'FakeCam'

    def getDAQName(self, ch):
        return 'DAQ'

    def listParams(self, params):
        return {'triggerMode': (['Normal', 'TriggerStart'], True, True, [])}


@pytest.fixture
def dock(qtbot):
    runner = _FakeTaskRunner()
    gui = CameraTaskGui(_FakeCameraDev(), runner)
    qtbot.addWidget(gui)
    gui._runner = runner  # keep alive; the channels hold weak references
    gui.ui.displayCheck.setChecked(True)
    yield gui
    gui.quit()


def _partial(nFrames, nSettledSamples=NPTS // 2):
    daq = SyntheticDaq(np.zeros(NPTS))
    future = FakeFuture(makeFrames(nFrames))
    task = makeTask(NORMAL, daq, future)
    daq.settle(nSettledSamples)
    return task, task.partialResult()


def _waitPainted(qtbot, gui):
    qtbot.waitUntil(
        lambda: not gui._liveImageRepaint.isPending() and not gui._partialRepaint.isPending(), timeout=1000
    )


def test_live_image_is_the_newest_settled_frame(qtbot, dock):
    task, res = _partial(3)
    dock.handlePartialResult(res, {})
    _waitPainted(qtbot, dock)
    np.testing.assert_array_equal(dock.ui.imageView.image, res.frames()[-1].data())

    # DAQ channels get their live curves from the DAQ part of the result
    chGui = dock.channels['exposure']
    x, y = chGui.liveCurve.getOriginalDataset()
    assert len(x) == NPTS // 2

    task._future.arrive(makeFrames(5)[3:])
    dock.handlePartialResult(task.partialResult(), {})
    _waitPainted(qtbot, dock)
    np.testing.assert_array_equal(dock.ui.imageView.image, res.frames()[4].data())


def test_no_live_image_when_display_is_off(qtbot, dock):
    dock.ui.displayCheck.setChecked(False)
    _, res = _partial(3)
    dock.handlePartialResult(res, {})
    _waitPainted(qtbot, dock)
    assert dock.ui.imageView.image is None


def test_no_live_image_without_settled_frames(qtbot, dock):
    _, res = _partial(0)
    dock.handlePartialResult(res, {})
    assert not dock._liveImageRepaint.isPending()


def _recordSetImage(monkeypatch, gui):
    # MetaArray lacks .size, which this pyqtgraph's ImageView.setImage requires; record the calls instead
    calls = []
    monkeypatch.setattr(gui.ui.imageView, 'setImage', lambda img, **kw: calls.append((img, kw)))
    return calls


def test_final_result_cancels_pending_live_image(qtbot, dock, monkeypatch):
    calls = _recordSetImage(monkeypatch, dock)
    task, res = _partial(3)
    dock.handlePartialResult(res, {})
    # a second partial before the event loop runs replaces the first
    task._future.arrive(makeFrames(4)[3:])
    dock.handlePartialResult(task.partialResult(), {})
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        final = task.getResult()
        dock.handleResult(final, {})
    assert not dock._liveImageRepaint.isPending() and not dock._partialRepaint.isPending()
    qtbot.wait(150)
    assert len(calls) == 1
    img, kw = calls[0]
    assert img is final.asArray() and list(kw) == ['xvals']
    assert np.array_equal(kw['xvals'], final.frameTimes()[0][:len(img)])


def test_final_result_display_unchanged(qtbot, dock, monkeypatch):
    calls = _recordSetImage(monkeypatch, dock)
    final = CameraTaskResult(makeTask(NORMAL), makeFrames(3), None)
    dock.handleResult(final, {})
    assert len(calls) == 1 and calls[0][0] is final.asArray()
    assert np.array_equal(calls[0][1]['xvals'], final.frameTimes()[0])
