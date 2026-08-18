import numpy as np

from acq4.filetypes.MultiPatchLog import IrregularTimeSeries


def test_timeseries_index():
    
    ts1 = [
        (10, 0.5),
        (12, 13.4),
        (29.8, 5),
        (29.8, 5.5),
        (29.9, 6),
        (30.0, 7),
        (30.1, 8),
        (35, 0),
    ]
    
    ts2 = [
        (10, (0.5, 13.4)),
        (12, (13.4, 5)),
        (29.8, (5, 0)),
        (29.9, (6, -102.7)),
        (30.0, (7, 23.)),
        (30.0, (7, 24.)),
        (30.1, (8, 0)),
        (35, (0, 0)),
    ]
    
    ts3 = [
        (10, 'a'),
        (12, 'b'),
        (29.8, 'c'),
        (29.9, 'd'),
        (30.0, 'e'),
        (30.1, 'f'),
        (30.1, 'g'),
        (35, 'h'),
    ]
    
    def lookup(t, ts):
        # inefficient (but easier to test) method for doing timeseries lookup
        # for comparison
        low = None
        for i,ev in enumerate(ts.events):
            if ev[0] <= t:
                low = i
            else:
                break
        if low is None:
            return None
        if low+1 >= len(ts.events) or ts.interpolate is False:
            return ts.events[low][1]
        else:
            t1, v1 = ts.events[low]
            t2, v2 = ts.events[low+1]
            return ts._interpolate(t, v1, v2, t1, t2)
        
    for tsdata in (ts1, ts2, ts3):
        for interp in (True, False):
            if interp and isinstance(tsdata[0][1], str):
                # don't test interpolation on strings
                continue
            for res in (0.1, 1.0, 10.0):
                ts = IrregularTimeSeries(interpolate=interp, resolution=res)
                for t,v in tsdata:
                    ts[t] = v
                for t in np.arange(-1, 40, 0.05):
                    assert ts[t] == lookup(t, ts)
    

"""Also: the record-button toggles map onto one MultiPatchLogRecorder, whose
options are what the two independent buttons switch."""
import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _RecorderSpy:
    """Stands in for MultiPatchLogRecorder so the toggle mapping can be tested
    without a Manager, real devices, or a storage directory."""

    instances = []

    def __init__(self, directory, pipettes=(), microscope=None,
                 record_full_test_pulses=True, write_events=True, initial_records=()):
        self.directory = directory
        self.pipettes = list(pipettes)
        self.microscope = microscope
        self.record_full_test_pulses = record_full_test_pulses
        self.write_events = write_events
        self.initial_records = list(initial_records)
        self.records = []
        self.stopped = False
        _RecorderSpy.instances.append(self)

    def record(self, event):
        self.records.append(event)

    def setRecordFullTestPulses(self, record):
        self.record_full_test_pulses = bool(record)

    def recordsFullTestPulses(self):
        return self.record_full_test_pulses

    def stop(self):
        self.stopped = True


@pytest.fixture
def spy(monkeypatch):
    import acq4.modules.MultiPatch.multipatch as mp

    _RecorderSpy.instances = []
    monkeypatch.setattr(mp, "MultiPatchLogRecorder", _RecorderSpy)
    return _RecorderSpy


def test_write_records_is_gone():
    # Its whole job moved into the recorder; leaving it would be a second
    # implementation of the format to drift from the first.
    from acq4.modules.MultiPatch.multipatch import MultiPatchWindow

    assert not hasattr(MultiPatchWindow, "writeRecords")


def test_reset_history_still_resets_the_clamp_history():
    # resetHistory is MultiPatch's Reset button, deliberately NOT moved into the
    # recorder: a recorder that reset device state would let one module wipe the
    # history another is plotting.
    import inspect

    from acq4.modules.MultiPatch.multipatch import MultiPatchWindow

    source = inspect.getsource(MultiPatchWindow.resetHistory)
    assert "resetTestPulseHistory" in source


def test_the_recorder_never_resets_device_state():
    import inspect

    from acq4.util import multipatch_log_recorder

    source = inspect.getsource(multipatch_log_recorder)
    assert "resetTestPulseHistory" not in source


class _FakeToggleButton:
    """One of the window's two record buttons, reduced to the checked state
    _syncRecorder reads off it."""

    def __init__(self, checked=False):
        self._checked = bool(checked)

    def isChecked(self):
        return self._checked

    def setChecked(self, checked):
        self._checked = bool(checked)


class _StandInWindow:
    """The parts of MultiPatchWindow that _syncRecorder touches.

    Instantiating the real window needs a Manager and real patch-pipette
    devices, which no fixture in this repo provides, so the recorder mapping is
    exercised against this instead and the method under test is the real one.
    """

    def __init__(self, directory, recording=False, recordingTestPulses=False):
        self.ui = _StandInUi(recording, recordingTestPulses)
        self.pips = []
        self.microscope = None
        self.eventHistory = []
        self._recorder = None
        self.resetCount = 0

    def resetHistory(self):
        """The real one also resets clamp test-pulse history and clears the
        pipette controls' event logs, both of which need real devices."""
        self.eventHistory = []
        self.resetCount += 1

    def _syncRecorder(self, *args, **kwargs):
        return self._call("_syncRecorder", *args, **kwargs)

    def recordEvent(self, *args, **kwargs):
        return self._call("recordEvent", *args, **kwargs)

    def _rememberEvent(self, *args, **kwargs):
        return self._call("_rememberEvent", *args, **kwargs)

    def pipetteEvent(self, *args, **kwargs):
        return self._call("pipetteEvent", *args, **kwargs)

    def surfaceDepthChanged(self, *args, **kwargs):
        return self._call("surfaceDepthChanged", *args, **kwargs)

    def _call(self, name, *args, **kwargs):
        from acq4.modules.MultiPatch.multipatch import MultiPatchWindow

        return getattr(MultiPatchWindow, name)(self, *args, **kwargs)


class _StandInUi:
    def __init__(self, recording, recordingTestPulses):
        self.recordBtn = _FakeToggleButton(recording)
        self.recordTestPulsesBtn = _FakeToggleButton(recordingTestPulses)


@pytest.fixture
def storageDir(monkeypatch):
    """The current storage directory _syncRecorder hands the recorder. Returned
    as a sentinel so tests can assert it reached the recorder unchanged."""
    import acq4.modules.MultiPatch.multipatch as mp

    directory = object()

    class _DirectoryOnlyManager:
        def getCurrentDir(self):
            return directory

    monkeypatch.setattr(mp, "getManager", _DirectoryOnlyManager)
    return directory


def test_no_recorder_while_both_buttons_are_off(spy, storageDir):
    win = _StandInWindow(storageDir)

    win._syncRecorder(writeEvents=False, recordTestPulses=False, replayHistory=False)

    assert win._recorder is None
    assert spy.instances == []


def test_event_log_button_alone_records_events_only(spy, storageDir):
    win = _StandInWindow(storageDir, recording=True)

    win._syncRecorder(writeEvents=True, recordTestPulses=False, replayHistory=True)

    assert win._recorder is spy.instances[-1]
    assert win._recorder.directory is storageDir
    assert win._recorder.write_events is True
    assert win._recorder.record_full_test_pulses is False


def test_test_pulse_button_alone_records_pulses_without_an_event_log(spy, storageDir):
    win = _StandInWindow(storageDir, recordingTestPulses=True)

    win._syncRecorder(writeEvents=False, recordTestPulses=True, replayHistory=False)

    assert win._recorder is spy.instances[-1]
    assert win._recorder.write_events is False
    assert win._recorder.record_full_test_pulses is True


def test_both_buttons_record_events_and_full_test_pulses(spy, storageDir):
    win = _StandInWindow(storageDir, recording=True, recordingTestPulses=True)

    win._syncRecorder(writeEvents=True, recordTestPulses=True, replayHistory=True)

    assert len(spy.instances) == 1
    assert win._recorder.write_events is True
    assert win._recorder.record_full_test_pulses is True


def test_toggling_test_pulses_mid_session_adjusts_the_live_recorder(spy, storageDir):
    # A second instance here would mean a second log file for one session.
    win = _StandInWindow(storageDir, recording=True)
    win._syncRecorder(writeEvents=True, recordTestPulses=False, replayHistory=True)
    recorder = win._recorder

    win._syncRecorder(writeEvents=True, recordTestPulses=True, replayHistory=False)

    assert win._recorder is recorder
    assert len(spy.instances) == 1
    assert recorder.stopped is False
    assert recorder.record_full_test_pulses is True

    win._syncRecorder(writeEvents=True, recordTestPulses=False, replayHistory=False)

    assert win._recorder is recorder
    assert len(spy.instances) == 1
    assert recorder.record_full_test_pulses is False


def test_turning_both_buttons_off_stops_the_recorder(spy, storageDir):
    win = _StandInWindow(storageDir, recording=True)
    win._syncRecorder(writeEvents=True, recordTestPulses=False, replayHistory=True)
    recorder = win._recorder

    win._syncRecorder(writeEvents=False, recordTestPulses=False, replayHistory=False)

    assert win._recorder is None
    assert recorder.stopped is True


def test_turning_the_event_log_off_leaves_test_pulses_recording(spy, storageDir):
    win = _StandInWindow(storageDir, recording=True, recordingTestPulses=True)
    win._syncRecorder(writeEvents=True, recordTestPulses=True, replayHistory=True)
    first = win._recorder

    win._syncRecorder(writeEvents=False, recordTestPulses=True, replayHistory=False)

    assert first.stopped is True
    assert win._recorder is not first
    assert win._recorder.write_events is False
    assert win._recorder.record_full_test_pulses is True


def test_starting_the_event_log_replays_the_in_memory_history(spy, storageDir):
    win = _StandInWindow(storageDir, recording=True)
    win.eventHistory = [{"event": "state_change", "device": "Pipette1"}]

    win._syncRecorder(writeEvents=True, recordTestPulses=False, replayHistory=True)

    assert win._recorder.initial_records == win.eventHistory


def test_test_pulse_toggle_does_not_replay_the_history_into_a_new_recorder(spy, storageDir):
    # The event log is off here, so the history has not been written anywhere;
    # replaying it into the test-pulse-only recorder would be the first time
    # these events were ever recorded, out of order with the live stream.
    win = _StandInWindow(storageDir, recordingTestPulses=True)
    win.eventHistory = [{"event": "state_change", "device": "Pipette1"}]

    win._syncRecorder(writeEvents=False, recordTestPulses=True, replayHistory=False)

    assert win._recorder.initial_records == []


class _StandInMicroscope:
    def name(self):
        return "Microscope"


def test_window_originated_events_reach_the_recorder(spy, storageDir):
    win = _StandInWindow(storageDir, recording=True)
    win._syncRecorder(writeEvents=True, recordTestPulses=False, replayHistory=True)
    event = {"device": None, "event": "global patch profiles changed", "profile": "{}"}

    win.recordEvent(event)

    assert win._recorder.records == [event]
    assert win.eventHistory == [event]


def test_pipette_events_are_not_handed_to_the_recorder(spy, storageDir):
    # The recorder subscribes to sigNewEvent itself, so handing it the event
    # here as well would write every pipette event twice.
    win = _StandInWindow(storageDir, recording=True)
    win._syncRecorder(writeEvents=True, recordTestPulses=True, replayHistory=True)

    win.pipetteEvent(object(), {"device": "Pipette1", "event": "state_change", "state": "bath"})

    assert win._recorder.records == []
    assert [e["event"] for e in win.eventHistory] == ["state_change"]


def test_surface_depth_changes_are_not_handed_to_the_recorder(spy, storageDir):
    # Same reason: _syncRecorder gives the recorder the microscope, so the
    # recorder is already subscribed to sigSurfaceDepthChanged.
    win = _StandInWindow(storageDir, recording=True)
    win.microscope = _StandInMicroscope()
    win._syncRecorder(writeEvents=True, recordTestPulses=False, replayHistory=True)

    win.surfaceDepthChanged(-1e-3)

    assert win._recorder.records == []
    assert [e["event"] for e in win.eventHistory] == ["surface_depth_changed"]
    assert win.eventHistory[0]["surface_depth"] == -1e-3


def test_the_recorder_is_given_the_microscope(spy, storageDir):
    win = _StandInWindow(storageDir, recording=True)
    win.microscope = _StandInMicroscope()

    win._syncRecorder(writeEvents=True, recordTestPulses=False, replayHistory=True)

    assert win._recorder.microscope is win.microscope


def test_the_in_memory_history_never_holds_a_full_test_pulse(spy, storageDir):
    # The history is replayed into a freshly opened log, where a whole test
    # pulse recording is neither serializable nor wanted.
    win = _StandInWindow(storageDir, recordingTestPulses=True)
    win._syncRecorder(writeEvents=False, recordTestPulses=True, replayHistory=False)

    win.pipetteEvent(
        object(),
        {"device": "Pipette1", "event": "test_pulse", "full_test_pulse": object()},
    )

    assert "full_test_pulse" not in win.eventHistory[0]


def test_events_arriving_with_no_recorder_still_reach_the_history(spy, storageDir):
    win = _StandInWindow(storageDir)

    win.recordEvent({"device": None, "event": "global patch profiles changed"})
    win.pipetteEvent(object(), {"device": "Pipette1", "event": "state_change"})

    assert win._recorder is None
    assert len(win.eventHistory) == 2
