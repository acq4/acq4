"""On-disk Stream Dock profile generation and VSD Craft process control.

There is **no SDK command to place an action on a key**: a plugin only ever learns about a
key through ``willAppear``, which fires for keys the user has already placed. Layout lives
entirely in profile JSON under

    %APPDATA%\\HotSpot\\StreamDock\\profiles\\<UUID>.sdProfile\\

with ``Actions`` keyed ``"column,row"``, so this module writes that JSON directly. VSD Craft
holds the profile in memory and rewrites it on exit, so it has to be stopped first and the
manifest re-read afterwards -- it may have been rewritten on the way out.

Page identity
-------------
``willAppear`` carries action, context, device, settings, controller and coordinates, but
**no page or profile id**, and the order in which keys appear follows whichever page the
user happens to open first. Numbering pages by visit order is therefore not reproducible.

Instead, each generated key carries its identity in its own per-instance ``Settings``, which
VSD Craft preserves across its own rewrites (it has no schema for these fields) and does
deliver in ``willAppear``::

    "Settings": {
        "generator": "acq4",
        "pageId":    "B3T761N3-JA70-7GLN-5UWV-7DPPKXJ7SKBS",
        "pageLabel": "acq4 1",
        "pageIndex": 0,
        "role": "button", "row": 0, "column": 0
    }

``pageIndex`` is the **acq4 page index**: the 0-based ordinal of this page among the
generated ones, which is exactly what
:class:`~acq4.devices.ControlSurface.ControlSurface` means by ``page``. ``row``/``column``
are the **logical address within the control block** -- button ``(0, 0)`` is the first
button of the top button row, not panel row 0, which is the knob strip along the bottom of
the panel. The block-to-panel mapping lives in :class:`GridSpec`, which documents the
panel's row direction, and is applied only when choosing the ``"column,row"`` JSON key, so
``willAppear`` hands the logical address straight back and no runtime mapping is needed.

Reconciliation
--------------
:func:`ensure_pages` makes the profile hold exactly N generated pages, adding or removing
them as needed. Only pages whose keys are tagged ``Settings['generator'] == 'acq4'`` are
touched, so anything the user built by hand survives -- including the profile's *first*
page, which lives in the parent manifest itself and is never generated.

A generated page is rewritten wholesale, so keys on it that this module did *not* write
are read back off the page being replaced and carried forward at their own panel
positions. That is what makes hand-placed content on a generated page durable.

Page switching
--------------
This module places no page-change action and reserves no position for one. Where a
page-switch control lives, and whether there is one at all, is configured by the user in
VSD Craft; there is no fixed position for it. The only thing acq4 does about it is to not
destroy it: a page-change key the user drops onto a generated page is preserved like any
other unmanaged key. A configured control block that needs that same panel position wins
and says so loudly -- see :func:`write_page`.
"""

from __future__ import annotations

import configparser
import json
import os
import random
import shutil
import string
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import psutil

from acq4.logging_config import get_logger

logger = get_logger(__name__)


# ------------------------------------------------------------------------------ constants

#: Plugin UUID; must match ``UUID`` in ``plugin/manifest.json``.
PLUGIN_UUID = 'com.acq4.streamdock'

#: The manifest declares exactly one Keypad action and one Knob action. All identity lives
#: in each placed instance's ``Settings``, never in separate actions per position.
BUTTON_ACTION = {'UUID': f'{PLUGIN_UUID}.button', 'Name': 'ACQ4 Button', 'Title': ''}
KNOB_ACTION = {'UUID': f'{PLUGIN_UUID}.knob', 'Name': 'ACQ4 Knob', 'Title': ''}

#: ``Settings['role']`` -> the action to place and the acq4 control type it becomes.
ROLE_ACTIONS = {'button': BUTTON_ACTION, 'dial': KNOB_ACTION}

#: Marks pages this module owns, so reconciliation never touches hand-built ones.
GENERATOR_TAG = 'acq4'

#: Image path recorded in each placed action, resolved against the plugin folder.
ACTION_IMAGE = 'images/button.png'

#: Suffix of the one-time backup :func:`ensure_pages` takes before its first write.
BACKUP_SUFFIX = '.preprofilegen.bak'

APPDATA = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
STREAMDOCK_ROOT = APPDATA / 'HotSpot' / 'StreamDock'
PROFILES_DIR = STREAMDOCK_ROOT / 'profiles'
CONFIG_INI = STREAMDOCK_ROOT / 'config' / 'StreamDockConfig.ini'
PLUGIN_DIR = STREAMDOCK_ROOT / 'plugins' / f'{PLUGIN_UUID}.sdPlugin'

#: Written by ``plugin/bootstrap.js`` on every plugin launch: websocket URL, plugin UUID,
#: register event and the ``-info`` payload (the only source of panel geometry).
WS_META_FILE = PLUGIN_DIR / 'ws-meta.json'

VSD_CRAFT_DIR = Path('C:/Program Files (x86)/VSD Craft')
VSD_CRAFT_EXE = VSD_CRAFT_DIR / 'VSD Craft.exe'

#: Where to download the Stream Dock software, for the "not installed" error.
DOWNLOAD_URL = 'https://www.vsdinside.com/pages/download'


class ProfileError(Exception):
    """Raised for an unusable profile, device or geometry."""


# ------------------------------------------------------------------------------ geometry


@dataclass
class GridSpec:
    """Which controls a generated page holds, and where they sit on the panel.

    A page carries two rectangular blocks: ``button_rows`` x ``button_cols`` buttons, with
    ``dial_rows`` x ``dial_cols`` dials below them on the panel's rotary knob strip.

    Addresses are per block and read the way a written layout reads, top row first: button
    ``(0, 0)`` is the leftmost button of the *upper* button row, which on a VSD N4 Pro is
    panel row 2. :meth:`panelPosition` is the only place that mapping exists; what goes
    into each key's ``Settings``, and so what ``willAppear`` hands back, is always the
    logical address.

    Notes
    -----
    **Panel row 0 is the bottom row of the panel**: the row index in the profile format's
    ``"column,row"`` keys counts upwards, so mapping a logical (top-down) block row to a
    panel row is a flip. Nothing announces this -- the ``-info`` payload the plugin is
    launched with reports the panel's size but never its orientation -- so it rests on two
    pieces of evidence:

    * a VSD N4 Pro's rotary knobs are the *bottom* strip of the panel, and they are driven
      by keys written at panel row 0;
    * while buttons were written to increasing panel rows going *down* from the knob row,
      the panel showed the two button rows swapped, which is exactly what an
      upward-counting row index does to them.

    The consequence is that a spec anchored at panel row 0 fills the panel from the bottom
    up. That is what keeps the dials on the knob strip, the one row whose panel position is
    not ours to choose.
    """

    button_rows: int = 2
    button_cols: int = 5
    dial_rows: int = 1
    dial_cols: int = 3

    @property
    def rows(self) -> int:
        """Total panel rows this spec occupies."""
        return int(self.dial_rows) + int(self.button_rows)

    @property
    def columns(self) -> int:
        """Widest panel column this spec occupies, plus one."""
        return max(int(self.dial_cols), int(self.button_cols))

    def keys(self, role: str) -> list:
        """Return the logical ``(row, col)`` keys of the *role* block, in row-major order."""
        rows, cols = self.shape(role)
        return [(row, col) for row in range(rows) for col in range(cols)]

    def shape(self, role: str) -> tuple:
        """Return the ``(rows, cols)`` shape of the *role* block."""
        if role == 'dial':
            return int(self.dial_rows), int(self.dial_cols)
        if role == 'button':
            return int(self.button_rows), int(self.button_cols)
        raise ValueError(f"Unknown control role {role!r}")

    def panelPosition(self, role: str, row: int, col: int) -> tuple:
        """Map a logical block address to the panel ``(column, row)`` the profile keys on.

        Dials occupy panel rows ``0 .. dial_rows - 1`` -- the knob strip along the bottom
        of the panel -- and buttons occupy the rows above. Panel rows count up from the
        bottom while block rows are numbered from the top (see the class notes), so this is
        where the two are flipped, and it is that flip which puts block row 0 at the top of
        its block.
        """
        rows, cols = self.shape(role)
        if not (0 <= row < rows and 0 <= col < cols):
            raise ValueError(f"{role} ({row}, {col}) is outside a {rows}x{cols} block")
        # distance from the top of the spec: the buttons, then the dials beneath them
        fromTop = int(row) if role == 'button' else int(self.button_rows) + int(row)
        return (int(col), self.rows - 1 - fromTop)


def read_meta(meta_file: Path = WS_META_FILE) -> dict:
    """Return the metadata ``plugin/bootstrap.js`` published, or ``{}``.

    Re-read this before *every* connection attempt: VSD Craft hands out a new port and a
    new plugin UUID each time it restarts, which it does on its own during startup and
    whenever pages are rewritten.
    """
    try:
        data = json.loads(Path(meta_file).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def device_size(device_uuid: str, meta_file: Path = WS_META_FILE) -> Optional[tuple]:
    """Return the ``(columns, rows)`` panel size reported for *device_uuid*, or None.

    Sizes come from the ``-info`` payload the plugin is launched with, which
    ``bootstrap.js`` stores in ``ws-meta.json``. That is the only authoritative source:
    ``willAppear`` reports a key's own column and row but never the panel dimensions.
    Models differ -- a VSD N4 Pro is 5x3 while a VSD N3 is 4x3 -- so there is nothing
    sensible to hard-code.
    """
    info = read_meta(meta_file).get('info') or {}
    for device in info.get('devices', []):
        if device.get('name') != device_uuid:
            continue
        size = device.get('size') or {}
        if 'columns' in size and 'rows' in size:
            return int(size['columns']), int(size['rows'])
    return None


def check_geometry(spec: GridSpec, device_uuid: str, meta_file: Path = WS_META_FILE) -> None:
    """Raise :exc:`ProfileError` if *spec* does not fit the reported panel.

    A no-op when the plugin has not yet published a size for this device, since there is
    then nothing to check against; keys written off-panel would otherwise simply never
    appear, which is a much worse failure than a startup error.
    """
    size = device_size(device_uuid, meta_file)
    if size is None:
        logger.info(
            f"No panel size reported for {device_uuid}; skipping the geometry check. "
            f"Configured layout needs {spec.rows} row(s) x {spec.columns} column(s)."
        )
        return
    columns, rows = size
    if spec.rows > rows or spec.columns > columns:
        raise ProfileError(
            f"Configured layout needs {spec.rows} row(s) x {spec.columns} column(s) "
            f"(dials {spec.dial_rows}x{spec.dial_cols}, buttons "
            f"{spec.button_rows}x{spec.button_cols}) but {device_uuid} is "
            f"{rows}x{columns}. Reduce 'buttons' or 'dials' in the device configuration."
        )


# --------------------------------------------------------------------------- identifiers


def _group(chars: str, n: int) -> str:
    return ''.join(random.choice(chars) for _ in range(n))


def new_action_id() -> str:
    """Return a lowercase 8-4-4-4-12 identifier, matching what VSD Craft writes."""
    alphabet = string.ascii_lowercase + string.digits
    return '-'.join(_group(alphabet, n) for n in (8, 4, 4, 4, 12))


def new_page_uuid() -> str:
    """Return an uppercase 8-4-4-4-12 identifier, matching VSD Craft's page folders."""
    alphabet = string.ascii_uppercase + string.digits
    return '-'.join(_group(alphabet, n) for n in (8, 4, 4, 4, 12))


# ---------------------------------------------------------------------- profile building


def page_meta(page_uuid: str, label: str, index: int) -> dict:
    """Return the page-identity fields baked into every generated key's ``Settings``."""
    return {
        'generator': GENERATOR_TAG,
        'pageId': page_uuid,
        'pageLabel': label,
        'pageIndex': int(index),
    }


def make_entry(action: dict, settings: dict) -> dict:
    """Build one placed action.

    ``Settings`` is per-instance and is handed back in ``willAppear``, so it is where
    identity is carried.
    """
    return {
        'ActionID': new_action_id(),
        'Controller': '',
        'Name': action['Name'],
        'Settings': settings,
        'State': 0,
        'States': [{'Image': ACTION_IMAGE, 'Title': action.get('Title', '')}],
        'UUID': action['UUID'],
    }


def build_actions(spec: GridSpec, meta: dict) -> dict:
    """Return the ``Actions`` mapping for one generated page.

    Keys are the panel ``"column,row"`` strings the profile format uses; each entry's
    ``Settings`` carries the *logical* block address instead.
    """
    actions: dict = {}
    for role in ('dial', 'button'):
        for row, col in spec.keys(role):
            column, panelRow = spec.panelPosition(role, row, col)
            settings = {**meta, 'role': role, 'row': row, 'column': col}
            actions[f'{column},{panelRow}'] = make_entry(ROLE_ACTIONS[role], settings)
    return actions


def build_page_manifest(actions: dict, parent: dict, name: str) -> dict:
    """Wrap *actions* in the per-page manifest structure VSD Craft expects."""
    return {
        'Actions': actions,
        'DeviceModel': parent.get('DeviceModel', ''),
        'DeviceUUID': parent.get('DeviceUUID', ''),
        'Name': name,
        'Version': '1.0',
    }


# ------------------------------------------------------------------- locating the profile


def unescape_qt(value: str) -> str:
    """Undo the quoting Qt's ini writer applies to a Windows path."""
    return value.strip('"').replace('\\\\', '\\')


def find_device_profile(device_uuid: Optional[str] = None, config_ini: Path = None) -> tuple:
    """Return ``(profile directory, device uuid)`` for the current or named device.

    Parameters
    ----------
    device_uuid : str, optional
        Device to look up; defaults to whichever device VSD Craft has selected.
    config_ini : Path, optional
        Override the location of ``StreamDockConfig.ini``, for testing.

    Raises
    ------
    ProfileError
        If the device or its profile cannot be determined.
    """
    config_ini = CONFIG_INI if config_ini is None else Path(config_ini)
    parser = configparser.RawConfigParser(strict=False)
    parser.optionxform = str
    parser.read(config_ini, encoding='utf-8')

    if device_uuid is None:
        device_uuid = parser.get('StreamDockCurrentDevice', 'Device', fallback=None)
        if not device_uuid:
            raise ProfileError(
                f"Could not determine the current Stream Dock device from {config_ini}. "
                f"Start VSD Craft with the device connected, or set 'device' in the "
                f"device configuration."
            )

    for section in parser.sections():
        if not section.endswith('DeviceConfig'):
            continue
        if parser.get(section, 'DeviceUUID', fallback=None) != device_uuid:
            continue
        path = parser.get(section, 'sdProfilePath', fallback=None)
        if path:
            return Path(unescape_qt(path)), device_uuid
        name = parser.get(section, 'sdProfileName', fallback=None)
        if name:
            return PROFILES_DIR / name, device_uuid

    raise ProfileError(f"No Stream Dock profile is registered for device {device_uuid!r}")


# ------------------------------------------------------------------- VSD Craft lifecycle


def vsd_craft_installed() -> bool:
    """Return True if the VSD Craft application directory exists."""
    return VSD_CRAFT_DIR.exists()


def vsd_craft_running() -> bool:
    """Return True if VSD Craft is already running."""
    result = subprocess.run(
        ['tasklist', '/FI', f'IMAGENAME eq {VSD_CRAFT_EXE.name}', '/NH'],
        capture_output=True,
        text=True,
    )
    return VSD_CRAFT_EXE.name.lower() in result.stdout.lower()


def launch_vsd_craft() -> None:
    """Start VSD Craft in the background without waiting for it."""
    subprocess.Popen(
        [str(VSD_CRAFT_EXE)],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    )


def stop_vsd_craft(timeout: float = 20.0) -> bool:
    """Close VSD Craft, forcing it if it ignores the polite request.

    It minimises to tray on ``WM_CLOSE``, so the graceful ``taskkill`` usually does nothing
    and the force path is the normal one. Forcing is safe here because the application
    writes profile changes as they happen rather than only on exit, and because we write
    only once it is gone -- a live instance would otherwise overwrite us from its in-memory
    copy.
    """
    if not vsd_craft_running():
        return True

    subprocess.run(['taskkill', '/IM', VSD_CRAFT_EXE.name], capture_output=True, text=True)
    deadline = time.monotonic() + min(timeout, 5.0)
    while time.monotonic() < deadline:
        if not vsd_craft_running():
            return True
        time.sleep(0.4)

    subprocess.run(['taskkill', '/F', '/IM', VSD_CRAFT_EXE.name], capture_output=True, text=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not vsd_craft_running():
            return True
        time.sleep(0.4)
    return False


def wait_for_plugin(
    meta_file: Path = WS_META_FILE, newer_than: float = 0.0, timeout: float = 45.0
) -> bool:
    """Wait for the plugin bootstrap to republish its websocket address.

    Restarting VSD Craft invalidates the old port, so a caller that restarted it must wait
    for a fresh ``ws-meta.json`` before connecting.
    """
    meta_file = Path(meta_file)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if meta_file.stat().st_mtime > newer_than:
                return True
        except OSError:
            pass
        time.sleep(0.5)
    return False


# ------------------------------------------------------------- plugin bridge processes

#: Fields ``ws-meta.json`` must carry before acq4 will trust it enough to connect.
REQUIRED_META_FIELDS = ('ws', 'pluginUUID')


def process_alive(pid) -> bool:
    """Return True if *pid* names a process that still exists."""
    try:
        return psutil.pid_exists(int(pid))
    except (TypeError, ValueError):
        return False


def _cmdline_option(cmdline: list, name: str) -> str:
    """Return the value following *name* in a command line, or ``''``."""
    for index, token in enumerate(cmdline[:-1]):
        if token == name:
            return cmdline[index + 1]
    return ''


def plugin_processes(plugin_dir: Path = None) -> list:
    """Return the live bridge processes launched from *plugin_dir*, **oldest first**.

    Each entry is ``{'pid', 'uuid', 'created'}``, where ``uuid`` is the ``-pluginUUID``
    VSD Craft assigned that launch -- the identity acq4 has to register under.

    VSD Craft does not reap the bridges it starts, so several can be alive at once: the
    one belonging to its current session, plus orphans left by sessions that are gone.
    They all write the same :data:`WS_META_FILE` at launch, so which of them is newest is
    the whole question, which is why this is ordered rather than a set.
    """
    plugin_dir = PLUGIN_DIR if plugin_dir is None else Path(plugin_dir)
    needle = str(plugin_dir).replace('/', '\\').casefold()
    found = []
    for proc in psutil.process_iter(['pid', 'name']):
        # Filter on the executable name before asking for a command line. The name comes
        # from the snapshot process_iter already holds, while each command line costs a
        # separate open: reading one for every process on a rig takes *tens of seconds* on
        # Windows, and this runs before every connection attempt. A bridge is always Node
        # -- VSD Craft ships its own as node20.exe -- so the name settles it.
        if not (proc.info.get('name') or '').casefold().startswith('node'):
            continue
        try:
            cmdline = proc.cmdline() or []
            created = proc.create_time()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue  # it exited while we looked, or is not ours to inspect
        joined = ' '.join(cmdline).replace('/', '\\').casefold()
        if needle not in joined or 'bootstrap.js' not in joined:
            continue
        found.append(
            {
                'pid': proc.pid,
                'uuid': _cmdline_option(cmdline, '-pluginUUID'),
                'created': created or 0.0,
            }
        )
    found.sort(key=lambda entry: entry['created'])
    return found


def bridge_identity(pid, plugin_dir: Path = None) -> Optional[str]:
    """Return the ``-pluginUUID`` the bridge running as *pid* was launched with.

    None means *pid* is not one of our bridges at all -- it exited, it belongs to another
    plugin, or the number has since been reused by something unrelated.

    This asks about one known process rather than searching for all of them, which is the
    difference between microseconds and seconds: reading a command line means opening the
    process, and on Windows doing that for every process on a rig takes tens of seconds.
    """
    plugin_dir = PLUGIN_DIR if plugin_dir is None else Path(plugin_dir)
    needle = str(plugin_dir).replace('/', '\\').casefold()
    try:
        cmdline = psutil.Process(int(pid)).cmdline() or []
    except (psutil.Error, TypeError, ValueError):
        return None
    joined = ' '.join(cmdline).replace('/', '\\').casefold()
    if needle not in joined or 'bootstrap.js' not in joined:
        return None
    return _cmdline_option(cmdline, '-pluginUUID')


def meta_problem(
    meta: dict, plugin_dir: Path = None, thorough: bool = False, bridges: list = None
) -> Optional[str]:
    """Return why *meta* cannot be trusted, or None if it describes the live bridge.

    ``ws-meta.json`` is a file left behind by whichever bridge wrote it last, and nothing
    deletes it when that bridge dies. Registering against a plugin session VSD Craft has
    already forgotten is the one failure this device cannot detect from the inside: the
    websocket still opens, because the port belongs to VSD Craft itself rather than to the
    plugin, and ``registerPlugin`` is accepted -- but no ``willAppear`` ever follows, so no
    control is ever bound and every appearance acq4 draws is dropped for want of a context.
    The panel sits there blank with nothing in the log. Checking the file against the
    running processes *before* connecting is what turns that silence into a diagnosis.

    The default checks all concern the one process the file names as its publisher, so they
    cost microseconds and are meant to run before every connection attempt. *thorough* adds
    a search for rival bridges the file does not mention; that costs seconds, so it belongs
    where the search is already being paid for -- beside the startup reap -- rather than in
    the reconnect loop. Pass *bridges* (a :func:`plugin_processes` result) to reuse a search
    already done instead of repeating it.
    """
    for field in REQUIRED_META_FIELDS:
        if not meta.get(field):
            return f"{WS_META_FILE.name} has no {field!r}"

    pid = meta.get('pid')
    if pid is None:
        return (
            f"{WS_META_FILE.name} records no publisher pid, so acq4 cannot tell whether "
            f"the plugin session it names still exists. An older ACQ4 bridge wrote it; "
            f"restarting VSD Craft will replace it."
        )
    if not process_alive(pid):
        return f"the bridge that published {WS_META_FILE.name} (pid {pid}) has exited"

    identity = bridge_identity(pid, plugin_dir)
    if identity is None:
        return (
            f"pid {pid}, named in {WS_META_FILE.name} as its publisher, is not an ACQ4 "
            f"bridge process"
        )
    if identity != meta['pluginUUID']:
        return (
            f"{WS_META_FILE.name} claims plugin session {meta['pluginUUID']!r}, but its "
            f"publisher (pid {pid}) was launched as {identity!r}"
        )

    if thorough or bridges is not None:
        # A caller that has already searched passes the result in rather than paying for
        # the search twice; see StreamDock._startup, which needs it for the reap anyway.
        live = plugin_processes(plugin_dir) if bridges is None else bridges
        if live and live[-1]['uuid'] != meta['pluginUUID']:
            return (
                f"{WS_META_FILE.name} describes plugin session {meta['pluginUUID']!r}, but "
                f"a newer bridge (pid {live[-1]['pid']}) was launched as "
                f"{live[-1]['uuid']!r}"
            )
    return None


def reap_plugin_processes(keep_pid=None, plugin_dir: Path = None, timeout: float = 5.0) -> list:
    """Kill every bridge process except *keep_pid*, returning the pids killed.

    VSD Craft leaves its old plugin processes running when it cycles, and each of them
    wrote the same :data:`WS_META_FILE` at launch, so orphans are exactly what makes that
    file untrustworthy. ``plugin/bootstrap.js`` clears its own predecessors on the way up;
    this is the same job from outside, for orphans that outlived the VSD Craft that
    started them.

    Raises
    ------
    RuntimeError
        If a bridge process could not be killed. A survivor is worth reporting rather than
        ignoring: it is free to republish the very metadata acq4 just rejected.
    """
    victims = [
        entry
        for entry in plugin_processes(plugin_dir)
        if keep_pid is None or entry['pid'] != int(keep_pid)
    ]
    pending, killed, failures = [], [], []
    for entry in victims:
        try:
            proc = psutil.Process(entry['pid'])
            proc.terminate()
        except psutil.NoSuchProcess:
            killed.append(entry['pid'])  # it got there on its own
        except psutil.Error as exc:
            failures.append(f"pid {entry['pid']} ({type(exc).__name__}: {exc})")
        else:
            pending.append(proc)

    gone, alive = psutil.wait_procs(pending, timeout=timeout)
    killed.extend(proc.pid for proc in gone)
    for proc in alive:
        # It ignored the polite request. The bridge holds no state worth saving -- it
        # publishes one file at launch and then sleeps -- so there is nothing to lose.
        try:
            proc.kill()
            proc.wait(timeout=timeout)
        except psutil.NoSuchProcess:
            pass
        except psutil.Error as exc:
            failures.append(f"pid {proc.pid} ({type(exc).__name__}: {exc})")
            continue
        killed.append(proc.pid)

    if killed:
        logger.info(
            f"Cleared {len(killed)} orphaned ACQ4 Stream Dock bridge process(es): "
            f"{', '.join(str(pid) for pid in sorted(killed))}"
        )
    if failures:
        raise RuntimeError(
            f"Could not clear {len(failures)} orphaned ACQ4 Stream Dock bridge "
            f"process(es): {'; '.join(failures)}"
        )
    return sorted(killed)


def restart_vsd_craft(timeout: float = 20.0) -> None:
    """Stop VSD Craft, clear every bridge it left behind, and start it again.

    Reaping between the stop and the start is the point of doing this here rather than
    calling :func:`stop_vsd_craft` and :func:`launch_vsd_craft` in sequence: a bridge that
    survives the stop still holds the metadata acq4 is trying to replace, and would go on
    advertising a plugin session that no longer exists.

    Raises
    ------
    RuntimeError
        If VSD Craft could not be stopped, or a bridge process survived.
    """
    if not stop_vsd_craft(timeout=timeout):
        raise RuntimeError(
            f"Could not stop {VSD_CRAFT_EXE.name}; it is still running after {timeout:g}s, "
            f"so a fresh plugin session cannot be established"
        )
    reap_plugin_processes()
    launch_vsd_craft()


# --------------------------------------------------------------------------- JSON helpers


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=4, ensure_ascii=False) + '\n', encoding='utf-8')


def backup(path: Path) -> Optional[Path]:
    """Copy *path* alongside itself once, the first time we ever touch this profile."""
    path = Path(path)
    dest = path.with_name(path.name + BACKUP_SUFFIX)
    if dest.exists():
        return None
    shutil.copy2(path, dest)
    return dest


# ---------------------------------------------------------------------- page reconciliation


def page_list(parent: dict, profile_folder: str) -> list:
    """Return the parent manifest's mutable list of page folders.

    The first entry is the profile folder itself: a profile's first page lives in the
    parent manifest rather than in a subfolder, which is why it is never generated.
    """
    pages = parent.setdefault('Pages', {'Current': profile_folder, 'Pages': [profile_folder]})
    return pages.setdefault('Pages', [])


def is_managed(page_manifest: dict) -> bool:
    """True if this page was generated by us, as marked in its keys' ``Settings``."""
    for entry in page_manifest.get('Actions', {}).values():
        if (entry.get('Settings') or {}).get('generator') == GENERATOR_TAG:
            return True
    return False


def managed_pages(profile_dir: Path, parent: dict) -> list:
    """Return the generated page folders, in the order the parent lists them."""
    found = []
    for folder in page_list(parent, Path(profile_dir).name):
        manifest = Path(profile_dir) / 'profiles' / folder / 'manifest.json'
        if not manifest.exists():
            continue  # the profile's first page lives in the parent manifest itself
        try:
            if is_managed(read_json(manifest)):
                found.append(folder)
        except (OSError, json.JSONDecodeError):
            continue
    return found


def page_layout(page_manifest: dict) -> dict:
    """Return the generated layout of a page as ``{panel key: (role, row, column)}``.

    Only keys carrying our generator tag are reported, so anything the user added to a
    generated page -- a page-change control, say -- is ignored and does not on its own
    make the page look stale.
    """
    layout = {}
    for key, entry in page_manifest.get('Actions', {}).items():
        settings = entry.get('Settings') or {}
        if settings.get('generator') != GENERATOR_TAG:
            continue
        layout[key] = (settings.get('role'), settings.get('row'), settings.get('column'))
    return layout


def spec_layout(spec: GridSpec) -> dict:
    """Return the layout *spec* describes, in the same form as :func:`page_layout`."""
    layout = {}
    for role in ('dial', 'button'):
        for row, col in spec.keys(role):
            column, panelRow = spec.panelPosition(role, row, col)
            layout[f'{column},{panelRow}'] = (role, row, col)
    return layout


def stale_pages(profile_dir: Path, folders: list, spec: GridSpec) -> list:
    """Return the generated pages whose layout no longer matches *spec*.

    The page count can be right while the layout is wrong -- the configured ``buttons`` or
    ``dials`` shape changed -- and a page nobody rewrites then reports addresses that no
    longer exist, so :func:`ensure_pages` regenerates these in place.
    """
    wanted = spec_layout(spec)
    stale = []
    for folder in folders:
        manifestPath = Path(profile_dir) / 'profiles' / folder / 'manifest.json'
        try:
            if page_layout(read_json(manifestPath)) != wanted:
                stale.append(folder)
        except (OSError, json.JSONDecodeError):
            stale.append(folder)
    return stale


def unmanaged_actions(profile_dir: Path, folder: str) -> dict:
    """Return the actions on an existing generated page that this module did not write.

    Anything without our generator tag was put there by the user, in VSD Craft, on a page
    acq4 owns. Pages are rewritten wholesale, so :func:`write_page` reads these back and
    re-places them; otherwise a rewrite -- which now happens on layout drift, not only on
    a page-count change -- would silently discard them. A page-change control is the
    obvious case: acq4 places none, so the user's own is the only one there is.

    Returns an empty mapping if the page does not exist or cannot be read.
    """
    manifestPath = Path(profile_dir) / 'profiles' / folder / 'manifest.json'
    try:
        manifest = read_json(manifestPath)
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        key: entry
        for key, entry in (manifest.get('Actions') or {}).items()
        if (entry.get('Settings') or {}).get('generator') != GENERATOR_TAG
    }


def write_page(
    profile_dir: Path, parent: dict, folder: str, label: str, index: int, spec: GridSpec
) -> dict:
    """Write one generated page and return its ``Actions``.

    Keys the user placed on this page survive the rewrite: they are read back off the page
    being replaced (see :func:`unmanaged_actions`) and re-added at their own panel
    positions.

    Where such a key sits on a position the configured layout needs, the configured
    control wins and the displaced key is dropped with a warning. The rig configuration is
    the declared intent, and the alternative is worse: an acq4 control with no key behind
    it never appears and never reports, so it is dead without saying so.
    """
    profile_dir = Path(profile_dir)
    pageUuid = folder[: -len('.sdProfile')] if folder.endswith('.sdProfile') else folder
    actions = build_actions(spec, page_meta(pageUuid, label, index))
    for key, entry in unmanaged_actions(profile_dir, folder).items():
        if key in actions:
            settings = actions[key]['Settings']
            logger.warning(
                f"Panel position {key} on generated page {label!r} holds a key that acq4 "
                f"did not place, but the configured layout puts {settings['role']} "
                f"({settings['row']}, {settings['column']}) there; the configured control "
                f"wins and that key is being dropped. Move it to a panel position the "
                f"configured 'buttons' and 'dials' blocks leave free, or shrink them."
            )
            continue
        actions[key] = entry
    write_json(
        profile_dir / 'profiles' / folder / 'manifest.json',
        build_page_manifest(actions, parent, label),
    )
    (profile_dir / 'profiles' / folder / 'Images').mkdir(exist_ok=True)
    return actions


def remove_page(profile_dir: Path, parent: dict, folder: str) -> None:
    """Drop one generated page from the parent manifest and delete its folder.

    If the profile's stored current page was the one being removed, it is reset to the
    parent page, which always exists. That is the only thing this module ever writes to
    ``Pages.Current``, and it is housekeeping rather than page control: leaving it pointing
    at a folder that has just been deleted leaves VSD Craft opening a page that is not
    there. Which page the panel actually shows is the user's business, configured in VSD
    Craft; acq4 neither switches pages nor places a control that does.
    """
    profile_dir = Path(profile_dir)
    pages = parent.setdefault('Pages', {'Current': profile_dir.name, 'Pages': []})
    if folder in pages.get('Pages', []):
        pages['Pages'].remove(folder)
    if pages.get('Current') == folder:
        pages['Current'] = profile_dir.name
    shutil.rmtree(profile_dir / 'profiles' / folder, ignore_errors=True)


def resync_page_meta(profile_dir: Path, folders: list, label: str) -> None:
    """Renumber ``pageIndex`` and ``pageLabel`` after the page set changes.

    ``pageIndex`` is the acq4 page index -- the 0-based ordinal among generated pages -- and
    ``pageLabel`` reads ``"<label> 1..N"``, so both go stale whenever a page is added or
    removed. Only keys carrying our generator tag are rewritten.
    """
    for index, folder in enumerate(folders):
        manifestPath = Path(profile_dir) / 'profiles' / folder / 'manifest.json'
        try:
            manifest = read_json(manifestPath)
        except (OSError, json.JSONDecodeError):
            continue
        newLabel = f'{label} {index + 1}'
        changed = False
        for entry in manifest.get('Actions', {}).values():
            settings = entry.get('Settings') or {}
            if settings.get('generator') != GENERATOR_TAG:
                continue
            if settings.get('pageLabel') != newLabel or settings.get('pageIndex') != index:
                settings['pageLabel'] = newLabel
                settings['pageIndex'] = index
                changed = True
        if manifest.get('Name') != newLabel:
            manifest['Name'] = newLabel
            changed = True
        if changed:
            write_json(manifestPath, manifest)


def ensure_pages(
    count: int,
    spec: GridSpec | None = None,
    label: str = GENERATOR_TAG,
    device_uuid: Optional[str] = None,
    config_ini: Path = None,
    restart: bool = True,
) -> dict:
    """Make the profile hold exactly *count* generated pages.

    Pages not marked with our generator tag are left alone, so anything the user built by
    hand survives -- including the profile's first page. Keys the user placed *on* a
    generated page survive too: a rewrite carries them forward at their own panel
    positions (see :func:`write_page`). The parent manifest is backed up once, before the
    first write this module ever makes to it.

    Parameters
    ----------
    count : int
        Number of generated pages the profile should end up with.
    spec : GridSpec, optional
        Which controls each generated page holds. Defaults to ``GridSpec()``.
    label : str
        Human label baked into ``Settings['pageLabel']`` as ``"<label> N"``.
    device_uuid : str, optional
        Device to reconcile; defaults to VSD Craft's current device.
    config_ini : Path, optional
        Override the location of ``StreamDockConfig.ini``, for testing.
    restart : bool
        Whether VSD Craft may be stopped in order to write, and started if absent. With
        False, a write that needs it raises instead.

    Returns
    -------
    dict
        ``{'device', 'profile', 'pages', 'have', 'want', 'added', 'removed', 'rewritten',
        'changed', 'restarted'}``. ``pages`` lists the generated page folders in acq4 page
        order, so ``pages[i]`` is the page whose keys report ``pageIndex == i``.
    """
    if count < 0:
        raise ValueError(f"Page count must not be negative (got {count})")
    spec = GridSpec() if spec is None else spec
    profileDir, device = find_device_profile(device_uuid, config_ini=config_ini)
    profileDir = Path(profileDir)
    manifestPath = profileDir / 'manifest.json'
    if not manifestPath.exists():
        raise ProfileError(f"Stream Dock profile manifest does not exist: {manifestPath}")

    parent = read_json(manifestPath)
    current = managed_pages(profileDir, parent)

    result = {
        'device': device,
        'profile': profileDir,
        'pages': list(current),
        'have': len(current),
        'want': count,
        'added': [],
        'removed': [],
        'rewritten': [],
        'changed': False,
        'restarted': False,
    }

    def ensureRunning():
        """Start VSD Craft if it is down; without it there is nothing to talk to."""
        if restart and not vsd_craft_running():
            logger.info("VSD Craft is not running; starting it")
            launch_vsd_craft()
            result['restarted'] = True

    stale = stale_pages(profileDir, current[:count], spec)
    if len(current) == count and not stale:
        logger.debug(f"{len(current)} generated page(s) present and current; nothing to do")
        ensureRunning()
        return result

    wasRunning = vsd_craft_running()
    if wasRunning:
        if not restart:
            raise ProfileError(
                "VSD Craft is running and would overwrite the profile from its in-memory "
                "copy; pass restart=True to cycle it"
            )
        logger.info(f"Reconciling profile to {count} page(s); stopping VSD Craft to write")
        if not stop_vsd_craft():
            raise ProfileError(f"Could not stop {VSD_CRAFT_EXE.name} in order to write the profile")

    # Re-read: the application may have rewritten the profile on its way out.
    parent = read_json(manifestPath)
    current = managed_pages(profileDir, parent)
    order = page_list(parent, profileDir.name)

    while len(current) > count:
        folder = current.pop()
        remove_page(profileDir, parent, folder)
        result['removed'].append(folder)

    # Regenerate in place any surviving page whose layout no longer matches the spec, so a
    # changed 'buttons' or 'dials' shape takes effect without also changing the page count.
    for folder in stale_pages(profileDir, current, spec):
        index = current.index(folder)
        write_page(profileDir, parent, folder, f'{label} {index + 1}', index, spec)
        result['rewritten'].append(folder)

    while len(current) < count:
        folder = f'{new_page_uuid()}.sdProfile'
        order.append(folder)
        write_page(profileDir, parent, folder, f'{label} {len(current) + 1}', len(current), spec)
        current.append(folder)
        result['added'].append(folder)

    resync_page_meta(profileDir, current, label)
    backup(manifestPath)
    write_json(manifestPath, parent)

    result['pages'] = list(current)
    result['changed'] = True
    logger.info(
        f"Reconciled {device} profile {profileDir.name}: "
        f"+{len(result['added'])} -{len(result['removed'])} "
        f"~{len(result['rewritten'])} page(s), "
        f"{len(current)} generated page(s) total"
    )
    ensureRunning()
    return result
