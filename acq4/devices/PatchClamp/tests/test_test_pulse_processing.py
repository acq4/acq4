"""Tests for TestPulseThread._processTestPulses: the analysis fit is forced on the
processing thread before any consumer of sigTestPulseAnalyzed can see the pulse."""
import logging
import queue
import threading
from types import SimpleNamespace

import pytest

from acq4.devices.PatchClamp import testpulse
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _RecordingPulse:
    """Appends ("analysis", <thread>) to a shared list on every analysis read."""

    def __init__(self, events, analysis=None):
        self._events = events
        self._analysis = {} if analysis is None else analysis

    @property
    def analysis(self):
        self._events.append(("analysis", threading.current_thread()))
        return self._analysis


def _processingThreadFor(pulses, postProcessing=None):
    """A bare TestPulseThread with just what _processTestPulses touches, as
    test_auto_bias does for updateAutoBias."""
    thread = testpulse.TestPulseThread.__new__(testpulse.TestPulseThread)
    Qt.QThread.__init__(thread)
    thread._params = {"postProcessing": postProcessing}
    thread._clampDev = SimpleNamespace(logger=logging.getLogger(__name__), name=lambda: "Clamp1")
    thread._testPulsesToProcess = queue.Queue()
    for tp in pulses:
        thread._testPulsesToProcess.put(tp)
    thread._testPulsesToProcess.put(None)
    return thread


def _drain(thread):
    """Run the processing loop to completion on its own thread, as start() does."""
    worker = threading.Thread(target=thread._processTestPulses, name="TestPulseProcessing(test)")
    worker.start()
    worker.join(10)
    assert not worker.is_alive()
    return worker


def test_analysis_is_forced_before_the_signal_and_off_the_calling_thread(qapp):
    """Every downstream reader -- the log writer thread, the GUI and the state
    machine -- gets a pulse whose analysis is already cached, so none of them
    enters PatchClampTestPulse's unsynchronised lazy _analyze()."""
    events = []
    caller = threading.current_thread()
    thread = _processingThreadFor([_RecordingPulse(events)])
    thread.sigTestPulseAnalyzed.connect(
        lambda dev, tp: events.append(("emit", threading.current_thread())),
        Qt.Qt.DirectConnection,
    )

    worker = _drain(thread)

    assert [step for step, _ in events] == ["analysis", "emit"]
    assert {thread_ for _, thread_ in events} == {worker}
    assert worker is not caller


def test_a_failing_analysis_is_logged_and_the_pulse_is_still_emitted(qapp, caplog):
    class _Unanalysable:
        @property
        def analysis(self):
            raise ValueError("fit did not converge")

    pulse = _Unanalysable()
    emitted = []
    thread = _processingThreadFor([pulse])
    thread.sigTestPulseAnalyzed.connect(
        lambda dev, tp: emitted.append(tp), Qt.Qt.DirectConnection
    )

    with caplog.at_level(logging.ERROR):
        _drain(thread)

    assert emitted == [pulse]
    assert "Error calculating test pulse analysis" in caplog.text


def test_post_processing_runs_after_the_analysis_is_forced(qapp):
    events = []
    original = _RecordingPulse(events)
    replacement = _RecordingPulse(events)
    seen = []

    def postProcessing(tp):
        seen.append((tp, list(events)))
        return replacement

    thread = _processingThreadFor([original], postProcessing=postProcessing)
    emitted = []
    thread.sigTestPulseAnalyzed.connect(
        lambda dev, tp: emitted.append(tp), Qt.Qt.DirectConnection
    )

    _drain(thread)

    assert emitted == [replacement]
    (seenPulse, eventsBefore) = seen[0]
    assert seenPulse is original
    assert [step for step, _ in eventsBefore] == ["analysis"]
