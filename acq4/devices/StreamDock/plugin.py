import os
import pathlib
import shutil
import struct
import subprocess
import sys
import zlib
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: The plugin package directory (contains bridge.py and manifest.json).
_PACKAGE_DIR = pathlib.Path(__file__).parent

#: Plugin UUID — must match the UUID in manifest.json.
PLUGIN_UUID = 'com.acq4.streamdock'

#: File written by bridge.py with the WebSocket port/UUID for this session.
HANDOFF_FILE = pathlib.Path.home() / '.acq4_streamdock_port.json'

#: VSDInside Stream Dock software download page.
_DOWNLOAD_URL = 'https://www.vsdinside.com/pages/download'

#: Root directory where VSD Craft is installed.
_VSD_CRAFT_DIR = pathlib.Path('C:/Program Files (x86)/VSD Craft')
_VSD_CRAFT_EXE = _VSD_CRAFT_DIR / 'VSD Craft.exe'

APPDATA = pathlib.Path(os.environ.get('APPDATA', '~/AppData/Roaming')).expanduser()
PLUGIN_DIR = APPDATA / 'HotSpot' / 'StreamDock' / 'plugins' / f'{PLUGIN_UUID}.sdPlugin'


# ---------------------------------------------------------------------------
# Plugin installation helpers
# ---------------------------------------------------------------------------

def vsdcraft_is_installed() -> bool:
    """Return True if the VSD Craft application directory exists."""
    return _VSD_CRAFT_DIR.exists()


def vsdcraft_is_running() -> bool:
    """Return True if VSD Craft is already running."""
    result = subprocess.run(
        ['tasklist', '/FI', f'IMAGENAME eq {_VSD_CRAFT_EXE.name}', '/NH'],
        capture_output=True, text=True,
    )
    return _VSD_CRAFT_EXE.name.lower() in result.stdout.lower()


def launch_vsdcraft() -> None:
    """Start VSD Craft in the background without waiting for it to finish."""
    subprocess.Popen(
        [str(_VSD_CRAFT_EXE)],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    )


def is_bridge_running() -> bool:
    """Return True if bridge.py is currently running as a Python subprocess."""
    # Search by the plugin's unique install directory path, not the generic filename,
    # to avoid matching unrelated processes (or the wmic query string itself).
    marker = str(PLUGIN_DIR).replace('\\', '\\\\')
    result = subprocess.run(
        ['wmic', 'process', 'where', f'commandline like "%{marker}%"', 'get', 'processid'],
        capture_output=True, text=True,
    )
    # wmic outputs "ProcessId" as a header, then one numeric PID per match.
    # When nothing matches it prints "No Instance(s) Available." — only count digits.
    return any(l.strip().isdigit() for l in result.stdout.splitlines())


def _make_png(color=(0, 120, 200), size=72) -> bytes:
    """Generate a minimal solid-colour PNG using only the stdlib."""
    w, h = size, size
    r, g, b = color

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', crc)

    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
    # One scanline: filter-type byte 0x00 then RGB triplets repeated w times
    row = b'\x00' + bytes([r, g, b] * w)
    idat = chunk(b'IDAT', zlib.compress(row * h))
    iend = chunk(b'IEND', b'')
    return sig + ihdr + idat + iend


def install_plugin(python_exe: str | None = None) -> None:
    """Copy the bridge plugin into the VSD Craft plugins directory.

    Creates the plugins directory if it does not already exist.

    Parameters
    ----------
    python_exe:
        Path to the Python interpreter to embed in ``bridge.bat``.
        Defaults to ``sys.executable``.

    Raises
    ------
    OSError
        If files cannot be written (e.g. permission denied).
    """
    if python_exe is None:
        python_exe = sys.executable

    idir = PLUGIN_DIR
    idir.mkdir(parents=True, exist_ok=True)

    # bridge.py — the actual plugin logic
    shutil.copy2(_PACKAGE_DIR / 'bridge.py', idir / 'bridge.py')

    # bridge.bat — Windows launcher with the correct Python path baked in
    bat = (
        '@echo off\n'
        f'"{python_exe}" "%~dp0bridge.py" %*\n'
    )
    (idir / 'bridge.bat').write_text(bat, encoding='utf-8')

    # manifest.json — plugin declaration for Stream Dock
    shutil.copy2(_PACKAGE_DIR / 'manifest.json', idir / 'manifest.json')

    # Placeholder icon images — Stream Dock requires these files to exist
    img_dir = idir / 'images'
    img_dir.mkdir(exist_ok=True)
    png = _make_png()
    for name in ('button.png', 'category.png'):
        dest = img_dir / name
        if not dest.exists():
            dest.write_bytes(png)


def auto_install_plugin():
    idir = PLUGIN_DIR
    if idir.exists():
        logger.debug(f"[StreamDock] Bridge plugin already present at {idir}")
        return

    if not vsdcraft_is_installed():
        raise RuntimeError(
            f"VSD Craft not found at {_VSD_CRAFT_DIR}.\n"
            f"Download and install the Stream Dock software from {_DOWNLOAD_URL}"
        )

    try:
        install_plugin()
        logger.info(f"[StreamDock] Bridge plugin installed to {idir}. Restart Stream Dock to activate it.")
    except Exception as exc:
        raise RuntimeError(f"Bridge plugin installation failed: {exc}") from exc


