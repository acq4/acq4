import glob
import sys
from collections import OrderedDict
from threading import Thread
from time import sleep

from acq4.devices.LightSource import LightSource
from acq4.drivers.SerialDevice import SerialDevice
from acq4.util.HelpfulException import HelpfulException
from acq4.util.Mutex import Mutex


class CoolLEDLightSource(LightSource):
    """
    Driver for CoolLED family of LED light sources.
    
    Supports multi-channel LED sources with serial communication and brightness control.
    
    CoolLED-specific configuration options:
    
    * **port** (str, required): Serial port for communication (e.g., 'COM1', '/dev/ttyS2')
      Use 'probe' to auto-detect port (may affect other serial devices)
    
    The device automatically creates three light sources: 'A', 'B', and 'C' corresponding
    to the LED channels with adjustable brightness control.
    
    Standard LightSource configuration options (see LightSource base class):
    
    * **sources** (dict, optional): Extra configuration for the 'A', 'B' and 'C' sources,
      such as *wavelength*, *control* or *initialState* (see LightSource base class)

    An *initialState* that does not say what brightness it wants is applied once the
    hardware has reported the brightness it is already at, rather than as the device is
    built: every command this device sends carries the on/off bit and the intensity in
    the same three digits, so there is no way to switch a channel without also setting
    its brightness.

    * **parentDevice** (str, optional): Name of parent optical device
    
    * **transform** (dict, optional): Spatial transform relative to parent device
    
    Example configuration::
    
        CoolLED:
            driver: 'CoolLEDLightSource'
            port: 'COM3'
            parentDevice: 'Microscope'
            sources:
                A:
                    wavelength: 470 * nm
                    initialState: False  # make sure this channel is off at startup
                B:
                    initialState:  # turn this channel on at half brightness at startup
                        active: True
                        brightness: 0.5
    
    or with auto-detection::
    
        CoolLED:
            driver: 'CoolLEDLightSource'
            port: 'probe'
    """
    def __init__(self, dm, config, name):
        super(CoolLEDLightSource, self).__init__(dm, config, name)
        self._port = config["port"]
        if self._port == "probe":
            self._port = self._detectCoolLEDPort()
        self._devConn = SerialDevice(port=self._port, baudrate=57600, timeout=0)
        self._writeBuffer = ""
        self._writeLock = Mutex()

        sources = config.get("sources", {})
        channelConfigs = OrderedDict()
        for chan in ("A", "B", "C"):
            conf = dict(sources.get(chan, {}))
            conf.setdefault("adjustableBrightness", True)
            channelConfigs[chan] = conf
        # every channel is checked before any of them is applied: addSource acts on
        # initialState, and a channel lit before a later one's config turns out to
        # be bad stays lit on a device that never finishes being constructed
        self.validateSourceConfigs(channelConfigs)

        # A startup state that does not say what brightness it wants has to wait
        # for the hardware to say what brightness it is at. Every command this
        # device sends carries the on/off bit and the intensity in the same three
        # digits, so applying such a state now would send 000 as the intensity:
        # `initialState: True` would enable the channel at 0%, lighting nothing
        # while the UI, the control-surface indicator and sourceActive() all said
        # it was on -- and the hardware would then confirm 000, so that
        # disagreement would never resolve. An explicit off would likewise zero
        # the channel's stored brightness on the way past.
        self._pendingInitialStates = OrderedDict()
        for chan, conf in channelConfigs.items():
            state = conf.get("initialState")
            if state is None:
                continue
            if "brightness" not in self._normalizedSourceState(chan, state):
                self._pendingInitialStates[chan] = conf.pop("initialState")
        for chan, conf in channelConfigs.items():
            # commands issued here (e.g. for initialState) are queued until the io thread starts
            self.addSource(chan, conf)

        self._ioThread = Thread(target=self._ioAsNeeded, name="CoolLEDIOThread")
        self._ioThread.start()
        if self._pendingInitialStates:
            self._requestStatus()

    @staticmethod
    def _detectCoolLEDPort():
        if sys.platform.startswith("win"):
            ports = ["COM%s" % (i + 1) for i in range(10)]
        elif sys.platform.startswith("linux") or sys.platform.startswith("cygwin"):
            # this excludes your current terminal "/dev/tty"
            ports = glob.glob("/dev/tty[A-Za-z]*")
        elif sys.platform.startswith("darwin"):
            ports = glob.glob("/dev/tty.*")
        else:
            raise EnvironmentError("Unsupported platform")

        for port in ports:
            try:
                conn = SerialDevice(port=port, baudrate=57600, timeout=0.1)
                if conn.readline()[0:7] == b"CoolLED" or conn.readline() == 4:
                    conn.close()
                    return port
                elif conn.readline() == b"":
                    conn.write("XVER\n".encode("utf-8"))
                    out = conn.read(7)
                    if out == b"XFW_VER":
                        conn.close()
                        return port
                else:
                    conn.close()
            except (OSError, TimeoutError):
                pass

        raise HelpfulException("Could not detect a usb CoolLED light source. Are the drivers installed?")

    def _ioAsNeeded(self):
        while True:
            if len(self._writeBuffer) > 0:
                with self._writeLock:
                    dataToWrite = self._writeBuffer
                    self._writeBuffer = ""
                self._devConn.write(dataToWrite.encode("utf-8"))
            while self._devConn.hasDataToRead():
                self._handleData(self._devConn.readline().decode("utf-8"))
            sleep(0.2)

    def _requestStatus(self):
        self._sendCommand("CSS?")

    def _sendCommand(self, cmd):
        with self._writeLock:
            self._writeBuffer += f"{cmd}\n"

    def _handleData(self, resp):
        try:
            self.sourceConfigs["A"]["active"] = (resp[5] == "N")
            self.sourceConfigs["A"]["brightness"] = int(resp[6:9])
            self.sourceConfigs["B"]["active"] = (resp[11] == "N")
            self.sourceConfigs["B"]["brightness"] = int(resp[12:15])
            self.sourceConfigs["C"]["active"] = (resp[17] == "N")
            self.sourceConfigs["C"]["brightness"] = int(resp[18:21])
        except (IndexError, ValueError):
            return  # not a status string
        self._applyPendingInitialStates()

    def _applyPendingInitialStates(self):
        """Apply the startup states that were waiting on the hardware's brightness.

        Called from the io thread, with each channel's real brightness now in
        sourceConfigs, so `initialState: True` means "on, at the brightness the
        hardware is set to" and an explicit off leaves that brightness alone. See
        __init__ for why these could not be applied as the device was built.
        """
        pending, self._pendingInitialStates = self._pendingInitialStates, OrderedDict()
        for chan, state in pending.items():
            self.setSourceState(chan, state)

    @staticmethod
    def _makeSetterCommand(channel, onOrOff, brightness):
        onOrOff = "N" if onOrOff else "F"
        return f"CSS{channel}S{onOrOff}{brightness:03d}"

    def quit(self):
        self._devConn.close()

    def sourceActive(self, name):
        return self.sourceConfigs[name].get("active", False)

    def setSourceActive(self, name, active):
        cmd = self._makeSetterCommand(name, active, int(self.getSourceBrightness(name) * 100))
        self._sendCommand(cmd)
        self._noteSourceState(name, active=active)

    def getSourceBrightness(self, name):
        return self.sourceConfigs[name].get("brightness", 0) / 100.

    def setSourceBrightness(self, name, percent):
        # The on/off bit travels with the intensity in every command, so it is
        # carried over rather than derived from the intensity: setting the
        # brightness of a dark channel must not light it, and a startup state
        # asking for a channel to be off at a given brightness must not flash it
        # on on the way there.
        active = self.sourceActive(name)
        cmd = self._makeSetterCommand(name, active, int(percent * 100))
        self._sendCommand(cmd)
        self._noteSourceState(name, active=active, brightness=int(percent * 100))

    def _noteSourceState(self, name, active, brightness=None):
        """Record the state we just asked the hardware for, until the device reports back."""
        self.sourceConfigs[name]["active"] = active
        if brightness is not None:
            self.sourceConfigs[name]["brightness"] = brightness
        self._updateXkeyLight(name)
        self.sigLightChanged.emit(self, name)
