"""MultiPatchLogWriter: writes PatchPipette events to a MultiPatch.log, optionally
saving chosen pipettes' full test pulses to a TestPulses.hdf5 sidecar beside it.

Both files are written only by the writer's own thread. Signal handlers just
enqueue, so they are safe to run on whatever thread emits.
"""
from __future__ import annotations

import json
import os
import queue
import threading

import h5py
import numpy as np
from neuroanalysis.test_pulse_stack import H5BackedTestPulseStack

from acq4.filetypes.MultiPatchLog import (
    TEST_PULSE_FILE_NAME,
    TEST_PULSE_GROUP,
    TEST_PULSE_NUMPY_DTYPE,
)
from acq4.logging_config import get_logger
from acq4.util import Qt, ptime
from acq4.util.json_encoder import ACQ4JSONEncoder

logger = get_logger(__name__)

# Matched case-insensitively by acq4.filetypes.MultiPatchLog and tools/autopatch_analysis.
LOG_FILE_NAME = "MultiPatch.log"

_TEST_PULSE_FIELDS = tuple(name for name, _type in TEST_PULSE_NUMPY_DTYPE)
_STOP = object()


def eventToRecord(event: dict) -> dict:
    """Return a JSON-safe copy of a PatchPipette event; `event` is not modified.

    A test_pulse event's PatchClampTestPulse (its "test_pulse" field) is replaced by
    the pulse's analysis fields at top level, as they appear in MultiPatch.log.
    Records that are already converted pass through unchanged.
    """
    record = dict(event)
    testPulse = record.pop("test_pulse", None)
    if testPulse is not None:
        record.update(testPulse.analysis)
    return record


class _SetFullTestPulseDevices:
    """Queue item: from here on, save full test pulses for these device names."""

    def __init__(self, devices):
        self.devices = frozenset(devices)


class MultiPatchLogWriter:
    """Writes events, one JSON object per line, to a new auto-numbered MultiPatch.log.

    For the pipettes chosen by `full_test_pulse_pipettes` or setFullTestPulsePipettes(),
    each test pulse is also appended to ``test_pulses/<device>`` in a TestPulses.hdf5
    sidecar, and its log line gets a ``"full_test_pulse": "<relpath>:<h5path>"`` field.
    Never touches device state (in particular, never resets a clamp's test-pulse
    history). Write failures are logged, not raised.

    Parameters
    ----------
    directory : DirHandle
        Where the log file and sidecar are created.
    pipettes : iterable of PatchPipette
        Whose sigNewEvent streams are recorded.
    microscope : Microscope or None
        If given, its sigSurfaceDepthChanged is recorded too.
    initial_records : iterable of dict
        Written before any live event.
    full_test_pulse_pipettes : iterable of PatchPipette
        Whose full test pulses are saved from the start.
    """

    stopTimeout = 10.0

    def __init__(
        self,
        directory,
        pipettes=(),
        microscope=None,
        initial_records=(),
        full_test_pulse_pipettes=(),
    ):
        self._directory = directory
        self._pipettes = list(pipettes)
        self._microscope = microscope
        self._initialRecords = list(initial_records)
        self._initialFullTestPulseDevices = frozenset(p.name() for p in full_test_pulse_pipettes)
        self._queue = queue.Queue()
        self._thread = None
        self._lifecycleLock = threading.Lock()
        self._stopped = False
        self._failures = 0
        self._logFileName = None
        self._logFile = None
        self._h5FileName = None
        self._h5File = None
        # Used only on the writer thread once it has started:
        self._fullTestPulseDevices = frozenset()
        self._stacks: dict[str, H5BackedTestPulseStack] = {}
        self._testPulseRows: list[tuple] = []

    def start(self) -> MultiPatchLogWriter:
        """Create the files, start the writer thread and subscribe. Returns self."""
        with self._lifecycleLock:
            if self._thread is not None or self._stopped:
                raise RuntimeError(f"{type(self).__name__} can only be started once")
            handle = self._directory.createFile(LOG_FILE_NAME, autoIncrement=True)
            self._logFileName = handle.name()
            self._logFile = open(self._logFileName, "ab")
            if self._initialFullTestPulseDevices:
                self._openTestPulseFile()
                self._fullTestPulseDevices = self._initialFullTestPulseDevices
            for record in self._initialRecords:
                self._queue.put(dict(record))
            self._initialRecords = []
            self._thread = threading.Thread(target=self._run, name=type(self).__name__, daemon=True)
            self._thread.start()
        try:
            for pip in self._pipettes:
                pip.sigNewEvent.connect(self._onPipetteEvent, Qt.Qt.DirectConnection)
            if self._microscope is not None:
                self._microscope.sigSurfaceDepthChanged.connect(
                    self._onSurfaceDepthChanged, Qt.Qt.DirectConnection
                )
        except Exception:
            self.stop()
            raise
        return self

    def isRecording(self) -> bool:
        return self._thread is not None and not self._stopped

    def logFileName(self) -> str | None:
        """Full path of the log file, or None before start()."""
        return self._logFileName

    def testPulseFileName(self) -> str | None:
        """Full path of the sidecar, or None while full test pulses have never been on."""
        return self._h5FileName

    def record(self, event: dict) -> None:
        """Queue one event or record for writing. Ignored after stop()."""
        if not self._stopped:
            self._queue.put(dict(event))

    def setFullTestPulsePipettes(self, pipettes) -> None:
        """Save full test pulses for exactly these pipettes from now on (empty: none).

        Takes effect in order with the events already queued. The sidecar is created
        on first use, on the calling thread, and reused after that.
        """
        devices = frozenset(p.name() for p in pipettes)
        with self._lifecycleLock:
            if self._stopped:
                return
            if self._thread is None:
                self._initialFullTestPulseDevices = devices
                return
            if devices and self._h5File is None:
                self._openTestPulseFile()
            self._queue.put(_SetFullTestPulseDevices(devices))

    def testPulseAnalysis(self) -> np.ndarray:
        """The test_pulse events written so far, with clampDevice.testPulseHistory()'s dtype.

        event_time is each event's emit time, as in the log. Rows carry no device, so
        this is only meaningful for a single pipette. Unlike the device's history it
        is never reset mid-recording.
        """
        return np.array(list(self._testPulseRows), dtype=TEST_PULSE_NUMPY_DTYPE)

    def stop(self, timeout: float | None = None) -> None:
        """Unsubscribe, finish writing everything queued so far, then close the files.

        Blocks until the writer thread exits or `timeout` (default stopTimeout)
        passes. Safe to call from any thread, including the writer's; idempotent.
        """
        with self._lifecycleLock:
            if self._stopped:
                return
            self._stopped = True
            thread = self._thread
        for pip in self._pipettes:
            Qt.disconnect(pip.sigNewEvent, self._onPipetteEvent)
        if self._microscope is not None:
            Qt.disconnect(self._microscope.sigSurfaceDepthChanged, self._onSurfaceDepthChanged)
        if thread is None:
            self._close()
            return
        self._queue.put(_STOP)
        if thread is threading.current_thread():
            return
        thread.join(self.stopTimeout if timeout is None else timeout)
        if thread.is_alive():
            logger.warning(
                f"{type(self).__name__} still writing after stop(); it will close its files when done"
            )

    # -- caller's thread ------------------------------------------------------

    def _openTestPulseFile(self) -> None:
        handle = self._directory.createFile(TEST_PULSE_FILE_NAME, autoIncrement=True)
        self._h5FileName = handle.name()
        self._h5File = h5py.File(self._h5FileName, "a")
        self._h5File.require_group(TEST_PULSE_GROUP)

    def _onPipetteEvent(self, _pipette, event) -> None:
        self._queue.put(dict(event))

    def _onSurfaceDepthChanged(self, depth) -> None:
        self._queue.put(
            {
                "device": self._microscope.name(),
                "event_time": ptime.time(),
                "event": "surface_depth_changed",
                "surface_depth": depth,
            }
        )

    # -- writer thread --------------------------------------------------------

    def _run(self) -> None:
        try:
            while (item := self._queue.get()) is not _STOP:
                try:
                    if isinstance(item, _SetFullTestPulseDevices):
                        self._fullTestPulseDevices = item.devices
                    else:
                        self._write(item)
                except Exception:
                    self._logFailure("failed to write a record")
        finally:
            if self._failures > 1:
                logger.error(f"{type(self).__name__}: {self._failures} writes failed")
            try:
                self._close()
            except Exception:
                logger.exception(f"{type(self).__name__} failed to close its files")

    def _logFailure(self, message: str) -> None:
        self._failures += 1
        if self._failures == 1:
            logger.exception(f"{type(self).__name__} {message}")

    def _write(self, event: dict) -> None:
        testPulse = event.get("test_pulse")
        record = eventToRecord(event)
        if testPulse is not None and record.get("device") in self._fullTestPulseDevices:
            try:
                record["full_test_pulse"] = self._saveTestPulse(record["device"], testPulse)
            except Exception:
                self._logFailure("failed to save a full test pulse")
        # No trailing comma; both readers strip b",\r\n" so older comma-terminated logs still parse.
        line = json.dumps(record, cls=ACQ4JSONEncoder).encode("utf8") + b"\n"
        if record.get("event") == "test_pulse":
            self._testPulseRows.append(
                tuple(np.nan if record.get(f) is None else record[f] for f in _TEST_PULSE_FIELDS)
            )
        self._logFile.write(line)
        self._logFile.flush()

    def _saveTestPulse(self, deviceName: str, testPulse) -> str:
        """Append to the device's stack; return the "<relpath>:<h5path>" the reader resolves."""
        stack = self._stacks.get(deviceName)
        if stack is None:
            group = self._h5File[TEST_PULSE_GROUP].require_group(deviceName)
            group.attrs["device"] = deviceName
            stack = self._stacks[deviceName] = H5BackedTestPulseStack(group)
        fileName, h5Path = stack.append(testPulse)
        if self._queue.empty():
            self._h5File.flush()
        # Relative to the log file's directory, which is what MultiPatchLogData joins it to.
        return f"{os.path.relpath(fileName, os.path.dirname(self._logFileName))}:{h5Path}"

    def _close(self) -> None:
        # Close the shared HDF5 file once; H5BackedTestPulseStack.close() would close it per stack.
        if self._h5File is not None:
            self._h5File.close()
        if self._logFile is not None:
            self._logFile.close()
