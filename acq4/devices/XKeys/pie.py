# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from acq4.devices.Device import Device
from acq4.util.Mutex import Mutex

try:
    import acq4.drivers.PIEngineering as PIEDriver
    PIE32_BRIDGE = False
except WindowsError as exc:
    if exc.winerror == 193:
        # can't load PIE driver from 64-bit python
        import acq4.pyqtgraph.multiprocess as mp
        # need to make this configurable..
        executable = "C:\\Anaconda2-32\\python.exe"
        pie32Proc = mp.QtProcess(executable=executable, copySysPath=False)
        PIEDriver = pie32Proc._import('acq4.drivers.PIEngineering')
        #PIEDriver._setProxyOptions(deferGetattr=False)
        import atexit
        atexit.register(pie32Proc.close)
        PIE32_BRIDGE = True
    else:
        raise


# create initial connection to all available devices
pieDevices = [PIEDriver.PIEDevice(h) for h in PIEDriver.getDeviceHandles()]


class PIEngineering(Device):
    """P.I. Engineering input device.
    """
    sigStateChanged = QtCore.Signal(object, object)  # self, changes

    def __init__(self, man, config, name):
        Device.__init__(self, man, config, name)
        if len(pieDevices) == 0:
            raise Exception("No PIE devices found.")
        index = config.get('index', 0)
        self.dev = pieDevices[index]
        if PIE32_BRIDGE:
            self._callback = mp.proxy(self._stateChanged, callSync='off')
            self.dev.setCallback(self._callback)
        else:
            self.dev.setCallback(self._stateChanged)

    def capabilities(self):
        return self.dev.capabilities.copy()

    def _stateChanged(self, changes):
        self.sigStateChanged.emit(self, changes)

    def quit(self):
        self.dev.close()

