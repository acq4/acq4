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

def resetDrive(method):
    # decorator to reset any changes to currently active drive
    def resetDrive(self, *args, **kwds):
        try:
            active = self.getActiveDrive()
            return method(self, *args, **kwds)
        finally:
            self.setDrive(active)
    return resetDrive


class SutterMPC200(SerialDevice):

    DEVICES = {}

    @classmethod
    def getDevice(cls, port):
        """
        Return a SutterMPC200 instance for the specified serial port. Only one instance will 
        be created for each port.
        """
        port = SerialDevice.normalizePortName(port)
        if port not in cls.DEVICES:
            cls.DEVICES[port] = SutterMPC200(port=port)
        return cls.DEVICES[port]

    def __init__(self, port):
        """
        port: serial COM port (eg. COM3 or /dev/ttyACM0)
        """
        self.lock = RLock()
        self.port = port
        self.pos = [(None,None)]*4  # used to remember position of each drive
        self.currentDrive = None
        SerialDevice.__init__(self, port=self.port, baudrate=128000)
        self.scale = [0.0625e-6]*3  # default is 16 usteps per micron
        # time.sleep(1.0)  ## Give devices a moment to chill after opening the serial line.
        # self.read()      ## and toss any junk in the buffer

    @threadsafe
    def setDrive(self, drive):
        """Set the current drive (1-4)"""
        cmd = b'I' + chr(drive)
        self.write(cmd)
        ret = self.read(2, term='\r')
        if ord(ret) == drive:
            return
        else:
            raise Exception('MPC200: Drive %d is not connected' % drive)
            
    @threadsafe
    def getDriveStatus(self):
        """Return the number of connected manipulators and status for each drive::
        
            (N, [d1, d2, d3, d4])
        """
        self.write('U')
        packet = self.read(length=6, term='\r')
        res = struct.unpack('=BBBBB', packet)
        return res[0], res[1:]

    @threadsafe
    def getActiveDrive(self):
        self.write('K')
        packet = self.read(4, term='\r')
        return struct.unpack('=B', packet[0])[0]
    
    @threadsafe
    def getFirmwareVersion(self):
        self.write('K')
        packet = self.read(4, term='\r')
        return struct.unpack('=BB', packet[1:])

    @threadsafe
    def getPos(self, scaled=True, drive=None):
        """Get current driver and position reported by controller.
        The drive will be reported as 1-4 depending on the currently active 
        drive. If *drive* is specified, then the active drive will be set 
        before reading position, and re-set to its original value afterward.
        Returns a tuple (x,y,z); values given in meters.
        If *scaled* is False, then values are returned as motor steps.
        """
        if drive is not None:
            return self._getDrivePos(drive, scaled=scaled)

        ## request position
        self.write('C')
        packet = self.read(length=14, timeout=2.0, term='\r')
        
        drive, x, y, z = struct.unpack('=Blll', packet)
        pos = (x, y, z)

        if drive != self.currentDrive:
            self.driveChanged(drive, self.currentDrive)
            self.currentDrive = drive
        if pos != self.pos[drive][0]:
            self.posChanged(drive, pos, self.pos[drive][0])
        self.pos[drive] = pos, time.time()  # record new position

        if not scaled:
            return drive, pos
        pos = [pos[i]*self.scale[i] for i in [0,1,2]]
        return drive, pos

    def posChanged(self, drive, newPos, oldPos):
        """
        Method called whenever the position of a drive has changed. This is initiated by calling getPos().
        Override this method to respond to position changes; the default does nothing. Note
        that the values passed to this method are unscaled; multiply element-wise
        by self.scale to obtain the scaled position values.
        """
        pass

    def driveChanged(self, newDrive, oldDrive):
        """
        Method called whenever the current drive has changed. This is initiated by calling getPos().
        Override this method to respond to drive changes; the default does nothing.
        """
        pass

    @threadsafe
    @resetDrive
    def _getDrivePos(self, drive, scaled=True):
        ## read the position of a specific drive
        self.setDrive(drive)
        return self.getPos(scaled=scaled)

    @threadsafe
    @resetDrive
    def moveTo(self, drive, pos, speed, timeout=2.0, scaled=True):
        """Set the position of *driver*.
        Returns a generator that yields the position and percent done until the
        move is complete. This function should be invoked in a for-loop::
        
            for pos, percent in mpc.moveTo((x,y,z)):
                print "Moving %d percent done" % percent
        
        Any item in the position may be set as None to leave it unchanged.
        Raises an exception if the move is cancelled before it completes.
        The move may also be cancelled while in-progress by sending "stop" 
        to the generator::
        
            gen = mpc.moveTo((x,y,z))
            for pos, percent in gen:
                if user_requested_stop():
                    gen.send('stop')
                    
        *speed* may be specified as an integer 0-15 for constant speed, or 
        'fast' indicating that the drive should use acceleration to move as
        quickly as possible. For constant speeds, a value of 15 is maximum,
        about 1.3mm/sec for the _fastest moving axis_, not for the net speed
        of all three axes. 
        
        Positions must be specified in meters unless *scaled* = False, in which 
        case position is specified in motor steps. 
        """
        raise NotImplementedError()
        if drive is not None:
            self.setDrive(drive)
        
        # Convert pos argument to motor steps
        if None in pos:
            currentPos = self.getPos(scaled=False)
        pos = [(pos[i]/self.scale[i] if pos[i] is not None else currentPos[i]) for i in range(3)]
        
        # Decide on move command
        if speed == 'fast':
            cmd = b'M' + struct.pack('=lll', (x,y,z))
        else:
            cmd = b'S' + struct.pack('=Blll', (s,x,y,z))
            
        # go!
        self.sp.write(cmd)
        
        # watch for updates



        
if __name__ == '__main__':
    class MPC200(SutterMPC200):
        """Test subclass that overrides position- and drive-change callbacks"""
        def posChanged(self, drive, newpos, oldpos):
            print drive, newpos, oldpos

        def driveChanged(self, newdrive, olddrive):
            print newdrive, olddrive

    s = MPC200(port='COM3')
    
    while True:
        s.getPos()

