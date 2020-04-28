from ..SerialDevice import SerialDevice
from six.moves import range


def packBits(bitvals):
    return chr(sum([2**i for i in range(len(bitvals)) if bitvals[i]]))


enableBits = {
    'red':   0,
    'green': 1,
    'cyan':  2,
    'uv':    3,
    'blue':  5,
    'teal':  6,
}

intensityBits = {
    'red':   ('\x18', 3),
    'green': ('\x18', 2),
    'cyan':  ('\x18', 1),
    'uv':    ('\x18', 0),
    'blue':  ('\x1a', 0),
    'teal':  ('\x1a', 1),
}


class SpectraXDriver(object):
    """Control Spectra X device by serial port.

    Command documentation found at https://lumencor.com/resources/control-software/
    """
    def __init__(self, port):
        self.serial = None
        self.port = port
        self.open()

    def open(self):
        if self.serial is not None:
            self.close()
        self.serial = SerialDevice(port=self.port, baudrate=9600)
        self.serial.write('\x57\x02\xff\x50')
        self.serial.write('\x57\x03\xab\x50')

    def setEnabled(self, channels):
        """Enable a list of color channels and disable all others.
        """
        bits = [1, 1, 1, 1, 1, 1, 1, 0]
        for ch in channels:
            bits[enableBits[ch]] = 0

        cmd = '\x4f' + packBits(bits) + '\x50'
        # print([hex(ord(c)) for c in cmd])
        self.serial.write(cmd)

    def setIntensity(self, channels, intensity):
        """Set the intensity of multiple channels.
        """
        assert isinstance(intensity, int) and 0 <= intensity <= 255, "intensity must be integer 0-255"

        intensityBytes = chr(0xf0 | ((255-intensity) >> 4)) + chr(((255-intensity) & 0x0F) << 4)

        for dac in ('\x18', '\x1a'):
            bits = [0] * 8
            update = False

            for ch in channels:
                chDac, chBit = intensityBits[ch]
                if chDac != dac:
                    continue
                update = True
                bits[chBit] = 1

            if update is False:
                continue

            cmd = '\x53' + dac + '\x03' + packBits(bits) + intensityBytes + '\x50'
            # print([hex(ord(c)) for c in cmd])
            self.serial.write(cmd)

    def close(self):
        self.serial.close()
        self.serial = None
