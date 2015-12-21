"""
Driver for communicating with Scientifica motorized devices by serial interface.
"""
from __future__ import division
import serial, struct, time, collections
import numpy as np

from acq4.util.Mutex import RecursiveMutex as RLock
from ..SerialDevice import SerialDevice, TimeoutError, DataError


# Data provided by Scientifica
_device_types = """
Device Type,Drive Current,Holding Current,UUX,UUY,UUZ,MODE,CARD TYPE
IMMTP,200,100,-5.12,-5.12,-5.12,0,1.01
MMTP,200,100,-5.12,-5.12,-5.12,0,1.03
Slicemaster,200,100,-5.12,-5.12,-5.12,0,1.04
Patchstar,230,175,-6.4,-6.4,-6.4,1,1.05
MMSP,230,175,-6.4,-6.4,-6.4,1,1.06
MMSP+Z,230,175,-6.4,-6.4,-6.4,1,1.07
Microstar,230,220,-6.4,-6.4,-6.4,0,1.08
UMS2,200,125,-4.03,-4.03,-5.12,0,1.09
Slicescope,200,125,-4.03,-4.03,-6.4,0,1.11
Condenser,200,125,-4.03,-4.03,-6.4,0,1.12
MMBP,200,125,-4.03,-4.03,-6.4,0,1.13
IVM,230,175,-6.4,-6.4,-6.4,0,1.14
IVM Mini,230,175,-6.4,-6.4,-6.4,0,1.14
"""


class Scientifica(SerialDevice):
    """
    Provides interface to a Scientifica manipulator.

    Example::

        dev = Scientifica('com4')
        print dev.getPos()
        dev.moveTo([10e-3, 0, 0], 'fast')
    """

    def __init__(self, port, baudrate=9600):
        self.lock = RLock()
        self.port = port
        SerialDevice.__init__(self, port=self.port, baudrate=baudrate)
        self._readAxisScale()

    def send(self, msg):
        with self.lock:
            self.write(msg + '\r')
            result = self.readUntil('\r')[:-1]
            if result.startswith('E,'):
                errno = int(result.strip()[2:])
                exc = RuntimeError("Received error %d from Scientifica controller (request: %r)" % (errno, msg))
                exc.errno = errno
                raise exc
            return result

    def getFirmwareVersion(self):
        return self.send('DATE').partition(' ')[2].partition('\t')[0]

    def getType(self):
        """Return a string indicating the type of the device, or the type's numerical value
        if it is unknown.
        """
        types = {
            '1': 'linear', '2': 'ums', '3': 'mmtp', '4': 'slicemaster', '5': 'patchstar',
            '6': 'mmsp', '7': 'mmsp_z', '1.05': 'patchstar', '1.08': 'microstar', '1.09': 'ums', '1.10': 'imtp',
            '1.11': 'slice_scope', '1.12': 'condenser', '1.13': 'mmbp', '1.14': 'ivm_manipulator'
        }
        typ = self.send('type')
        return types.get(typ, typ)

    def getDescription(self):
        """Return this device's description string.
        """
        return self.send('desc')

    def setDescription(self, desc):
        """Set this device's description string.
        """
        return self.send('desc %s' % desc)

    def getPos(self):
        """Get current manipulator position reported by controller in micrometers.

        Usually the stage reports this value in units of 0.1 micrometers (and it is converted to um
        before returning). However, this relies on having correct axis scaling--see get/setAxisScale().
        """
        with self.lock:
            ## request position
            packet = self.send('POS')
            return [int(x) / 10. for x in packet.split('\t')]

    _param_commands = {
        'maxSpeed': ('TOP', 'TOP %f', float),
        'minSpeed': ('FIRST', 'FIRST %f', float),
        'accel': ('ACC', 'ACC %f', float),
        'joyAccel': ('JACC', 'JACC %f', float),
        'joyFastScale': ('JSPEED', 'JSPEED %f', float),
        'joySlowScale': ('JSSPEED', 'JSSPEED %f', float),
        'joyDirectionX': ('JDX ?', 'JDX %d', bool),
        'joyDirectionY': ('JDY ?', 'JDY %d', bool),
        'joyDirectionZ': ('JDZ ?', 'JDZ %d', bool),
        'approachAngle': ('ANGLE', 'ANGLE %f', float),
        'approachMode': ('APPROACH', 'APPROACH %d', bool),
    }

    @staticmethod
    def boolToInt(v):
        v = bool(v)
        return 0 if v is False else 1

    @staticmethod
    def intToBool(v):
        v = int(v)
        return v == 1

    def getParam(self, name):
        """Return a configuration parameter from the manipulator.

        These parameters are used to configure the speed, acceleration, and direction of the device under
        various conditions.

        Parameters
        ----------
        name : str
            Must be one of:

            * maxSpeed: Maximum speed for stage movement under both programmatic and manual control.
              This value is equal to `max_speed (um/sec) * 2 * userScale[axis]`. Must be between 1000
              and 50,000.
            * minSpeed: Initial speed for stage movement under both programmatic and manual control.
              This value is equal to `max_speed (um/sec) * 2 * userScale[axis]`. Must be between 1000
              and 50,000.
            * accel: Acceleration for stage movement under both programmatic and manual control.
              This value is equal to `accel (um^2/sec) * userScale[axis] / 250`. Must be between
              10 and 1,000.
            * joyFastScale: Speed scaling used when a manual input device is used in fast mode. Must
              be between 1 and 250.
            * joySlowScale: Speed scaling used when a manual input device is used in slow mode. Must
              be between 1 and 50.
            * joyAccel: Acceleration used at start and end of manually controlled movements. See `accel`
              for details.
            * joyDirectionX,Y,Z: Boolean values indicating whether manual input is reversed on any axis.
            * approachAngle: The angle at which the manipulator should move when in approach mode.
              Note: setting this value can also affect `approachMode`.
            * approachMode: Boolean indicating whether the manipulator is in approach mode. This can be
              set programmatically or by toggling the approach switch on the input device (but to
              prevent user confusion, setting this value programmatically is discouraged).
        """
        cmd, _, typ = self._param_commands[name]
        if typ is bool:
            typ = self.intToBool
        return typ(self.send(cmd))

    def setParam(self, name, val):
        """Set a configuration parameter on the manipulator.

        These parameters are used to configure the speed, acceleration, and direction of the device under
        various conditions.

        See `getParam` for parameter descriptions.
        """
        _, cmd, typ = self._param_commands[name]
        if typ is bool:
            typ = self.boolToInt
        return self.send(cmd % typ(val))

    def __getitem__(self, name):
        return self.getParam(name)

    def __setitem__(self, name, value):
        self.setParam(name, value)

    def getLimits(self):
        """Return the status of the device's limit switches.

        Format is `[(x_low, x_high), (y_low, y_high), (z_low, z_high)]`, where all values are bool.
        """
        lim = int(self.send('limits'))
        return [(lim&1>0, lim&2>0), (lim&4>0, lim&8>0), (lim&16>0, lim&32>0)]

    def getAxisScale(self, axis):
        """Return the scale factor that the device uses when calculating distance,
        speed, and acceleration along a single axis.

        The *axis* argument must be 0, 1, or 2 indicating the axis to be queried.

        These values are normally configured such that position values have units of 1/10th micrometer,
        and generally should not be changed. They may also be negative to reverse the stage direction
        under both manual and programmatic control.
        """
        cmd = ['UUX', 'UUY', 'UUZ'][axis]
        return float(self.send(cmd))

    def setAxisScale(self, axis, scale):
        """Set the scale factor used by the device when determining its position.

        The *axis* argument must be 0, 1, or 2 indicating the axis to be queried.

        These values are normally configured such that position values have units of 1/10th micrometer,
        and generally should not be changed. They may also be negative to reverse the stage direction
        under both manual and programmatic control.

        Typical values:

        * PatchStar: 6.4, 6.4, 6.4
        * Microstar: 6.4, 6.4, 6.4
        * SliceScope: 4.03, 4.03, 6.4  (sometimes 5.12, 5.12, 6.4)
        * Condenser: 4.03, 4.03, 6.4
        """
        cmd = ['UUX', 'UUY', 'UUZ'][axis]
        self.send('%s %f' % (cmd, float(scale)))
        self._readAxisScale()

    def _readAxisScale(self):
        # read and record axis scale factors
        self._axis_scale = tuple([self.getAxisScale(i) for i in (0, 1, 2)])

    def getSpeed(self):
        """Return the maximum speed of the stage along the X axis in um/sec.

        Note: If other axes have different scale factors, then their max speds will be different as
        well.
        """
        return self.getParam('maxSpeed') / abs(2. * self._axis_scale[0])

    def setSpeed(self, speed):
        """Set the maximum speed of the stage in um/sec.

        Note: this method uses the axis scaling of the X axis to determine the 
        speed value. If other axes have different scale factors, then their maximum
        speed will also be different.
        """
        self.setParam('maxSpeed', abs(speed * 2 * self._axis_scale[0]))

    def moveTo(self, pos, speed=None):
        """Set the position of the manipulator.
        
        *pos* must be a list of 3 items, each is either an integer representing the desired position
        of the manipulator (in 1/10 micrometers), or None which indicates the axis should not be moved.

        If *speed* is given, then the maximum speed of the manipulator is set before initiating the move.

        This method returns immediately. Use isMoving() to determine whether the move has completed.
        If the manipulator is already moving, then this method will time out and the command will be ignored.
        """
        with self.lock:
            currentPos = self.getPos()

            # fill in Nones with current position
            pos = list(pos)
            for i in range(3):
                if pos[i] is None:
                    pos[i] = currentPos[i]
                pos[i] = int(pos[i] * 10)  # convert to units of 0.1 um

            if speed is None:
                speed = self.getSpeed()
            else:
                self.setSpeed(speed)

            # Send move command
            self.write(b'ABS %d %d %d\r' % tuple(pos))
            self.readUntil('\r')

    def zeroPosition(self):
        """Reset the stage coordinates to (0, 0, 0) without moving the stage.
        """
        self.send('ZERO')

    def getCurrents(self):
        """Return a tuple of the (run, standby) current values.
        """
        c = self.send('CURRENT').split(' ')
        return (int(c[0]), int(c[1]))

    def setCurrents(self, run, standby):
        """Set the run and standby current values.

        Values must be between 1 and 255.
        Usually these values should be set by the manufacturer.
        """
        self.send('CURRENT %d %d' % (int(run), int(standby)))

    def stop(self):
        """Stop moving the manipulator.
        """
        self.send('STOP')

    def isMoving(self):
        """Return True if the manipulator is moving.
        """
        return int(self.send('S')) != 0

    def reset(self):
        self.send('RESET')
