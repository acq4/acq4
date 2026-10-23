"""Tests of ensure_rs485_4w's behavior where it does not touch the Windows registry."""
import sys

import pytest

from acq4.drivers.pmdmotion import serial_ports
from acq4.drivers.pmdmotion.serial_ports import ensure_rs485_4w


def test_ensure_rs485_4w_off_windows_is_a_config_error(monkeypatch):
    """Only setRs485_4w: True reaches here, and only Windows has the Moxa registry.

    Doing nothing would leave a 2-wire adapter answering nothing on the bus, which
    reads downstream as a dead node rather than as an option that cannot be honoured.
    """
    monkeypatch.setattr(serial_ports.sys, 'platform', 'linux')
    with pytest.raises(serial_ports.CommunicationError, match="only supported on Windows"):
        ensure_rs485_4w('COM7')


@pytest.mark.skipif(sys.platform == 'win32', reason='winreg is importable on Windows')
def test_ensure_rs485_4w_on_windows_needs_winreg(monkeypatch):
    monkeypatch.setattr(serial_ports.sys, 'platform', 'win32')
    with pytest.raises(ModuleNotFoundError):
        ensure_rs485_4w('COM7')
