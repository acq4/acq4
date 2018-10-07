from __future__ import print_function
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
    """
    Provides access to all drives on a Sutter MPC200 controller.

    Example::

        dev = SutterMPC200.getDevice('com4')

        # get information about which drives are active
        n, drives = dev.getDriveStatus()

        # read position of drive 0
        print(dev.getPos(0))

        # move drive 1 to x=10mm
        dev.moveTo(1, [10e-3, 0, 0], 'fast')
    """

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

        *port* must be a serial COM port (eg. COM3 or /dev/ttyACM0)        
        """
        port = SerialDevice.normalizePortName(port)
        if port in cls.DEVICES:
            return cls.DEVICES[port]
        else:
            return SutterMPC200(port=port)

    def __init__(self, port):
        port = SerialDevice.normalizePortName(port)
        if port in SutterMPC200.DEVICES:
            raise Exception("The port %s is already accessed by another instance of this class. Use getDevice(port) instead.")
        SutterMPC200.DEVICES[port] = self
        self.lock = RLock()
        self.port = port
        SerialDevice.__init__(self, port=self.port, baudrate=128000)
        self.scale = [0.0625e-6]*3  # default is 16 usteps per micron
        self._moving = False

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
        res = struct.unpack('<BBBBB', packet)
        return res[0], res[1:]

    @threadsafe
    def getActiveDrive(self):
        self.write('K')
        packet = self.read(4, term='\r')
        return struct.unpack('<B', packet[0])[0]
    
    @threadsafe
    def getFirmwareVersion(self):
        self.write('K')
        packet = self.read(4, term='\r')
        return struct.unpack('<BB', packet[1:])

    @threadsafe
    def getPos(self, drive=None, scaled=True):
        """Get current drive and position reported by controller.

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
        pos = (x, y, z)

        if not scaled:
            return drive, pos
        pos = [pos[i]*self.scale[i] for i in [0,1,2]]
        return drive, pos

    @threadsafe
    @resetDrive
    def _getDrivePos(self, drive, scaled=True):
        ## read the position of a specific drive
        self.setDrive(drive)
        return self.getPos(scaled=scaled)

    @threadsafe
    @resetDrive
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

        This method will either 1) block until the move is complete and return the 
        final position, 2) raise TimeoutError if the timeout has elapsed or, 3) raise 
        RuntimeError if the move was unsuccessful (final position does not match the 
        requested position). Exceptions contain the final position as `ex.lastPosition`.
        """
        assert drive is None or drive in range(1,5)
        assert speed == 'fast' or speed in range(16)

        if drive is not None:
            self.setDrive(drive)

        currentPos = self.getPos(scaled=False)[1]

        # scale position to microsteps, fill in Nones with current position
        ustepPos = np.empty(3, dtype=int)
        for i in range(3):
            if pos[i] is None:
                ustepPos[i] = currentPos[i]
            else:
                if scaled:
                    ustepPos[i] = np.round(pos[i] / self.scale[i])
                else:
                    ustepPos[i] = pos[i]

        if np.all(np.abs(ustepPos-np.asarray(currentPos)) < 16):
            # step is too small; MPC200 will ignore this command and will not return \r
            return tuple([currentPos[i] * self.scale[i] for i in (0, 1, 2)])

        # be sure to never request out-of-bounds position
        for i,x in enumerate(ustepPos):
            if not (0 <= x < (25e-3 / self.scale[i])):
                raise ValueError("Invalid coordinate %d=%g; must be in [0, 25e-3]" % (i, x * self.scale[i]))

        if timeout is None:
            # maximum distance to be travelled along any axis
            dist = (np.abs(ustepPos - currentPos) * self.scale).max()
            v = self.speedTable[speed]
            timeout = 1.0 + 1.5 * dist / v
            # print "dist, speed, timeout:", dist, v, timeout

        # Send move command
        self.readAll()
        if speed == 'fast':
            cmd = b'M' + struct.pack('<lll', *ustepPos)
            self.write(cmd)
        else:
            #self.write(b'O')  # position updates on (these are broken in mpc200?)
            # self.write(b'F')  # position updates off
            # self.read(1, term='\r')
            self.write(b'S')
            # MPC200 crashes if the entire packet is written at once; this sleep is mandatory
            time.sleep(0.03)
            self.write(struct.pack('<B3i', speed, *ustepPos))

        # wait for move to complete
        try:
            self._moving = True
            self.read(1, term='\r', timeout=timeout)
        except DataError:
            # If the move is interrupted, sometimes we get junk on the serial line.
            time.sleep(0.03)
            self.readAll()
        except TimeoutError:
            # just for debugging
            print("start pos:", currentPos, "move pos:", ustepPos)
            raise
        finally:
            self._moving = False

        # finally, make sure we ended up at the right place.
        newPos = self.getPos(scaled=False)[1]
        scaled = tuple([newPos[i] * self.scale[i] for i in (0, 1, 2)])
        for i in range(3):
            if abs(newPos[i] - ustepPos[i]) > 1:
                err = RuntimeError("Move was unsuccessful (%r != %r)."  % (tuple(newPos), tuple(ustepPos)))
                err.lastPosition = scaled
                raise err

        return scaled

    def expectedMoveDuration(self, drive, pos, speed):
        """Return the expected time duration required to move *drive* to *pos* at *speed*.
        """
        cpos = np.array(self.getPos(drive)[1])

        dx = np.abs(np.array(pos) - cpos[:len(pos)]).max()
        return dx / self.speedTable[speed]

    # Disabled--official word from Sutter is that the position updates sent during a move are broken.
    # def readMoveUpdate(self):
    #     """Read a single update packet sent during a move.

    #     If the drive is moving, then return the current position of the drive.
    #     If the drive is stopped, then return True.
    #     If the drive motion was interrupted, then return False.

    #     Note: update packets are not generated when moving in 'fast' mode.
    #     """
    #     try:
    #         d = self.read(12, timeout=0.5)
    #     except TimeoutError as err:
    #         if err.data == 'I':
    #             return False
    #         else:
    #             print "timeout:", repr(err.data)
    #             return True

    #     pos = []
    #     # unpack four three-byte integers
    #     for i in range(4):
    #         x = d[i*3:(i+1)*3] + '\0'
    #         pos.append(struct.unpack('<i', x)[0])

    #     return pos

    def stop(self):
        """Stop moving the active drive.
        """
        # lock before stopping if possible
        if self.lock.acquire(blocking=False):
            try:
                self.write('\3')
                self.read(1, term='\r')
            finally:
                self.lock.release()

        # If the lock is in use, then we write immediately and hope for the best.
        else:
            self.write('\3')
            with self.lock:
                time.sleep(0.02)
                self.readAll()




def measureSpeedTable(dev, drive, dist=3e-3):
    """Measure table of speeds supported by the stage.

    Warning: this function moves the stage to (0, 0, 0); do not 
    run this function unless you know it is safe for your setup!
    """
    from acq4.pyqtgraph import ptime
    v = []
    for i in range(16):
        pos = (dist, 0, 0)
        dev.moveTo(drive, [0,0,0], 'fast')
        start = ptime.time()
        dev.moveTo(drive, pos, i, timeout=100)
        stop = ptime.time()
        dt = stop - start
        v.append(dist / dt)
        print('%d: %0.4g,  # %0.2g m / %0.2g s' % (i, v[-1], dist, dt))
        dist *= 1.1
    return v

