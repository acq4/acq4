"""Tests for the test_pulse event PatchPipette emits for each finished test pulse."""
import threading

from acq4.devices.PatchPipette.patchpipette import PatchPipette
from acq4.util import Qt


class _Pip(Qt.QObject):
    """Runs PatchPipette's event methods without a Manager or devices."""

    sigNewEvent = Qt.Signal(object, object)

    _testPulseFinished = PatchPipette._testPulseFinished
    emitNewEvent = PatchPipette.emitNewEvent
    eventLog = PatchPipette.eventLog

    def __init__(self):
        super().__init__()
        self._logEvents = []
        self._logLock = threading.RLock()

    def name(self):
        return "Pipette1"


class _TestPulse:
    analysis = {"steady_state_resistance": 1e9, "start_time": 1000.0}


def test_a_test_pulse_event_carries_only_the_test_pulse_object():
    pip = _Pip()
    events = []
    pip.sigNewEvent.connect(lambda _pip, event: events.append(event), Qt.Qt.DirectConnection)
    tp = _TestPulse()

    pip._testPulseFinished(object(), tp)

    (event,) = events
    assert set(event) == {"device", "event_time", "event", "test_pulse"}
    assert event["device"] == "Pipette1"
    assert event["event"] == "test_pulse"
    assert event["test_pulse"] is tp


def test_test_pulse_events_are_not_kept_in_the_pipettes_event_log():
    pip = _Pip()

    pip._testPulseFinished(object(), _TestPulse())

    assert pip.eventLog() == []
