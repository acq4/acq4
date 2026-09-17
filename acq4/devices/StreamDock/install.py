"""Install the ACQ4 plugin into the Stream Dock plugins directory.

VSD Craft only ever talks to plugins it has discovered under

    %APPDATA%\\HotSpot\\StreamDock\\plugins\\<UUID>.sdPlugin\\

so the ``plugin/`` folder shipped beside this module is copied there. The plugin itself is
a few lines of Node that publish the websocket address VSD Craft handed it; ACQ4 then
connects to that address as a second client. Nothing about the plugin needs updating when
ACQ4 changes.

A newly installed or updated plugin is only picked up when VSD Craft next starts, so
:func:`ensure_plugin` reports whether it wrote anything and the caller decides whether to
cycle the application.
"""

from __future__ import annotations

import filecmp
import shutil
from pathlib import Path

from acq4.logging_config import get_logger

from .profile import DOWNLOAD_URL, PLUGIN_DIR, PLUGIN_UUID, VSD_CRAFT_DIR, vsd_craft_installed

logger = get_logger(__name__)

#: The plugin payload shipped in this package.
SOURCE_DIR = Path(__file__).parent / 'plugin'

#: Files copied into the install directory. Everything else there -- notably the
#: ``ws-meta.json`` the plugin writes at runtime, and any older bridge left over from a
#: previous ACQ4 release -- is left alone.
PAYLOAD = [
    'manifest.json',
    'bootstrap.js',
    'images/button.png',
    'images/knob.png',
    'images/category.png',
]


def install_plugin(dest: Path = None) -> list:
    """Copy the plugin payload into *dest* (default :data:`PLUGIN_DIR`).

    Returns
    -------
    list
        The relative paths actually written; empty if everything was already identical.

    Raises
    ------
    OSError
        If the files cannot be written.
    """
    dest = PLUGIN_DIR if dest is None else Path(dest)
    written = []
    for relative in PAYLOAD:
        source = SOURCE_DIR / relative
        target = dest / relative
        if target.exists() and filecmp.cmp(source, target, shallow=False):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        written.append(relative)
    return written


def ensure_plugin(dest: Path = None, requireSoftware: bool = True) -> list:
    """Install or refresh the plugin, returning the files written.

    A non-empty return means VSD Craft has to be restarted before it will load the new
    plugin.

    Parameters
    ----------
    dest : Path, optional
        Install directory; defaults to :data:`PLUGIN_DIR`.
    requireSoftware : bool
        Raise if the Stream Dock software is not installed. Pass False to install the
        payload anyway, which is only useful for testing.

    Raises
    ------
    RuntimeError
        If the Stream Dock software is missing, or the copy fails.
    """
    if requireSoftware and not vsd_craft_installed():
        raise RuntimeError(
            f"VSD Craft was not found at {VSD_CRAFT_DIR}. Download and install the "
            f"Stream Dock software from {DOWNLOAD_URL}"
        )
    dest = PLUGIN_DIR if dest is None else Path(dest)
    try:
        written = install_plugin(dest)
    except OSError as exc:
        raise RuntimeError(
            f"Could not install the {PLUGIN_UUID} plugin into {dest}: {exc}"
        ) from exc

    if written:
        logger.info(
            f"Installed the ACQ4 Stream Dock plugin into {dest} ({len(written)} file(s)); "
            f"VSD Craft must restart to load it"
        )
    else:
        logger.debug(f"ACQ4 Stream Dock plugin already up to date at {dest}")
    return written
