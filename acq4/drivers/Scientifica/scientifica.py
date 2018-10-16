"""
Driver for communicating with Scientifica motorized devices by serial interface.
"""
from __future__ import print_function
from __future__ import division
import serial, struct, time, collections, re
import numpy as np

from acq4.util.Mutex import RecursiveMutex as RLock
from acq4.util.debug import printExc
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

    This can be initialized either with the com port name or with the string description
    of the device.
    Will attempt to connect at both 9600 and 38400 baud rates.

    Examples::

        dev = Scientifica('com4')
        print(dev.getPos())
        dev.moveTo([10e-3, 0, 0], 'fast')

        # search for device with this description
        dev2 = Scientifica(name='SliceScope')


    Notes
    -----

    The `getParam()` and `setParam()` methods provide access to several speed and acceleration values
    used by the motion card. These values are interpreted differently between version 2 and version 3
    motion cards. To avoid possible device damage, it is required to explicitly instantiate this class
    using the argument `ctrl_version=3` when connecting to version 3 devices. 

    Version 3 device documentation is available at
    http://elecsoft.eu/motion2/commandset/Motion%20Card%202%20Command%20Documentation.html 
    """
    openDevices = {}
    availableDevices = None

    @classmethod
    def enumerateDevices(cls):
        """Generate a list of all Scientifica devices found in the system.

        Sets Scientifica.availableDevices to a dict of {name: port} pairs.

        This works by searching for USB serial devices with device IDs used by Scientifica
        (vid=0403, pid=6010) and sending a single serial request.
        """
        import serial.tools.list_ports
        coms = serial.tools.list_ports.comports()
        devs = {}
        for com, name, ident in coms:
            # several different ways this can appear:
            #  VID_0403+PID_6010
            #  VID_0403&PID_6010
            #  VID:PID=0403:6010
            if ('VID_0403' not in ident or 'PID_6010' not in ident) and '0403:6010' not in ident:
                continue
            com = cls.normalizePortName(com)
            if com in cls.openDevices:
                name = cls.openDevices[com].getDescription()
                devs[name] = com
            else:
                try:
                    s = Scientifica(port=com, ctrl_version=None)
                    devs[s.getDescription()] = com
                    s.close()
                except Exception:
                    printExc("Error while initializing Scientifica device at %s (the device at this port will not be available):" % com)

        cls.availableDevices = devs

    def __init__(self, port=None, name=None, baudrate=None, ctrl_version=2):
        self.lock = RLock()

        if name is not None:
            if isinstance(name, str):
                name = name.encode()
            assert port is None, "May not specify both name and port."
            if self.availableDevices is None:
                self.enumerateDevices()
            if name not in self.availableDevices:
                raise ValueError('Could not find Scientifica device with description "%s". Options are: %s' % 
                    (name, list(self.availableDevices.keys())))
            port = self.availableDevices[name]

        if port is None:
            raise ValueError("Must specify either name or port.")
            
        self.port = self.normalizePortName(port)
        if self.port in self.openDevices:
            raise RuntimeError("Port %s is already in use by %s" % (port, self.openDevices[self.port]))

        # try both baudrates, regardless of the requested rate
        # (but try the requested rate first)
        baudrate = 9600 if baudrate is None else int(baudrate)
        if baudrate == 9600:
            baudrates = [9600, 38400]
        elif baudrate == 38400:
            baudrates = [38400, 9600]
        else:
            raise ValueError('invalid baudrate %s' % baudrate)

        # Attempt connection
        connected = False
        for baudrate in baudrates:
            try:
                SerialDevice.__init__(self, port=self.port, baudrate=baudrate)
                try:
                    sci = self.send('scientifica', timeout=0.2)
                except RuntimeError:
                    # try again because prior communication at a different baud rate may have garbled serial communication.
                    sci = self.send('scientifica', timeout=1.0)

                if sci != b'Y519':
                    # Device responded, not scientifica.
                    raise ValueError("Received unexpected response from device at %s. (Is this a scientifica device?)" % port)
                connected = True
                break
            except TimeoutError:
                pass

        if not connected:
            raise RuntimeError("No response received from Scientifica device at %s. (tried baud rates: %s)" % (port, ', '.join(map(str, baudrates))))

        Scientifica.openDevices[self.port] = self
        self._version = float(self.send('ver'))
        if ctrl_version is not None and ((self._version >= 3) != (ctrl_version >= 3)):
            name = self.getDescription()
            err = RuntimeError("Scientifica device %s uses controller version %s, but version %s was requested. Warning: speed and acceleration"
                               " parameter values are NOT compatible between controller versions." % (name, self._version, ctrl_version))
            err.dev_version = self._version
            raise err

        self._readAxisScale()

    def close(self):
        port = self.port
        SerialDevice.close(self)
        del Scientifica.openDevices[port]

    def send(self, msg, timeout=5):
        with self.lock:
            self.write(msg + '\r')
            result = self.readUntil(b'\r', timeout=timeout)[:-1]
            if result.startswith(b'E,'):
                errno = int(result.strip()[2:])
                exc = RuntimeError("Received error %d from Scientifica controller (request: %r)" % (errno, msg))
                exc.errno = errno
                raise exc
            return result

    def getFirmwareVersion(self):
        return self.send('DATE').partition(b' ')[2].partition(b'\t')[0]

    def getType(self):
        """Return a string indicating the type of the device, or the type's numerical value
        if it is unknown.
        """
        types = {
            '1': 'linear', '2': 'ums', '3': 'mmtp', '4': 'slicemaster', '5': 'patchstar',
            '6': 'mmsp', '7': 'mmsp_z', '1.05': 'patchstar', '1.08': 'microstar', '1.09': 'ums', '1.10': 'imtp',
            '1.11': 'slice_scope', '1.12': 'condenser', '1.13': 'mmbp', '1.14': 'ivm_manipulator',
            '3.01': 'linear', '3.02': 'ums', '3.03': 'mmtp', '3.04': 'slicemaster', '3.05': 'patchstar',
            '3.06': 'mmsp', '3.07': 'mmsp_z', '3.08': 'microstar', '3.09': 'ums', '3.10': 'imtp',
            '3.11': 'slicescope', '3.12': 'condenser', '3.13': 'mmbp', '3.14': 'ivm_manipulator', '3.15': 'custom',
            '3.16': 'extended_patchstar', '3.17': 'ivm_mini',
        }
        typ = self.send('type').decode()
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
            if self._version < 3:
                packet = self.send('POS')
                return [int(x) / 10. for x in packet.split(b'\t')]
            else:
                packet = self.send('P')
                return [int(x) / 100. for x in packet.split(b'\t')]

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
        'objDisp': ('OBJDISP', 'OBJDISP %d', float),
        'objLift': ('OBJLIFT', 'OBJLIFT %d', float),
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

        Notes
        -----

        For version 2 devices, all speed and acceleration values are expressed relative to the device's
        user step parameter. Speed values are expressed as `actual_speed (um/sec) * 2 * userScale[axis]`,
        and acceleration values are expressed as `actual_accel (um^2/sec) * userScale[axis] / 250`. 

        For version 3 devices, these values are expressed in units of um/sec and um^2/sec, with no scaling
        applied.
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
        if self._version < 3:
            cmd = ['UUX', 'UUY', 'UUZ'][axis]
        else:
            cmd = ['USTEP X', 'USTEP Y', 'USTEP Z'][axis]
        return float(self.send(cmd))

    def setAxisScale(self, axis, scale):
        """Set the scale factor used by the device when determining its position.

        The *axis* argument must be 0, 1, or 2 indicating the axis to be queried.

        These values are normally configured such that position values have units of 1/10th micrometer,
        and generally should not be changed. They may also be negative to reverse the stage direction
        under both manual and programmatic control.

        Typical values for version 2.x devices:

        * PatchStar: 6.4, 6.4, 6.4
        * Microstar: 6.4, 6.4, 6.4
        * SliceScope: 4.03, 4.03, 6.4  (sometimes 5.12, 5.12, 6.4)
        * Condenser: 4.03, 4.03, 6.4

        For version 3.x devices, use ``10240 / x``, where x is the equivalent axis scale for a version 2 device.
        (e.g. use 1600 instead of 6.4)
        """
        if self._version < 3:
            cmd = ['UUX', 'UUY', 'UUZ'][axis]
        else:
            cmd = ['USTEP X', 'USTEP Y', 'USTEP Z'][axis]
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
        if self._version < 3:
            return self.getParam('maxSpeed') / abs(2. * self._axis_scale[0])
        else:
            return self.getParam('maxSpeed')

    def setSpeed(self, speed):
        """Set the maximum speed of the stage in um/sec.

        Note: this method uses the axis scaling of the X axis to determine the 
        speed value. If other axes have different scale factors, then their maximum
        speed will also be different.
        """
        if self._version < 3:
            self.setParam('maxSpeed', speed * 2 * abs(self._axis_scale[0]))
        else:
            self.setParam('maxSpeed', speed)

    def moveTo(self, pos, speed=None):
        """Set the position of the manipulator.
        
        *pos* must be a list of 3 items, each is either an integer representing the desired position
        of the manipulator (in 1/10 micrometers), or None which indicates the axis should not be moved.

        If *speed* is given, then the maximum speed of the manipulator is set (in um/sec) before initiating the move.

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
                if self._version < 3:
                    pos[i] = int(pos[i] * 10)  # convert to units of 0.1 um
                else:
                    pos[i] = int(pos[i] * 100)  # convert to units of 0.01 um

            if speed is None:
                speed = self.getSpeed()
            else:
                self.setSpeed(speed)

            # Send move command
            self.write(b'ABS %d %d %d\r' % tuple(pos))
            self.readUntil(b'\r')

    def zeroPosition(self):
        """Reset the stage coordinates to (0, 0, 0) without moving the stage.
        """
        self.send('ZERO')

    def getCurrents(self):
        """Return a tuple of the (run, standby) current values.
        """
        c = re.split(br'\s+', self.send('CURRENT'))
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

    def setBaudrate(self, baudrate):
        """Set the baud rate of the device.
        May be either 9600 or 38400.
        """
        baudkey = {9600: '96', 38400: '38'}[baudrate]
        with self.lock:
            self.write('BAUD %s\r' % baudkey)
            self.close()
            self.open(baudrate=baudrate)

