"""Show the Windows USB device tree and which hubs/devices Windows may power off."""

import json
import subprocess

from acq4.modules.Module import Module
from acq4.util import Qt

_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$devs = @(Get-PnpDevice | Where-Object { $_.InstanceId -like 'USB\*' })
# serial ports from vendor drivers (e.g. MOXA) enumerate outside USB\ but hang off a USB device
$ports = @(Get-PnpDevice -Class Ports | Where-Object { $_.InstanceId -notlike 'USB\*' -and $_.InstanceId -notlike 'ACPI\*' })
$parents = @{}
$all = @($devs) + @($ports)
if ($all.Count) {
    Get-PnpDeviceProperty -InstanceId $all.InstanceId -KeyName DEVPKEY_Device_Parent |
        ForEach-Object { $parents[$_.InstanceId] = $_.Data }
}
$usbIds = @{}
foreach ($d in $devs) { $usbIds[$d.InstanceId] = $true }
$devs = @($devs) + @($ports | Where-Object { $usbIds.ContainsKey($parents[$_.InstanceId]) })
$out = foreach ($d in $devs) {
    $dp = "HKLM:\SYSTEM\CurrentControlSet\Enum\$($d.InstanceId)\Device Parameters"
    $p = Get-ItemProperty $dp
    $w = Get-ItemProperty "$dp\WDF"
    [pscustomobject]@{
        id = $d.InstanceId
        parent = $parents[$d.InstanceId]
        name = $d.FriendlyName
        cls = $d.Class
        status = [string]$d.Status
        idleInWorkingState = $w.IdleInWorkingState
        enhancedPowerMgmt = $p.EnhancedPowerManagementEnabled
        selectiveSuspend = $p.SelectiveSuspendEnabled
    }
}
ConvertTo-Json -Compress -InputObject @($out)
"""

_USB_SUSPEND_SUBGROUP = "2a737441-1930-4402-8d77-b2bebba308a3"
_USB_SUSPEND_SETTING = "48e6b7a6-50f5-4782-a5d4-53bb8f07e226"

_SETTING_KEYS = ("idleInWorkingState", "enhancedPowerMgmt", "selectiveSuspend")


def _powershell(script):
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, creationflags=flags, timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"PowerShell failed: {proc.stderr.strip()}")
    return proc.stdout


def list_usb_devices():
    """Return a list of dicts describing every USB device Windows knows about."""
    out = _powershell(_SCRIPT).strip()
    return json.loads(out) if out else []


def usb_suspend_plan_setting():
    """Return (ac, dc) USB selective suspend values (1 = enabled) for the active power plan."""
    out = _powershell(f"powercfg /q SCHEME_CURRENT {_USB_SUSPEND_SUBGROUP} {_USB_SUSPEND_SETTING}")
    vals = [int(line.rsplit("0x", 1)[1], 16) for line in out.splitlines() if "Power Setting Index" in line]
    return tuple(vals[:2]) if len(vals) >= 2 else (None, None)


def power_off_state(dev):
    """Return 'Yes', 'No' or '?' for whether Windows may power this device off.

    Based on the per-device driver policy values in the registry; '?' means the driver
    exposes no setting. The power plan's USB selective suspend setting applies on top of this.
    """
    vals = [_setting(dev, k) for k in _SETTING_KEYS]
    vals = [v for v in vals if v is not None]
    if not vals:
        return "?"
    return "Yes" if any(vals) else "No"


def _setting(dev, key):
    """Return a registry policy value as an int, or None if unset (REG_BINARY arrives as a list of bytes)."""
    val = dev.get(key)
    if isinstance(val, list):
        val = val[0] if val else None
    return val


def _details(dev):
    return ", ".join(f"{k}={_setting(dev, k)}" for k in _SETTING_KEYS if _setting(dev, k) is not None)


class UsbTreeWidget(Qt.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = Qt.QVBoxLayout(self)
        self.planLabel = Qt.QLabel()
        layout.addWidget(self.planLabel)
        self.tree = Qt.QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["Device", "Class", "Status", "Can power off", "Policy values"])
        layout.addWidget(self.tree)
        buttons = Qt.QHBoxLayout()
        layout.addLayout(buttons)
        self.refreshBtn = Qt.QPushButton("Refresh")
        self.refreshBtn.clicked.connect(self.refresh)
        buttons.addWidget(self.refreshBtn)
        self.showAbsent = Qt.QCheckBox("Show absent devices")
        self.showAbsent.toggled.connect(self.rebuild)
        buttons.addWidget(self.showAbsent)
        buttons.addStretch()
        self.devs = []
        self.refresh()

    def refresh(self):
        Qt.QApplication.setOverrideCursor(Qt.Qt.CursorShape.WaitCursor)
        try:
            self.devs = list_usb_devices()
            ac, dc = usb_suspend_plan_setting()
        finally:
            Qt.QApplication.restoreOverrideCursor()
        self.planLabel.setText(
            f"Power plan USB selective suspend: AC={_enabled(ac)}, battery={_enabled(dc)}"
        )
        self.rebuild()

    def rebuild(self):
        devs = self.devs
        if not self.showAbsent.isChecked():
            devs = [d for d in devs if d.get("status") != "Unknown"]
        items = {}
        for dev in devs:
            item = Qt.QTreeWidgetItem([
                dev.get("name") or dev["id"],
                dev.get("cls") or "",
                dev.get("status") or "",
                power_off_state(dev),
                _details(dev),
            ])
            item.setToolTip(0, dev["id"])
            if dev.get("status") != "OK":
                for col in range(5):
                    item.setForeground(col, Qt.QBrush(Qt.QColor("gray")))
            items[dev["id"].lower()] = (dev, item)

        self.tree.clear()
        for dev, item in items.values():
            parent = items.get((dev.get("parent") or "").lower())
            if parent is None:
                self.tree.addTopLevelItem(item)
            else:
                parent[1].addChild(item)
        self.tree.expandAll()
        for col in range(5):
            self.tree.resizeColumnToContents(col)


def _enabled(value):
    return "unknown" if value is None else ("enabled" if value else "disabled")



class UsbTree(Module):
    """Display the USB device tree with a column showing which devices Windows may power off.

    Read-only; useful for diagnosing cameras that drop off the bus after idling.
    """
    moduleDisplayName = "USB Tree"
    moduleCategory = "Utilities"

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.win = Qt.QMainWindow()
        self.win.setWindowTitle("USB device tree")
        self.widget = UsbTreeWidget()
        self.win.setCentralWidget(self.widget)
        self.win.resize(1000, 700)
        self.win.show()
