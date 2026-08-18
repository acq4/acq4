"""MultiPatchLogRecorder: writes a PatchPipette event stream to a MultiPatch-
format log file, with an optional full-test-pulse HDF5 sidecar beside it."""
from __future__ import annotations

import json
import os

import h5py
import numpy as np
from neuroanalysis.test_pulse_stack import H5BackedTestPulseStack

from acq4.filetypes.MultiPatchLog import TEST_PULSE_NUMPY_DTYPE
from acq4.util import Qt, ptime
from acq4.util.json_encoder import ACQ4JSONEncoder

# Base name of the log file, matched case-insensitively by
# acq4.filetypes.MultiPatchLog and by tools/autopatch_analysis. Changing it
# makes the resulting file invisible to both readers.
LOG_FILE_NAME = "MultiPatch.log"

# Base name of the full-test-pulse sidecar, and the group each device's stack
# lives at inside it. MultiPatchLogData reads exactly `test_pulses/{device}`.
TEST_PULSE_FILE_NAME = "TestPulses.hdf5"
TEST_PULSE_GROUP = "test_pulses"

# The analysis field names a test_pulse event can carry, taken from the dtype
# the readers and PatchClamp's own history both use, so an accumulated array is
# interchangeable with clampDevice.testPulseHistory()'s.
_TEST_PULSE_FIELDS = tuple(name for name, _type in TEST_PULSE_NUMPY_DTYPE)


def _nanIfNone(value):
    """NaN for a missing or None analysis field, matching how PatchClamp's own
    test-pulse history records one."""
    return np.nan if value is None else value


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
    before anything is written. __init__ pins that affinity itself rather than
    trusting the constructing thread, so a recorder opened from a worker thread
    with no Qt event loop still receives its events.

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
    full_test_pulse_pipettes : iterable of PatchPipette or None
        The narrower set whose *whole* test-pulse recordings go into the
        sidecar; None means every pipette in `pipettes`. The two scopes differ
        because a full recording costs orders of magnitude more disk than the
        analysis fields in an event, so MultiPatch logs events from every
        pipette while capturing waveforms only from the selected ones. This set
        is fixed when the recorder is built: changing which pipettes are
        selected while recording does not re-scope capture, and only stopping
        and restarting the recorder will.
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
        full_test_pulse_pipettes=None,
        initial_records=(),
    ):
        super().__init__()
        # Pin signal affinity to the GUI thread when there is one, before any
        # connect below. A recorder is routinely constructed from a worker
        # thread (an Autopatch action runs on a gentletask ThreadTask, which has
        # no Qt event loop); without this the queued sigNewEvent connections
        # would target that loop-less thread and the slots would silently never
        # fire, so test_pulse events emitted from the clamp's own thread would
        # never be recorded. moveToThread is legal from the constructing thread
        # because this object is parentless. Headless contexts have no
        # QApplication; there the QObject stays on its creating thread and
        # events still arrive via direct connection.
        app = Qt.QApplication.instance()
        if app is not None:
            self.moveToThread(app.thread())
        self._directory = directory
        self._pipettes = list(pipettes)
        self._fullTestPulsePipettes = (
            list(self._pipettes)
            if full_test_pulse_pipettes is None
            else list(full_test_pulse_pipettes)
        )
        self._microscope = microscope
        self._stopped = False
        self._writeEvents = bool(write_events)
        # Kept separately from the file object so it survives the file being
        # closed and reopened by setWriteEvents, which is what keeps one
        # recorder's records pointing at one log.
        self._logFileName = None
        self._logFile = None
        if self._writeEvents:
            self._openLogFile()
        self._recordFullTestPulses = record_full_test_pulses
        # device name -> its H5BackedTestPulseStack, created on first use so a
        # recorder that never sees a full test pulse writes no sidecar at all.
        self._testPulseStacks = {}
        self._testPulseContainer = None
        # One row per test_pulse event this recorder saw, in order. Accumulated
        # here rather than read from clampDevice.testPulseHistory() because the
        # device's history is reset mid-patch -- approach.py:251 does it on every
        # attempt -- so slicing that by time silently loses data.
        self._testPulseRows: list[tuple] = []
        try:
            for pip in self._pipettes:
                pip.sigNewEvent.connect(self._onPipetteEvent)
            if microscope is not None:
                microscope.sigSurfaceDepthChanged.connect(self._onSurfaceDepthChanged)
            if self._recordFullTestPulses:
                self._requestFullTestPulseData()
            for record in initial_records:
                self.record(record)
        except Exception:
            # A record that ACQ4JSONEncoder cannot serialize, or any failure
            # in the subscription setup above, raises out of this block
            # before the caller ever gets an instance back to call stop() on.
            # Without this, the open file handle and any subscriptions/tokens
            # would be reachable only through a partially-constructed self,
            # leaving their release to refcounting -- and a traceback holding
            # this frame's locals can keep them alive well past the raise.
            # stop() is idempotent, so it is safe to call even if nothing was
            # opened or subscribed yet.
            self.stop()
            raise

    def logFileName(self) -> str | None:
        """This recorder's log file, or None if it has never opened one. Still
        the name after setWriteEvents(False) closed it, since that is the file
        every record written by this recorder is in."""
        return self._logFileName

    def isRecording(self) -> bool:
        return not self._stopped

    def writesEvents(self) -> bool:
        return self._writeEvents

    def setWriteEvents(self, write: bool) -> None:
        """Open or close the event log for the rest of this recorder's life.

        Touches nothing else: subscriptions, full-test-pulse tokens and the HDF5
        sidecar all carry on across the switch, so a caller whose event log and
        test-pulse capture are separate switches can adjust a live recorder
        instead of replacing it -- and one session keeps one sidecar. Reopening
        appends to the same log file rather than starting a second one.
        """
        write = bool(write)
        if self._stopped or write == self._writeEvents:
            return
        self._writeEvents = write
        if write:
            self._openLogFile()
        else:
            self._logFile.close()
            self._logFile = None

    def _openLogFile(self) -> None:
        if self._logFileName is None:
            handle = self._directory.createFile(LOG_FILE_NAME, autoIncrement=True)
            self._logFileName = handle.name()
        self._logFile = open(self._logFileName, "ab")

    def record(self, event) -> None:
        """Write one record. Ignored once stopped, so a late queued event
        arriving after the action that opened this recorder has ended does not
        reopen a closed file."""
        if self._stopped:
            return
        self._writeRecords([event])

    def recordsFullTestPulses(self) -> bool:
        return self._recordFullTestPulses

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

    def _requestFullTestPulseData(self) -> None:
        for pip in self._fullTestPulsePipettes:
            pip.requestFullTestPulseData(self)

    def _releaseFullTestPulseData(self) -> None:
        for pip in self._fullTestPulsePipettes:
            pip.releaseFullTestPulseData(self)

    def _onPipetteEvent(self, _pipette, event) -> None:
        # Guarded the same way record() guards itself: sigNewEvent is a queued
        # connection, so a test_pulse event already in flight when stop() runs
        # can still reach this slot afterward. Without this check that event
        # would add a row here even though record() below silently drops it,
        # leaving testPulseAnalysis() disagreeing with what was actually
        # logged.
        if not self._stopped and event.get("event") == "test_pulse":
            self._testPulseRows.append(
                tuple(_nanIfNone(event.get(field)) for field in _TEST_PULSE_FIELDS)
            )
        self.record(event)

    def _onSurfaceDepthChanged(self, depth) -> None:
        # Guarded for the same reason as _onPipetteEvent above: this is a
        # queued connection, and stop() sets self._microscope to None, so a
        # surface-depth signal already in flight when stop() runs would
        # otherwise dereference None here.
        if self._stopped:
            return
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

        Meaningful only when this recorder watches a single pipette: rows carry
        no device field, so a recorder watching several pipettes interleaves
        their rows in event order with no way to tell which device any row came
        from. Attributing rows to a device would need a dtype that carries one.
        """
        return np.array(self._testPulseRows, dtype=TEST_PULSE_NUMPY_DTYPE)

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
        if self._logFileName is not None:
            filename = os.path.relpath(filename, os.path.dirname(self._logFileName))
        record["full_test_pulse"] = f"{filename}:{h5path}"
        return record

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

    def stop(self) -> None:
        """Release everything this recorder holds. Idempotent."""
        if self._stopped:
            return
        self._stopped = True
        self._releaseFullTestPulseData()
        for pip in self._pipettes:
            Qt.disconnect(pip.sigNewEvent, self._onPipetteEvent)
        # Dropped so a stopped recorder is not what keeps a device object
        # alive, and so a second stop() has nothing left to disconnect.
        self._pipettes = []
        self._fullTestPulsePipettes = []
        if self._microscope is not None:
            Qt.disconnect(
                self._microscope.sigSurfaceDepthChanged, self._onSurfaceDepthChanged
            )
            self._microscope = None
        try:
            # All of self._testPulseStacks share one h5py.File --
            # self._testPulseContainer, opened once in _makeTestPulseStack --
            # so closing it here is sufficient for every stack. Do not also
            # call stack.close() per stack: H5BackedTestPulseStack.close()
            # closes the *file* its groups belong to, so the first call would
            # close the file out from under every other device's stack and
            # the next call would raise trying to close it again.
            self._testPulseStacks = {}
            if self._testPulseContainer is not None:
                self._testPulseContainer.close()
                self._testPulseContainer = None
        finally:
            # However the sidecar teardown above turns out, the event log
            # must still be closed and flushed -- a raise here must never
            # leave it open for the rest of the process, since _stopped is
            # already set and every later stop() call is now a no-op.
            if self._logFile is not None:
                self._logFile.close()
