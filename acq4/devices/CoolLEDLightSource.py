import glob
import sys
from collections import OrderedDict
from threading import Event, Thread

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

    An *initialState* with no brightness is applied after the hardware first reports
    each channel's current brightness, because every CoolLED command sets on/off and
    brightness together.

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
        # Validate all channels before adding any: addSource applies initialState, so a
        # bad config in a later channel would leave earlier channels lit on a device
        # that never finishes construction.
        self.validateSourceConfigs(channelConfigs)

        # A CoolLED command sets on/off and brightness together, and brightness reads 0
        # until the hardware reports it, so applying an initialState with no brightness
        # now would switch the channel on at 0%. Defer those states until the reply to
        # _requestStatus gives each channel's current brightness.
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

        self._ioStop = Event()
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
        while not self._ioStop.is_set():
            if len(self._writeBuffer) > 0:
                with self._writeLock:
                    dataToWrite = self._writeBuffer
                    self._writeBuffer = ""
                self._devConn.write(dataToWrite.encode("utf-8"))
            while self._devConn.hasDataToRead():
                self._handleData(self._devConn.readline().decode("utf-8"))
            self._ioStop.wait(0.2)

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
        """Apply the initial states deferred until the hardware reported its brightness.

        Runs on the io thread, after _handleData has stored each channel's reported
        brightness in sourceConfigs.
        """
        pending, self._pendingInitialStates = self._pendingInitialStates, OrderedDict()
        for chan, state in pending.items():
            self.setSourceState(chan, state)

    @staticmethod
    def _makeSetterCommand(channel, onOrOff, brightness):
        onOrOff = "N" if onOrOff else "F"
        return f"CSS{channel}S{onOrOff}{brightness:03d}"

    def quit(self):
        LightSource.quit(self)
        # Stop the io thread before closing the port: the thread is not a daemon, so it
        # would read a closed port and keep the process alive.
        self._ioStop.set()
        self._ioThread.join(timeout=1.0)
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
        # The command also sets on/off; keep the current on/off state so that setting
        # brightness does not switch on a source that is off.
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
