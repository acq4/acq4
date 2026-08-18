"""Tests for MultiPatchLogRecorder: the writer half of the MultiPatch log
format, extracted so both MultiPatch and Autopatch can record."""
import json

import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakeFileHandle:
    def __init__(self, path):
        self._path = str(path)

    def name(self):
        return self._path


class _FakeDir:
    """Stands in for a DirHandle: createFile hands back a real path under
    tmp_path, auto-incrementing the way the managed original does."""

    def __init__(self, root):
        self.root = root
        self.created = []

    def createFile(self, name, autoIncrement=False):
        stem, _, ext = name.rpartition(".")
        index = 0
        while True:
            candidate = self.root / (f"{stem}_{index:03d}.{ext}" if autoIncrement else name)
            if not candidate.exists():
                break
            index += 1
        candidate.touch()
        self.created.append(candidate)
        return _FakeFileHandle(candidate)


@pytest.fixture
def directory(tmp_path):
    return _FakeDir(tmp_path)


def _lines(path):
    with open(path, "rb") as fh:
        return [line for line in fh if line.strip()]


def test_recorder_creates_an_auto_incremented_log_file(qapp, directory):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    first = MultiPatchLogRecorder(directory, record_full_test_pulses=False)
    second = MultiPatchLogRecorder(directory, record_full_test_pulses=False)
    try:
        assert first.logFileName().endswith("MultiPatch_000.log")
        assert second.logFileName().endswith("MultiPatch_001.log")
    finally:
        first.stop()
        second.stop()


def test_recorded_events_are_one_json_object_per_line(qapp, directory):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    recorder = MultiPatchLogRecorder(directory, record_full_test_pulses=False)
    try:
        recorder.record({"device": "Clamp1", "event_time": 1.0, "event": "state_change"})
        recorder.record({"device": "Clamp1", "event_time": 2.0, "event": "test_pulse"})
    finally:
        recorder.stop()

    lines = _lines(recorder.logFileName())
    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "state_change"
    assert json.loads(lines[1])["event_time"] == 2.0


def test_lines_have_no_trailing_comma(qapp, directory):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    recorder = MultiPatchLogRecorder(directory, record_full_test_pulses=False)
    try:
        recorder.record({"device": "Clamp1", "event_time": 1.0, "event": "state_change"})
    finally:
        recorder.stop()

    assert _lines(recorder.logFileName())[0].rstrip(b"\r\n").endswith(b"}")


def test_records_are_flushed_before_stop(qapp, directory):
    # An Autopatch action's log has to be readable the moment the action ends,
    # not whenever the OS gets round to it.
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    recorder = MultiPatchLogRecorder(directory, record_full_test_pulses=False)
    try:
        recorder.record({"device": "Clamp1", "event_time": 1.0, "event": "state_change"})
        assert len(_lines(recorder.logFileName())) == 1
    finally:
        recorder.stop()


def test_initial_records_are_replayed_into_the_fresh_file(qapp, directory):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    history = [
        {"device": "Clamp1", "event_time": 0.5, "event": "state_change"},
        {"device": "Clamp1", "event_time": 0.7, "event": "move_stop"},
    ]
    recorder = MultiPatchLogRecorder(
        directory, record_full_test_pulses=False, initial_records=history
    )
    try:
        pass
    finally:
        recorder.stop()

    lines = _lines(recorder.logFileName())
    assert [json.loads(line)["event"] for line in lines] == ["state_change", "move_stop"]


def test_write_events_false_creates_no_log_file(qapp, directory):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    recorder = MultiPatchLogRecorder(
        directory, record_full_test_pulses=False, write_events=False
    )
    try:
        recorder.record({"device": "Clamp1", "event_time": 1.0, "event": "state_change"})
        assert recorder.logFileName() is None
        assert directory.created == []
    finally:
        recorder.stop()


def test_is_recording_reflects_the_lifecycle(qapp, directory):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    recorder = MultiPatchLogRecorder(directory, record_full_test_pulses=False)
    assert recorder.isRecording() is True
    recorder.stop()
    assert recorder.isRecording() is False


def test_stop_is_idempotent(qapp, directory):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    recorder = MultiPatchLogRecorder(directory, record_full_test_pulses=False)
    recorder.stop()
    recorder.stop()  # must not raise on an already-closed file


def test_recording_after_stop_is_ignored(qapp, directory):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    recorder = MultiPatchLogRecorder(directory, record_full_test_pulses=False)
    recorder.stop()

    recorder.record({"device": "Clamp1", "event_time": 1.0, "event": "state_change"})

    assert _lines(recorder.logFileName()) == []


def test_encodes_values_the_plain_json_encoder_cannot(qapp, directory):
    # State-change events carry numpy scalars; ACQ4JSONEncoder is what handles
    # them, and the reader expects its output.
    import numpy as np
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    recorder = MultiPatchLogRecorder(directory, record_full_test_pulses=False)
    try:
        recorder.record(
            {
                "device": "Clamp1",
                "event_time": 1.0,
                "event": "test_pulse",
                "steady_state_resistance": np.float64(1.5e9),
            }
        )
    finally:
        recorder.stop()

    assert json.loads(_lines(recorder.logFileName())[0])["steady_state_resistance"] == 1.5e9


def test_unserializable_initial_record_closes_the_file_before_raising(qapp, directory):
    # A record ACQ4JSONEncoder can't handle raises out of __init__ before the
    # caller ever receives an instance to call stop() on. The file opened for
    # write_events must not depend on refcounting to get closed in that case;
    # find the partially-constructed self via the traceback and check it
    # directly, since the caller never gets a reference of its own.
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    history = [{"device": "Clamp1", "event_time": 0.5, "bad": {1, 2, 3}}]

    with pytest.raises(TypeError) as excinfo:
        MultiPatchLogRecorder(directory, record_full_test_pulses=False, initial_records=history)

    partial_self = None
    tb = excinfo.value.__traceback__
    while tb is not None:
        candidate = tb.tb_frame.f_locals.get("self")
        if isinstance(candidate, MultiPatchLogRecorder):
            partial_self = candidate
        tb = tb.tb_next

    assert partial_self is not None
    assert partial_self._logFile is not None
    assert partial_self._logFile.closed


class _FakeTestPulse:
    """Stands in for a PatchClampTestPulse. H5BackedTestPulseStack.append is
    monkeypatched in these tests, so this only has to be identifiable."""

    def __init__(self, tag):
        self.tag = tag


@pytest.fixture
def stubbed_stack(monkeypatch):
    """Replace the HDF5 stack with a recorder of appends, returning the
    (filename, h5path) pair the real one returns."""
    import acq4.util.multipatch_log_recorder as mod

    appended = []

    class _Stack:
        def __init__(self, group):
            self.group = group
            self.files = []

        def append(self, test_pulse, retain_data=False):
            appended.append(test_pulse)
            return (self.group["filename"], f"{self.group['path']}/{len(appended) - 1}")

        def flush(self):
            return None

        def close(self):
            return None

    created = []

    def fakeMakeStack(self, deviceName):
        stack = _Stack(
            {
                "filename": str(self._directory.root / "TestPulses_000.hdf5"),
                "path": f"test_pulses/{deviceName}",
            }
        )
        created.append((deviceName, stack))
        return stack

    monkeypatch.setattr(mod.MultiPatchLogRecorder, "_makeTestPulseStack", fakeMakeStack)
    return appended, created


def test_full_test_pulse_is_diverted_into_the_sidecar(qapp, directory, stubbed_stack):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    appended, _created = stubbed_stack
    recorder = MultiPatchLogRecorder(
        directory, pipettes=(), record_full_test_pulses=True
    )
    tp = _FakeTestPulse("tp-1")
    try:
        recorder.record(
            {
                "device": "Clamp1",
                "event_time": 1.0,
                "event": "test_pulse",
                "full_test_pulse": tp,
            }
        )
    finally:
        recorder.stop()

    assert appended == [tp]
    written = json.loads(_lines(recorder.logFileName())[0])
    assert written["full_test_pulse"] == "TestPulses_000.hdf5:test_pulses/Clamp1/0"


def test_the_sidecar_path_is_relative_to_the_log_file(qapp, directory, stubbed_stack):
    # The reader resolves it with os.path.join(os.path.dirname(logfile), ...),
    # so an absolute path here would break every viewer that moves the data.
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    recorder = MultiPatchLogRecorder(directory, record_full_test_pulses=True)
    try:
        recorder.record(
            {
                "device": "Clamp1",
                "event_time": 1.0,
                "event": "test_pulse",
                "full_test_pulse": _FakeTestPulse("tp"),
            }
        )
    finally:
        recorder.stop()

    location = json.loads(_lines(recorder.logFileName())[0])["full_test_pulse"]
    assert not location.startswith("/")


def test_the_test_pulse_object_never_reaches_the_json(qapp, directory, stubbed_stack):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    recorder = MultiPatchLogRecorder(directory, record_full_test_pulses=True)
    try:
        recorder.record(
            {
                "device": "Clamp1",
                "event_time": 1.0,
                "event": "test_pulse",
                "full_test_pulse": _FakeTestPulse("tp"),
                "steady_state_resistance": 1.5e9,
            }
        )
    finally:
        recorder.stop()

    written = json.loads(_lines(recorder.logFileName())[0])
    assert isinstance(written["full_test_pulse"], str)
    assert written["steady_state_resistance"] == 1.5e9


def test_full_test_pulse_is_stripped_when_not_recording_them(qapp, directory):
    # No sidecar to divert into, so the object must be dropped rather than
    # handed to the JSON encoder.
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    recorder = MultiPatchLogRecorder(directory, record_full_test_pulses=False)
    try:
        recorder.record(
            {
                "device": "Clamp1",
                "event_time": 1.0,
                "event": "test_pulse",
                "full_test_pulse": _FakeTestPulse("tp"),
                "steady_state_resistance": 1.5e9,
            }
        )
    finally:
        recorder.stop()

    written = json.loads(_lines(recorder.logFileName())[0])
    assert "full_test_pulse" not in written
    assert written["steady_state_resistance"] == 1.5e9


def test_set_record_full_test_pulses_toggles_at_runtime(qapp, directory, stubbed_stack):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    recorder = MultiPatchLogRecorder(directory, record_full_test_pulses=False)
    try:
        assert recorder.recordsFullTestPulses() is False
        recorder.setRecordFullTestPulses(True)
        assert recorder.recordsFullTestPulses() is True
        recorder.setRecordFullTestPulses(False)
        assert recorder.recordsFullTestPulses() is False
    finally:
        recorder.stop()


def _make_real_test_pulse(start_time, amplitude=-10e-3):
    """A genuine PatchClampTestPulse -- real PatchClampRecording and TSeries
    objects wrapping a single square pulse on the command channel -- built
    without NEURON so it stays cheap to construct in a unit test. Used to
    exercise the real H5BackedTestPulseStack rather than the monkeypatched
    stack every other sidecar test in this file uses.
    """
    import numpy as np
    from neuroanalysis.data import PatchClampRecording, TSeries
    from neuroanalysis.test_pulse import PatchClampTestPulse

    dt = 1e-4
    n = 100
    command = np.zeros(n)
    command[20:80] = amplitude
    primary = np.zeros(n)
    primary[20:80] = amplitude * (1 - np.exp(-np.arange(60) / 5.0))
    rec = PatchClampRecording(
        channels={"primary": TSeries(primary, dt=dt), "command": TSeries(command, dt=dt)},
        dt=dt,
        t0=0,
        start_time=start_time,
        clamp_mode="vc",
        bridge_balance=0,
        lpf_cutoff=None,
        pipette_offset=0,
        holding_current=None,
        holding_potential=0.0,
    )
    return PatchClampTestPulse(rec)


def test_stop_closes_the_shared_sidecar_file_with_two_real_devices(qapp, directory):
    # Regression test for a Critical bug: H5BackedTestPulseStack.close()
    # closes the *file* its groups belong to, and every device's stack in
    # one recorder shares the same file (opened once in
    # _makeTestPulseStack). Closing each stack in turn used to close the
    # file out from under the next device's stack, raising ValueError on
    # the second close and skipping the log file's own close() -- and since
    # every other sidecar test here stubs out _makeTestPulseStack with a
    # single device, none of them could have caught it. This one uses the
    # real stack with two devices.
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    recorder = MultiPatchLogRecorder(directory, record_full_test_pulses=True)
    recorder.record(
        {
            "device": "Clamp1",
            "event_time": 1.0,
            "event": "test_pulse",
            "full_test_pulse": _make_real_test_pulse(1000.0),
        }
    )
    recorder.record(
        {
            "device": "Clamp2",
            "event_time": 2.0,
            "event": "test_pulse",
            "full_test_pulse": _make_real_test_pulse(2000.0),
        }
    )

    container = recorder._testPulseContainer
    log_file = recorder._logFile
    recorder.stop()  # must not raise

    assert not bool(container)  # the shared h5py.File is actually closed
    assert log_file.closed
    assert recorder.isRecording() is False


def test_second_stop_after_two_real_devices_is_still_a_no_op(qapp, directory):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    recorder = MultiPatchLogRecorder(directory, record_full_test_pulses=True)
    recorder.record(
        {
            "device": "Clamp1",
            "event_time": 1.0,
            "event": "test_pulse",
            "full_test_pulse": _make_real_test_pulse(1000.0),
        }
    )
    recorder.record(
        {
            "device": "Clamp2",
            "event_time": 2.0,
            "event": "test_pulse",
            "full_test_pulse": _make_real_test_pulse(2000.0),
        }
    )
    recorder.stop()
    recorder.stop()  # must not raise on an already-closed shared file
    assert recorder.isRecording() is False


class _FakePipette(Qt.QObject):
    sigNewEvent = Qt.Signal(object, object)

    def __init__(self, name="Clamp1"):
        super().__init__()
        self._name = name
        self.requested = []
        self.released = []

    def name(self):
        return self._name

    def requestFullTestPulseData(self, token):
        self.requested.append(token)

    def releaseFullTestPulseData(self, token):
        self.released.append(token)

    def emit(self, event):
        self.sigNewEvent.emit(self, event)


class _FakeMicroscope(Qt.QObject):
    sigSurfaceDepthChanged = Qt.Signal(object)

    def name(self):
        return "Microscope"


def test_pipette_events_are_recorded(qapp, directory):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    pip = _FakePipette()
    recorder = MultiPatchLogRecorder(
        directory, pipettes=(pip,), record_full_test_pulses=False
    )
    try:
        pip.emit({"device": "Clamp1", "event_time": 1.0, "event": "state_change"})
    finally:
        recorder.stop()

    assert json.loads(_lines(recorder.logFileName())[0])["event"] == "state_change"


def test_events_after_stop_are_not_recorded(qapp, directory):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    pip = _FakePipette()
    recorder = MultiPatchLogRecorder(
        directory, pipettes=(pip,), record_full_test_pulses=False
    )
    recorder.stop()

    pip.emit({"device": "Clamp1", "event_time": 1.0, "event": "state_change"})

    assert _lines(recorder.logFileName()) == []


def test_full_test_pulse_data_is_requested_and_released(qapp, directory):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    pip = _FakePipette()
    recorder = MultiPatchLogRecorder(
        directory, pipettes=(pip,), record_full_test_pulses=True
    )
    assert pip.requested == [recorder]
    assert pip.released == []

    recorder.stop()

    assert pip.released == [recorder]


def test_no_full_test_pulse_request_when_not_recording_them(qapp, directory):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    pip = _FakePipette()
    recorder = MultiPatchLogRecorder(
        directory, pipettes=(pip,), record_full_test_pulses=False
    )
    try:
        assert pip.requested == []
    finally:
        recorder.stop()


def test_toggling_full_test_pulses_requests_and_releases(qapp, directory):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    pip = _FakePipette()
    recorder = MultiPatchLogRecorder(
        directory, pipettes=(pip,), record_full_test_pulses=False
    )
    try:
        recorder.setRecordFullTestPulses(True)
        assert pip.requested == [recorder]
        recorder.setRecordFullTestPulses(False)
        assert pip.released == [recorder]
    finally:
        recorder.stop()


def test_microscope_surface_depth_changes_are_recorded(qapp, directory):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    scope = _FakeMicroscope()
    recorder = MultiPatchLogRecorder(
        directory, microscope=scope, record_full_test_pulses=False
    )
    try:
        scope.sigSurfaceDepthChanged.emit(-1.5e-3)
    finally:
        recorder.stop()

    written = json.loads(_lines(recorder.logFileName())[0])
    assert written["event"] == "surface_depth_changed"
    assert written["surface_depth"] == -1.5e-3
    assert written["device"] == "Microscope"


def test_test_pulse_analysis_accumulates_the_events_seen(qapp, directory):
    import numpy as np
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    pip = _FakePipette()
    recorder = MultiPatchLogRecorder(
        directory, pipettes=(pip,), record_full_test_pulses=False
    )
    try:
        pip.emit(
            {
                "device": "Clamp1",
                "event_time": 1.0,
                "event": "test_pulse",
                "steady_state_resistance": 1.0e9,
                "capacitance": 5e-12,
            }
        )
        pip.emit(
            {
                "device": "Clamp1",
                "event_time": 2.0,
                "event": "test_pulse",
                "steady_state_resistance": 2.0e9,
                "capacitance": 6e-12,
            }
        )
        history = recorder.testPulseAnalysis()
    finally:
        recorder.stop()

    assert len(history) == 2
    assert np.array_equal(history["event_time"], [1.0, 2.0])
    assert np.array_equal(history["steady_state_resistance"], [1.0e9, 2.0e9])


def test_test_pulse_analysis_records_missing_fields_as_nan(qapp, directory):
    import numpy as np
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    pip = _FakePipette()
    recorder = MultiPatchLogRecorder(
        directory, pipettes=(pip,), record_full_test_pulses=False
    )
    try:
        pip.emit(
            {
                "device": "Clamp1",
                "event_time": 1.0,
                "event": "test_pulse",
                "steady_state_resistance": None,
            }
        )
        history = recorder.testPulseAnalysis()
    finally:
        recorder.stop()

    assert np.isnan(history["steady_state_resistance"][0])


def test_test_pulse_analysis_ignores_other_event_types(qapp, directory):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    pip = _FakePipette()
    recorder = MultiPatchLogRecorder(
        directory, pipettes=(pip,), record_full_test_pulses=False
    )
    try:
        pip.emit({"device": "Clamp1", "event_time": 1.0, "event": "state_change"})
        history = recorder.testPulseAnalysis()
    finally:
        recorder.stop()

    assert len(history) == 0


def test_test_pulse_analysis_is_unaffected_by_a_device_history_reset(qapp, directory):
    # approach.py resets the clamp's own test-pulse history mid-patch, which is
    # exactly why the recorder accumulates its own rather than slicing the
    # device's.
    import numpy as np
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    pip = _FakePipette()
    recorder = MultiPatchLogRecorder(
        directory, pipettes=(pip,), record_full_test_pulses=False
    )
    try:
        for index, t in enumerate([1.0, 2.0, 3.0]):
            pip.emit(
                {
                    "device": "Clamp1",
                    "event_time": t,
                    "event": "test_pulse",
                    "steady_state_resistance": float(index),
                }
            )
        history = recorder.testPulseAnalysis()
    finally:
        recorder.stop()

    assert np.array_equal(history["event_time"], [1.0, 2.0, 3.0])


def test_the_recorder_holds_no_reference_to_a_stopped_pipette(qapp, directory):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    pip = _FakePipette()
    recorder = MultiPatchLogRecorder(
        directory, pipettes=(pip,), record_full_test_pulses=False
    )
    recorder.stop()

    assert recorder._pipettes == []


class _FakeClampDevice:
    """Stands in for a PatchClamp for the one thing these tests need: a
    testPulseHistory() a caller can empty out from under the recorder, the way
    approach.py's mid-patch reset empties the real one."""

    def __init__(self):
        self._history = []

    def testPulseHistory(self):
        return list(self._history)

    def resetTestPulseHistory(self):
        self._history = []


def test_test_pulse_analysis_is_unaffected_by_a_device_history_reset(qapp, directory):
    # approach.py resets the clamp's own test-pulse history mid-patch, which is
    # exactly why the recorder accumulates its own rather than reading
    # clampDevice.testPulseHistory(). Exercise that directly: reset the fake
    # clamp's history partway through and confirm the recorder's own
    # accumulation still holds every row regardless.
    import numpy as np
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    pip = _FakePipette()
    pip.clampDevice = _FakeClampDevice()
    recorder = MultiPatchLogRecorder(
        directory, pipettes=(pip,), record_full_test_pulses=False
    )
    try:
        pip.emit(
            {
                "device": "Clamp1",
                "event_time": 1.0,
                "event": "test_pulse",
                "steady_state_resistance": 0.0,
            }
        )
        pip.clampDevice._history.append("whatever the device tracked")
        pip.clampDevice.resetTestPulseHistory()
        assert pip.clampDevice.testPulseHistory() == []

        pip.emit(
            {
                "device": "Clamp1",
                "event_time": 2.0,
                "event": "test_pulse",
                "steady_state_resistance": 1.0e9,
            }
        )
        pip.emit(
            {
                "device": "Clamp1",
                "event_time": 3.0,
                "event": "test_pulse",
                "steady_state_resistance": 2.0e9,
            }
        )
        history = recorder.testPulseAnalysis()
    finally:
        recorder.stop()

    assert np.array_equal(history["event_time"], [1.0, 2.0, 3.0])


def test_onPipetteEvent_after_stop_does_not_add_a_test_pulse_row(qapp, directory):
    # sigNewEvent is a queued connection: disconnecting it in stop() does not
    # cancel a test_pulse event already posted to the event queue, so this
    # slot can still run once after stop() tears the recorder down. Call it
    # directly rather than going through the Qt event loop so the test does
    # not depend on when Qt happens to deliver the queued call.
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    pip = _FakePipette()
    recorder = MultiPatchLogRecorder(
        directory, pipettes=(pip,), record_full_test_pulses=False
    )
    recorder.stop()

    recorder._onPipetteEvent(
        pip, {"device": "Clamp1", "event_time": 1.0, "event": "test_pulse"}
    )

    assert recorder._testPulseRows == []
    assert len(recorder.testPulseAnalysis()) == 0


def test_onSurfaceDepthChanged_after_stop_does_not_raise(qapp, directory):
    # Same late-queued-delivery hazard as above: stop() sets self._microscope
    # to None, and a surface-depth signal already in flight when stop() runs
    # would otherwise dereference it. Call the slot directly, as above.
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    scope = _FakeMicroscope()
    recorder = MultiPatchLogRecorder(
        directory, microscope=scope, record_full_test_pulses=False
    )
    recorder.stop()

    recorder._onSurfaceDepthChanged(-1.5e-3)  # must not raise

    assert _lines(recorder.logFileName()) == []


def test_construction_failure_releases_the_pipettes_subscriptions(qapp, directory):
    # Same failure as test_unserializable_initial_record_closes_the_file_before_raising,
    # but with a live pipette and microscope subscribed, so it exercises the
    # rest of what the __init__ try/except's stop() call has to release: not
    # just the file, but every token and signal connection picked up before
    # the raise. The caller never gets a reference of its own, so find the
    # partially-constructed self via the traceback, as that test does.
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    pip = _FakePipette()
    scope = _FakeMicroscope()
    history = [{"device": "Clamp1", "event_time": 0.5, "bad": {1, 2, 3}}]

    with pytest.raises(TypeError) as excinfo:
        MultiPatchLogRecorder(
            directory,
            pipettes=(pip,),
            microscope=scope,
            initial_records=history,
        )

    partial_self = None
    tb = excinfo.value.__traceback__
    while tb is not None:
        candidate = tb.tb_frame.f_locals.get("self")
        if isinstance(candidate, MultiPatchLogRecorder):
            partial_self = candidate
        tb = tb.tb_next

    assert partial_self is not None
    assert pip.released == [partial_self]
    assert pip.receivers(pip.sigNewEvent) == 0
    assert scope.receivers(scope.sigSurfaceDepthChanged) == 0
