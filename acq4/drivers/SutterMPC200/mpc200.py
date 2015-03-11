import serial, struct, time, collections
import numpy as np

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
        active = self.getActiveDrive()
        try:
            return method(self, *args, **kwds)
        finally:
            self.setDrive(active)
    return resetDrive


class SutterMPC200(SerialDevice):

    DEVICES = {}


    speedTable = {
        # Measured 2015.03 for sutter stage. (see measureSpeedTable() below)
        # Values might vary for other devices..
        0: 0.0003379,  # 0.003 m / 8.9 s
        1: 0.0003606,  # 0.0033 m / 9.2 s
        2: 0.000383,  # 0.0036 m / 9.5 s
        3: 0.000412,  # 0.004 m / 9.7 s
        4: 0.0004408,  # 0.0044 m / 10 s
        5: 0.0004782,  # 0.0048 m / 10 s
        6: 0.0005233,  # 0.0053 m / 10 s
        7: 0.0005726,  # 0.0058 m / 10 s
        8: 0.0006381,  # 0.0064 m / 10 s
        9: 0.000718,  # 0.0071 m / 9.9 s
        10: 0.0008146,  # 0.0078 m / 9.6 s
        11: 0.0009575,  # 0.0086 m / 8.9 s
        12: 0.001139,  # 0.0094 m / 8.3 s
        13: 0.001404,  # 0.01 m / 7.4 s
        14: 0.00189,  # 0.011 m / 6 s
        15: 0.002767,  # 0.013 m / 4.5 s
        'fast': 0.00465  # 0.025 m / 5.38 s
    }

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
        """Set the current drive (0-3)"""
        drive += 1
        cmd = b'I' + chr(drive)
        self.write(cmd)
        ret = self.read(2, term='\r')
        if ord(ret) == drive:
            return
        else:
            raise Exception('MPC200: Drive %d is not connected' % (drive-1))
            
    @threadsafe
    def getDriveStatus(self):
        """Return the number of connected manipulators and status for each drive::
        
            (N, [d1, d2, d3, d4])
        """
        self.write('U')
        packet = self.read(length=6, term='\r')
        res = struct.unpack('<BBBBB', packet)
        return res[0], res[1:]

    @threadsafe
    def getActiveDrive(self):
        self.write('K')
        packet = self.read(4, term='\r')
        return struct.unpack('<B', packet[0])[0]-1
    
    @threadsafe
    def getFirmwareVersion(self):
        self.write('K')
        packet = self.read(4, term='\r')
        return struct.unpack('<BB', packet[1:])

    @threadsafe
    def getPos(self, drive=None, scaled=True):
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
        try:
            packet = self.read(length=14, timeout=2.0, term='\r')
        except DataError as err:
            packet = err.data
            # If interrupt occurred, there will be an extra 'I' byte at the beginning
            if packet[0] == 'I' and err.extra == '\r':
                packet = packet[1:]
            else:
                raise err

        
        drive, x, y, z = struct.unpack('<Blll', packet)
        drive -= 1
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
    def moveTo(self, drive, pos, speed, timeout=None, scaled=True):
        """Set the position of *drive*.
        
        Any item in the position may be set as None to leave it unchanged.
        
        *speed* may be specified as an integer 0-15 for constant speed, or 
        'fast' indicating that the drive should use acceleration to move as
        quickly as possible. For constant speeds, a value of 15 is maximum,
        about 1.3mm/sec for the _fastest moving axis_, not for the net speed
        of all three axes.

        If *timeout* is None, then a suitable timeout is chosen based on the selected 
        speed and distance to be traveled.
        
        Positions must be specified in meters unless *scaled* = False, in which 
        case position is specified in motor steps. 

        This method will either 1) block until the move is complete, 2) raise 
        TimeoutError if the timeout has elapsed or, 3) raise RuntimeError if the 
        move was unsuccessful (final position does not match the requested position). 
        """
        assert drive is None or drive in range(4)
        assert speed == 'fast' or speed in range(16)

        if drive is not None:
            self.setDrive(drive)

        # get current position if needed
        if None in pos or timeout is None:
            currentPos = self.getPos(scaled=False)[1]

        # scale position to microsteps, fill in Nones with current position
        ustepPos = np.empty(3, dtype=int)
        for i in range(3):
            if pos[i] is None:
                ustepPos[i] = currentPos[i]
            else:
                ustepPos[i] = np.round(pos[i] / self.scale[i])

        # be sure to never request out-of-bounds position
        for i,x in enumerate(ustepPos):
            assert 0 <= x < (25e-3 / self.scale[i])

        if timeout is None:
            # maximum distance to be travelled along any axis
            dist = (np.abs(ustepPos - currentPos) * self.scale).max()
            v = self.speedTable[speed]
            timeout = 1.0 + 1.5 * dist / v
            # print "dist, speed, timeout:", dist, v, timeout

        # Send move command
        if speed == 'fast':
            cmd = b'M' + struct.pack('<lll', *ustepPos)
            self.write(cmd)
        else:
            #self.write(b'O')  # position updates on (these are broken in mpc200?)
            self.write(b'F')  # position updates off
            self.read(1, term='\r')
            self.write(b'S' + struct.pack('B', speed))
            # MPC200 crashes if the entire packet is written at once; this sleep is mandatory
            time.sleep(0.03)
            self.write(struct.pack('<3i', *ustepPos))

        # wait for move to complete
        try:
            self.read(1, term='\r', timeout=timeout)
        except DataError:
            # If the move is interrupted, sometimes we get junk on the serial line.
            time.sleep(0.03)
            self.readAll()

        # finally, make sure we ended up at the right place.
        newPos = self.getPos(scaled=False)[1]
        for i in range(3):
            if abs(newPos[i] - ustepPos[i]) > 1:
                raise RuntimeError("Move was unsuccessful (%r != %r)."  % (tuple(newPos), tuple(ustepPos)))

    def readMoveUpdate(self):
        """Read a single update packet sent during a move.

        If the drive is moving, then return the current position of the drive.
        If the drive is stopped, then return True.
        If the drive motion was interrupted, then return False.

        Note: update packets are not generated when moving in 'fast' mode.
        """
        try:
            d = self.read(12, timeout=0.5)
        except TimeoutError as err:
            if err.data == 'I':
                return False
            else:
                print "timeout:", repr(err.data)
                return True

        pos = []
        # unpack four three-byte integers
        for i in range(4):
            x = d[i*3:(i+1)*3] + '\0'
            pos.append(struct.unpack('<i', x)[0])

        return pos

    @threadsafe
    @resetDrive
    def stop(self, drive):
        """Stop moving *drive*
        """
        if drive is not None:
            self.setDrive(drive)
            self.write('\3')
            self.read(1, term='\r')


def measureSpeedTable(dev, drive, dist=3e-3):
    """Measure table of speeds supported by the stage.

    Warning: this function moves the stage to (0, 0, 0); do not 
    run this function unless you know it is safe for your setup!
    """
    v = []
    for i in range(16):
        pos = (dist, 0, 0)
        dev.moveTo(drive, [0,0,0], 'fast')
        start = ptime.time()
        dev.moveTo(drive, pos, i, timeout=100)
        stop = ptime.time()
        dt = stop - start
        v.append(dist / dt)
        print '%d: %0.4g,  # %0.2g m / %0.2g s' % (i, v[-1], dist, dt)
        dist *= 1.1
    return v

