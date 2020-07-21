from __future__ import print_function
import os, sys, ctypes, atexit, time, threading, platform
import numpy as np
from ctypes import (c_int, c_uint, c_ulong, c_short, c_ushort,
                    c_byte, c_void_p, c_char, c_char_p, c_longlong,
                    byref, POINTER, pointer, Structure, c_float)
from timeit import default_timer
from six.moves import map
from six.moves import range
from six.moves import zip


SOCKET = c_int
if sys.platform == 'win32' and platform.architecture()[0] == '64bit':
    SOCKET = c_longlong

LIBUM_MAX_MANIPULATORS = 254
LIBUM_MAX_LOG_LINE_LENGTH = 256
LIBUM_DEF_TIMEOUT = 20
LIBUM_DEF_BCAST_ADDRESS = b"169.254.255.255"
LIBUM_DEF_GROUP = 0
LIBUM_MAX_MESSAGE_SIZE = 1502
LIBUM_ARG_UNDEF = float('nan')

# error codes
LIBUM_NO_ERROR     =  0,  # No error
LIBUM_OS_ERROR     = -1,  # Operating System level error
LIBUM_NOT_OPEN     = -2,  # Communication socket not open
LIBUM_TIMEOUT      = -3,  # Timeout occured
LIBUM_INVALID_ARG  = -4,  # Illegal command argument
LIBUM_INVALID_DEV  = -5,  # Illegal Device Id
LIBUM_INVALID_RESP = -6,  # Illegal response received
UM_LIB_PATH = None


def setLibraryPath(path):
    global UM_LIB_PATH
    UM_LIB_PATH = path


class sockaddr_in(Structure):
    _fields_ = [
        ("family", c_short),
        ("port", c_ushort),
        ("in_addr", c_byte*4),
        ("zero", c_byte*8),
    ]


log_func_ptr = ctypes.CFUNCTYPE(c_void_p, c_int, c_void_p, POINTER(c_char), POINTER(c_char))


class um_positions(Structure):
    _fields_ = [
        ("x", c_int),
        ("y", c_int),
        ("z", c_int),
        ("w", c_int),
        ("updated", c_ulong),
    ]


# used in v0.600 and later
class um_state_v0_600(Structure):
    _fields_ = [
        ("last_received_time", c_ulong),
        ("socket", SOCKET),
        ("own_id", c_int),
        ("message_id", c_int),
        ("last_device_sent", c_int),
        ("last_device_received", c_int),
        ("retransmit_count", c_int),
        ("refresh_time_limit", c_int),
        ("last_error", c_int),
        ("last_os_errno", c_int),
        ("timeout", c_int),
        ("udp_port", c_int),
        ("last_status", c_int * LIBUM_MAX_MANIPULATORS),
        ("drive_status", c_int * LIBUM_MAX_MANIPULATORS),
        ("drive_status_id", c_ushort * LIBUM_MAX_MANIPULATORS),
        ("addresses", sockaddr_in * LIBUM_MAX_MANIPULATORS),
        ("cu_address", sockaddr_in),
        ("last_positions", um_positions * LIBUM_MAX_MANIPULATORS),
        ("laddr", sockaddr_in),
        ("raddr", sockaddr_in),
        ("errorstr_buffer", c_char * LIBUM_MAX_LOG_LINE_LENGTH),
        ("verbose", c_int),
        ("log_func_ptr", log_func_ptr),
        ("log_print_arg", c_void_p),
    ]


# used before v0.600
class um_state_pre_v0_600(Structure):
    _fields_ = [
        ("last_received_time", c_ulong),
        ("socket", SOCKET),
        ("own_id", c_int),
        ("message_id", c_int),
        ("last_device_sent", c_int),
        ("last_device_received", c_int),
        ("retransmit_count", c_int),
        ("refresh_time_limit", c_int),
        ("last_error", c_int),
        ("last_os_errno", c_int),
        ("timeout", c_int),
        ("udp_port", c_int),
        ("last_status", c_int * LIBUM_MAX_MANIPULATORS),
        ("addresses", sockaddr_in * LIBUM_MAX_MANIPULATORS),
        ("cu_address", sockaddr_in),
        ("last_positions", um_positions * LIBUM_MAX_MANIPULATORS),
        ("laddr", sockaddr_in),
        ("raddr", sockaddr_in),
        ("errorstr_buffer", c_char * LIBUM_MAX_LOG_LINE_LENGTH),
        ("verbose", c_int),
        ("log_func_ptr", log_func_ptr),
        ("log_print_arg", c_void_p),
    ]


class UMError(Exception):
    def __init__(self, msg, errno, oserrno):
        Exception.__init__(self, msg)
        self.errno = errno
        self.oserrno = oserrno


_timer_offset = time.time() - default_timer()
def timer():
    global _timer_offset
    return _timer_offset + default_timer()


class UMP(object):
    """Wrapper for the Sensapex uMp API.
    
    All calls except get_ump are thread-safe.
    """
    _um_state = None
    _single = None
    _lib = None

    @classmethod
    def get_lib(cls):
        if cls._lib is None:
            cls._lib = cls.load_lib()
            cls._lib.um_get_version.restype = c_char_p
        return cls._lib

    @classmethod
    def load_lib(cls):
        path = os.path.abspath(os.path.dirname(__file__))
        if sys.platform == 'win32':
            if UM_LIB_PATH is not None:
                return ctypes.windll.LoadLibrary(os.path.join(UM_LIB_PATH, 'umsdk'))

            try:
                return ctypes.windll.umsdk
            except OSError:
                pass

            return ctypes.windll.LoadLibrary(os.path.join(path, 'umsdk'))
        else:
            if UM_LIB_PATH is not None:
                return ctypes.windll.LoadLibrary(os.path.join(UM_LIB_PATH, 'libump.so.1.0.0'))

            return ctypes.cdll.LoadLibrary(os.path.join(path, 'libump.so.1.0.0'))

    @classmethod
    def get_um_state_class(cls):
        if cls._um_state is None:
            version = cls.get_lib().um_get_version().decode('ascii')
            if version >= "v0.600":
                cls._um_state = um_state_v0_600
            else:
                cls._um_state = um_state_pre_v0_600
        return cls._um_state

    @classmethod
    def get_ump(cls, address=None, start_poller=True):
        """Return a singleton UM instance.
        """
        # question: can we have multiple UM instances with different address/group ?
        if cls._single is None:
            cls._single = UMP(address=address, start_poller=start_poller)
        return cls._single
    
    def __init__(self, address=None, start_poller=True):
        self.lock = threading.RLock()
        if self._single is not None:
            raise Exception("Won't create another UM object. Use get_ump() instead.")
        self._timeout = 200

        # duration that manipulator must be not busy before a move is considered complete.
        self.move_expire_time = 50e-3

        # if we miss any axis by more than 0.5 um, try again
        self.retry_threshold = np.array([0.5, 0.5, 0.5, 0.5])

        # retry up to 3 times, then fail
        self.max_move_retry = 3

        self.max_acceleration = {}
        
        self.lib = self.get_lib()
        self.lib.um_errorstr.restype = c_char_p

        min_version = (0, 918)
        min_version_str = 'v%d.%d' % min_version
        version_str = self.sdk_version()
        version = tuple(map(int, version_str.lstrip(b'v').split(b'.')))

        assert version >= min_version, "SDK version %s or later required (your version is %s)" % (min_version_str, version_str)

        self.h = None
        self.open(address=address)

        # keep track of requested moves and whether they completed, failed, or were interrupted.
        self._last_move = {}  # {device: MoveRequest}
        # last time each device was seen moving
        self._last_busy_time = {}

        self._um_has_axis_count = hasattr(self.lib, 'um_get_axis_count')
        self._axis_counts = {}

        self.devices = {}

        self.poller = PollThread(self)
        if start_poller:
            self.poller.start()

    def get_device(self, dev_id):
        if dev_id not in self.devices:
            all_devs = self.list_devices()
            if dev_id not in all_devs:
                raise Exception("Invalid sensapex device ID %s. Options are: %r" % (dev_id, all_devs))
            self.devices[dev_id] = SensapexDevice(dev_id)
        return self.devices[dev_id]

    def sdk_version(self):
        """Return version of UM SDK.
        """
        self.lib.um_get_version.restype = ctypes.c_char_p
        return self.lib.um_get_version()
        
    def list_devices(self, max_id=50):
        """Return a list of all connected device IDs.
        """
        devarray = (c_int*max_id)()
        r = self.call('um_get_device_list', byref(devarray), c_int(max_id))
        devs = [devarray[i] for i in range(r)]
        
        return devs

    def axis_count(self, dev):
        if not self._um_has_axis_count:
            return 4
        c = self._axis_counts.get(dev, None)
        if c is None:
            c = self.call('um_get_axis_count', dev)
            self._axis_counts[dev] = c
        return c

    def call(self, fn, *args):
        # print "%s%r" % (fn, args)
        with self.lock:
            if self.h is None:
                raise TypeError("UM is not open.")
            # print("Call:", fn, self.h, args)
            rval = getattr(self.lib, fn)(self.h, *args)
            #if 'get_pos' not in fn:
                #print "sensapex:", rval, fn, args
            if rval < 0:
                err = self.lib.um_last_error(self.h)
                errstr = self.lib.um_errorstr(err)
                # print "   -!", errstr
                if err == -1:
                    oserr = self.lib.um_last_os_errno(self.h)
                    raise UMError("UM OS Error %d: %s" % (oserr, os.strerror(oserr)), None, oserr)
                else:
                    raise UMError("UM Error %d: %s  From %s%r" % (err, errstr, fn, args), err, None)
            # print "   ->", rval
            return rval

    def set_timeout(self, timeout):
        self._timeout = timeout
        self.call('um_set_timeout', timeout)

    def set_max_acceleration(self, dev, max_acc):
        self.max_acceleration[dev] = max_acc

    def open(self, address=None):
        """Open the UM device at the given address.
        
        The default address "169.254.255.255" should suffice in most situations.
        """
        if address is None:
            address = LIBUM_DEF_BCAST_ADDRESS

        if self.h is not None:
            raise TypeError("UM is already open.")
        addr = ctypes.create_string_buffer(address)
        self.lib.um_open.restype = c_longlong
        ptr = self.lib.um_open(addr, c_uint(self._timeout))
        if ptr <= 0:
            raise RuntimeError("Error connecting to UM:", self.lib.um_errorstr(ptr))
        self.h = pointer(self.get_um_state_class().from_address(ptr))
        atexit.register(self.close)
        
    def close(self):
        """Close the UM device.
        """
        if self.poller.is_alive():
            self.poller.stop()
            self.poller.join()
        with self.lock:
            self.lib.um_close(self.h)
            self.h = None

    def get_pos(self, dev, timeout=0):
        """Return the absolute position of the specified device (in um).
        
        If *timeout* == 0, then the position is returned directly from cache
        and not queried from the device.
        """
        if timeout is None:
            timeout = self._timeout
        xyzwe = c_float(), c_float(), c_float(), c_float(), c_int()
        timeout = c_int(timeout)
       
        r = self.call('um_get_positions', c_int(dev), timeout, *[byref(x) for x in xyzwe]) 

        n_axes = self.axis_count(dev)
        #if dev == 9:
        #    return [-x.value for x in xyzwe[:n_axes]]
        return [x.value for x in xyzwe[:n_axes]]

    def goto_pos(self, dev, pos, speed, simultaneous=True, linear=False, max_acceleration=0, _request=None):
        """Request the specified device to move to an absolute position (in um).

        Parameters
        ----------
        dev : int
            ID of device to move
        pos : array-like
            X,Y,Z,W coordinates to move to. Values may be NaN or omitted to leave
            the axis unaffected.
        speed : float
            Manipulator speed in um/sec
        simultaneous: bool
            If True, then all axes begin moving at the same time
        linear : bool
            If True, then axis speeds are scaled to produce more linear movement
        max_acceleration : int
            Maximum acceleration in um/s^2

        Returns
        -------
        move_id : int
            Unique ID that can be used to retrieve the status of this move at a later time.
        """
        kwargs = {'dev': dev, 'pos': pos, 'speed': speed, 'simultaneous': simultaneous, 'linear': linear, 'max_acceleration': max_acceleration}
        pos = [float(x) for x in pos]
        pos4 = pos + [float('nan')] * (4-len(pos))  # extend to 4 values

        mode = int(bool(simultaneous))  # all axes move simultaneously

        current_pos = self.get_pos(dev)
        diff = [float(p-c) for p,c in zip(pos4, current_pos) if p is not None]
        dist = max(1, np.linalg.norm(diff))
        original_speed = speed
        if linear:
            speed = [max(1, speed * abs(d / dist)) for d in diff]
            speed = speed + [0] * (4-len(speed))
        else:
            speed = [max(1, speed)] * 4  # speed < 1 crashes the uMp

        if max_acceleration==0 or max_acceleration == None:
            if self.max_acceleration[dev] != None:
                max_acceleration = self.max_acceleration[dev]
            else:
                max_acceleration = 0

        args = [c_int(dev)] + [c_float(x) for x in pos4] + [c_int(int(x)) for x in speed + [mode] + [max_acceleration]]
        duration = max(np.array(diff) / speed[:len(diff)])

        with self.lock:
            last_move = self._last_move.pop(dev, None)
            if last_move is not None:
                self.call('um_stop', c_int(dev))
                last_move._interrupt("started another move before the previous finished")

            if _request is None:
                next_move = MoveRequest(dev, current_pos, pos, original_speed, duration, kwargs)
            else:
                # We are retrying a previous move; re-use the old request object.
                next_move = _request

            self._last_move[dev] = next_move

            self.call('um_goto_position_ext', *args)

        return next_move

    def is_busy(self, dev):
        """Return True if the specified device is currently moving.

        Note: this should not be used to determine whether a move has completed;
        use MoveRequest.finished or .finished_event as returned from goto_pos().
        """
        # idle/complete=0; moving>0; failed<0
        try:
            return self.call('um_get_drive_status', c_int(dev)) > 0
        except UMError as err:
            if err.errno in (LIBUM_NOT_OPEN, LIBUM_INVALID_DEV):
                raise
            else:
                return False

    def stop(self, dev):
        """Stop the specified manipulator.
        """
        with self.lock:
            self.call('um_stop', c_int(dev))
            move = self._last_move.pop(dev, None)
            if move is not None:
                move._interrupt('stop requested before move finished')

    def select(self, dev):
        """Select a device on the TCU.
        """
        self.call('um_cu_select_manipulator', dev)

    def set_active(self, dev, active):
        """Set whether TCU remote control can move a manipulator.
        """
        self.call('um_cu_set_active', dev, int(active))

    def set_pressure(self, dev, channel, value):
        return self.call('umc_set_pressure_setting', dev, int(channel), c_float(value))

    def get_pressure(self, dev, channel):
        p = c_float()
        self.call('umc_get_pressure_setting', dev, int(channel), byref(p))
        return p.value

    def set_valve(self, dev, channel, value):
        return self.call('umc_set_valve', dev, int(channel), int(value))

    def get_valve(self, dev, channel):
        return self.call('umc_get_valve', dev, int(channel))

    def set_custom_slow_speed(self, dev, enabled):
        feature_custom_slow_speed = 32
        return self.call('um_set_ext_feature', c_int(dev), c_int(feature_custom_slow_speed), c_int(enabled))
    
    def get_custom_slow_speed(self,dev):
        feature_custom_slow_speed = 32
        return self.call('um_get_ext_feature', c_int(dev), c_int(feature_custom_slow_speed))

    def send_um_cmd(self, dev, cmd, argList):
        args = (c_int * len(argList))()
        args[:] = argList
        return self.call('um_cmd', c_int(dev), c_int(cmd), len(argList), args)

    def get_um_param(self, dev, param):
        value = c_int()
        self.call('um_get_param',c_int(dev),c_int(param), *[byref(value)])
        return value
        
    def set_um_param(self,dev,param, value):
        return self.call('um_set_param',c_int(dev),c_int(param), value)

    def calibrate_zero_position(self, dev):
        return self.send_um_cmd(dev, 4, [])

    def calibrate_load(self, dev):
        return self.send_um_cmd(dev, 5, [0])

    def get_soft_start_state(self, dev):
        feature_soft_start = 33
        return self.call('um_get_ext_feature', c_int(dev), c_int(feature_soft_start))
    
    def set_soft_start_state(self, dev, enabled):
        feature_soft_start = 33
        return self.call('um_set_ext_feature', c_int(dev), c_int(feature_soft_start), c_int(enabled))

    def get_soft_start_value(self, dev):
        return self.get_um_param(dev,15)

    def set_soft_start_value(self, dev, value):
        return self.set_um_param(dev,15, value)

    def recv_all(self):
        """Receive all queued position/status update packets and update any pending moves.
        """
        self.call('um_receive', 0)
        self._update_moves()

    def _update_moves(self):
        with self.lock:
            for dev,move in list(self._last_move.items()):
                if not self.is_busy(dev):
                    move_req = self._last_move.pop(dev)

                    pos = np.array(self.get_pos(dev, timeout=-1))
                    target = np.array(move_req.target_pos).astype(float)
                    err = np.abs(pos - target)
                    mask = np.isfinite(err)
                    reached_target = np.all(err[mask] < self.retry_threshold[:len(mask)][mask])
                    if reached_target or move_req.retry_count >= self.max_move_retry:
                        move._finish(pos)
                    else:
                        # retry move if we missed the target
                        move_req.retry_count += 1
                        self.goto_pos(_request=move_req, **move_req.kwargs)


class MoveRequest(object):
    """Simple class for tracking the status of requested moves.
    """
    def __init__(self, dev, start_pos, target_pos, speed, duration, kwargs):
        self.dev = dev
        self.start_time = timer()
        self.estimated_duration = duration
        self.start_pos = start_pos
        self.target_pos = target_pos
        self.speed = speed
        self.kwargs = kwargs
        self.finished = False
        self.interrupted = False
        self.interrupt_reason = None
        self.last_pos = None
        self.finished_event = threading.Event()
        self.retry_count = 0

    def _interrupt(self, reason):
        self.interrupt_reason = reason
        self.interrupted = True
        self.finished = True
        self.finished_event.set()

    def _finish(self, pos):
        self.last_pos = pos
        self.finished = True
        self.finished_event.set()


class SensapexDevice(object):
    """UM wrapper for accessing a single sensapex manipulator.

    Example:
    
        dev = SensapexDevice(1)  # get handle to manipulator 1
        pos = dev.get_pos()
        pos[0] += 10000  # add 10 um to x axis 
        dev.goto_pos(pos, speed=10)
    """
    def __init__(self, devid, callback=None, n_axes=None, max_acceleration=0):
        self.devid = int(devid)
        self.ump = UMP.get_ump()

        # Save max acceleration from config
        if max_acceleration == None:
            max_acceleration = 0
        self.set_max_acceleration(max_acceleration)

        # some devices will fail when asked how many axes they have; this
        # allows a manual override.
        if n_axes is not None:
            self.set_n_axes(n_axes)

        self.ump.poller.add_callback(devid, self._change_callback)
        self.callbacks = []

        if callback is not None:
            self.add_callback(callback)

    def set_n_axes(self, n_axes):
        self.ump._axis_counts[self.devid] = n_axes

    def set_max_acceleration(self, max_acceleration):
        self.ump.set_max_acceleration(self.devid, max_acceleration)

    def add_callback(self, callback):
        self.callbacks.append(callback)
        
    def get_pos(self, timeout=None):
        return self.ump.get_pos(self.devid, timeout=timeout)
    
    def goto_pos(self, pos, speed, simultaneous=True, linear=False, max_acceleration=0):
        return self.ump.goto_pos(self.devid, pos, speed, simultaneous=simultaneous, linear=False, max_acceleration=max_acceleration)
    
    def is_busy(self):
        return self.ump.is_busy(self.devid)
    
    def stop(self):
        return self.ump.stop(self.devid)

    def select(self):
        return self.ump.select(self.devid)

    def set_active(self, active):
        return self.ump.set_active(self.devid, active)

    def _change_callback(self, devid, new_pos, old_pos):
        for cb in self.callbacks:
            cb(self, new_pos, old_pos)

    def set_pressure(self, channel, value):
        """
        Parameters
        ----------
        value : float
            pressure in kPa
        """
        return self.ump.set_pressure(self.devid, int(channel), float(value))

    def get_pressure(self, channel):
        """
        Returns
        -------
        float
            pressure in kPa
        """
        return self.ump.get_pressure(self.devid, int(channel))

    def set_valve(self, channel, value):
        return self.ump.set_valve(self.devid, int(channel), int (value))

    def get_valve(self, channel):
        return self.ump.get_valve(self.devid, int(channel)) 

    def set_lens_position(self, pos):
        return self.ump.call('ums_set_lens_position', c_int(self.devid), c_int(pos))

    def get_lens_position(self):
        return self.ump.call('ums_get_lens_position', c_int(self.devid))

    def set_custom_slow_speed(self, enabled):
        return self.ump.set_custom_slow_speed(self.devid, enabled)

    def calibrate_zero_position(self):
        self.ump.calibrate_zero_position(self.devid)
    
    def calibrate_load(self):
        self.ump.calibrate_load(self.devid)

    def get_soft_start_state(self):
        return self.ump.get_soft_start_state(self.devid)
    
    def set_soft_start_state(self, enabled):
        return self.ump.set_soft_start_state(self.devid,enabled)

    def get_soft_start_value(self):
        return self.ump.get_soft_start_value(self.devid).value

    def set_soft_start_value(self, value):
        return self.ump.set_soft_start_value(self.devid,value)


class PollThread(threading.Thread):
    """Thread to poll for all manipulator position changes.

    Running this thread ensures that calling get_pos will always return the most recent
    values available.

    An optional callback function is called periodically with a list of
    device IDs from which position updates have been received.
    """
    def __init__(self, ump, callback=None, interval=0.03):
        self.ump = ump
        self.callbacks = {}
        self.interval = interval
        self.lock = threading.RLock()
        self.__stop = False
        threading.Thread.__init__(self)
        self.daemon = True

    def start(self):
        self.__stop = False
        threading.Thread.start(self)

    def stop(self):
        self.__stop = True

    def add_callback(self, dev_id, callback):
        with self.lock:
            self.callbacks.setdefault(dev_id, []).append(callback)

    def remove_callback(self, dev_id, callback):
        with self.lock:
            self.callbacks[dev_id].remove(callback)

    def run(self):
        ump = self.ump
        last_pos = {}

        while True:
            try:
                if self.__stop:
                    break

                # read all updates waiting in queue
                ump.recv_all()
                
                # check for position changes and invoke callbacks
                with self.lock:
                    callbacks = self.callbacks.copy()

                for dev_id, dev_callbacks in callbacks.items():
                    if len(callbacks) == 0:
                        continue
                    new_pos = ump.get_pos(dev_id, timeout=0)
                    old_pos = last_pos.get(dev_id)
                    if new_pos != old_pos:
                        for cb in dev_callbacks:
                            cb(dev_id, new_pos, old_pos)

                time.sleep(self.interval)

            except Exception:
                print('Error in sensapex poll thread:')
                sys.excepthook(*sys.exc_info())
                time.sleep(1)
            except:
                print("Uncaught")
                raise
