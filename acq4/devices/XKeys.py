from acq4.devices.Keyboard import Keyboard

XKeysDriver = None
pieDevices = None


def __reload__(old):
    # avoid enumerating devices more than once because this seems to generate lots of (potentially dangerous)
    # random input events
    global XKeysDriver, pieDevices, mp
    if 'pieDevices' in old:
        pieDevices = old['pieDevices']
    if 'XKeysDriver' in old:
        XKeysDriver = old['XKeysDriver']


def getDriver():
    global XKeysDriver, mp
    if XKeysDriver is None:
        import acq4.drivers.xkeys as XKeysDriver
    return XKeysDriver


def getDevices():
    global pieDevices, XKeysDriver
    if pieDevices is None:
        # create initial connection to all available devices
        drv = getDriver()
        try:
            pieDevices = [drv.XKeysDevice(h) for h in drv.getDeviceHandles()]
        except mp.NoResultError as e:
            # XKeys can completely lock up the remote process if the device
            # is left in a bad state
            XKeysDriver = None
            raise RuntimeError(
                "No response received from xkeys remote process (try unplugging/replugging your xkeys device)."
            ) from e
    return pieDevices


class XKeys(Keyboard):
    """P.I. Engineering X-Keys input device.

    Configuration example::

        PIKeyboard:
            driver: 'XKeys'
            index: 0
    """
    def __init__(self, man, config, name):
        super().__init__(man, config, name)
        index = config.get('index', 0)
        devs = getDevices()
        if len(devs) == 0:
            raise RuntimeError("No X-Keys devices found.")
        try:
            self.dev = devs[index]
        except IndexError as e:
            devstr = ", ".join([f"{i}: {devs[i].model}" for i in range(len(devs))])
            raise ValueError(f"No X-Keys with device index {index}. Options are: {devstr}") from e
        self.model = self.dev.model
        self.keyshape = self.dev.keyshape
        self.capabilities = self.dev.capabilities

        self.dev.setCallback(self._stateChanged)

        self.dev.setIntensity(255, 255)

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

    def quit(self):
        self.dev.setBacklightRows(0, 0)
        self.dev.close()
