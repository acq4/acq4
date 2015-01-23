"""
Summary
-------

Device code to interface with the PMT Controller implemented in an Arduino Due.
Provides connection to the PMT to read various status flags, values, and
errors, as well as commands to reset the PMT overcurrent flag. 

V0.30 commands:
n       : Report the number of PMTs handled by this controller
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
s       : Report overall status for all PMTs in the system.

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
        self.PMTCmd = 0.0  # used to remember voltage on each PMT
        self.PMTIds = None  # used to remember which PMTs are present
        SerialDevice.__init__(self, port=self.port, baudrate=115200)
        time.sleep(0.5)  # Give devices a moment to chill after opening the serial line.
        # self.read()      # and toss any junk in the buffer
        self.NPMT = self.getNumberofPMTs()  # get the number of PMTs first
        self.PMTList = range(0, self.NPMT)

    @threadsafe
    def getFirmwareVersion(self):
        """ get the Arduino Firmware Version

        Returns
        -------
        version : str
            A string with the reported firmware version
        """
        self.write('v\n')
        packet = self.readUntil(term='\r\n')
        return packet[:-2]

    @threadsafe
    def getNumberofPMTs(self):
        """ Get the number of PMTs known to the controller
        
        Returns
        -------
        npmt : int
            The number of pmts in the system
        """
        self.write('n\n')
        packet = self.readUntil(term='\r\n')
        return int(packet[6:8])

    @threadsafe
    def getPMTStatus(self):
        """Get the current overall status of the PMT:
            devicename, I, Measured, V, Overcurrentflag
        
        Returns
        -------
        status : strings
            A string holding the status information
        """
        self.write('s\n')
        packet = []
        for i in self.PMTList:
            packet.append(self.readUntil(term='\r\n')[:-2])
        return packet

    @threadsafe
    def getPMTStatusDict(self):
        """ Get the PMT status and parse into a dictionary. All PMTs are interrogated.
        Returns a dictionary with one entry per PMT.
        Each entry is a dictionary of the status values
        """
        r = self.getPMTStatus()
        d = {}
        for i in self.PMTList:
            
            d['PMT%02d' % i] = {'Type': r[i][6:15], 'Iinst': float(r[i][19:26]), 'Units': r[i][26:28], 
                                'Measuremode': r[i][30:34], 'Imeasuremode': float(r[i][34:44]), 
                                'Vcmd': float(r[i][52:58]), 'Error': int(r[i][64:66])}
        return d

    @threadsafe
    def getPMTId(self, pmt=None):
        """ for the PMT that is addressed, get it's ID (type)

        Parameters
        ----------
        pmt : int
            The pmt to read. Default None.

        Returns
        -------
        ID : str
            The PMT name as encoded in the firmware.
        """
        if pmt not in self.PMTList:
            raise ValueError ("PMTController Device getPMTId requires a pmt number")
        self.write('d%d\n' % pmt)
        packet = self.readUntil(term='\r\n')
        return packet[6:15]

    @threadsafe
    def getPMTCurrent(self, pmt=None):
        """
        get the immediate measured current from one PMT

        Parameters
        ----------
        pmt : int
            The pmt to read. Default None.

        Returns
        -------
        current : float
            The PMT current, in microamperes.
        """
        if pmt not in self.PMTList:
            raise ValueError ("PMTController Device getPMTCurrent requires a pmt number")
        self.write('i%d\n' % pmt)
        packet = self.readUntil(term='\r\n')
        return float(packet[3:9])

    @threadsafe
    def setMeasureTime(self, measuretime=100.):
        """ set the time window for averaging the PMT V and ID

        Parameters
        ----------
        measuretime : float
            Time for measurement, in msec. Default 100

        """
        self.write('t%8.1f\n' % measuretime)

    @threadsafe
    def setMeasureMode(self, mode='m'):
        """ Set the PMT reading mode over the time window

        Parameters
        ----------
        mode : str
            mode is either 'mean', 'm', or 'peak', 'p'

        """
        if mode in ['mean', 'm']:
            self.write('m\n')
        elif mode in ['peak', 'p']:
            self.write('p\n')
        else:
            raise ValueError('Measurement mode must be either peak or mean: got "%s"' % mode)

    @threadsafe
    def getPMTMeasures(self, pmt=None):
        """
        get the peak or mean measured current from one PMT

        Parameters
        ----------
        pmt : int
            The pmt to read. Default None.

        Returns
        -------
        mode : char
            the meaurement mode (m for mean, p for peak)
        signal : float
            The pmt current, measured as peak or average (depending on setting)
        """
        if pmt not in self.PMTList:
            raise ValueError ("PMTController Device getPMTMeasures requires a pmt number")
        self.write('c%d\n' % pmt)
        packet = self.readUntil(term='\r\n')
        return (packet[0], float(packet[3:12]))

    @threadsafe
    def getPMTAnodeV(self, pmt=None):
        """
        Get PMT command voltage as measured; instantaneous value.

        Parameters
        ----------
        pmt : int
            The pmt to read. Default None.

        Returns
        -------
        anodev : float
            Command anode voltage, in V.
        """
        if pmt not in self.PMTList:
            raise ValueError ("PMTController Device getPMTAnodeV requires a pmt number")
        self.write('a%d\n' % pmt)
        packet = self.readUntil(term='\r\n')
        return float(packet[3:9])

    @threadsafe
    def getPMTOverCurrent(self, pmt=None):
        """
        Get the PMT Overcurrent flag (e.g., if tripped, will be set)

        Parameters
        ----------
        pmt : int
            The pmt to read. Default None.

        Returns
        -------
        overrcurrentflag : int
            0 if ok, 1 if overcurrent detection has tripped and shut off pmt
        """
        if pmt not in self.PMTList:
            raise ValueError ("PMTController Device getPMTOverCurrent requires a pmt number")
        self.write('o%d\n' % pmt)
        packet = self.readUntil(term='\r\n')
        return int(packet[3:5])

    @threadsafe
    def resetPMT(self, pmt=None):
        """ Reset a specific PMT
        
        Parameters
        ----------
        pmt : int
            The pmt to read. Default None.
        
        """
        if pmt not in self.PMTList:
            raise ValueError ("PMTController Device resetPMT requires a pmt number")
        self.write('r%d\n' % pmt)


if __name__ == '__main__':
    """Test subclass that reads the PMT information"""

    s = PMTController(port='COM8')   # we have to set the port manually here - no reading from config.

    print("\n")
    vers = s.getFirmwareVersion()
    print("PMT firmware version: {:s}".format(vers))
    print("Number of PMTs : {:d}".format(s.NPMT))
    for i in range(0, s.NPMT):
        p = s.getPMTId(pmt=i)
        print("   PMT {:02d} is {:s}".format(i, p))

    status = s.getPMTStatus()
    s.setMeasureMode('p')
    s.setMeasureTime(500.)
    print ('\nStatus:')
    for i in range(0, s.NPMT):
        print('   PMT {:02d}: {:s}'.format(i, status[i]))
    print('\n')
    for i in range(0, s.NPMT):
        v = s.getPMTAnodeV(pmt=i)  # anode voltage
        anodei = s.getPMTCurrent(pmt=i)  # instantaneous current
        mtype, curr = s.getPMTMeasures(pmt=i)  # average or peak current
        o = s.getPMTOverCurrent(pmt=i)
        print ('V{0:d}: {1:6.3f}  I: {2:6.3f}  meas({3:1s}): {4:6.3f}, over: {5:1d}'.format(i, v, anodei, mtype, curr, o))

    print (s.getPMTStatusDict())

