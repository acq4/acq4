"""Root pytest configuration for acq4.
Excludes hardware-only diagnostic scripts from automated test collection.
"""

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
