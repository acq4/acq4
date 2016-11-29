# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from acq4.devices.Device import Device
from acq4.util.Mutex import Mutex

def __reload__(old):
    # avoid enumerating devices more than once because this seems to generate lots of (potentially dangerous)
    # random input events
    global XKeysDriver, PIE32_BRIDGE, pie32Proc, pieDevices, mp
    if 'pieDevices' in old:
        pieDevices = old['pieDevices']
    if 'XKeysDriver' in old:
        PIE32_BRIDGE = old['PIE32_BRIDGE']
        XKeysDriver = old['XKeysDriver']
        if 'pie32Proc' in old:
            pie32Proc = old['pie32Proc']
            mp = old['mp']


XKeysDriver = None

def getDriver():
    global XKeysDriver, PIE32_BRIDGE, mp, pie32Proc
    if XKeysDriver is None:
        try:
            import acq4.drivers.xkeys as XKeysDriver
            PIE32_BRIDGE = False
        except WindowsError as exc:
            if exc.winerror == 193:
                global pie32Proc
                # can't load PIE driver from 64-bit python
                import acq4.pyqtgraph.multiprocess as mp
                # need to make this configurable..
                executable = "C:\\Anaconda2-32\\python.exe"
                pie32Proc = mp.QtProcess(executable=executable, copySysPath=False)
                XKeysDriver = pie32Proc._import('acq4.drivers.xkeys')
                import atexit
                atexit.register(pie32Proc.close)
                PIE32_BRIDGE = True
            else:
                raise

    return XKeysDriver


pieDevices = None

def getDevices():
    global pieDevices
    if pieDevices is None:
        # create initial connection to all available devices
        drv = getDriver()
        pieDevices = [drv.XKeysDevice(h) for h in drv.getDeviceHandles()]
    return pieDevices



class XKeys(Device):
    """P.I. Engineering X-Keys input device.
    """
    sigStateChanged = QtCore.Signal(object, object)  # self, changes

    def __init__(self, man, config, name):
        Device.__init__(self, man, config, name)
        index = config.get('index', 0)
        devs = getDevices()
        if len(devs) == 0:
            raise Exception("No PIE devices found.")
        self.dev = devs[index]
        self.model = self.dev.model
        self.keyshape = self.dev.keyshape
        self.capabilities = self.dev.capabilities

        if PIE32_BRIDGE:
            self._callback = mp.proxy(self._stateChanged, callSync='off')
            self.dev.setCallback(self._callback)
        else:
            self.dev.setCallback(self._stateChanged)

        self.dev.setIntensity(255,255)

    def setBacklights(self, state, **kwds):
        if PIE32_BRIDGE:
            self.dev.__getattr__('setBacklights', _deferGetattr=True)(state, _callSync='off', **kwds)
        else:
            self.dev.setBacklights(state, **kwds)

    def getBacklights(self):
        return self.dev.backlightState.copy()

    def getState(self):
        return self.dev.state.copy()

    def capabilities(self):
        return self.dev.capabilities.copy()

    def _stateChanged(self, changes):
        self.sigStateChanged.emit(self, changes)

    def quit(self):
        self.dev.setBacklightRows(0, 0)
        self.dev.close()

