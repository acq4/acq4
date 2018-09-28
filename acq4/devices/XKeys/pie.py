# -*- coding: utf-8 -*-
from __future__ import print_function
import platform
from acq4.util import Qt
from acq4.devices.Device import Device
from acq4.util.Mutex import Mutex
import acq4.pyqtgraph.multiprocess as mp

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
        if platform.architecture()[0] == '32bit':
            import acq4.drivers.xkeys as XKeysDriver
            PIE32_BRIDGE = False
        else:
            # can't load PIE driver from 64-bit python
            global pie32Proc
            # need to make this configurable..
            executable = "C:\\Anaconda2-32\\python.exe"
            pie32Proc = mp.QtProcess(executable=executable, copySysPath=False)
            XKeysDriver = pie32Proc._import('acq4.drivers.xkeys')
            import atexit
            atexit.register(pie32Proc.close)
            PIE32_BRIDGE = True

    return XKeysDriver


pieDevices = None

def getDevices():
    global pieDevices
    if pieDevices is None:
        # create initial connection to all available devices
        drv = getDriver()
        try:
            pieDevices = [drv.XKeysDevice(h) for h in drv.getDeviceHandles()]
        except mp.NoResultError:
            # XKeys can completely lock up the remote process if the device
            # is left in a bad state
            XKeysDriver = None
            global pie32Proc
            pie32Proc.proc.kill()
            pie32Proc = None
            raise Exception("No response received from xkeys remote process (try unplugging/replugging your xkeys device).")
    return pieDevices



class XKeys(Device):
    """P.I. Engineering X-Keys input device.
    """
    sigStateChanged = Qt.Signal(object, object)  # self, changes

    def __init__(self, man, config, name):
        Device.__init__(self, man, config, name)
        index = config.get('index', 0)
        devs = getDevices()
        if len(devs) == 0:
            raise Exception("No X-Keys devices found.")
        try:
            self.dev = devs[index]
        except IndexError:
            devstr = ", ".join(["%d: %s" % (i, devs[i].model) for i in range(len(devs))])
            raise ValueError("No X-Keys with device index %d. Options are: %s" % (index, devstr))
        self.model = self.dev.model
        self.keyshape = self.dev.keyshape
        self.capabilities = self.dev.capabilities

        if PIE32_BRIDGE:
            self._callback = mp.proxy(self._stateChanged, callSync='off')
            self.dev.setCallback(self._callback)
        else:
            self.dev.setCallback(self._stateChanged)

        self.dev.setIntensity(255,255)

        self._callbacks = {}
        # use queued signal here to ensure events are processed in GUI thread
        self.sigStateChanged.connect(self._handleCallbacks, Qt.Qt.QueuedConnection)

    def setBacklights(self, state, **kwds):
        if PIE32_BRIDGE:
            self.dev.__getattr__('setBacklights', _deferGetattr=True)(state, _callSync='off', **kwds)
        else:
            self.dev.setBacklights(state, **kwds)

    def getBacklights(self):
        return self.dev.backlightState.copy()

    def setBacklight(self, key, blue=None, red=None):
        """Set backlight status of a specific key.

        *blue* and *red* may be 0=off, 1=on, 2=flash.
        """
        self.dev.setBacklight(key[0], key[1], blue, red)

    def getState(self):
        return self.dev.state.copy()

    def capabilities(self):
        return self.dev.capabilities.copy()

    def _stateChanged(self, changes):
        self.sigStateChanged.emit(self, changes)

    def _handleCallbacks(self, dev, changes):
        # check for key press callbacks
        keych = changes.get('keys', [])
        for pos, state in keych:
            if state is False:
                continue
            for cb, args in self._callbacks.get(pos, []):
                cb(dev, changes, *args)
    
    def quit(self):
        self.dev.setBacklightRows(0, 0)
        self.dev.close()

    def addKeyCallback(self, key, callback, args=()):
        self._callbacks.setdefault(key, []).append((callback, args))
