import json

import numpy as np
import pytest

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


# The rest of this module covers the two record buttons, which drive one writer.


class _WriterSpy:
    """Stands in for MultiPatchLogWriter."""

    instances = []

    def __init__(self, directory, pipettes=(), microscope=None, initial_records=(), full_test_pulse_pipettes=()):
        self.directory = directory
        self.pipettes = list(pipettes)
        self.microscope = microscope
        self.initial_records = list(initial_records)
        self.fullTestPulsePipettes = list(full_test_pulse_pipettes)
        self.fullTestPulseHistory = []
        self.records = []
        self.started = False
        self.stopped = False
        type(self).instances.append(self)

    def start(self):
        self.started = True
        return self

    def record(self, event):
        self.records.append(event)

    def setFullTestPulsePipettes(self, pipettes):
        self.fullTestPulsePipettes = list(pipettes)
        self.fullTestPulseHistory.append(list(pipettes))

    def stop(self):
        self.stopped = True


@pytest.fixture
def spy(monkeypatch):
    import acq4.modules.MultiPatch.multipatch as mp

    _WriterSpy.instances = []
    monkeypatch.setattr(mp, "MultiPatchLogWriter", _WriterSpy)
    return _WriterSpy


def test_write_records_is_gone():
    from acq4.modules.MultiPatch.multipatch import MultiPatchWindow

    assert not hasattr(MultiPatchWindow, "writeRecords")


def test_reset_history_still_resets_the_clamp_history():
    # Reset is MultiPatch's job, not the writer's.
    import inspect

    from acq4.modules.MultiPatch.multipatch import MultiPatchWindow

    source = inspect.getsource(MultiPatchWindow.resetHistory)
    assert "resetTestPulseHistory" in source


def test_the_writer_never_resets_device_state():
    import inspect

    from acq4.util import multipatch_log_recorder

    source = inspect.getsource(multipatch_log_recorder)
    assert "resetTestPulseHistory" not in source


class _FakeToggleButton:
    def __init__(self, checked=False):
        self._checked = bool(checked)
        self._enabled = True

    def isChecked(self):
        return self._checked

    def setChecked(self, checked):
        self._checked = bool(checked)

    def isEnabled(self):
        return self._enabled

    def setEnabled(self, enabled):
        self._enabled = bool(enabled)


class _StandInWindow:
    """The parts of MultiPatchWindow that the record buttons touch; any other
    attribute resolves to the real MultiPatchWindow method, bound to this."""

    def __init__(self, directory):
        self.ui = _StandInUi()
        self.pips = []
        self.selected = []
        self.microscope = None
        self.eventHistory = []
        self._logWriter = None
        self.resetCount = 0

    def selectedPipettes(self):
        return list(self.selected)

    def resetHistory(self):
        self.eventHistory = []
        self.resetCount += 1

    def __getattr__(self, name):
        from acq4.modules.MultiPatch.multipatch import MultiPatchWindow

        method = getattr(MultiPatchWindow, name)
        return lambda *args, **kwargs: method(self, *args, **kwargs)


class _StandInUi:
    def __init__(self):
        self.recordBtn = _FakeToggleButton()
        self.recordTestPulsesBtn = _FakeToggleButton()
        # As MultiPatchWindow.__init__ leaves it with "record" off.
        self.recordTestPulsesBtn.setEnabled(False)


@pytest.fixture
def storageDir(monkeypatch):
    import acq4.modules.MultiPatch.multipatch as mp

    directory = object()

    class _DirectoryOnlyManager:
        def getCurrentDir(self):
            return directory

    monkeypatch.setattr(mp, "getManager", _DirectoryOnlyManager)
    return directory


@pytest.fixture
def profiles(monkeypatch):
    import acq4.modules.MultiPatch.multipatch as mp

    values = {"default": {"bath": {"testPulseEnabled": True}}}

    class _Parameters:
        def getValues(self):
            return values

    class _StandInStateManager:
        @staticmethod
        def buildPatchProfilesParameters():
            return _Parameters()

    monkeypatch.setattr(mp, "PatchPipetteStateManager", _StandInStateManager)
    return values


class _StandInPipette:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


@pytest.fixture
def pipetteClass(monkeypatch):
    import acq4.modules.MultiPatch.multipatch as mp

    monkeypatch.setattr(mp, "PatchPipette", _StandInPipette)
    return _StandInPipette


def _press(win, button, checked):
    """Set a record button and call its toggled() handler, as Qt would."""
    if button == "events":
        win.ui.recordBtn.setChecked(checked)
        win.recordToggled(checked)
    else:
        win.ui.recordTestPulsesBtn.setChecked(checked)
        win.recordTestPulsesToggled(checked)


@pytest.fixture
def win(spy, storageDir, profiles, pipetteClass):
    win = _StandInWindow(storageDir)
    win.pips = [_StandInPipette("Pipette1"), _StandInPipette("Pipette2"), object()]
    win.selected = win.pips[:1]
    return win


def test_the_test_pulse_button_is_enabled_only_while_events_record(win):
    assert not win.ui.recordTestPulsesBtn.isEnabled()

    _press(win, "events", True)
    assert win.ui.recordTestPulsesBtn.isEnabled()

    _press(win, "events", False)
    assert not win.ui.recordTestPulsesBtn.isEnabled()


def test_the_test_pulse_button_alone_starts_nothing(win, spy):
    _press(win, "pulses", True)
    _press(win, "pulses", False)

    assert spy.instances == []
    assert win._logWriter is None


@pytest.mark.parametrize("pulses", [False, True])
def test_the_record_button_starts_one_writer_with_raw_capture_per_the_other_button(win, spy, storageDir, pulses):
    if pulses:
        _press(win, "pulses", True)  # ignored until events record

    _press(win, "events", True)

    (writer,) = spy.instances
    assert win._logWriter is writer
    assert writer.started and not writer.stopped
    assert writer.directory is storageDir
    assert writer.fullTestPulsePipettes == (win.pips[:1] if pulses else [])


def test_the_test_pulse_button_toggles_raw_capture_on_the_live_writer(win, spy):
    _press(win, "events", True)
    writer = win._logWriter

    _press(win, "pulses", True)
    _press(win, "pulses", False)
    _press(win, "pulses", True)

    assert spy.instances == [writer] and not writer.stopped
    assert writer.fullTestPulseHistory == [win.pips[:1], [], win.pips[:1]]


def test_raw_capture_is_scoped_to_the_pipettes_selected_when_it_starts(win):
    _press(win, "events", True)
    _press(win, "pulses", True)

    win.selected = win.pips[1:2]

    assert win._logWriter.fullTestPulsePipettes == win.pips[:1]


def test_the_record_button_off_stops_the_writer_and_back_on_starts_a_new_one(win, spy):
    _press(win, "events", True)
    _press(win, "pulses", True)
    first = win._logWriter

    _press(win, "events", False)

    assert first.stopped and win._logWriter is None

    _press(win, "events", True)

    second = win._logWriter
    assert spy.instances == [first, second]
    assert second.fullTestPulsePipettes == win.pips[:1]


def test_stop_recording_stops_the_writer(win):
    _press(win, "events", True)
    writer = win._logWriter

    win.stopRecording()

    assert writer.stopped and win._logWriter is None


def test_the_record_button_replays_the_history_then_records_the_profile(win, profiles):
    history = [{"event": "state_change", "device": "Pipette1"}]
    win.eventHistory = list(history)

    _press(win, "events", True)

    writer = win._logWriter
    assert writer.initial_records == history
    assert [e["event"] for e in writer.records] == ["global patch profiles changed"]
    assert json.loads(writer.records[0]["profile"]) == profiles


def test_the_record_button_off_resets_the_history(win):
    _press(win, "events", True)
    resetsBefore = win.resetCount

    _press(win, "events", False)

    assert win.resetCount == resetsBefore + 1
    assert win.eventHistory == []


def test_the_writer_covers_every_patch_pipette_and_the_microscope(win):
    win.microscope = object()

    _press(win, "events", True)

    assert win._logWriter.pipettes == win.pips[:2]
    assert win._logWriter.microscope is win.microscope


def test_window_originated_events_reach_the_writer(win):
    _press(win, "events", True)
    win._logWriter.records.clear()
    event = {"device": None, "event": "global patch profiles changed", "profile": "{}"}

    win.recordEvent(event)

    assert win._logWriter.records == [event]
    assert win.eventHistory[-1] == event


def test_pipette_and_surface_events_only_reach_the_history(win):
    # The writer subscribes to these itself; passing them on would write them twice.
    class _Scope:
        def name(self):
            return "Microscope"

    win.microscope = _Scope()
    _press(win, "events", True)
    win._logWriter.records.clear()

    win.pipetteEvent(object(), {"device": "Pipette1", "event": "state_change", "state": "bath"})
    win.surfaceDepthChanged(-1e-3)

    assert win._logWriter.records == []
    assert [e["event"] for e in win.eventHistory][-2:] == ["state_change", "surface_depth_changed"]


def test_events_arriving_with_no_writer_still_reach_the_history(win):
    win.recordEvent({"device": None, "event": "global patch profiles changed"})
    win.pipetteEvent(object(), {"device": "Pipette1", "event": "state_change"})

    assert win._logWriter is None
    assert len(win.eventHistory) == 2


def test_the_in_memory_history_never_holds_a_test_pulse_object(win):
    # The history is replayed into a newly started log, so it holds JSON-safe records.
    class _TestPulse:
        analysis = {"steady_state_resistance": 1e9, "start_time": 1000.0}

    event = {"device": "Pipette1", "event_time": 1000.5, "event": "test_pulse", "test_pulse": _TestPulse()}
    win.pipetteEvent(object(), event)

    (record,) = win.eventHistory
    assert record == {
        "device": "Pipette1",
        "event_time": 1000.5,
        "event": "test_pulse",
        "steady_state_resistance": 1e9,
        "start_time": 1000.0,
    }
    json.dumps(record)
    assert "test_pulse" in event  # the shared event itself is untouched
