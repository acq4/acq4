# -*- coding: utf-8 -*-
from __future__ import print_function
import platform
from acq4.util import Qt
from acq4.devices.Device import Device
from acq4.util.Mutex import Mutex
import pyqtgraph.multiprocess as mp
from six.moves import range

def __reload__(old):
    # avoid enumerating devices more than once because this seems to generate lots of (potentially dangerous)
    # random input events
    global XKeysDriver, pieDevices, mp
    if 'pieDevices' in old:
        pieDevices = old['pieDevices']
    if 'XKeysDriver' in old:
        XKeysDriver = old['XKeysDriver']


XKeysDriver = None

def getDriver():
    global XKeysDriver, mp
    if XKeysDriver is None:
        import acq4.drivers.xkeys as XKeysDriver
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
            raise Exception("No response received from xkeys remote process (try unplugging/replugging your xkeys device).")
    return pieDevices



class XKeys(Device):
    """P.I. Engineering X-Keys input device.

    Configuration example::

        PIKeyboard:
            driver: 'XKeys'
            index: 0
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

        self.dev.setCallback(self._stateChanged)

        self.dev.setIntensity(255,255)

        self._callbacks = {}
        # use queued signal here to ensure events are processed in GUI thread
        self.sigStateChanged.connect(self._handleCallbacks, Qt.Qt.QueuedConnection)

    def setBacklights(self, state, **kwds):
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
