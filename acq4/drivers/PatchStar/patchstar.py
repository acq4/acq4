"""
Driver for communicating with Scientifica PatchStar by serial interface.
"""
from __future__ import division
import serial, struct, time, collections
import numpy as np

from acq4.util.Mutex import RecursiveMutex as RLock
from ..SerialDevice import SerialDevice, TimeoutError, DataError


def threadsafe(method):
    # decorator for automatic mutex lock/unlock
    def lockMutex(self, *args, **kwds):
        with self.lock:
            return method(self, *args, **kwds)
    return lockMutex


class PatchStar(SerialDevice):
    """
    Provides interface to a PatchStar manipulator.

    Example::

        dev = PatchStar('com4')
        print dev.getPos()
        dev.moveTo([10e-3, 0, 0], 'fast')
    """

    def __init__(self, port):
        self.lock = RLock()
        self.port = port
        SerialDevice.__init__(self, port=self.port, baudrate=9600)
        self.scale = [0.0625e-6]*3  # default is 16 usteps per micron
        self._moving = False

    @threadsafe
    def getFirmwareVersion(self):
        self.write('DATE\r')
        return self.readUntil('\r').partition(' ')[2].partition('\t')[0]

    @threadsafe
    def getPos(self):
        """Get current manipulator position reported by controller (in micrometers).
        """
        ## request position
        self.write('POS\r')
        packet = self.readUntil('\r')
        return [int(x) for x in packet.split('\t')]

    @threadsafe
    def getSpeed(self):
        """Return the manipulator's maximum speed in micrometers per second.
        """
        self.write('TOP\r')
        return int(self.readUntil('\r'))

    @threadsafe
    def moveTo(self, pos, speed=None, timeout=None):
        """Set the position of the manipulator.
        
        *pos* must be a list of 3 items, each is either an integer representing the desired position
        of the manipulator (in micrometers), or None which indicates the axis should not be moved.

        If *speed* is given, then the maximum speed of the manipulator is set before initiating the move.
        
        If *timeout* is None, then a suitable timeout is chosen based on the selected 
        speed and distance to be traveled.
        """
        currentPos = self.getPos()

        # fill in Nones with current position
        for i in range(3):
            if pos[i] is None:
                pos[i] = currentPos[i]

        # be sure to never request out-of-bounds position
        # for i,x in enumerate(ustepPos):
        #     if not (0 <= x < (25e-3 / self.scale[i])):
        #         raise ValueError("Invalid coordinate %d=%g; must be in [0, 25e-3]" % (i, x * self.scale[i]))

        if speed is None:
            speed = self.getSpeed()
        else:
            self.setSpeed(speed)

        if timeout is None:
            dist = ((pos[0] - currentPos[0])**2 + (pos[1] - currentPos[1])**2 + (pos[2] - currentPos[2])**2)**0.5
            timeout = 1.0 + 2 * dist / speed

        # Send move command
        self.write(b'ABS %d %d %d\r' % tuple(pos))
        self.readUntil('\r')

    @threadsafe
    def stop(self):
        """Stop moving the active drive.
        """
        self.write('REL 0 0 0\r')
        self.readUntil(term='\r')

    @threadsafe
    def isMoving(self):
        self.write('S\r')
        return int(self.readUntil('\r')) != 0
