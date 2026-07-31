"""Tests that the test session runs against the Qt binding acq4 declares.
Covers subprocesses too, since teleprox-based tests import acq4 in a fresh
interpreter that inherits the environment but none of pytest's configuration.
"""

import subprocess
import sys

import pyqtgraph
from pytestqt.qt_compat import qt_api

# acq4 imports PyQt5 directly throughout, and declares pyqt5 in pyproject.toml.
# pytest-qt and pyqtgraph each auto-detect a binding independently, and both
# prefer PyQt6/PySide6 when those merely happen to be importable, so a session
# left to auto-detect can end up exercising a binding acq4 does not use.
DECLARED_BINDING = "PyQt5"


def test_pytest_qt_uses_the_declared_binding():
    assert qt_api.pytest_qt_api == DECLARED_BINDING.lower()


def test_pyqtgraph_uses_the_declared_binding():
    assert pyqtgraph.Qt.QT_LIB == DECLARED_BINDING


def test_pyqtgraph_uses_the_declared_binding_in_a_subprocess():
    """pyqtgraph's own detection runs again in every child interpreter, where
    pytest's ini options do not reach, so the pin has to travel as part of the
    environment."""
    completed = subprocess.run(
        [sys.executable, "-c", "import pyqtgraph; print(pyqtgraph.Qt.QT_LIB)"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == DECLARED_BINDING
