"""Start MultiClamp 700B Commander for amplifiers that do not have a running instance.

Commander is launched once per amplifier serial number as ``MC700B.exe /S<serial> /T<title>``.
"""
import os
import subprocess
import time

from acq4.logging_config import get_logger
from .multiclamp import listRunningSerials

logger = get_logger(__name__)

__all__ = ['findCommander', 'buildCommand', 'startCommanders']

# Relative to each Program Files folder
COMMANDER_LOCATIONS = [
    os.path.join('Molecular Devices', 'MultiClamp_64', 'MC700B.exe'),
    os.path.join('Molecular Devices', 'MultiClamp 700B Commander', 'MC700B.exe'),
]
PROGRAM_FILES_VARS = ['ProgramW6432', 'ProgramFiles', 'ProgramFiles(x86)']
RELAUNCH_DELAY = 2.0  # seconds between killing a stuck Commander and starting it again


def _normalizeSerial(serial):
    return str(serial).strip().lstrip('0')


def findCommander(configured=None):
    """Return the path to MC700B.exe: *configured* if given, otherwise the first standard
    installation location that exists. Raises FileNotFoundError if none is found.
    """
    if configured is not None:
        if not os.path.isfile(configured):
            raise FileNotFoundError(f"Configured MultiClamp Commander path does not exist: {configured}")
        return configured

    candidates = []
    for var in PROGRAM_FILES_VARS:
        folder = os.environ.get(var)
        if folder:
            candidates.extend(os.path.join(folder, loc) for loc in COMMANDER_LOCATIONS)
    for path in candidates:
        if os.path.isfile(path):
            return path
    raise FileNotFoundError(
        "MultiClamp Commander is not running and MC700B.exe was not found in any of: "
        + "; ".join(dict.fromkeys(candidates))
        + ". Configure the Commander path to use a different location."
    )


def buildCommand(exe, serial, title):
    """Return the argument list that starts Commander for amplifier *serial* with window *title*."""
    return [exe, f"/S{str(serial).strip().zfill(8)}", f"/T{title}"]


def _terminate(proc):
    proc.kill()
    proc.wait(timeout=10)


def startCommanders(commanders, listRunning=listRunningSerials, attempts=3, attemptTimeout=20.0):
    """Start Commander for each amplifier in *commanders* that is not already running.

    commanders maps amplifier serial number -> {'title': window title, 'path': MC700B.exe path
    or None to search the standard locations}. listRunning returns the serial numbers of running
    amplifiers.

    Commander sometimes fails to find its amplifier at startup and stops at its "Select Device"
    dialog, so a Commander that has not registered its amplifier within *attemptTimeout* seconds
    is killed and started again, up to *attempts* times in total. Raises TimeoutError if any
    amplifier is still missing after the last attempt.
    """
    if not commanders:
        return

    def missing(candidates):
        running = {_normalizeSerial(sn) for sn in listRunning()}
        return {sn: c for sn, c in candidates.items() if _normalizeSerial(sn) not in running}

    pending = missing(commanders)
    procs = {}
    for attempt in range(1, attempts + 1):
        for serial, commander in pending.items():
            exe = findCommander(commander.get('path'))
            cmd = buildCommand(exe, serial, commander['title'])
            logger.info("Starting MultiClamp Commander (attempt %d of %d): %s", attempt, attempts, cmd)
            procs[serial] = subprocess.Popen(cmd, cwd=os.path.dirname(exe))

        deadline = time.monotonic() + attemptTimeout
        while True:
            pending = missing(pending)
            if not pending or time.monotonic() >= deadline:
                break
            time.sleep(0.5)
        if not pending:
            return

        for serial in pending:
            logger.warning(
                "MultiClamp Commander did not find amplifier %s within %gs; killing it", serial, attemptTimeout)
            _terminate(procs[serial])
        if attempt < attempts:
            time.sleep(RELAUNCH_DELAY)

    raise TimeoutError(
        f"MultiClamp Commander did not find amplifier(s) {', '.join(pending)} after {attempts} attempts of "
        f"{attemptTimeout:g}s. Check that the amplifier is powered and connected by USB."
    )
