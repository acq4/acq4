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
