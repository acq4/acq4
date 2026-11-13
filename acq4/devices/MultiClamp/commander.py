"""Start MultiClamp 700B Commander for configured MultiClamp devices when it is not already running.

Commander is launched once per amplifier serial number as ``MC700B.exe /S<serial> /T<title>``;
the title lists the ACQ4 devices that use that amplifier.
"""
import os
import subprocess
import time

from acq4.logging_config import get_logger

logger = get_logger(__name__)

# Relative to each Program Files folder
COMMANDER_LOCATIONS = [
    os.path.join('Molecular Devices', 'MultiClamp_64', 'MC700B.exe'),
    os.path.join('Molecular Devices', 'MultiClamp 700B Commander', 'MC700B.exe'),
]
PROGRAM_FILES_VARS = ['ProgramW6432', 'ProgramFiles', 'ProgramFiles(x86)']
RELAUNCH_DELAY = 2.0  # seconds between killing a stuck Commander and starting it again


def serial_from_channel_id(channel_id):
    """Return the ``sn`` field of a MultiClamp channelID string, or None if it has none (700A)."""
    for field in str(channel_id).split(','):
        key, _, value = field.partition(':')
        if key.strip() == 'sn' and value.strip():
            return value.strip()
    return None


def _normalize_serial(serial):
    return str(serial).strip().lstrip('0')


def find_commander(configured=None):
    """Return the path to MC700B.exe: *configured* if given, otherwise the first standard
    installation location that exists. Raises FileNotFoundError if none is found.
    """
    if configured is not None:
        if not os.path.isfile(configured):
            raise FileNotFoundError(f"Configured MultiClamp Commander 'commanderPath' does not exist: {configured}")
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
        + ". Set 'commanderPath' in the MultiClamp device config."
    )


def build_command(exe, serial, title):
    """Return the argument list that starts Commander for amplifier *serial* with window *title*."""
    return [exe, f"/S{str(serial).strip().zfill(8)}", f"/T{title}"]


def commander_targets(device_configs):
    """Group MultiClamp 700B device configs by amplifier serial number.

    *device_configs* maps device name -> device config for every device to consider.
    Returns {serial: {'names': [device names], 'path': configured commanderPath or None}}
    in config order. Devices that are not MultiClamp 700B channels are ignored.
    """
    targets = {}
    for name, conf in device_configs.items():
        if conf.get('driver') != 'MultiClamp':
            continue
        conf = conf.get('config', conf)
        serial = serial_from_channel_id(conf.get('channelID', ''))
        if serial is None:
            continue
        target = targets.setdefault(serial, {'names': [], 'path': None})
        target['names'].append(name)
        if target['path'] is None:
            target['path'] = conf.get('commanderPath')
    return targets


def _terminate(proc):
    proc.kill()
    proc.wait(timeout=10)


def start_commanders(device_configs, list_running, attempts=3, attempt_timeout=20.0):
    """Start Commander for each amplifier in *device_configs* that is not already running.

    list_running is a callable returning the serial numbers of running amplifiers. Commander
    sometimes fails to find its amplifier at startup and stops at its "Select Device" dialog, so
    a Commander that has not registered its amplifier within *attempt_timeout* seconds is killed
    and started again, up to *attempts* times in total. Raises TimeoutError if any amplifier is
    still missing after the last attempt.
    """
    targets = commander_targets(device_configs)
    if not targets:
        return

    def missing(candidates):
        running = {_normalize_serial(sn) for sn in list_running()}
        return {sn: t for sn, t in candidates.items() if _normalize_serial(sn) not in running}

    pending = missing(targets)
    procs = {}
    for attempt in range(1, attempts + 1):
        for serial, target in pending.items():
            exe = find_commander(target['path'])
            cmd = build_command(exe, serial, ", ".join(target['names']))
            logger.info("Starting MultiClamp Commander (attempt %d of %d): %s", attempt, attempts, cmd)
            procs[serial] = subprocess.Popen(cmd, cwd=os.path.dirname(exe))

        deadline = time.monotonic() + attempt_timeout
        while True:
            pending = missing(pending)
            if not pending or time.monotonic() >= deadline:
                break
            time.sleep(0.5)
        if not pending:
            return

        for serial in pending:
            logger.warning(
                "MultiClamp Commander did not find amplifier %s within %gs; killing it", serial, attempt_timeout)
            _terminate(procs[serial])
        if attempt < attempts:
            time.sleep(RELAUNCH_DELAY)

    raise TimeoutError(
        f"MultiClamp Commander did not find amplifier(s) {', '.join(pending)} after {attempts} attempts of "
        f"{attempt_timeout:g}s. Check that the amplifier is powered and connected by USB."
    )
