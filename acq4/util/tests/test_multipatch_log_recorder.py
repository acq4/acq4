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
