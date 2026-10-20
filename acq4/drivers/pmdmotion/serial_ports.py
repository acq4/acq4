"""Serial-port search and RS-485-4W configuration for the Magellan bus."""
from __future__ import annotations

import logging
import re
import subprocess
import sys

from .protocol import CommunicationError

logger = logging.getLogger(__name__)

RS485_4W = 0x3
_VID_PID = re.compile(r'^([0-9a-f]{4}):([0-9a-f]{4})$', re.IGNORECASE)

#: Where Windows records every device it has enumerated, keyed by device instance ID.
ENUM_PATH = r'SYSTEM\CurrentControlSet\Enum'


def _matches(port, search: str) -> bool:
    if (m := _VID_PID.match(search.strip())) is not None:
        vid, pid = m.group(1).upper(), m.group(2).upper()
        # hwid forms: VID_0403+PID_6010, VID_0403&PID_6010, VID:PID=0403:6010
        ident = (port.hwid or '').upper()
        return (f'VID_{vid}' in ident and f'PID_{pid}' in ident) or f'{vid}:{pid}' in ident
    return search.lower() in (port.description or '').lower()


def find_ports(search: str) -> dict:
    """Attached serial ports matching *search* as ``{device: ListPortInfo}``.

    *search* is either ``'VID:PID'`` (hex, e.g. ``'0403:6010'``) matched against the hardware
    ID, or text matched case-insensitively against the port description.
    """
    import serial.tools.list_ports
    return {p.device: p for p in serial.tools.list_ports.comports() if _matches(p, search)}


def resolve_port(port: str | None = None, search: str | None = None) -> str:
    """Return *port*, or the one port matching *search* if *port* is None.

    Raises CommunicationError if *port* is None and *search* matches zero or several ports.
    """
    if port:
        return port
    found = find_ports(search)
    if len(found) == 1:
        return next(iter(found))
    if not found:
        raise CommunicationError(f'no serial port matches portSearch {search!r}; specify "port" in the device config')
    raise CommunicationError(
        f'multiple serial ports match portSearch {search!r}: {sorted(found)}; specify "port" in the device config')


def ensure_rs485_4w(port: str) -> None:
    """Set the Moxa driver's SerInterface registry value for *port* to RS-485-4W.

    No-op off Windows. Changing the value runs ``reg`` elevated (UAC prompt). Raises
    CommunicationError if the adapter cannot be put in 4-wire mode, since a 2-wire adapter
    answers nothing on the bus and the failure then looks like a dead node instead.
    """
    if sys.platform != 'win32':
        return
    import winreg
    set_rs485_4w(winreg, port)


def set_rs485_4w(winreg, port: str) -> None:
    """Do the work of :func:`ensure_rs485_4w` through the *winreg* module given."""
    instance = device_instance_id(winreg, port)
    if instance is None:
        raise CommunicationError(
            f'cannot set RS-485-4W on {port}: no device under HKEY_LOCAL_MACHINE\\{ENUM_PATH} '
            f'serves that port')
    reg_path = f'{ENUM_PATH}\\{instance}\\Device Parameters'
    current = _ser_interface(winreg, reg_path)
    if current is None:
        raise CommunicationError(
            f'cannot set RS-485-4W on {port}: its driver has no SerInterface setting in '
            f'{reg_path}, so it is not a Moxa serial interface. Set setRs485_4w to False and '
            f'put the adapter in 4-wire mode by its own means.')
    if current == RS485_4W:
        return
    subprocess.check_call([
        'powershell', '-Command', 'Start-Process', 'reg', '-ArgumentList',
        f"'add \"HKEY_LOCAL_MACHINE\\{reg_path}\" /v SerInterface /t REG_DWORD /d {RS485_4W} /f'",
        '-Verb', 'RunAs', '-Wait'])
    written = _ser_interface(winreg, reg_path)
    if written != RS485_4W:
        raise CommunicationError(
            f'cannot set RS-485-4W on {port}: SerInterface in {reg_path} is still {written} '
            f'after the elevated write; it needs administrator rights.')
    logger.info('Set SerInterface to RS-485-4W on %s', port)


def _ser_interface(winreg, reg_path: str):
    """The SerInterface value at *reg_path*, or None if the driver has no such setting."""
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_READ) as key:
        try:
            return winreg.QueryValueEx(key, 'SerInterface')[0]
        except FileNotFoundError:
            return None


def device_instance_id(winreg, port: str) -> str | None:
    """The device instance ID of the device serving COM *port*, or None if none does.

    pyserial reports ``hwid`` as ``usb_info()`` for a USB or FTDI port -- 'USB VID:PID=0403:6010
    SER=... LOCATION=...' -- which is not a registry path, so the instance ID is found the way
    Windows itself records the association: the device whose ``Device Parameters\\PortName``
    is *port*.
    """
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ENUM_PATH) as root:
        for enumerator, devices in _subkeys(winreg, root):
            with devices:
                for device, instances in _subkeys(winreg, devices):
                    with instances:
                        for instance, key in _subkeys(winreg, instances):
                            with key:
                                if _port_name(winreg, key) == port:
                                    return f'{enumerator}\\{device}\\{instance}'
    return None


def _subkeys(winreg, key):
    """Yield ``(name, open key)`` for each subkey of *key*, skipping those it cannot open.

    Parts of the Enum tree deny read to a standard user; the port being looked for may still
    be behind one of the others.
    """
    names = []
    while True:
        try:
            names.append(winreg.EnumKey(key, len(names)))
        except OSError:
            break
    for name in names:
        try:
            sub = winreg.OpenKey(key, name)
        except OSError:
            continue
        yield name, sub


def _port_name(winreg, key):
    """``Device Parameters\\PortName`` under *key*, or None; most devices are not serial ports."""
    try:
        with winreg.OpenKey(key, r'Device Parameters') as params:
            return winreg.QueryValueEx(params, 'PortName')[0]
    except OSError:
        return None
