"""Tests for MultiPatchLogWriter and eventToRecord, and for reading the writer's
output back with MultiPatchLogData."""
import json
import logging
import threading

import h5py
import numpy as np
import pytest

from acq4.filetypes.MultiPatchLog import TEST_PULSE_METAARRAY_INFO
from acq4.util import Qt
from acq4.util.json_encoder import ACQ4JSONEncoder
from acq4.util.multipatch_log_writer import MultiPatchLogWriter, eventToRecord


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakeFileHandle:
    def __init__(self, path):
        self._path = str(path)

    def name(self):
        return self._path


class _FakeDir:
    """Stands in for a DirHandle: createFile returns an auto-incremented real path,
    and records which thread asked."""

    def __init__(self, root):
        self.root = root
        self.created = []
        self.creatingThreads = []

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
        self.creatingThreads.append(threading.current_thread())
        return _FakeFileHandle(candidate)


class _RefusingDir(_FakeDir):
    """A _FakeDir whose createFile raises for files matching `refuse`."""

    def __init__(self, root, refuse=".hdf5"):
        super().__init__(root)
        self.refuse = refuse

    def createFile(self, name, autoIncrement=False):
        if self.refuse in name:
            raise OSError("disk full")
        return super().createFile(name, autoIncrement=autoIncrement)


# Analysis fields of every test pulse below; event_time comes from the event.
_ANALYSIS_FIELDS = [info["name"] for info in TEST_PULSE_METAARRAY_INFO if info["name"] != "event_time"]


def _analysis(start_time, resistance=1e9):
    analysis = {name: 1.0 for name in _ANALYSIS_FIELDS}
    analysis["start_time"] = start_time
    analysis["steady_state_resistance"] = resistance
    return analysis


def _make_test_pulse(start_time, resistance=1e9):
    """A real PatchClampTestPulse with a preset analysis covering every logged field."""
    from neuroanalysis.data import PatchClampRecording, TSeries
    from neuroanalysis.test_pulse import PatchClampTestPulse

    dt = 1e-4
    n = 100
    command = np.zeros(n)
    command[20:80] = -10e-3
    primary = np.zeros(n)
    primary[20:80] = -10e-3 * (1 - np.exp(-np.arange(60) / 5.0))
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
    tp = PatchClampTestPulse(rec)
    tp._analysis = _analysis(start_time, resistance)
    return tp


class _FakePipette(Qt.QObject):
    sigNewEvent = Qt.Signal(object, object)

    def __init__(self, name="Pipette1"):
        super().__init__()
        self._name = name

    def name(self):
        return self._name

    def emit(self, event):
        self.sigNewEvent.emit(self, event)

    def emitTestPulse(self, tp, event_time=None):
        """Emit a test_pulse event shaped like PatchPipette's."""
        event_time = tp.recording.start_time + 0.01 if event_time is None else event_time
        self.emit({"device": self._name, "event_time": event_time, "event": "test_pulse", "test_pulse": tp})


class _FakeMicroscope(Qt.QObject):
    sigSurfaceDepthChanged = Qt.Signal(object)

    def name(self):
        return "Microscope"


@pytest.fixture
def directory(tmp_path):
    return _FakeDir(tmp_path)


def _lines(path):
    with open(path, "rb") as fh:
        return [line for line in fh if line.strip()]


def _events(path):
    return [json.loads(line) for line in _lines(path)]


def _resolve(logFileName, location):
    """The dataset a "full_test_pulse" location names, opened relative to the log."""
    import os

    relpath, h5path = location.split(":")
    fh = h5py.File(os.path.join(os.path.dirname(logFileName), relpath), "r")
    return fh, fh[h5path]


# -- eventToRecord ----------------------------------------------------------------


def _testPulseEvent(tp, device="Pipette1", event_time=5.0):
    return {"device": device, "event_time": event_time, "event": "test_pulse", "test_pulse": tp}


def test_event_to_record_flattens_the_test_pulse_and_keeps_no_object():
    tp = _make_test_pulse(1000.0)
    event = _testPulseEvent(tp)

    record = eventToRecord(event)

    assert "test_pulse" not in record
    assert record == {"device": "Pipette1", "event_time": 5.0, "event": "test_pulse", **tp.analysis}
    assert not any(isinstance(v, type(tp)) for v in record.values())
    assert json.loads(json.dumps(record)) == record
    json.dumps(record, cls=ACQ4JSONEncoder)


def test_event_to_record_does_not_modify_the_event():
    tp = _make_test_pulse(1000.0)
    event = _testPulseEvent(tp)

    eventToRecord(event)

    assert event == _testPulseEvent(tp)


def test_event_to_record_is_idempotent_and_passes_other_events_through():
    record = eventToRecord(_testPulseEvent(_make_test_pulse(1000.0)))
    stateChange = {"device": "Pipette1", "event_time": 1.0, "event": "state_change", "state": "bath"}

    assert eventToRecord(record) == record
    assert eventToRecord(stateChange) == stateChange
    assert eventToRecord(stateChange) is not stateChange


def test_acq4_json_encoder_cannot_encode_a_test_pulse():
    # Why every serializing path has to go through eventToRecord.
    with pytest.raises(TypeError):
        json.dumps(_testPulseEvent(_make_test_pulse(1000.0)), cls=ACQ4JSONEncoder)


# -- event log ---------------------------------------------------------------


def test_log_files_are_auto_incremented(qapp, directory):
    first = MultiPatchLogWriter(directory).start()
    second = MultiPatchLogWriter(directory).start()
    first.stop()
    second.stop()

    assert first.logFileName().endswith("MultiPatch_000.log")
    assert second.logFileName().endswith("MultiPatch_001.log")


def test_events_are_written_in_order_one_json_object_per_line(qapp, directory):
    pip = _FakePipette()
    writer = MultiPatchLogWriter(
        directory,
        pipettes=[pip],
        initial_records=[{"device": "Pipette1", "event_time": 0.5, "event": "init"}],
    ).start()
    pip.emit({"device": "Pipette1", "event_time": 1.0, "event": "state_change"})
    writer.record({"device": None, "event_time": 2.0, "event": "global patch profiles changed"})
    pip.emit({"device": "Pipette1", "event_time": 3.0, "event": "move_stop"})
    writer.stop()

    lines = _lines(writer.logFileName())
    assert [json.loads(line)["event_time"] for line in lines] == [0.5, 1.0, 2.0, 3.0]
    assert all(line.rstrip(b"\r\n").endswith(b"}") for line in lines)


def test_numpy_values_are_encoded(qapp, directory):
    writer = MultiPatchLogWriter(directory).start()
    writer.record({"device": "Pipette1", "event_time": 1.0, "event": "x", "value": np.float64(1.5e9)})
    writer.stop()

    assert _events(writer.logFileName())[0]["value"] == 1.5e9


def test_an_unserializable_record_is_logged_and_writing_continues(qapp, directory, caplog):
    writer = MultiPatchLogWriter(directory).start()
    with caplog.at_level(logging.ERROR):
        writer.record({"device": "Pipette1", "event_time": 1.0, "bad": {1, 2}})
        writer.record({"device": "Pipette1", "event_time": 2.0, "event": "ok"})
        writer.stop()

    assert [e["event_time"] for e in _events(writer.logFileName())] == [2.0]
    assert any("MultiPatchLogWriter" in r.getMessage() for r in caplog.records)


def test_surface_depth_changes_are_recorded(qapp, directory):
    scope = _FakeMicroscope()
    writer = MultiPatchLogWriter(directory, microscope=scope).start()
    scope.sigSurfaceDepthChanged.emit(-1.5e-3)
    writer.stop()

    (written,) = _events(writer.logFileName())
    assert written["event"] == "surface_depth_changed"
    assert written["surface_depth"] == -1.5e-3
    assert written["device"] == "Microscope"


def test_stop_unsubscribes_and_later_events_are_not_written(qapp, directory):
    pip = _FakePipette()
    scope = _FakeMicroscope()
    writer = MultiPatchLogWriter(directory, pipettes=[pip], microscope=scope).start()
    writer.stop()

    pip.emit({"device": "Pipette1", "event_time": 1.0, "event": "state_change"})
    writer.record({"device": "Pipette1", "event_time": 2.0, "event": "state_change"})

    assert pip.receivers(pip.sigNewEvent) == 0
    assert scope.receivers(scope.sigSurfaceDepthChanged) == 0
    assert _lines(writer.logFileName()) == []
    assert writer.isRecording() is False


def test_stop_is_idempotent_and_safe_before_start(qapp, directory):
    writer = MultiPatchLogWriter(directory).start()
    writer.stop()
    writer.stop()

    unstarted = MultiPatchLogWriter(directory)
    unstarted.stop()
    assert directory.created == [directory.root / "MultiPatch_000.log"]


def test_a_writer_cannot_be_restarted(qapp, directory):
    writer = MultiPatchLogWriter(directory).start()
    writer.stop()
    with pytest.raises(RuntimeError):
        writer.start()


def test_start_closes_the_log_file_when_the_sidecar_cannot_be_created(qapp, tmp_path):
    """start() must not leave an open handle behind: it raises before returning the
    writer, so the caller has no object to stop()."""
    pip = _FakePipette()
    directory = _RefusingDir(tmp_path)
    writer = MultiPatchLogWriter(directory, pipettes=[pip], full_test_pulse_pipettes=[pip])

    with pytest.raises(OSError):
        writer.start()

    assert writer._logFile is None or writer._logFile.closed
    assert writer.isRecording() is False
    assert pip.receivers(pip.sigNewEvent) == 0


def test_start_closes_the_log_file_when_subscribing_fails(qapp, directory, monkeypatch):
    pip = _FakePipette()
    monkeypatch.setattr(
        type(pip.sigNewEvent), "connect", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    writer = MultiPatchLogWriter(directory, pipettes=[pip])

    with pytest.raises(RuntimeError):
        writer.start()

    assert writer._logFile is None or writer._logFile.closed
    assert writer.isRecording() is False


def test_a_writer_whose_start_failed_cannot_be_started_again(qapp, tmp_path):
    writer = MultiPatchLogWriter(_RefusingDir(tmp_path), full_test_pulse_pipettes=[_FakePipette()])
    with pytest.raises(OSError):
        writer.start()
    with pytest.raises(RuntimeError):
        writer.start()


def test_turning_raw_capture_on_logs_a_sidecar_failure_instead_of_raising(qapp, tmp_path, caplog):
    """setFullTestPulsePipettes runs on the caller's thread, which is a Qt slot in
    MultiPatch; the class contract is that write failures are logged, not raised."""
    pip = _FakePipette()
    writer = MultiPatchLogWriter(_RefusingDir(tmp_path), pipettes=[pip]).start()
    try:
        with caplog.at_level(logging.ERROR):
            writer.setFullTestPulsePipettes([pip])
        assert "disk full" in caplog.text

        pip.emitTestPulse(_make_test_pulse(1000.0), event_time=1000.5)
        writer.stop()
    finally:
        writer.stop()

    # The pulse still gets its log line, just with no location.
    (written,) = _events(writer.logFileName())
    assert written["event"] == "test_pulse"
    assert "full_test_pulse" not in written
    assert writer.testPulseFileName() is None


# -- test pulse lines -----------------------------------------------------------


def test_a_test_pulse_line_has_the_flattened_analysis_and_no_location_when_raw_is_off(qapp, directory):
    pip = _FakePipette()
    writer = MultiPatchLogWriter(directory, pipettes=[pip]).start()
    tp = _make_test_pulse(1000.0)
    pip.emitTestPulse(tp, event_time=1000.5)
    writer.stop()

    (written,) = _events(writer.logFileName())
    assert written == {"device": "Pipette1", "event_time": 1000.5, "event": "test_pulse", **tp.analysis}
    assert writer.testPulseFileName() is None
    assert [p.name for p in directory.created] == ["MultiPatch_000.log"]


def test_a_test_pulse_line_has_the_original_layout_and_a_resolving_location_when_raw_is_on(qapp, directory):
    pip = _FakePipette()
    writer = MultiPatchLogWriter(directory, pipettes=[pip], full_test_pulse_pipettes=[pip]).start()
    tp = _make_test_pulse(1000.0)
    pip.emitTestPulse(tp, event_time=1000.5)
    writer.stop()

    (written,) = _events(writer.logFileName())
    # Field order as written before test pulses travelled in events.
    assert list(written) == ["device", "event_time", "event", *tp.analysis, "full_test_pulse"]
    assert written["full_test_pulse"] == "TestPulses_000.hdf5:/test_pulses/Pipette1/1000.0"
    fh, dataset = _resolve(writer.logFileName(), written["full_test_pulse"])
    with fh:
        assert dataset.parent.attrs["device"] == "Pipette1"
    assert writer.testPulseFileName().endswith("TestPulses_000.hdf5")


def test_full_test_pulses_are_saved_only_for_the_chosen_pipettes(qapp, directory):
    pip1, pip2 = _FakePipette("Pipette1"), _FakePipette("Pipette2")
    writer = MultiPatchLogWriter(directory, pipettes=[pip1, pip2], full_test_pulse_pipettes=[pip1]).start()
    pip1.emitTestPulse(_make_test_pulse(1000.0))
    pip2.emitTestPulse(_make_test_pulse(1001.0))
    writer.stop()

    byDevice = {e["device"]: e for e in _events(writer.logFileName())}
    assert "full_test_pulse" in byDevice["Pipette1"]
    assert "full_test_pulse" not in byDevice["Pipette2"]
    with h5py.File(writer.testPulseFileName(), "r") as fh:
        assert list(fh["test_pulses"]) == ["Pipette1"]


def test_raw_capture_toggled_mid_recording_applies_in_order_and_reuses_one_sidecar(qapp, directory):
    pip = _FakePipette()
    writer = MultiPatchLogWriter(directory, pipettes=[pip]).start()
    pip.emitTestPulse(_make_test_pulse(1000.0))
    writer.setFullTestPulsePipettes([pip])
    pip.emitTestPulse(_make_test_pulse(1001.0))
    writer.setFullTestPulsePipettes([])
    pip.emitTestPulse(_make_test_pulse(1002.0))
    writer.setFullTestPulsePipettes([pip])
    pip.emitTestPulse(_make_test_pulse(1003.0))
    writer.stop()

    written = _events(writer.logFileName())
    saved = [e["start_time"] for e in written if "full_test_pulse" in e]
    assert saved == [1001.0, 1003.0]
    assert len(written) == 4
    assert [p.name for p in directory.created] == ["MultiPatch_000.log", "TestPulses_000.hdf5"]
    with h5py.File(writer.testPulseFileName(), "r") as fh:
        assert sorted(fh["test_pulses/Pipette1"]) == ["1001.0", "1003.0"]


def test_raw_capture_chosen_before_start_applies_from_the_start(qapp, directory):
    pip = _FakePipette()
    writer = MultiPatchLogWriter(directory, pipettes=[pip])
    writer.setFullTestPulsePipettes([pip])
    writer.start()
    pip.emitTestPulse(_make_test_pulse(1000.0))
    writer.stop()

    assert "full_test_pulse" in _events(writer.logFileName())[0]


def test_the_sidecar_is_created_on_the_callers_thread(qapp, directory):
    pip = _FakePipette()
    writer = MultiPatchLogWriter(directory, pipettes=[pip]).start()
    writer.setFullTestPulsePipettes([pip])
    pip.emitTestPulse(_make_test_pulse(1000.0))
    writer.stop()

    assert directory.creatingThreads == [threading.current_thread()] * 2


def test_test_pulse_analysis_rows_come_from_the_logged_analysis(qapp, directory):
    pip = _FakePipette()
    writer = MultiPatchLogWriter(directory, pipettes=[pip]).start()
    pip.emitTestPulse(_make_test_pulse(1000.0, resistance=1e9), event_time=1000.5)
    pip.emit({"device": "Pipette1", "event_time": 1001.0, "event": "state_change"})
    pip.emitTestPulse(_make_test_pulse(1002.0, resistance=2e9), event_time=1002.5)
    writer.stop()

    history = writer.testPulseAnalysis()
    # event_time is the event's emit time, as in the log -- not recording.start_time.
    assert np.array_equal(history["event_time"], [1000.5, 1002.5])
    assert np.array_equal(history["start_time"], [1000.0, 1002.0])
    assert np.array_equal(history["steady_state_resistance"], [1e9, 2e9])


def test_a_full_test_pulse_that_fails_to_save_still_gets_its_log_line(qapp, directory, caplog):
    class _UnsavableTestPulse:
        analysis = _analysis(1000.0)

    pip = _FakePipette()
    writer = MultiPatchLogWriter(directory, pipettes=[pip], full_test_pulse_pipettes=[pip]).start()
    with caplog.at_level(logging.ERROR):
        pip.emit(_testPulseEvent(_UnsavableTestPulse()))
        pip.emitTestPulse(_make_test_pulse(1001.0))
        writer.stop()

    first, second = _events(writer.logFileName())
    assert "full_test_pulse" not in first and first["start_time"] == 1000.0
    assert "full_test_pulse" in second
    assert any("MultiPatchLogWriter" in r.getMessage() for r in caplog.records)


# -- threading ----------------------------------------------------------------


def _runInThread(fn):
    errors = []

    def run():
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    return thread, errors


def test_stop_from_another_thread_writes_everything_emitted_before_it(qapp, directory):
    # Started and stopped on one worker thread (as Autopatch does) while a
    # second thread emits test pulses and other events.
    pip = _FakePipette()
    holder = {}
    emitted = []
    stopAt = threading.Event()
    stopped = threading.Event()

    def emitter():
        i = 0
        while not stopped.is_set():
            if i % 5 == 0:
                pip.emitTestPulse(_make_test_pulse(1000.0 + i), event_time=float(i))
            else:
                pip.emit({"device": "Pipette1", "event_time": float(i), "event": "move_stop"})
            emitted.append(i)
            i += 1
            if i == 200:
                stopAt.set()

    def worker():
        holder["writer"] = writer = MultiPatchLogWriter(
            directory, pipettes=[pip], full_test_pulse_pipettes=[pip]
        ).start()
        holder["emitThread"], holder["emitErrors"] = _runInThread(emitter)
        stopAt.wait(10)
        holder["emittedBeforeStop"] = len(emitted)
        writer.stop()
        stopped.set()

    workerThread, workerErrors = _runInThread(worker)
    workerThread.join(30)
    holder["emitThread"].join(10)

    assert workerErrors == [] and holder["emitErrors"] == []
    writer = holder["writer"]
    assert not writer._thread.is_alive()
    written = _events(writer.logFileName())
    assert len(written) >= holder["emittedBeforeStop"] >= 200
    assert [e["event_time"] for e in written] == [float(i) for i in range(len(written))]
    locations = [e["full_test_pulse"] for e in written if e["event"] == "test_pulse"]
    assert len(locations) == len(range(0, len(written), 5))
    with h5py.File(writer.testPulseFileName(), "r") as fh:
        for location in locations:
            assert location.split(":")[1] in fh


def test_stop_without_waiting_returns_at_once_and_the_thread_still_closes(qapp, directory):
    """MultiPatch stops this way from the GUI thread, so stop() must not join."""
    pip = _FakePipette()
    writer = MultiPatchLogWriter(directory, pipettes=[pip], full_test_pulse_pipettes=[pip]).start()
    release = threading.Event()
    saveTestPulse = writer._saveTestPulse

    def blockUntilReleased(deviceName, testPulse):
        release.wait(10)
        return saveTestPulse(deviceName, testPulse)

    writer._saveTestPulse = blockUntilReleased
    pip.emitTestPulse(_make_test_pulse(1000.0), event_time=1000.5)

    writer.stop(wait=False)
    assert writer._thread.is_alive()
    assert writer.isRecording() is False

    release.set()
    writer._thread.join(10)
    assert not writer._thread.is_alive()
    assert writer._logFile.closed
    (written,) = _events(writer.logFileName())
    assert written["event"] == "test_pulse"


def test_stop_warns_and_returns_when_the_writer_is_still_draining(qapp, directory, caplog):
    pip = _FakePipette()
    writer = MultiPatchLogWriter(directory, pipettes=[pip]).start()
    release = threading.Event()
    write = writer._write
    writer._write = lambda event: (release.wait(10), write(event))[1]
    pip.emit({"device": "Pipette1", "event_time": 1.0, "event": "move_stop"})

    with caplog.at_level(logging.WARNING):
        writer.stop(timeout=0.05)
    assert "still writing after stop()" in caplog.text

    release.set()
    writer._thread.join(10)
    assert writer._logFile.closed


def test_a_test_pulse_whose_analysis_raises_is_logged_and_writing_continues(qapp, directory, caplog):
    class _UnanalysableTestPulse:
        @property
        def analysis(self):
            raise ValueError("fit did not converge")

    pip = _FakePipette()
    writer = MultiPatchLogWriter(directory, pipettes=[pip]).start()
    with caplog.at_level(logging.ERROR):
        pip.emit(_testPulseEvent(_UnanalysableTestPulse()))
        pip.emit({"device": "Pipette1", "event_time": 6.0, "event": "move_stop"})
        writer.stop()

    (written,) = _events(writer.logFileName())
    assert written["event"] == "move_stop"
    assert any("MultiPatchLogWriter" in r.getMessage() for r in caplog.records)


# -- reading back ---------------------------------------------------------------


def _record_session(directory, start, count, pipName="Pipette1", raw=True):
    """One writer for one pipette over `count` test pulses starting at time `start`."""
    pip = _FakePipette(pipName)
    writer = MultiPatchLogWriter(
        directory, pipettes=[pip], full_test_pulse_pipettes=[pip] if raw else ()
    ).start()
    pip.emit({"device": pipName, "event_time": start - 0.5, "event": "state_change", "state": "bath"})
    for i in range(count):
        pip.emitTestPulse(_make_test_pulse(start + i))
    writer.stop()
    return writer


def test_the_reader_loads_a_new_logs_test_pulses_and_every_location_resolves(qapp, directory):
    from acq4.filetypes.MultiPatchLog import MultiPatchLogData

    writer = _record_session(directory, 1000.0, 3)

    data = MultiPatchLogData(writer.logFileName())

    stack = data.fullTestPulseStacks["Pipette1"]
    assert len(stack) == 3
    assert stack.at_time(1001.5).recording.start_time == 1001.0
    analysis = data["Pipette1"]["test_pulse"]
    assert np.array_equal(analysis["start_time"], [1000.0, 1001.0, 1002.0])
    for location in data["Pipette1"]["full_test_pulse"]:
        fh, dataset = _resolve(writer.logFileName(), location)
        with fh:
            assert float(dataset.name.rsplit("/", 1)[1]) in analysis["start_time"]


def test_each_log_in_a_directory_loads_only_its_own_sidecar(qapp, directory):
    # Autopatch writes one log and one sidecar per attempt into the same directory.
    from acq4.filetypes.MultiPatchLog import MultiPatchLogData

    first = _record_session(directory, 1000.0, 3)
    second = _record_session(directory, 2000.0, 2)

    assert len(MultiPatchLogData(first.logFileName()).fullTestPulseStacks["Pipette1"]) == 3
    assert len(MultiPatchLogData(second.logFileName()).fullTestPulseStacks["Pipette1"]) == 2


def test_a_log_recorded_without_raw_capture_has_no_stacks(qapp, directory):
    from acq4.filetypes.MultiPatchLog import MultiPatchLogData

    _record_session(directory, 1000.0, 2)  # a sidecar in the same directory
    writer = _record_session(directory, 1000.5, 2, raw=False)

    data = MultiPatchLogData(writer.logFileName())

    assert data.fullTestPulseStacks == {}
    assert len(data["Pipette1"]["test_pulse"]) == 2


def _write_old_style_log(path, device, locations, times):
    with open(path, "wb") as fh:
        for location, t in zip(locations, times):
            event = {"device": device, "event_time": t, "event": "test_pulse", **_analysis(t)}
            event["full_test_pulse"] = location
            fh.write(json.dumps(event).encode() + b",\n")


def test_the_reader_loads_an_old_style_log_from_its_location_strings(qapp, tmp_path):
    from neuroanalysis.test_pulse_stack import H5BackedTestPulseStack

    from acq4.filetypes.MultiPatchLog import MultiPatchLogData

    with h5py.File(tmp_path / "TestPulses.hdf5", "w") as fh:
        stack = H5BackedTestPulseStack(fh.create_group("test_pulses").create_group("Clamp1"))
        locations = [f"TestPulses.hdf5:{stack.append(_make_test_pulse(t))[1]}" for t in (1000.0, 1001.0)]
    _write_old_style_log(tmp_path / "MultiPatch.log", "Clamp1", locations, (1000.0, 1001.0))

    data = MultiPatchLogData(str(tmp_path / "MultiPatch.log"))

    stack = data.fullTestPulseStacks["Clamp1"]
    assert len(stack) == 2
    assert stack.at_time(1000.5).recording.start_time == 1000.0


def test_stacks_from_several_sidecars_are_merged_in_time_order(qapp, tmp_path):
    from neuroanalysis.test_pulse_stack import H5BackedTestPulseStack

    from acq4.filetypes.MultiPatchLog import MultiPatchLogData

    locations = []
    # Named so that sorting by file name puts the later pulses first.
    for name, times in (("A.hdf5", (1005.0, 1006.0)), ("B.hdf5", (1000.0, 1001.0))):
        with h5py.File(tmp_path / name, "w") as fh:
            stack = H5BackedTestPulseStack(fh.create_group("test_pulses").create_group("Clamp1"))
            locations += [(t, f"{name}:{stack.append(_make_test_pulse(t))[1]}") for t in times]
    locations.sort()
    _write_old_style_log(
        tmp_path / "MultiPatch.log", "Clamp1", [loc for _t, loc in locations], [t for t, _loc in locations]
    )

    stack = MultiPatchLogData(str(tmp_path / "MultiPatch.log")).fullTestPulseStacks["Clamp1"]

    assert len(stack) == 4
    assert stack.at_time(1003.0).recording.start_time == 1001.0
    assert stack.at_time(1005.5).recording.start_time == 1005.0


def test_the_reader_tolerates_blank_lines(qapp, directory):
    from acq4.filetypes.MultiPatchLog import MultiPatchLogData

    writer = MultiPatchLogWriter(directory).start()
    writer.record({"device": "Pipette1", "event_time": 1.0, "event": "state_change", "state": "bath"})
    writer.stop()
    with open(writer.logFileName(), "ab") as fh:
        fh.write(b"\n")

    data = MultiPatchLogData(writer.logFileName())

    assert "Pipette1" in data.devices()
    assert data.fullTestPulseStacks == {}


def test_the_analysis_tool_parses_an_event_log(qapp, directory):
    import sys
    from pathlib import Path

    toolsPath = str(Path(__file__).resolve().parents[3] / "tools" / "autopatch_analysis")
    if toolsPath not in sys.path:
        sys.path.insert(0, toolsPath)
    import autopatch_log

    pip = _FakePipette()
    writer = MultiPatchLogWriter(directory, pipettes=[pip], full_test_pulse_pipettes=[pip]).start()
    for t, state, old in ((1.0, "bath", "out"), (2.0, "approach", "bath")):
        writer.record({"device": "Pipette1", "event_time": t, "event": "state_change", "state": state, "old_state": old})
    pip.emitTestPulse(_make_test_pulse(1000.0), event_time=3.0)
    writer.stop()

    events = autopatch_log.parse_log_events(writer.logFileName())

    assert [e.get("state") for e in events if e["event"] == "state_change"] == ["bath", "approach"]
    (tp,) = [e for e in events if e["event"] == "test_pulse"]
    assert tp["steady_state_resistance"] == 1e9
