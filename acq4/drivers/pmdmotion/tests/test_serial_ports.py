"""Tests of ensure_rs485_4w's behavior where it does not touch the Windows registry."""
import sys

import pytest

from acq4.drivers.pmdmotion import serial_ports
from acq4.drivers.pmdmotion.serial_ports import ensure_rs485_4w


def test_ensure_rs485_4w_is_a_noop_off_windows(monkeypatch):
    # on any other platform it would raise ModuleNotFoundError importing winreg
    monkeypatch.setattr(serial_ports.sys, 'platform', 'linux')
    ensure_rs485_4w('COM7')


@pytest.mark.skipif(sys.platform == 'win32', reason='winreg is importable on Windows')
def test_ensure_rs485_4w_on_windows_needs_winreg(monkeypatch):
    monkeypatch.setattr(serial_ports.sys, 'platform', 'win32')
    with pytest.raises(ModuleNotFoundError):
        ensure_rs485_4w('COM7')
