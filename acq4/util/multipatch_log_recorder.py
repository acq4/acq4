"""MultiPatchLogRecorder: writes a PatchPipette event stream to a MultiPatch-
format log file, with an optional full-test-pulse HDF5 sidecar beside it."""
from __future__ import annotations

import json
import os

import h5py
from neuroanalysis.test_pulse_stack import H5BackedTestPulseStack

from acq4.util import Qt
from acq4.util.json_encoder import ACQ4JSONEncoder

# Base name of the log file, matched case-insensitively by
# acq4.filetypes.MultiPatchLog and by tools/autopatch_analysis. Changing it
# makes the resulting file invisible to both readers.
LOG_FILE_NAME = "MultiPatch.log"

# Base name of the full-test-pulse sidecar, and the group each device's stack
# lives at inside it. MultiPatchLogData reads exactly `test_pulses/{device}`.
TEST_PULSE_FILE_NAME = "TestPulses.hdf5"
TEST_PULSE_GROUP = "test_pulses"


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
        self._recordFullTestPulses = record_full_test_pulses
        # device name -> its H5BackedTestPulseStack, created on first use so a
        # recorder that never sees a full test pulse writes no sidecar at all.
        self._testPulseStacks = {}
        self._testPulseContainer = None
        try:
            for record in initial_records:
                self.record(record)
        except Exception:
            # A record that ACQ4JSONEncoder cannot serialize raises out of
            # this loop before the caller ever gets an instance back to call
            # stop() on. Without this, the open file handle would be
            # reachable only through a partially-constructed self, leaving
            # its release to refcounting -- and a traceback holding this
            # frame's locals can keep it open well past the raise. stop() is
            # idempotent, so it is safe to call even if nothing was opened.
            self.stop()
            raise

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
        for stack in self._testPulseStacks.values():
            stack.close()
        self._testPulseStacks = {}
        if self._testPulseContainer is not None:
            self._testPulseContainer.close()
            self._testPulseContainer = None
        if self._logFile is not None:
            self._logFile.close()
