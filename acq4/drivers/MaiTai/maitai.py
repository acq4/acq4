import logging
import re
import time

import serial

from ..SerialDevice import SerialDevice

logger = logging.getLogger(__name__)


StatusCodesPumpLaser = {
    1: 'Laser ON, Power Mode OK',
    2: 'Laser ON, Current Mode OK',
    3: 'Laser ON, Power Mode Adjust',
    4: 'Laser ON, Current Mode Adjust',
    5: 'Laser Diodes OFF, Ready',
    6: 'Sleep Mode OK',
    56: 'Watchdog expired, Turn laser key',
    58: 'Watchdog working normally',
    88: 'Diode Therm Short',
    89: 'Diode Therm Open',
    90: 'Diode MaxT Exceed',
    91: 'Diode Over Temperature',
    92: 'Diode Under Temperature',
    100: 'Diode Temperature',
    101: 'HSink Over Temperature',
    102: 'HSink Under Temperature',
    103: 'HSink Therm Short',
    104: 'HSink Therm Open',
    105: 'HSink MaxT Exceed',
    106: 'Tower Temperature',
    116: 'Interlocks Cleared',
    117: 'Fuse Interlock',
    118: 'System Interlock',
    119: 'User Interlock',
    120: 'Key Switch ILK',
    121: 'Remote Interlock',
    122: 'Head Interlock',
    123: 'Boot test Fail',
    131: 'Head overtemp check chiller',
    201: 'Current Calibration Diode 1',
    202: 'Current Calibration Diode 2',
    205: 'Temperature Calibration Diode 1',
    206: 'Temperature Calibration Diode 2',
    209: 'SHG temperature Setting',
}

StatusCodes = {
    400: 'System just finished boot',
    405: 'System ON',
    406: 'System OFF',
    407: 'command MODE PCUR received',
    408: 'command MODE PPOW received',
    409: 'command MODE POW received',
    421: 'communication error between Mai Tai & Power Supply',
    430: 'motors are moving',
    431: 'wavelength is stable, all motors stopped',
    444: 'P2 is between 10 and 90 %',
    445: 'P2 (X or Y) is between 1 and 10 % or 90 and 99 %',
    446: 'P2 (X or Y) is lower than 1 % or greater than 99 %',
    450: 'M3 is not available',
    451: 'M3 is disabled',
    452: 'M3 is inactive',
    453: 'M3 is active',
    454: 'M3 are between 10 and 90 %',
    455: 'M3 (X or Y) is between 1 and 10 % or 90 and 99 %',
    456: 'M3 (X or Y) is lower than 1 or greater than 99 %',
    460: 'IR loop is not available',
    461: 'IR loop disabled',
    462: 'IR loop is inactive',
    463: 'IR loop is active',
    470: 'Tower temperature is correct',
    471: 'Tower temperature is warm',
    472: 'Tower temperature is hot',
    474: 'Tower temperature is cold',
}

# READ:PDITher? response codes
P2_STATUS = {
    441: False,  # P2 switch off: servo always inactive
    442: False,  # P2 autoseek, output power < ~130 mW: servo inactive
    443: True,   # P2 autoseek, output power > ~150 mW: servo active
}


# Pump mode names accepted by setPumpMode and returned by getPumpMode
PUMP_CURRENT = 'Current %'
PUMP_GREEN_POWER = 'Green Power'
PUMP_IR_POWER = 'IR Power'


class MaiTaiError(Exception):
    pass


class MaiTai(SerialDevice):
    """Serial interface to a Spectra-Physics Mai Tai Ti:sapphire laser.

    Wavelengths are in nm and powers in W, as reported by the laser.
    """

    # MODE? response codes and their human-readable names
    pumpModes = {'PCUR': PUMP_CURRENT, 'PPOW': PUMP_GREEN_POWER, 'POW': PUMP_IR_POWER}

    def __init__(self, port, baud=9600):
        SerialDevice.__init__(
            self,
            port=port,
            baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            xonxoff=True,
        )
        # pause after on/off commands, and between warmup polls
        self.waitTime = 0.5

    @staticmethod
    def _parseFloat(response):
        """Return the first number in a response string such as '800nm' or '1.23W'."""
        return float(re.findall(r'[-+]?\d*\.?\d+', response)[0])

    @staticmethod
    def _isBitSet(x, n):
        return x & (1 << n) != 0

    def getWavelength(self):
        """Return the current operating wavelength.

        This may differ from the commanded wavelength until tuning is complete.
        """
        return self._parseFloat(self['READ:WAVelength?'])

    def setWavelength(self, wl, block=False):
        """Set the wavelength in nm (range depends on the Mai Tai model).

        If *block* is True, do not return until tuning is complete.
        """
        minWl, maxWl = self.getWavelengthRange()
        if not minWl <= wl <= maxWl:
            raise ValueError(f"Wavelength {wl} nm is outside the Mai Tai range {minWl}-{maxWl} nm")
        self['WAVelength'] = int(wl)
        if block:
            while self.getWavelength() != int(wl):
                time.sleep(0.1)

    def getWavelengthRange(self):
        return self._parseFloat(self['WAVelength:MIN?']), self._parseFloat(self['WAVelength:MAX?'])

    def getRelativeHumidity(self):
        """Return the relative humidity (%) of the laser cavity. This should always be below 10%."""
        return self._parseFloat(self['READ:HUM?'])

    def _statusByte(self):
        return int(self['*STB?'])

    def isLaserOn(self):
        return self._isBitSet(self._statusByte(), 0)

    def isPulsing(self):
        return self._isBitSet(self._statusByte(), 1)

    def getPower(self):
        """Return the measured IR output power."""
        return self._parseFloat(self['READ:POWer?'])

    def getCommandedPower(self):
        """Return the programmed IR output power."""
        return self._parseFloat(self['POWer?'])

    def getPumpCurrentPercentage(self):
        """Return the measured pump laser current (%)."""
        return self._parseFloat(self['READ:PLASer:PCURrent?'])

    def getCommandedPumpCurrentPercentage(self):
        return self._parseFloat(self['PLASer:PCURrent?'])

    def setPumpCurrentPercentage(self, pcurrent):
        self['PLASer:PCURrent'] = float(pcurrent)

    def getPumpPower(self):
        """Return the measured pump laser (green) output power."""
        return self._parseFloat(self['READ:PLASer:POWer?'])

    def getCommandedPumpPower(self):
        return self._parseFloat(self['PLASer:POWer?'])

    def setPumpPower(self, power):
        self['PLASer:POWer'] = float(power)

    def getShutter(self):
        """Return True if the internal shutter is open."""
        return bool(int(self['SHUTter?']))

    def setShutter(self, val, attempts=5):
        """Open (True) or close (False) the internal shutter."""
        for _ in range(attempts):
            self['SHUTter'] = 1 if val else 0
            if self.getShutter() == val:
                return
        raise MaiTaiError(f"Shutter did not {'open' if val else 'close'} after {attempts} attempts")

    def getPumpMode(self):
        """Return the pump mode as one of the names in `pumpModes`."""
        return self.pumpModes[self['MODE?']]

    def setPumpMode(self, mode):
        """Set the pump mode by name (one of the values in `pumpModes`)."""
        codes = {name: code for code, name in self.pumpModes.items()}
        self['MODE'] = codes[mode]

    def getSystemIdentification(self):
        """Return the identification string (4 comma-separated fields)."""
        return self['*IDN?']

    def getStatus(self):
        """Return a description of the most recent system status code."""
        code = int(self['READ:AHISTory?'].split()[0])
        return StatusCodes.get(code, f"Unknown status code {code}")

    def getPumpLaserStatus(self):
        """Return a description of the most recent pump laser status code."""
        code = int(self['PLASer:AHISTory?'].split()[0])
        return StatusCodesPumpLaser.get(code, f"Unknown pump laser status code {code}")

    def getP2Status(self):
        """Return True if the P2 pump optimization servo is active."""
        code = int(self['READ:PDITher?'])
        if code not in P2_STATUS:
            raise MaiTaiError(f"Unknown P2 status code {code}")
        return P2_STATUS[code]

    def setP2Status(self, enable):
        """Enable or disable P2 pump optimization ('dither for power')."""
        self['CONTrol:PDITher'] = int(enable)

    def getWarmupPercentage(self):
        return self._parseFloat(self['READ:PCTWarmedup?'])

    def turnLaserOn(self):
        """Turn on the laser, first blocking until warmup is complete."""
        while True:
            warmup = self.getWarmupPercentage()
            if warmup >= 100:
                break
            logger.info("Mai Tai warming up: %.0f%%", warmup)
            time.sleep(self.waitTime)
        self.sendCommand('ON')
        time.sleep(self.waitTime)

    def turnLaserOff(self):
        if self.getShutter():
            self.setShutter(False)
        self.sendCommand('OFF')
        time.sleep(self.waitTime)

    def sendCommand(self, cmd):
        """Send a command without reading any response."""
        self.readAll()  # discard any stale data so it is not mistaken for the next response
        self.write(f"{cmd}\r")

    def query(self, cmd):
        """Send a query and return the response string."""
        self.sendCommand(cmd)
        response = self.readUntil(b'\n', timeout=10).decode().strip()
        if 'Error' in response:
            raise MaiTaiError(f"Mai Tai returned error for {cmd!r}: {response}")
        return response

    def __getitem__(self, cmd):
        return self.query(cmd)

    def __setitem__(self, cmd, val):
        self.sendCommand(f"{cmd} {val}")


if __name__ == '__main__':
    import sys

    mt = MaiTai(sys.argv[1])
    print('identification:', mt.getSystemIdentification())
    print('wavelength:', mt.getWavelength())
    print('relative humidity:', mt.getRelativeHumidity())
    print('output power:', mt.getPower())
    print('pump power:', mt.getPumpPower())
    print('shutter open:', mt.getShutter())
    print('pump mode:', mt.getPumpMode())
