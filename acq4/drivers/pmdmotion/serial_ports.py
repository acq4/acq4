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

    No-op off Windows or if *port* is not attached. Changing the value runs ``reg`` elevated
    (UAC prompt). Failures are logged, not raised.
    """
    if sys.platform != 'win32':
        return
    try:
        import serial.tools.list_ports
        import winreg
        info = next((p for p in serial.tools.list_ports.comports() if p.device == port), None)
        if info is None:
            return
        reg_path = f'SYSTEM\\CurrentControlSet\\Enum\\{info.hwid}\\Device Parameters'
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path, 0, winreg.KEY_READ) as key:
            current, _ = winreg.QueryValueEx(key, 'SerInterface')
        if current == RS485_4W:
            return
        subprocess.check_call([
            'powershell', '-Command', 'Start-Process', 'reg', '-ArgumentList',
            f"'add \"HKEY_LOCAL_MACHINE\\{reg_path}\" /v SerInterface /t REG_DWORD /d {RS485_4W} /f'",
            '-Verb', 'RunAs'])
        logger.info('Set SerInterface to RS-485-4W on %s', port)
    except Exception:
        logger.exception('could not configure %s for RS-485-4W', port)
