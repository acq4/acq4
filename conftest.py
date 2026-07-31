"""Root pytest configuration for acq4.
Excludes hardware-only diagnostic scripts, and tests needing an unpublished
dependency, from automated test collection, and pins the Qt binding.
"""

import importlib.util
import os

# acq4 imports PyQt5 directly throughout and declares pyqt5 in pyproject.toml,
# but pytest-qt and pyqtgraph each auto-detect a binding independently and both
# prefer PyQt6/PySide6 whenever those merely happen to be importable. Left to
# auto-detect, a session with several bindings installed exercises one acq4 does
# not use, and typically dies importing QtGui.
#
# These are environment variables, set here because this module is imported
# before anything can pull in Qt, rather than pytest ini options, so that they
# also reach the subprocesses the teleprox-based tests spawn -- those get a
# fresh interpreter, where pyqtgraph's detection runs again and pytest's own
# configuration does not reach. setdefault, so that deliberately asking for
# another binding still works.
os.environ.setdefault("PYTEST_QT_API", "pyqt5")
os.environ.setdefault("PYQTGRAPH_QT_LIB", "PyQt5")

# These files have ``test_``-shaped names but are NOT unit tests. They are
# interactive bench/diagnostic scripts, predating this repo's pytest suite, that
# talk to real physical hardware. Keep them: they are run by hand at the rig when
# debugging a device. Do NOT "helpfully" re-enable them -- under pytest they at
# best fail to import and at worst hang CI forever.
#
# Paths are relative to this file, so they apply no matter which directory pytest
# is invoked from.
collect_ignore = [
    # Requires pymmcore plus a real Micro-Manager camera; parses argv at import
    # time and sys.exit()s on an unrecognised adapter.
    "acq4/devices/MicroManagerCamera/test_pymmcore.py",
    # Defines no tests at all. Constructs a PlotWindow() at import time (a name
    # since removed from pyqtgraph) and calls time.clock() (removed in Py3.8).
    "acq4/devices/NiDAQ/resample_test.py",
    # Windows-only: loads the QCam DLL via ctypes.windll and acquires from the
    # camera at import time. Defines no test functions.
    "acq4/drivers/QImaging/qi_test.py",
    # Requires pyserial plus a Thorlabs MFC1 on a serial port; prints a usage
    # banner and sys.exit(1)s at import time.
    "acq4/drivers/ThorlabsMFC1/test_mfc.py",
    # Requires pyserial plus TMCM motor hardware; sys.exit(1)s at import time.
    # Its test_stall/test_encoder functions are deliberate `while True:` loops --
    # pytest would collect them by name and never return.
    "acq4/drivers/ThorlabsMFC1/test_tmcm.py",
    # Windows-only: needs pythonnet's `clr` to reach the Zeiss MTB API, and runs
    # a module-level input() loop that would block collection indefinitely.
    "acq4/drivers/zeiss/zeiss_test.py",
]

# acq4-automation (feature tracking, cell detection) lives in an INTERNAL
# repository, so a public runner cannot install it. Where it is present -- any
# rig or dev checkout -- these run normally; where it is not, skip them rather
# than fail collection for the whole suite. Anything reaching PatchPipette,
# Pipette.tracker, AutomationDebug, or Autopatch's CellPanel needs it.
def _installed(name):
    """Whether `name` can be imported. find_spec() itself raises for some
    unimportable states, and a raise here would abort collection for the whole
    repository, so anything other than a found spec counts as absent."""
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


if not _installed("acq4_automation"):
    collect_ignore += [
        "acq4/modules/AutomationDebug/tests",
        "acq4/modules/Autopatch/tests",
    ]
