"""

Summary
-------
Interface to PMT controller (Arduino Due)

The PMTController class provides an interface to the PMT controller, which is implemented
as a serial device (USB) on an Arduino Due. 

"""
import serial, struct, time, collections, threading
from ..SerialDevice import SerialDevice

ErrorVals = {
    0: ('SP Over-run', 'The previous character was not unloaded before the latest was received.'),
    1: ('Frame Error', 'A valid stop bit was not received during the appropriate time period.'), 
    2: ('Buffer Over-run', 'The input buffer is filled and CR has not been received.'),
    4: ('Bad Command', 'Input can not be interpreted -- command byte not valid.'),
    8: ('PMT Overload', 'The PMTs are overloaded.'),
    16:('Arduino error', 'Error was reported by arduino interface.'),
    32:('PMT Controller Timeout', 'Arduino timed out waiting for response from PMT Controller.'),
    64:('Command timeout', 'Arduino timed out waiting for full command from computer.'),
}
    

class TimeoutError(Exception):
    pass

class PMTError(Exception):
    pass

class PMTController(SerialDevice):
    """
    Class for communicating with PMT Controller (Arduino Due) via serial port.
    
    Note that this class is NOT thread-safe.
    """
    def __init__(self, port, baud=115200):
        """
        port: serial COM port (0 => com1)
        """
        self.devicelist = range(0,2)  # for number of PMTs available - pmt 0,1 so far
        SerialDevice.__init__(self, port=port, baudrate=baud)
 
        time.sleep(1.0)  ## Give devices a moment to chill after opening the serial line.
        
    def getVersion(self):
        """Get current position reported by controller.

        Returns
        -------
        packet : string
            string representing the firmware version
        """
        self.write('v')
        packet = self.read(length=6, timeout=5.0, term='\r')
        return(packet)

    def getPMTID(self, devicenum=0):
        """ Read the PMT identification for this device

        Parameters
        ----------
        devicenum : int
            PMT number to read

        Returns
        -------
        name : string
            The PMT name (e.g., H7422P-40)

        """
        if devicenum not in self.devicelist:
            raise ValueError ('PMTController.getPMTName: bad device (expect in [0,1], got %d)' % devicenum)
        self.write('d%1d' % channel)
        packet = self.read(length=15, timeout=5.0, term='\r')
        name = packet[6:15])
        return name

    def getAnodeV(self, devicenum=0):
        """ Read the anode command voltage for a selected pmt

        Parameters
        ----------
        devicenum : int
            PMT number to read

        Returns
        -------
        anodev : float
            The anode command voltage, in Volts

        """
        if devicenum not in [0,1]:
            raise ValueError ('PMTController.getAnodeV: bad device (expect in [0,1], got %d)' % devicenum)
        self.write('a%1d' % channel)
        packet = self.read(length=10, timeout=5.0, term='\r')
        anodev = float(packet[3:9])
        return anodev

    def getAnodeI(self, devicenum=0):
        """ Read the anode current for a selected pmt

        Parameters
        ----------
        devicenum : int
            PMT number to read

        Returns
        -------
        anodei : float
            The anode current, in microamps

        """
        if devicenum not in self.devicelist:
            raise ValueError ('PMTController.getAnodeI: bad device (expect in [0,1], got %d)' % devicenum)
        self.write('i%1d' % channel)
        packet = self.read(length=10, timeout=5.0, term='\r')
        anodei = float(packet[3:9])
        return anodei

    def getOverloadStates(self):
        errs = [0, 0]
        for i in range(2):
            errs[i] = self.getErrorState(i)
        return errs
    
    def getOverloadState(self, devicenum):
        if devicenum in self.devicelist:
            self.write('e%1d' % devicenum)
        else:
            raise ValueError ('PMTController.resetDevice: bad device (expect in [0,1], got %d)' % devicenum)
        result = self.read(length=4, timeout=5.0, term='\r')
        return(int(result[3]))

    def getStatus(self):
        """
        Read the PMT status information (mostly this is information shown in the display)
        Returns:
            Dictionary containing:
            {'PMTID': #, 'Type': PMT Model Number, 'InstCurrent': I in uA, 'Mode': peak or mean current in uA,
            'AnodeV': V in Volts, 'Error': Errorstatusflag}
        """
       # self.readPacket(block=False)
        self.write('s')  # talks to Arduino only.
        packet = self.read(length=67, timeout=5.0, term='\r')
        if len(packet) != 67:
            raise Exception("PMTController: getStatus: bad status packet: <%s> (%d)" % (repr(packet),len(packet)))
     
        pos = [packet[:4], packet[4:8], packet[8:12]]
        pos = [struct.unpack('=l', x)[0] for x in pos]
        scale = self.scale()
        pos = [x*scale for x in pos]
        if returnButtons:
            btn = packet[12]
            btns = [ord(btn) & x == 0 for x in [1, 4, 16, 64]]
            return pos, btns
        return pos
    
    def resetPMT(self, devicenum):
        """
        reset the specified PMT from here
        """
        if devicenum in [0,1]:
            self.write('r%1d' % devicenum)
        else:
            raise ValueError ('PMTController.resetDevice: bad device (expect in [0,1], got %d)' % devicenum)

    def resetAllPMTs(self):
        for i in range(2):
            self.resetPMT(i)

    def raiseError(self, errVals):
        ## errVals should be list of error codes
        errors = []
        for err in errVals:
            hit = False
            for k in ErrorVals:
                if ord(err) & k:
                    hit = True
                    errors.append((k,)+ErrorVals[k])
            if not hit:
                errors.append((ord(err), "Unknown error code", ""))
        raise PMTError(errors)


        
if __name__ == '__main__':
    s = PMTController(port=8, baud=115200) # Arduino baud rate, NOT MP285 baud rate.

    # def pos():
    #     p = s.getPos()
    #     print "<mp285> x: %0.2fum  y: %0.2fum,  z: %0.2fum" % (p[0]*1e6, p[1]*1e6, p[2]*1e6)
        
    # def ipos():
    #     p = s.getImmediatePos()
    #     print "x: %0.2fum  y: %0.2fum,  z: %0.2fum" % (p[0]*1e6, p[1]*1e6, p[2]*1e6)
        
    # def stat():
    #     st = s.stat()
    #     for k in st:
    #         print "%s:%s%s" % (k, " "*(15-len(k)), str(st[k]))
            
    # def monitor():
    #     while True:
    #         pos()

        