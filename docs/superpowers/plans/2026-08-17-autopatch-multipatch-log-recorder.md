# MultiPatch Log Recorder — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract MultiPatch's event-log writing into a reusable recorder that Autopatch can also construct, so an Autopatch run produces a log the MultiPatch viewer and `tools/autopatch_analysis` can both read.

**Architecture:** A new `MultiPatchLogRecorder` owns one log file, its optional full-test-pulse HDF5 sidecar, and the signal connections that feed them. It never touches device state. `MultiPatchWindow` is refactored onto it, so there is one implementation of the format rather than two. `PatchPipette.emitFullTestPulseData`'s boolean becomes a subscriber set so two recorders can coexist over one pipette.

**Tech Stack:** Python 3, PyQt (via `acq4.util.Qt`), numpy, h5py, `neuroanalysis.test_pulse_stack.H5BackedTestPulseStack`, pytest.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-17-autopatch-area5-details-widgets-design.md` §5, §6, §7. This plan implements phase 2 of its §11 phasing.
- **The recorder never touches device state.** In particular it must never call `clampDevice.resetTestPulseHistory()` — that is MultiPatch's Reset button, and a recorder doing it would let Autopatch wipe the history MultiPatch is plotting.
- **Format compatibility is the whole point.** A recorder-written file must be readable by `acq4.filetypes.MultiPatchLog.MultiPatchLogData` and by `tools/autopatch_analysis.autopatch_log`, and must differ from the current writer's output *only* by the dropped trailing comma.
- **The recorder lives on the GUI thread.** Its `sigNewEvent` connections must stay queued, since events are emitted from clamp and state-machine threads.
- **Python interpreter:** `/home/martin/.miniforge3/envs/acq4-gl/bin/python`. Run pytest as `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest`.
- **Commits:** conventional format, `--author="Martin Chase (claude) <outofculture@gmail.com>"`, footer `🤖 Generated with [Claude Code](https://claude.ai/code)`. Never `--no-verify`.
- **Not in this phase:** anything in `acq4/experiment/actions/fsm.py`, the `"test_pulse_history"` renderer, or any Autopatch action constructing a recorder. Those are phase 3. Nothing here has an Autopatch caller yet — that is deliberate, so the format lands behind its own tests before anything depends on it.

## File Structure

| File | Responsibility | Action |
| --- | --- | --- |
| `acq4/util/multipatch_log_recorder.py` | the recorder: one log file, its HDF5 sidecar, its subscriptions | Create |
| `acq4/util/tests/test_multipatch_log_recorder.py` | recorder behavior, the golden-output check, reader round-trips | Create |
| `acq4/devices/PatchPipette/patchpipette.py` | `requestFullTestPulseData` / `releaseFullTestPulseData` | Modify |
| `acq4/devices/PatchPipette/tests/test_full_test_pulse_subscription.py` | subscription refcounting | Create |
| `acq4/modules/MultiPatch/multipatch.py` | refactored onto the recorder | Modify |
| `acq4/modules/MultiPatch/tests/test_logfile.py` | the toggle-combination tests | Modify |
| `acq4/filetypes/MultiPatchLog.py` | blank-line guard in the reader | Modify |
| `tools/autopatch_analysis/tests/test_autopatch_log.py` | comma-free / legacy parity | Modify |

The recorder goes in `acq4/util/` rather than `acq4/filetypes/`: that package registers `FileType` *readers* for DataManager, and its `MultiPatchLog.py` is already over 1100 lines. It is not an attribute of `PatchPipette` because one attribute would mean one recorder per pipette, which is exactly the collision this phase exists to prevent.

---

### Task 1: `PatchPipette` full-test-pulse subscriptions

**Files:**
- Modify: `acq4/devices/PatchPipette/patchpipette.py:91,428-435`
- Test: `acq4/devices/PatchPipette/tests/test_full_test_pulse_subscription.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `PatchPipette.requestFullTestPulseData(token) -> None`, `PatchPipette.releaseFullTestPulseData(token) -> None`, `PatchPipette.emitsFullTestPulseData() -> bool`. `emitFullTestPulseData(bool)` is **removed**.

- [ ] **Step 1: Write the failing test**

Create `acq4/devices/PatchPipette/tests/test_full_test_pulse_subscription.py`:

```python
"""Tests for PatchPipette's full-test-pulse subscription: independent recorders
must each be able to request the full test-pulse object without one's release
silencing the other's."""
import pytest

from acq4.devices.PatchPipette.patchpipette import PatchPipette


class _Pip:
    """Exercises the subscription methods against a bare instance, without
    standing up a real PatchPipette (which needs a Manager and devices)."""

    requestFullTestPulseData = PatchPipette.requestFullTestPulseData
    releaseFullTestPulseData = PatchPipette.releaseFullTestPulseData
    emitsFullTestPulseData = PatchPipette.emitsFullTestPulseData

    def __init__(self):
        self._fullTestPulseSubscribers = set()


def test_no_subscribers_means_no_full_data():
    assert _Pip().emitsFullTestPulseData() is False


def test_one_subscriber_turns_it_on():
    pip = _Pip()
    pip.requestFullTestPulseData("recorder-a")
    assert pip.emitsFullTestPulseData() is True


def test_releasing_the_only_subscriber_turns_it_off():
    pip = _Pip()
    token = object()
    pip.requestFullTestPulseData(token)
    pip.releaseFullTestPulseData(token)
    assert pip.emitsFullTestPulseData() is False


def test_one_recorder_releasing_does_not_silence_another():
    # The whole reason this is a set and not a bool: Autopatch stopping its
    # recorder must not switch off MultiPatch's full-test-pulse capture.
    pip = _Pip()
    autopatch, multipatch = object(), object()
    pip.requestFullTestPulseData(autopatch)
    pip.requestFullTestPulseData(multipatch)

    pip.releaseFullTestPulseData(autopatch)

    assert pip.emitsFullTestPulseData() is True


def test_requesting_twice_with_one_token_is_idempotent():
    pip = _Pip()
    token = object()
    pip.requestFullTestPulseData(token)
    pip.requestFullTestPulseData(token)
    pip.releaseFullTestPulseData(token)
    assert pip.emitsFullTestPulseData() is False


def test_releasing_an_unknown_token_is_harmless():
    # stop() is idempotent, so it may release a token it already released.
    pip = _Pip()
    pip.releaseFullTestPulseData(object())
    assert pip.emitsFullTestPulseData() is False


def test_the_old_boolean_setter_is_gone():
    # A bare setter is what let the last caller to stop win; leaving it in place
    # would leave that footgun loaded.
    assert not hasattr(PatchPipette, "emitFullTestPulseData")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/devices/PatchPipette/tests/test_full_test_pulse_subscription.py -v`

Expected: FAIL with `AttributeError: type object 'PatchPipette' has no attribute 'requestFullTestPulseData'`.

- [ ] **Step 3: Replace the flag with a subscriber set**

In `acq4/devices/PatchPipette/patchpipette.py`, replace line 91's `self._emitTestPulseData = False` with:

```python
        # Tokens held by whoever currently wants test_pulse events to carry the
        # full PatchClampTestPulse object, not just its analysis. A set rather
        # than a bool because independent recorders subscribe independently:
        # with a bool, whichever one stopped last would silence the others.
        # Holds tokens, never the subscribers themselves, so nothing here keeps
        # a recorder alive.
        self._fullTestPulseSubscribers = set()
```

Replace `emitFullTestPulseData` (lines 428-429) with:

```python
    def requestFullTestPulseData(self, token) -> None:
        """Ask that test_pulse events carry the full PatchClampTestPulse object.

        `token` identifies the subscriber and is what releaseFullTestPulseData()
        takes back; any hashable will do. Idempotent per token.
        """
        self._fullTestPulseSubscribers.add(token)

    def releaseFullTestPulseData(self, token) -> None:
        """Withdraw `token`'s request. Full data keeps flowing while any other
        subscriber holds one. Releasing an unknown token is a no-op, so a
        recorder's idempotent stop() can call it freely."""
        self._fullTestPulseSubscribers.discard(token)

    def emitsFullTestPulseData(self) -> bool:
        return bool(self._fullTestPulseSubscribers)
```

Replace the `if self._emitTestPulseData:` test in `_testPulseFinished` (line 433) with:

```python
        if self._fullTestPulseSubscribers:
```

- [ ] **Step 4: Fix the one existing caller**

`acq4/modules/MultiPatch/multipatch.py:632` calls `pip.emitFullTestPulseData(rec)` inside `recordTestPulsesToggled`. Replace that line with:

```python
            if rec:
                pip.requestFullTestPulseData(self)
            else:
                pip.releaseFullTestPulseData(self)
```

`self` (the `MultiPatchWindow`) is its token; Task 6 moves this onto the recorder.

Verify no other caller remains:

Run: `grep -rn "emitFullTestPulseData\|_emitTestPulseData" acq4/ tools/`

Expected: no output.

- [ ] **Step 5: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/devices/PatchPipette/tests -v`

Expected: PASS, 7 new tests plus every pre-existing PatchPipette test.

- [ ] **Step 6: Commit**

```bash
git add acq4/devices/PatchPipette/patchpipette.py acq4/devices/PatchPipette/tests/test_full_test_pulse_subscription.py acq4/modules/MultiPatch/multipatch.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
refactor(patchpipette): make full-test-pulse data a subscription

emitFullTestPulseData set a bare boolean, so with two independent recorders
whichever stopped last won -- one stopping would silence the other's
full-test-pulse capture. A subscriber set ORs the requests instead, and it
holds tokens rather than subscribers so nothing keeps a recorder alive.

The boolean setter is removed rather than kept as a wrapper: it had exactly
one caller, and leaving it would leave the footgun loaded.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 2: The recorder's log file and JSONL writing

**Files:**
- Create: `acq4/util/multipatch_log_recorder.py`
- Test: `acq4/util/tests/test_multipatch_log_recorder.py`

**Interfaces:**
- Consumes: `acq4.util.json_encoder.ACQ4JSONEncoder`.
- Produces: `MultiPatchLogRecorder(directory, pipettes=(), microscope=None, record_full_test_pulses=True, write_events=True, initial_records=())`; `.record(event) -> None`; `.stop() -> None`; `.logFileName() -> str | None`; `.isRecording() -> bool`.

`write_events` exists because MultiPatch's two record buttons are independent today: test-pulse recording works with the event log switched off. Task 6 maps both toggles onto one recorder, which needs each to be separately switchable.

- [ ] **Step 1: Write the failing tests**

Create `acq4/util/tests/test_multipatch_log_recorder.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_multipatch_log_recorder.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'acq4.util.multipatch_log_recorder'`.

- [ ] **Step 3: Create the module with the file lifecycle**

Create `acq4/util/multipatch_log_recorder.py`:

```python
"""MultiPatchLogRecorder: writes a PatchPipette event stream to a MultiPatch-
format log file, with an optional full-test-pulse HDF5 sidecar beside it."""
from __future__ import annotations

import json

from acq4.util import Qt
from acq4.util.json_encoder import ACQ4JSONEncoder

# Base name of the log file, matched case-insensitively by
# acq4.filetypes.MultiPatchLog and by tools/autopatch_analysis. Changing it
# makes the resulting file invisible to both readers.
LOG_FILE_NAME = "MultiPatch.log"


class MultiPatchLogRecorder(Qt.QObject):
    """One MultiPatch-format log file and the subscriptions that fill it.

    Owns a file and (optionally) an HDF5 test-pulse stack, and **nothing else**:
    it never touches device state. In particular it never resets a clamp's
    test-pulse history -- that is MultiPatch's Reset button, and a recorder
    doing it would let one module wipe the history another is plotting.

    Any number of recorders may observe the same pipette. That is what lets
    Autopatch record a patch attempt while MultiPatch records the session, with
    neither able to switch the other off (see
    PatchPipette.requestFullTestPulseData).

    A QObject on the GUI thread: events are emitted from clamp and state-machine
    threads, and the default (queued) connections are what marshal them here
    before anything is written.

    Parameters
    ----------
    directory : DirHandle
        Where the log file and its sidecar are created.
    pipettes : iterable of PatchPipette
        Whose sigNewEvent streams to record. One for an Autopatch action, all of
        them for MultiPatch.
    microscope : Microscope or None
        Optional; its surface-depth changes are recorded too.
    record_full_test_pulses : bool
        Whether test_pulse events carry the whole recording into an HDF5
        sidecar, rather than just their analysis.
    write_events : bool
        Whether to write the log file at all. False records full test pulses
        without an event log, which is a combination MultiPatch's two
        independent record buttons allow.
    initial_records : iterable of dict
        Records replayed into the fresh file before any live event, for a caller
        that has been accumulating events before recording started.
    """

    def __init__(
        self,
        directory,
        pipettes=(),
        microscope=None,
        record_full_test_pulses: bool = True,
        write_events: bool = True,
        initial_records=(),
    ):
        super().__init__()
        self._directory = directory
        self._pipettes = list(pipettes)
        self._microscope = microscope
        self._stopped = False
        self._logFile = None
        if write_events:
            handle = directory.createFile(LOG_FILE_NAME, autoIncrement=True)
            self._logFile = open(handle.name(), "ab")
        for record in initial_records:
            self.record(record)

    def logFileName(self) -> str | None:
        return None if self._logFile is None else self._logFile.name

    def isRecording(self) -> bool:
        return not self._stopped

    def record(self, event) -> None:
        """Write one record. Ignored once stopped, so a late queued event
        arriving after the action that opened this recorder has ended does not
        reopen a closed file."""
        if self._stopped:
            return
        self._writeRecords([event])

    def _writeRecords(self, records) -> None:
        if self._logFile is None:
            return
        for record in records:
            # One JSON object per line, with no trailing comma. Both readers
            # strip b",\r\n" as a character set rather than as a suffix, so
            # they parse this and the historical comma-terminated form alike.
            self._logFile.write(
                json.dumps(record, cls=ACQ4JSONEncoder).encode("utf8") + b"\n"
            )
        self._logFile.flush()

    def stop(self) -> None:
        """Release everything this recorder holds. Idempotent."""
        if self._stopped:
            return
        self._stopped = True
        if self._logFile is not None:
            self._logFile.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_multipatch_log_recorder.py -v`

Expected: PASS, 10 tests.

- [ ] **Step 5: Commit**

```bash
git add acq4/util/multipatch_log_recorder.py acq4/util/tests/test_multipatch_log_recorder.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat(util): add MultiPatchLogRecorder's log-file writing

The writer half of the MultiPatch log format, extracted so Autopatch can
produce a log the MultiPatch viewer and tools/autopatch_analysis both read.

Writes clean JSONL rather than the historical trailing-comma form: both
readers strip b",\r\n" as a character set rather than a suffix, so they
already parse either. Owns a file and nothing else -- never device state, and
in particular never a clamp's test-pulse history, which is MultiPatch's Reset
button and not a recorder's business.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 3: The full-test-pulse HDF5 sidecar

**Files:**
- Modify: `acq4/util/multipatch_log_recorder.py`
- Test: `acq4/util/tests/test_multipatch_log_recorder.py`

**Interfaces:**
- Consumes: Task 2's recorder; `neuroanalysis.test_pulse_stack.H5BackedTestPulseStack`.
- Produces: `MultiPatchLogRecorder.setRecordFullTestPulses(bool) -> None`; `.recordsFullTestPulses() -> bool`. The `full_test_pulse` field of a written record becomes `"<relpath>:<h5path>"`.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/util/tests/test_multipatch_log_recorder.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_multipatch_log_recorder.py -v -k "sidecar or test_pulse_object or stripped or set_record"`

Expected: FAIL — `AttributeError: type object 'MultiPatchLogRecorder' has no attribute '_makeTestPulseStack'` from the fixture's monkeypatch.

- [ ] **Step 3: Add the sidecar**

In `acq4/util/multipatch_log_recorder.py`, add imports:

```python
import os

import h5py
from neuroanalysis.test_pulse_stack import H5BackedTestPulseStack
```

Add the sidecar constant beside `LOG_FILE_NAME`:

```python
# Base name of the full-test-pulse sidecar, and the group each device's stack
# lives at inside it. MultiPatchLogData reads exactly `test_pulses/{device}`.
TEST_PULSE_FILE_NAME = "TestPulses.hdf5"
TEST_PULSE_GROUP = "test_pulses"
```

In `__init__`, after the log file is opened and before `initial_records` are replayed:

```python
        self._recordFullTestPulses = record_full_test_pulses
        # device name -> its H5BackedTestPulseStack, created on first use so a
        # recorder that never sees a full test pulse writes no sidecar at all.
        self._testPulseStacks = {}
        self._testPulseContainer = None
```

Add the methods before `stop`:

```python
    def recordsFullTestPulses(self) -> bool:
        return self._recordFullTestPulses

    def setRecordFullTestPulses(self, record: bool) -> None:
        """Turn full-test-pulse capture on or off for the rest of this
        recorder's life. Existing stacks are kept: turning capture back on
        appends to the same sidecar rather than starting a second one."""
        self._recordFullTestPulses = bool(record)

    def _makeTestPulseStack(self, deviceName: str):
        """The HDF5 stack for one device, creating the sidecar on first use."""
        if self._testPulseContainer is None:
            handle = self._directory.createFile(TEST_PULSE_FILE_NAME, autoIncrement=True)
            self._testPulseContainer = h5py.File(handle.name(), "a")
            self._testPulseContainer.create_group(TEST_PULSE_GROUP)
        group = self._testPulseContainer[TEST_PULSE_GROUP].create_group(deviceName)
        group.attrs["device"] = deviceName
        return H5BackedTestPulseStack(group)

    def _divertFullTestPulse(self, record):
        """Move a record's full_test_pulse object into the sidecar, replacing the
        field with the "<relpath>:<h5path>" location the reader resolves.

        The relative path is relative to the *log file's* directory, because
        that is what MultiPatchLogData joins it against. Returns a copy: the
        caller's dict belongs to the device that emitted it.
        """
        testPulse = record["full_test_pulse"]
        record = {k: v for k, v in record.items() if k != "full_test_pulse"}
        if not self._recordFullTestPulses:
            # Nowhere to put it, and it must never reach the JSON encoder.
            return record
        deviceName = record.get("device")
        stack = self._testPulseStacks.get(deviceName)
        if stack is None:
            stack = self._testPulseStacks[deviceName] = self._makeTestPulseStack(deviceName)
        filename, h5path = stack.append(testPulse)
        if self._logFile is not None:
            filename = os.path.relpath(filename, os.path.dirname(self._logFile.name))
        record["full_test_pulse"] = f"{filename}:{h5path}"
        return record
```

Rewrite `_writeRecords` to divert first and flush the stacks:

```python
    def _writeRecords(self, records) -> None:
        for record in records:
            if "full_test_pulse" in record:
                record = self._divertFullTestPulse(record)
            if self._logFile is not None:
                # One JSON object per line, with no trailing comma. Both readers
                # strip b",\r\n" as a character set rather than as a suffix, so
                # they parse this and the historical comma-terminated form alike.
                self._logFile.write(
                    json.dumps(record, cls=ACQ4JSONEncoder).encode("utf8") + b"\n"
                )
        if self._logFile is not None:
            self._logFile.flush()
        for stack in self._testPulseStacks.values():
            stack.flush()
```

Note `record()`'s early return on `self._logFile is None` is gone: a recorder with `write_events=False` still has to divert test pulses into its sidecar.

Extend `stop` to close the sidecar:

```python
    def stop(self) -> None:
        """Release everything this recorder holds. Idempotent."""
        if self._stopped:
            return
        self._stopped = True
        for stack in self._testPulseStacks.values():
            stack.close()
        self._testPulseStacks = {}
        if self._testPulseContainer is not None:
            self._testPulseContainer.close()
            self._testPulseContainer = None
        if self._logFile is not None:
            self._logFile.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_multipatch_log_recorder.py -v`

Expected: PASS, 15 tests.

- [ ] **Step 5: Commit**

```bash
git add acq4/util/multipatch_log_recorder.py acq4/util/tests/test_multipatch_log_recorder.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat(util): divert full test pulses into the recorder's HDF5 sidecar

Each device's stack lives at test_pulses/{device}, and the event's field
becomes the "<relpath>:<h5path>" location MultiPatchLogData resolves against
the log file's own directory -- so an absolute path here would break any
viewer opening moved data.

The sidecar is created on first use, so a recorder that never sees a full
test pulse writes no HDF5 at all. With capture off, the test-pulse object is
dropped rather than handed to the JSON encoder.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 4: Subscriptions, and the accumulated test-pulse analysis

**Files:**
- Modify: `acq4/util/multipatch_log_recorder.py`
- Test: `acq4/util/tests/test_multipatch_log_recorder.py`

**Interfaces:**
- Consumes: Task 1's `requestFullTestPulseData`/`releaseFullTestPulseData`; Task 3's recorder; `acq4.filetypes.MultiPatchLog.TEST_PULSE_NUMPY_DTYPE`.
- Produces: `MultiPatchLogRecorder.testPulseAnalysis() -> np.ndarray` (structured, `TEST_PULSE_NUMPY_DTYPE`). Phase 3 consumes exactly this.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/util/tests/test_multipatch_log_recorder.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_multipatch_log_recorder.py -v -k "pipette_events or subscription or requested or microscope or analysis or reference"`

Expected: FAIL — nothing connects `sigNewEvent`, so no records are written, and `testPulseAnalysis` does not exist.

- [ ] **Step 3: Add subscriptions and the analysis accumulator**

In `acq4/util/multipatch_log_recorder.py`, add imports:

```python
import numpy as np

from acq4.filetypes.MultiPatchLog import TEST_PULSE_NUMPY_DTYPE
from acq4.util import ptime

# The analysis field names a test_pulse event can carry, taken from the dtype
# the readers and PatchClamp's own history both use, so an accumulated array is
# interchangeable with clampDevice.testPulseHistory()'s.
_TEST_PULSE_FIELDS = tuple(name for name, _type in TEST_PULSE_NUMPY_DTYPE)
```

In `__init__`, after the sidecar attributes:

```python
        # One row per test_pulse event this recorder saw, in order. Accumulated
        # here rather than read from clampDevice.testPulseHistory() because the
        # device's history is reset mid-patch -- approach.py:251 does it on every
        # attempt -- so slicing that by time silently loses data.
        self._testPulseRows: list[tuple] = []
        for pip in self._pipettes:
            pip.sigNewEvent.connect(self._onPipetteEvent)
        if microscope is not None:
            microscope.sigSurfaceDepthChanged.connect(self._onSurfaceDepthChanged)
        if self._recordFullTestPulses:
            self._requestFullTestPulseData()
```

Note the `initial_records` replay must move to *after* this block, so a recorder constructed with both history and live pipettes writes history first.

Add the methods before `stop`:

```python
    def _requestFullTestPulseData(self) -> None:
        for pip in self._pipettes:
            pip.requestFullTestPulseData(self)

    def _releaseFullTestPulseData(self) -> None:
        for pip in self._pipettes:
            pip.releaseFullTestPulseData(self)

    def _onPipetteEvent(self, _pipette, event) -> None:
        if event.get("event") == "test_pulse":
            self._testPulseRows.append(
                tuple(_nanIfNone(event.get(field)) for field in _TEST_PULSE_FIELDS)
            )
        self.record(event)

    def _onSurfaceDepthChanged(self, depth) -> None:
        self.record(
            {
                "device": self._microscope.name(),
                "event_time": ptime.time(),
                "event": "surface_depth_changed",
                "surface_depth": depth,
            }
        )

    def testPulseAnalysis(self) -> np.ndarray:
        """Every test_pulse event this recorder saw, as a structured array with
        the same dtype as clampDevice.testPulseHistory().

        This -- not the device's own history -- is what a UI should plot for one
        action's span: the device's is reset mid-patch by the approach state, so
        slicing it by the action's start and end times loses whatever preceded
        the reset.
        """
        return np.array(self._testPulseRows, dtype=TEST_PULSE_NUMPY_DTYPE)
```

Add the module-level helper after the constants:

```python
def _nanIfNone(value):
    """NaN for a missing or None analysis field, matching how PatchClamp's own
    test-pulse history records one."""
    return np.nan if value is None else value
```

Extend `setRecordFullTestPulses` to move the subscription with the flag:

```python
    def setRecordFullTestPulses(self, record: bool) -> None:
        """Turn full-test-pulse capture on or off for the rest of this
        recorder's life. Existing stacks are kept: turning capture back on
        appends to the same sidecar rather than starting a second one."""
        record = bool(record)
        if record == self._recordFullTestPulses:
            return
        self._recordFullTestPulses = record
        if record:
            self._requestFullTestPulseData()
        else:
            self._releaseFullTestPulseData()
```

Extend `stop` to sever everything, before it closes the files:

```python
        self._releaseFullTestPulseData()
        for pip in self._pipettes:
            Qt.disconnect(pip.sigNewEvent, self._onPipetteEvent)
        # Dropped so a stopped recorder is not what keeps a device object
        # alive, and so a second stop() has nothing left to disconnect.
        self._pipettes = []
        if self._microscope is not None:
            Qt.disconnect(
                self._microscope.sigSurfaceDepthChanged, self._onSurfaceDepthChanged
            )
            self._microscope = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_multipatch_log_recorder.py -v`

Expected: PASS, 26 tests.

- [ ] **Step 5: Commit**

```bash
git add acq4/util/multipatch_log_recorder.py acq4/util/tests/test_multipatch_log_recorder.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat(util): subscribe the recorder to its pipettes, and accumulate analysis

testPulseAnalysis() returns the same dtype clampDevice.testPulseHistory()
does, but accumulated from the events this recorder actually saw. That is not
a convenience: the approach state resets the device's history mid-patch, so
slicing the device's by an action's start and end times silently loses
whatever preceded the reset.

stop() releases the full-test-pulse tokens, disconnects every signal, and
drops its device references, so a stopped recorder holds nothing.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 5: The golden-output check and the reader round-trips

**Files:**
- Test: `acq4/util/tests/test_multipatch_log_recorder.py`
- Modify: `acq4/filetypes/MultiPatchLog.py:232`
- Modify: `tools/autopatch_analysis/tests/test_autopatch_log.py:17-19`

**Interfaces:**
- Consumes: Tasks 2–4's recorder.
- Produces: no production API. This is the safety net that makes "identical behavior, so the viewer still renders it" a tested claim.

This task exists because `acq4/modules/MultiPatch/tests/test_logfile.py` covers only `IrregularTimeSeries` and nothing in the logging path — so before Task 6 rewrites that path, its output has to be pinned against the current implementation.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/util/tests/test_multipatch_log_recorder.py`:

```python
# -- golden output vs. the implementation being replaced ----------------------


def _referenceWriteRecords(records, logPath):
    """The pre-refactor MultiPatchWindow.writeRecords, verbatim apart from the
    test-pulse-stack branch, held here as the reference the recorder's output is
    checked against. Deliberately duplicated rather than imported: its whole
    job is to keep saying what the old code said after the old code is gone."""
    from acq4.util.json_encoder import ACQ4JSONEncoder

    with open(logPath, "ab") as fh:
        for rec in records:
            rec = {k: v for k, v in rec.items() if k != "full_test_pulse"}
            fh.write(json.dumps(rec, cls=ACQ4JSONEncoder).encode("utf8") + b",\n")
        fh.flush()


_GOLDEN_EVENTS = [
    {"device": "Clamp1", "event_time": 1.0, "event": "state_change", "state": "bath"},
    {"device": "Clamp1", "event_time": 1.5, "event": "move_stop", "position": [1.0, 2.0, 3.0]},
    {
        "device": "Clamp1",
        "event_time": 2.0,
        "event": "test_pulse",
        "baseline_potential": -0.07,
        "steady_state_resistance": 1.5e9,
        "capacitance": None,
    },
    {"device": "Clamp1", "event_time": 2.5, "event": "pressure_changed", "pressure": 0.0},
    {"device": None, "event_time": 3.0, "event": "global patch profiles changed", "profile": "{}"},
]


def test_recorder_output_matches_the_reference_apart_from_the_comma(qapp, directory, tmp_path):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    recorder = MultiPatchLogRecorder(directory, record_full_test_pulses=False)
    try:
        for event in _GOLDEN_EVENTS:
            recorder.record(event)
    finally:
        recorder.stop()

    referencePath = tmp_path / "reference.log"
    _referenceWriteRecords(_GOLDEN_EVENTS, referencePath)

    ours = _lines(recorder.logFileName())
    theirs = _lines(referencePath)
    assert len(ours) == len(theirs)
    for ourLine, theirLine in zip(ours, theirs):
        # Byte-for-byte the same record; only the trailing comma differs.
        assert ourLine.rstrip(b"\r\n") == theirLine.rstrip(b"\r\n").rstrip(b",")


def test_recorder_output_parses_identically_to_the_reference(qapp, directory, tmp_path):
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    recorder = MultiPatchLogRecorder(directory, record_full_test_pulses=False)
    try:
        for event in _GOLDEN_EVENTS:
            recorder.record(event)
    finally:
        recorder.stop()
    referencePath = tmp_path / "reference.log"
    _referenceWriteRecords(_GOLDEN_EVENTS, referencePath)

    def parse(path):
        return [json.loads(line.rstrip(b",\r\n")) for line in _lines(path)]

    assert parse(recorder.logFileName()) == parse(referencePath)


# -- reader round-trips ------------------------------------------------------


def test_the_multipatch_log_reader_parses_a_recorder_file(qapp, directory):
    from acq4.filetypes.MultiPatchLog import MultiPatchLogData
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    recorder = MultiPatchLogRecorder(directory, record_full_test_pulses=False)
    try:
        for event in _GOLDEN_EVENTS:
            if event["device"] is not None:
                recorder.record(event)
    finally:
        recorder.stop()

    data = MultiPatchLogData(recorder.logFileName())

    assert "Clamp1" in data.devices()
    assert data.firstTime() == 1.0
    assert data.lastTime() == 2.5


def test_the_analysis_tool_parses_a_recorder_file(qapp, directory):
    import sys
    from pathlib import Path

    toolsPath = str(Path(__file__).resolve().parents[3] / "tools" / "autopatch_analysis")
    if toolsPath not in sys.path:
        sys.path.insert(0, toolsPath)
    import autopatch_log

    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    recorder = MultiPatchLogRecorder(directory, record_full_test_pulses=False)
    try:
        recorder.record(
            {
                "device": "Clamp1",
                "event_time": 1.0,
                "event": "state_change",
                "state": "bath",
                "old_state": "out",
            }
        )
        recorder.record(
            {
                "device": "Clamp1",
                "event_time": 2.0,
                "event": "state_change",
                "state": "approach",
                "old_state": "bath",
            }
        )
    finally:
        recorder.stop()

    events = autopatch_log.parse_log_events(recorder.logFileName())

    assert [e["state"] for e in events] == ["bath", "approach"]
```

In `tools/autopatch_analysis/tests/test_autopatch_log.py`, make the comma tolerance explicit. Change `_write` (lines 17-19) to take the terminator, defaulting to the legacy form so every existing caller keeps testing it:

```python
def _write(tmp_path, lines, name="MultiPatch_000.log", terminator=",\n"):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(line + terminator for line in lines))
    return p
```

and add a parity test at the end of the file:

```python
def test_comma_free_and_legacy_lines_parse_identically(tmp_path):
    """The writer emits clean JSONL; historical files end every line with a
    comma. rstrip(b",\\r\\n") is a character-set strip, not a suffix strip, so
    both forms must yield the same records -- pinned here rather than left to
    luck."""
    events = [_state(0.0, "bath", "out"), _state(5.0, "out", "bath")]
    legacy = _write(tmp_path / "legacy", events)
    modern = _write(tmp_path / "modern", events, terminator="\n")

    assert parse_log_events(str(legacy)) == parse_log_events(str(modern))
```

Add `parse_log_events` to that file's imports if it is not already imported.

- [ ] **Step 2: Run tests to verify they fail or reveal the reader gap**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests/test_multipatch_log_recorder.py tools/autopatch_analysis/tests/test_autopatch_log.py -v`

Expected: the golden and round-trip tests PASS if Tasks 2–4 are correct. Any failure here is a real format discrepancy — fix the recorder, never the reference implementation or the expected bytes.

The reader entry point is `parse_log_events(path: str) -> list[dict]` at `tools/autopatch_analysis/autopatch_log.py:67`; it takes a `str`, so the tests above pass `str(path)`.

- [ ] **Step 3: Add the reader's blank-line guard**

`acq4/filetypes/MultiPatchLog.py:232` parses every line with no blank-line guard, where `tools/autopatch_analysis/autopatch_log.py:77` has one. It is latent today rather than triggered — a file ending in a newline yields no trailing empty line when iterated — but the two readers should agree. Replace that line:

```python
            events: list[dict[str, Any]] = [
                json.loads(stripped)
                for stripped in (line.rstrip(b',\r\n') for line in fh)
                if stripped.strip()
            ]
```

- [ ] **Step 4: Add a test for the guard**

Append to `acq4/util/tests/test_multipatch_log_recorder.py`:

```python
def test_the_reader_tolerates_blank_lines(qapp, directory):
    # Parity with tools/autopatch_analysis, which has always skipped them.
    from acq4.filetypes.MultiPatchLog import MultiPatchLogData
    from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder

    recorder = MultiPatchLogRecorder(directory, record_full_test_pulses=False)
    try:
        recorder.record(
            {"device": "Clamp1", "event_time": 1.0, "event": "state_change", "state": "bath"}
        )
    finally:
        recorder.stop()
    with open(recorder.logFileName(), "ab") as fh:
        fh.write(b"\n")

    data = MultiPatchLogData(recorder.logFileName())

    assert "Clamp1" in data.devices()
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests acq4/filetypes/tests tools/autopatch_analysis/tests -v`

Expected: PASS, all tests.

- [ ] **Step 6: Commit**

```bash
git add acq4/util/tests/test_multipatch_log_recorder.py acq4/filetypes/MultiPatchLog.py tools/autopatch_analysis/tests/test_autopatch_log.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
test(util): pin the recorder's output against the writer it replaces

MultiPatch's only test file covers IrregularTimeSeries and nothing in the
logging path, so before that path is rewritten its output has to be pinned.
A reference copy of the current writeRecords lives in the test, deliberately
duplicated rather than imported: its job is to keep saying what the old code
said after the old code is gone.

Also round-trips a recorder file through both readers, pins that comma-free
and legacy lines parse identically, and gives the MultiPatchLog reader the
blank-line guard tools/autopatch_analysis has always had.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 6: Refactor `MultiPatchWindow` onto the recorder

**Files:**
- Modify: `acq4/modules/MultiPatch/multipatch.py:50-52,601-665`
- Test: `acq4/modules/MultiPatch/tests/test_logfile.py`

**Interfaces:**
- Consumes: the full recorder from Tasks 2–4.
- Produces: `MultiPatchWindow._recorder: MultiPatchLogRecorder | None`. `writeRecords` is **removed**; `recordEvent`, `resetHistory`, and `eventHistory` remain.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/modules/MultiPatch/tests/test_logfile.py`:

```python
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
```

The remaining toggle-combination coverage requires a `MultiPatchWindow` instance, which needs a Manager. Add this integration-style test guarded on the manager fixture the repo already uses for module tests; if none exists, note that in the task report and leave the four combinations to live testing rather than inventing a Manager fake:

Run: `grep -rn "def manager\|getManager" acq4/modules/*/tests/*.py | head`

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/MultiPatch/tests/test_logfile.py -v`

Expected: FAIL on `test_write_records_is_gone` (it still exists) and on `test_the_recorder_never_resets_device_state` only if the recorder wrongly touches device state — that one should already pass.

- [ ] **Step 3: Import the recorder and replace the state**

In `acq4/modules/MultiPatch/multipatch.py`, add to the imports:

```python
from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder
```

Replace lines 50-51 (`self._eventStorageFile = None` and `self._testPulseStacks = {}`) with:

```python
        # The single recorder this window's two record buttons drive, or None
        # while both are off. One instance covering every pipette, the
        # microscope, and this window's own profile records -- the same
        # single-file behavior the two buttons have always produced.
        self._recorder = None
```

- [ ] **Step 4: Rewrite the two toggles**

Replace `recordToggled` (lines 601-612) and `recordTestPulsesToggled` (lines 614-632) with:

```python
    def recordToggled(self, rec):
        if not rec:
            self.resetHistory()
        self._syncRecorder(
            writeEvents=rec,
            recordTestPulses=self.ui.recordTestPulsesBtn.isChecked(),
            replayHistory=rec,
        )
        if rec:
            profile_data = PatchPipetteStateManager.buildPatchProfilesParameters().getValues()
            self.patchProfilesChanged(profile_data)

    def recordTestPulsesToggled(self, rec):
        self._syncRecorder(
            writeEvents=self.ui.recordBtn.isChecked(),
            recordTestPulses=rec,
            replayHistory=False,
        )

    def _syncRecorder(self, writeEvents: bool, recordTestPulses: bool, replayHistory: bool):
        """Bring self._recorder in line with the two record buttons.

        The buttons are independent -- test-pulse capture works with the event
        log off -- so a recorder exists while *either* is on, with each button
        mapped to one of its options. Switching a button that does not need a
        different recorder adjusts the live one in place, so toggling test
        pulses mid-session does not start a second log file.
        """
        if not writeEvents and not recordTestPulses:
            if self._recorder is not None:
                self._recorder.stop()
                self._recorder = None
            return
        if self._recorder is not None and self._recorder.write_events == writeEvents:
            self._recorder.setRecordFullTestPulses(recordTestPulses)
            return
        if self._recorder is not None:
            self._recorder.stop()
        self._recorder = MultiPatchLogRecorder(
            getManager().getCurrentDir(),
            pipettes=[p for p in self.pips if isinstance(p, PatchPipette)],
            microscope=self.microscope,
            record_full_test_pulses=recordTestPulses,
            write_events=writeEvents,
            initial_records=list(self.eventHistory) if replayHistory else (),
        )
```

`write_events` must be readable off the recorder for the in-place branch above, so expose it in `acq4/util/multipatch_log_recorder.py`'s `__init__`:

```python
        self.write_events = bool(write_events)
```

and use `self.write_events` in place of the local `write_events` for the rest of that method.

- [ ] **Step 5: Delete the window's own writing, and stop double-recording**

Delete `writeRecords` (lines 649-665) entirely.

Replace `recordEvent` (lines 634-639) with:

```python
    def recordEvent(self, event):
        """Record one event this window originates -- a patch-profile change, or
        a microscope surface-depth change.

        Pipette events are NOT routed through here: the recorder subscribes to
        each pipette's sigNewEvent directly, so passing them along as well
        would write every one of them twice.
        """
        if not self.eventHistory:
            self.resetHistory()
        if self._recorder is not None:
            self._recorder.record(event)
        event = {k: v for k, v in event.items() if k != 'full_test_pulse'}
        self.eventHistory.append(event)
```

Delete `pipetteEvent` (lines 589-590) and the `pip.sigNewEvent.connect(self.pipetteEvent)` line at line 86 — the recorder owns that subscription now. Then verify the window's in-memory `eventHistory` still gets pipette events, which `PipetteControl`'s own event log does not cover:

Run: `grep -rn "eventHistory" acq4/modules/MultiPatch/multipatch.py`

If `eventHistory`'s only remaining writer is `recordEvent`, keep `pipetteEvent` and its connection but have it append to `eventHistory` **without** calling the recorder:

```python
    def pipetteEvent(self, pip, ev):
        """Keep this window's in-memory history, which its Reset button and the
        replay into a freshly opened log both read. The recorder subscribes to
        sigNewEvent itself, so this must not also hand the event to it."""
        if not self.eventHistory:
            self.resetHistory()
        self.eventHistory.append({k: v for k, v in ev.items() if k != 'full_test_pulse'})
```

Also delete the now-dangling `import h5py`, `H5BackedTestPulseStack`, `os`, and `json`/`ACQ4JSONEncoder` imports **only if** nothing else in the file uses them:

Run: `grep -n "h5py\|H5BackedTestPulseStack\|os\.\|json\.\|ACQ4JSONEncoder" acq4/modules/MultiPatch/multipatch.py`

Remove only the imports with no remaining use.

- [ ] **Step 6: Also remove the Task 1 stopgap**

Task 1 left `recordTestPulsesToggled` calling `pip.requestFullTestPulseData(self)` directly. The recorder now owns that, so verify no such call survives in the module:

Run: `grep -n "requestFullTestPulseData\|releaseFullTestPulseData" acq4/modules/MultiPatch/multipatch.py`

Expected: no output.

- [ ] **Step 7: Run the tests**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/MultiPatch/tests acq4/util/tests acq4/devices/PatchPipette/tests acq4/filetypes/tests tools/autopatch_analysis/tests -v`

Expected: PASS, all tests.

- [ ] **Step 8: Import-check the refactored module**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -c "import acq4.modules.MultiPatch.multipatch as m; print(m.MultiPatchWindow)"`

Expected: prints the class with no import error — the module has real device imports, so a broken import is the first thing to catch.

- [ ] **Step 9: Commit**

```bash
git add acq4/modules/MultiPatch/multipatch.py acq4/modules/MultiPatch/tests/test_logfile.py acq4/util/multipatch_log_recorder.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
refactor(multipatch): record through MultiPatchLogRecorder

One implementation of the log format instead of two, so "identical behavior,
so the viewer still renders it" holds by construction rather than by
inspection. The window's writeRecords is deleted; the recorder subscribes to
each pipette's sigNewEvent itself, so recordEvent now carries only the events
this window originates and pipetteEvent only maintains the in-memory history.

The two record buttons stay independent -- test-pulse capture works with the
event log off -- so one recorder exists while either is on and each button
maps to one of its options. Toggling test pulses mid-session adjusts the live
recorder rather than starting a second log file.

resetHistory stays in the window on purpose: it resets clamp test-pulse
history, and a recorder that touched device state would let one module wipe
the history another is plotting.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 7: Verify the phase end to end

**Files:** none modified.

- [ ] **Step 1: Run every suite this phase touched**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/util/tests acq4/devices/PatchPipette/tests acq4/modules/MultiPatch/tests acq4/filetypes/tests tools/autopatch_analysis/tests acq4/modules/Autopatch/tests acq4/experiment/tests -v`

Expected: PASS with no failures, errors, or new warnings. Output must be pristine.

- [ ] **Step 2: Confirm the format claim holds against a real historical file**

If any `MultiPatch_*.log` exists under `../minirig-data`, parse one with both readers to confirm the blank-line guard and comma tolerance did not regress reading real data:

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -c "
import glob, sys
from acq4.filetypes.MultiPatchLog import MultiPatchLogData
paths = sorted(glob.glob('../minirig-data/**/MultiPatch_*.log', recursive=True))
if not paths:
    print('no historical logs available; skipped')
    sys.exit(0)
d = MultiPatchLogData(paths[0])
print(paths[0], d.devices(), d.firstTime(), d.lastTime())
"
```

Expected: either `no historical logs available; skipped`, or a parsed device list and time range with no exception.

- [ ] **Step 3: Report**

State which tasks landed, the final test count, whether the historical-file check ran or was skipped, and whether the four record-button combinations were covered by tests or deferred to live testing (Task 6, Step 1).

---

## Self-Review Notes

**Spec coverage for phase 2.** §5's placement and rationale → Task 2's module docstring; API → Tasks 2–4; carried-over format behaviors → Tasks 2–3; "deliberately left in MultiPatchWindow" → Task 6, asserted by `test_reset_history_still_resets_the_clamp_history` and `test_the_recorder_never_resets_device_state`; MultiPatch refactored onto it → Task 6; "MultiPatch's UI shows nothing about other recorders" → satisfied by omission, since no registry or indicator is built anywhere in this plan. §6 → Task 1. §7 → Tasks 2 and 5.

**Known risk, and where it is contained.** Task 6 is the only task modifying working code with no pre-existing test coverage of its behavior. Task 5 lands the golden-output check *before* it, deliberately, so the rewrite has something to be wrong against.

**Known test edits, not additions:** Task 5 changes `_write`'s signature in `tools/autopatch_analysis/tests/test_autopatch_log.py`, keeping the legacy terminator as its default so every existing caller keeps exercising the historical format.

**Verified against the code:** the analysis tool's reader is `parse_log_events` at `autopatch_log.py:67` and takes a `str` path; both readers strip `b",\r\n"` as a character set (`MultiPatchLog.py:232`, `autopatch_log.py:76`), which is why dropping the trailing comma needs no reader change; `emitFullTestPulseData` has exactly one caller (`multipatch.py:632`); and `approach.py:251` plus `patchpipette.py:237` are the two mid-patch `resetTestPulseHistory()` calls that make `testPulseAnalysis()` necessary.
