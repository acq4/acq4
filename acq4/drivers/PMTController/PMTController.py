"""

V0.30 commands:
v       : Report Controller Firmware Version
d#      : Print ID of the selected PMT #
i#      : Read the current from the selected PMT #
c#       : Read the mean or peak current
m       : Select Mean reading mode
p       : Select Peak reading mode
a#      : Read the command voltage to the PMT #
r#      : Reset the power to the selected PMT #
o#      : Read the Overcurrent status of the selected PMT #
t###.   : Set the reading/averaging period for mean/peak mode (msec, float)
s       : Report overall status

"""
import serial, struct, time, collections

try:
    # this is nicer because it provides deadlock debugging information
    from acq4.util.Mutex import RecursiveMutex as RLock
except ImportError:
    from threading import RLock

try:
    from ..SerialDevice import SerialDevice, TimeoutError, DataError
except ValueError:
    ## relative imports not allowed when running from command prompt
    if __name__ == '__main__':
        import sys, os
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
        from SerialDevice import SerialDevice, TimeoutError, DataError


def threadsafe(method):
    # decorator for automatic mutex lock/unlock
    def lockMutex(self, *args, **kwds):
        with self.lock:
            return method(self, *args, **kwds)
    return lockMutex


class PMTController(SerialDevice):

    DEVICES = {}

    @classmethod
    def getDevice(cls, port):
        """
        Return a PMT Controller instance for the specified serial port. Only one instance will
        be created for each port.
        """
        port = SerialDevice.normalizePortName(port)
        if port not in cls.DEVICES:
            cls.DEVICES[port] = PMTController(port=port)
        return cls.DEVICES[port]

    def __init__(self, port):
        """
        port: serial COM port (eg. COM3 or /dev/ttyACM0)
        """
        self.lock = RLock()
        self.port = port
        self.PMTCurrent = 0.0  # used to remember current on each PMT
        self.PMTCmd = 0.0 # used to remember voltage on each PMT
        self.PMTIds = None  # used to remember which PMTs are present
        SerialDevice.__init__(self, port=self.port, baudrate=115200)
        time.sleep(0.5)  ## Give devices a moment to chill after opening the serial line.
        # self.read()      ## and toss any junk in the buffer

    @threadsafe
    def getPMTStatus(self):
        """Return the current status of the PMT:
            devicename, I, Measured, V, Overcurrentflag
        """
        self.write('s\n')
        packet1 = self.readUntil(term='\r\n')
        print repr(packet1)
        packet2 = self.readUntil(term='\r\n')
        return [packet1[:-1], packet2[:-1]]

    @threadsafe
    def getPMTId(self, pmt=None):
        """
        for the PMT that is addressed, get it's ID (type)
        :return: PMT ID (string)
        """
        if pmt is None:
            raise ValueError ("PMTController Device getPMTId requires a pmt number")
        self.write('d%d\n' % pmt)
        packet = self.readUntil(term='\r\n')
        return packet[:-1]

    @threadsafe
    def getFirmwareVersion(self):
        self.write('v\n')
        packet = self.readUntil(term='\r\n')
        return packet[:-1]

    @threadsafe
    def getPMTCurrent(self, pmt=None):
        """
        get the immediate measured current from one PMT
        """
        if pmt is None:
            raise ValueError ("PMTController Device getPMTCurrent requires a pmt number")
        self.write('i%d\n' % pmt)
        packet = self.readUntil(term='\r\n')
        return packet[:-1]

    # @threadsafe
    # def getPMTMeasures(self, pmt=None):
    #     """
    #     get the peak or mean measured current from one PMT
    #     """
    #     if pmt is None:
    #         raise ValueError ("PMTController Device getPMTMeasures requires a pmt number")
    #     self.write('m%d\n' % pmt)
    #     packet = self.readUntil(term='\r')
    #     return packet[:-1]

    @threadsafe
    def getPMTAnodeV(self, pmt=None):
        """
        Get PMT command voltage as measured
        """
        if pmt is None:
            raise ValueError ("PMTController Device getPMTAnodeV requires a pmt number")
        self.write('a%d\n' % pmt)
        packet = self.readUntil(term='\r\n')
        return float(packet[2:-3])

    @threadsafe
    def getPMTOverCurrent(self, pmt=None):
        """
        Get the PMT Overcurrent flag (e.g., if tripped, will be set)
        """
        if pmt is None:
            raise ValueError ("PMTController Device getPMTOverCurrent requires a pmt number")
        self.write('o%d\n' % pmt)
        packet = self.readUntil(term='\r\n')
        return packet[:-2]

    @threadsafe
    def resetPMT(self, pmt=None):
        """
        Reset a specific PMT
        :param pmt: The ID of the pmt to reset
        :return: Nothing
        """
        if pmt is None:
            raise ValueError ("PMTController Device resetPMT requires a pmt number")
        self.write('r%d\n' % pmt)


if __name__ == '__main__':
    """Test subclass that reads the PMT information"""


    s = PMTController(port='COM8')   # we have to set the port manually here - no reading from config.

    vers = s.getFirmwareVersion()
    print("PMT firmware version: {:s}".format(vers))

    status = s.getPMTStatus()
    print('Status0: {:s}\n'.format(status[0]))
    print('Status1: {:s}\n'.format(status[1]))
    v0 = s.getPMTAnodeV(0)
    v1 = s.getPMTAnodeV(1)
    print ('V0: {:6.3f}  \nV1: {:6.3f}'.format(v0, v1))

