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
