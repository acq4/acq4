import serial, struct, time, collections, threading, re, pdb
try:
    from ..SerialDevice import SerialDevice, TimeoutError, DataError
except ValueError:
    ## relative imports not allowed when running from command prompt, so
    ## we adjust sys.path when running the script for testing
    if __name__ == '__main__':
        import sys, os
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
        from SerialDevice import SerialDevice, TimeoutError, DataError
        
ErrorVals = {
    0: ('SP Over-run', 'The previous character was not unloaded before the latest was received.'),
    1: ('Frame Error', 'A valid stop bit was not received during the appropriate time period.'), 
    2: ('Buffer Over-run', 'The input buffer is filled and CR has not been received.'),
    4: ('Bad Command', 'Input can not be interpreted -- command byte not valid.'),
    8: ('Move Interrupted', 'A requested move was interrupted by input on the serial port.'),
    16:('Arduino error', 'Error was reported by arduino interface.'),
    32:('MP285 Timeout', 'Arduino timed out waiting for response from MP285.'),
    64:('Command timeout', 'Arduino timed out waiting for full command from computer.'),
}
    

class TimeoutError(Exception):
    pass

class MaiTaiError(Exception):
    pass

class MaiTai(SerialDevice):
    """
    Class for communicating with Sutter MP-285 via serial port.
    
    Note that this class is NOT thread-safe.
    """
    def __init__(self, port, baud=9600):
        """
        port: serial COM port (0 => com1)"""

        self.re_float = re.compile(r'\d*\.?\d+')
        self.port = port
        self.baud = baud
        self.sp = serial.Serial(int(self.port), baudrate=self.baud, bytesize=serial.EIGHTBITS,parity=serial.PARITY_NONE,stopbits=serial.STOPBITS_ONE,xonxoff=True)
        self.waitTime = 0.5
        
        self.modeNames = OrderedDict([('PCURrent', 'Current %'), ('PPOWer', 'Green Power'), ('POWer', 'IR Power')])
    
    def convertToFloat(self,returnString):
        return float(re.findall(self.re_float,returnString)[0])
        
    def getWavelength(self):
        """Reads and returns the Mai Tai operating wavelength. the returned value may not match the commanded wavelength until the system has finished moving to the newly commanded wavelength."""
        waveLengthStr = self['READ:WAVelength?']
        return self.convertToFloat(waveLengthStr)
    
    def setWavelength(self, wl, block=False):
        """Sets the Mai Tai wavelength betweeen 690 and 1020 nm (actual wavelength range may depend on the Mai Tai model ordered).
        If block=True, do not return until the tuning is complete."""
        (minWaveLength,maxWaveLength) = self.getWavelengthRange()
        if (wl < minWaveLength) or (wl > maxWaveLength):
            raise Exception("Specified wavelength of %s nm is outside the supported range by the Mai Tai : %s < wavelength < %s" % (wl,minWaveLength,maxWaveLength)  )
        
        self['WAVelength'] = int(wl)
        
        if block:
            while True:
                if self.getWavelength() == wl:
                    break
                time.sleep(0.1)

    def getWavelengthRange(self):
        minWl = self['WAVelength:MIN?']
        maxWl = self['WAVelength:MAX?']
        return self.convertToFloat(minWl), self.convertToFloat(maxWl)
    
    def getRelativeHumidity(self):
        """Reads and returns the relative humidity (in percent) of the Mai Tai Ti:sapphire laser cavity. Humidity should always be below 10 %."""
        relHumidity = self['READ:HUM?']
        return self.convertToFloat(relHumidity)
    
    def isLaserOn(self):
        """Returns wheter laser is on."""
        status = int(self['*STB?'])  #Returns the product status byte.
        return self.is_set(status,0)
    
    def getPower(self):
        """Reads and returns Mai Tai output power"""
        outputPower = self['READ:POWer?']
        return self.convertToFloat(outputPower)
    
    def getPumpPower(self):
        """Reads and returns laser output power of the pump laser"""
        pumpOutputPower = self['READ:PLASer:POWer?']
        return self.convertToFloat(pumpOutputPower)
    
    def getLastCommandedPumpLaserPower(self):
        """ returns the last commanded pump laser power in Watts."""
        return self['PLASer:POWer?']
    
    def setPumpLaserPower(self, ppower):
        """ set the pump laser power """
        pass
    
    def getShutter(self):
        """Return True if the shutter is open."""
        return bool(int(self['SHUTter?']))
    
    def setShutter(self, val):
        """Open (True) or close (False) the shutter"""
        while self.getShutter() != val:
            self['SHUTter'] = (1 if val else 0)
        if val:
            print 'Shutter OPEN'
        else:
            print 'Shutter CLOSED'
        
    def getPumpMode(self):
        """ returns pump mode of the laser """
        crypticMode = self['MODE?']
        print crypticMode
        return self.modeNames[crypticMode]
    
    def setPumpMode(self, mode):
        """ sets the pump mode of the laser """
        for key, value in self.modeNames :
            if mode == value :
                self['MODE'] = key
        newMode = self.getPumpMode()
        print 'changedMode : ', mode, newMode
        
    def getSystemIdentification(self):
        """Return a system identification string that contains 4 fields separated by commas."""
        return self['*IDN?']
    
    def checkPulsing(self):
        """Return True if the laser is pulsing."""
        status = int(self['*STB?'])  #Returns the product status byte.
        return self.is_set(status,1)
    
    def is_set(self,x, n):
        """ checks whether n^th bit is set"""
        return (x & 2**n != 0)

    def turnLaserOn(self):
        
        while True:
            warmedUP = self.convertToFloat(self['READ:PCTWarmedup?'])
            if warmedUP == 100.:
                break
            else:
                print ('System warming up. Currently at %f ' % warmedUP)
                time.sleep(self.waitTime)

        self.write('ON\r')
        time.sleep(self.waitTime)
        print 'LASER IS ON'
        
    def turnLaserOff(self):
        if self.getShutter():
            self.setShutter(False)
        self.write('OFF\r')
        time.sleep(self.waitTime)
        print 'LASER IS OFF'
    
    def __getitem__(self, arg):  ## request a single value from the laser
        #print "write", arg
        self.write("%s\r" % arg)
        ret = self.readPacket()
        #print "   return:", ret
        return ret
        
    def __setitem__(self, arg, val):  ## set a single value on the laser
        #print "write", arg, val
        self.write("%s %s\r" % (arg,str(val)))
        #ret = self.readPacket()
        #print "   return:", ret
        #return ret

    def clearBuffer(self):
        d = self.read()
        time.sleep(0.1)
        d += self.read()
        if len(d) > 0:
            print "Sutter MP285: Warning: tossed data ", repr(d)
        return d
    
    def read(self):
        ## read all bytes waiting in buffer; non-blocking.
        n = self.sp.inWaiting()
        if n > 0:
            return self.sp.read(n)
        return ''
    
    def write(self, data):
        self.read()  ## always empty buffer before sending command
        self.sp.write(data)
        
    def close(self):
        self.sp.close()

    def readPacket(self, expect=0, timeout=10, block=True):
        ## Read until a CRLF is encountered (or timeout).
        ## If expect is >0, then try to get a packet of that length, ignoring CRLF within that data
        ## if block is False, then return immediately if no data is available.
        start = time.time()
        s = ''
        errors = []
        packets = []
        while True:
            s += self.read()
            #print "read:", repr(s)
            if not block and len(s) == 0:
                return
            
            while len(s) > 0:  ## pull packets out of s one at a time
                if '\n' in s[expect:]:
                    i = expect + s[expect:].index('\n')
                    packets.append(s[:i])
                    expect = 0
                    s = s[i+2:]
                else:
                    break
                
            if len(s) == 0:
                if len(packets) == 1:
                    if 'Error' in packets[0]:
                        raise Exception(packets[0])
                    return packets[0]   ## success
                if len(packets) > 1:
                    raise Exception("Too many packets read.", packets)
            
            time.sleep(0.01)
            if time.time() - start > timeout:
                raise TimeoutError("Timeout while waiting for response. (Data so far: %s)" % (repr(s)))
      
        
if __name__ == '__main__':
    maiTai = MaiTai(port=2) 
    #maiTai.setWavelength(910)
    #print 'current wavelength : ', maiTai.getWavelength()
    #maiTai.setWavelength(880)
    #print 'current wavelength : ', maiTai.getWavelength()
    
    print 'relative Humidity : ', maiTai.getRelativeHumidity()
    print 'current wavelength : ', maiTai.getWavelength()
    
    print 'output power : ', maiTai.getPower()
    print 'pump power : ', maiTai.getPumpPower()
    
    print 'shutter open? : ', maiTai.getShutter()
    
    print 'check status : ', maiTai.checkStatus()
    
    print 'turning laser on : ', 
    maiTai.turnLaserOn()
    print 'done'
    print 'check status : ', maiTai.checkStatus()
    print 'opening shutter : ',
    maiTai.setShutter(True)
    print 'done'
    print 'check status : ', maiTai.checkStatus()
    n=0
    while n < 10:
        print 'relative Humidity : ', maiTai.getRelativeHumidity()
        print 'output power : ', maiTai.getPower()
        print 'pump power : ', maiTai.getPumpPower()
        time.sleep(1)
        n+=1
    
    print 'closing shutter : ', 
    maiTai.setShutter(False)
    print 'done'
    print 'turning laser off : ', 
    maiTai.turnLaserOff()
    print 'done'
            