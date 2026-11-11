import time

from acq4.devices.Laser import Laser, LaserTask
from acq4.drivers.MaiTai import MaiTai, PUMP_GREEN_POWER, PUMP_IR_POWER
from acq4.util import Qt
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread

from .MaiTaiDevGui import MaiTaiDevGui


class MaiTaiLaser(Laser):
    """
    Driver for Spectra-Physics Mai Tai tunable Ti:sapphire lasers.

    Extends the base Laser class with wavelength tuning, laser on/off and internal shutter
    control, pump mode selection, and status monitoring (output and pump power, humidity,
    pulsing, P2 optimization, and status codes).

    Configuration options:

    * **port** (str | int, required): Serial port (e.g. 'COM3' or '/dev/ttyUSB0')

    * **baud** (int, optional): Serial baud rate (default: 9600)

    * **alignmentPower** (float, optional): Target output power in W for pump alignment mode
      (default: 0.2). While alignment mode is active, the pump power is continuously adjusted
      to keep output between this value and 25% above it.

    * **externalSwitch** (dict, optional): DAQ digital output that the device GUI toggles,
      optionally linked to turn off whenever the internal shutter opens.

    * All options from base Laser class are supported.

    Example configuration::

        Laser-2P:
            driver: 'MaiTaiLaser'
            port: 'COM3'
            baud: 9600
            scope: 'Microscope'
            pCell:
                device: 'DAQ'
                channel: '/Dev2/ao0'
                type: 'ao'
            shutter:
                device: 'DAQ'
                channel: '/Dev2/port0/line0'
                type: 'do'
                delay: 10*ms
            externalSwitch:
                device: 'DAQ'
                channel: '/Dev2/port0/line2'
                type: 'do'
    """

    sigStatusChanged = Qt.Signal(object)  # dict of Mai Tai status values; see MaiTaiThread.readStatus

    def __init__(self, dm, config, name):
        self.alignmentPower = config.get('alignmentPower', 0.2)
        self.driver = MaiTai(config['port'], config.get('baud', 9600))
        self.driverLock = Mutex(Qt.QMutex.Recursive)  # access to low level driver calls

        self.pumpAlignmentMode = False
        self._pumpPowerBeforeAlignment = None

        Laser.__init__(self, dm, config, name)

        self.hasShutter = True
        self.hasTunableWavelength = True

        self.mThread = MaiTaiThread(self)
        self.mThread.sigStatusChanged.connect(self._statusChanged)
        self.mThread.start()

        if self.hasExternalSwitch and not self.getInternalShutter():
            self.setExternalSwitch(True)

        dm.sigAbortAll.connect(self.closeInternalShutter)

    def _statusChanged(self, status):
        power = status['power']
        self.setParam(currentPower=power)
        self.sigOutputPowerChanged.emit(power, self.checkPowerValidity(power))
        self.sigWavelengthChanged.emit(status['wavelength'])
        self.sigStatusChanged.emit(status)

    def _measurePower(self):
        with self.driverLock:
            return self.driver.getPower()

    def isLaserOn(self):
        with self.driverLock:
            return self.driver.isLaserOn()

    def switchLaserOn(self):
        """Turn on the laser. Blocks until the laser has finished warming up."""
        with self.driverLock:
            self.driver.turnLaserOn()

    def switchLaserOff(self):
        with self.driverLock:
            self.driver.turnLaserOff()

    def getWavelength(self):
        with self.driverLock:
            return self.driver.getWavelength() * 1e-9

    def setWavelength(self, wl):
        with self.driverLock:
            self.driver.setWavelength(wl * 1e9)

    def getWavelengthRange(self):
        with self.driverLock:
            bounds = self.driver.getWavelengthRange()
        return bounds[0] * 1e-9, bounds[1] * 1e-9

    def getPumpMode(self):
        with self.driverLock:
            return self.driver.getPumpMode()

    def setPumpMode(self, mode):
        with self.driverLock:
            self.driver.setPumpMode(mode)

    def setPumpCurrent(self, percent):
        with self.driverLock:
            self.driver.setPumpCurrentPercentage(percent)

    def setPumpPower(self, power):
        with self.driverLock:
            self.driver.setPumpPower(power)

    def openInternalShutter(self):
        with self.driverLock:
            self.driver.setShutter(True)

    def closeInternalShutter(self):
        with self.driverLock:
            self.driver.setShutter(False)

    def getInternalShutter(self):
        with self.driverLock:
            return self.driver.getShutter()

    def setPumpAlignmentMode(self, enable):
        """Enable or disable low-power alignment mode.

        In alignment mode, P2 optimization is disabled, the laser is switched to green power
        mode, and the pump power is regulated to hold the output near *alignmentPower*.
        Disabling restores the previous pump power, IR power mode, and P2 optimization.
        """
        with self.driverLock:
            if enable:
                self.driver.setP2Status(False)
                self._pumpPowerBeforeAlignment = self.driver.getCommandedPumpPower()
                self.driver.setPumpMode(PUMP_GREEN_POWER)
            else:
                self.driver.setPumpPower(self._pumpPowerBeforeAlignment)
                self.driver.setPumpMode(PUMP_IR_POWER)
                self.driver.setP2Status(True)
            self.pumpAlignmentMode = enable

    def regulateAlignmentPower(self, outputPower):
        """Adjust pump power to keep output between alignmentPower and alignmentPower + 25%."""
        target = self.alignmentPower
        with self.driverLock:
            pumpPower = self.driver.getCommandedPumpPower()
            if outputPower > target * 1.25:
                self.driver.setPumpPower(round(pumpPower * 0.98, 2))
            elif outputPower < target:
                self.driver.setPumpPower(round(pumpPower * 1.01, 2))

    def createTask(self, cmd, parentTask):
        return MaiTaiTask(self, cmd, parentTask)

    def deviceInterface(self, win):
        return MaiTaiDevGui(self)

    def quit(self):
        self.mThread.stop(block=True)
        Laser.quit(self)


class MaiTaiTask(LaserTask):
    # The internal shutter is not operated during tasks; use an external shutter instead.
    pass


class MaiTaiThread(Thread):
    """Polls the laser for status, and drives pump power regulation during alignment mode."""

    sigStatusChanged = Qt.Signal(object)

    def __init__(self, dev):
        Thread.__init__(self, name=f'MaiTaiThread_{dev.name()}')
        self.lock = Mutex(Qt.QMutex.Recursive)
        self.dev = dev
        self.stopThread = False

    def readStatus(self):
        d = self.dev.driver
        return {
            'power': d.getPower(),
            'wavelength': d.getWavelength() * 1e-9,
            'humidity': d.getRelativeHumidity(),
            'pumpPower': d.getPumpPower(),
            'pumpCurrent': d.getPumpCurrentPercentage(),
            'commandedPower': d.getCommandedPower(),
            'isPulsing': d.isPulsing(),
            'pumpMode': d.getPumpMode(),
            'p2Optimization': d.getP2Status(),
            'status': d.getStatus(),
            'pumpLaserStatus': d.getPumpLaserStatus(),
        }

    def run(self):
        while True:
            try:
                with self.dev.driverLock:
                    status = self.readStatus()
                if self.dev.pumpAlignmentMode:
                    self.dev.regulateAlignmentPower(status['power'])
                self.sigStatusChanged.emit(status)
            except Exception:
                self.dev.logger.exception("Error in Mai Tai laser communication thread:")

            with self.lock:
                if self.stopThread:
                    break
            time.sleep(0.5)

        self.dev.driver.close()

    def stop(self, block=False):
        with self.lock:
            self.stopThread = True
        if block and not self.wait(10000):
            raise TimeoutError("Timed out while waiting for Mai Tai thread to exit")
