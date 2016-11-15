import os, sys, ctypes, atexit, time, threading
from ctypes import (c_int, c_uint, c_long, c_ulong, c_short, c_ushort, 
                    c_byte, c_ubyte, c_void_p, c_char, c_char_p, byref,
                    POINTER, pointer, Structure)

path = os.path.abspath(os.path.dirname(__file__))
if sys.platform == 'win32':
    os.environ['PATH'] += ";" + path
    UMP_LIB = ctypes.windll.ump
else:
    UMP_LIB = ctypes.cdll.LoadLibrary(os.path.join(path, 'libump.so.1.0.0'))

LIBUMP_MAX_MANIPULATORS = 254
LIBUMP_MAX_LOG_LINE_LENGTH = 256
LIBUMP_DEF_TIMEOUT = 20
LIBUMP_DEF_BCAST_ADDRESS = "169.254.255.255"
LIBUMP_DEF_GROUP = 0
LIBUMP_MAX_MESSAGE_SIZE = 1502


class sockaddr_in(Structure):
    _fields_ = [
        ("family", c_short),
        ("port", c_ushort),
        ("in_addr", c_byte*4),
        ("zero", c_byte*8),
    ]


log_func_ptr = ctypes.CFUNCTYPE(c_void_p, c_int, c_void_p, POINTER(c_char), POINTER(c_char))


class ump_positions(Structure):
    _fields_ = [
        ("x", c_int),
        ("y", c_int),
        ("z", c_int),
        ("w", c_int),
        ("updated", c_ulong),
    ]

            
class ump_state(Structure):
    _fields_ = [
        ("last_received_time", c_ulong),
        ("socket", c_int),
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
        ("last_status", c_int * LIBUMP_MAX_MANIPULATORS),
        ("addresses", sockaddr_in * LIBUMP_MAX_MANIPULATORS),
        ("cu_address", sockaddr_in),
        ("last_positions", ump_positions * LIBUMP_MAX_MANIPULATORS),
        ("laddr", sockaddr_in),
        ("raddr", sockaddr_in),
        ("errorstr_buffer", c_char * LIBUMP_MAX_LOG_LINE_LENGTH),
        ("verbose", c_int),
        ("log_func_ptr", log_func_ptr),
        ("log_print_arg", c_void_p),
    ]


class UMPError(Exception):
    def __init__(self, msg, errno, oserrno):
        Exception.__init__(self, msg)
        self.errno = errno
        self.oserrno = oserrno


class UMP(object):
    """Wrapper for the Sensapex uMp API.
    
    All calls except get_ump are thread-safe.
    """
    _single = None
    
    @classmethod
    def get_ump(cls):
        """Return a singleton UMP instance.
        """
        if cls._single is None:
            cls._single = UMP()
        return cls._single
    
    def __init__(self):
        self.lock = threading.RLock()
        if self._single is not None:
            raise Exception("Won't create another UMP object. Use get_ump() instead.")
        self._timeout = 200
        self.lib = UMP_LIB
        self.lib.ump_errorstr.restype = c_char_p
        self.h = None
        self.open()
        
    def list_devices(self, max_id=16):
        """Return a list of all connected device IDs.
        """
        devs = []
        with self.lock:
            old_timeout = self._timeout
            self.set_timeout(10)
            try:
                for i in range(min(max_id, LIBUMP_MAX_MANIPULATORS)):
                    try:
                        p = self.get_pos(i)
                        devs.append(i)
                    except UMPError as ex:
                        if ex.errno == -5:  # device does not exist
                            continue
                        else:
                            raise
            finally:
                self.set_timeout(old_timeout)
        return devs

    def call(self, fn, *args):
        with self.lock:
            if self.h is None:
                raise TypeError("UMP is not open.")
            rval = getattr(self.lib, 'ump_' + fn)(self.h, *args)
            #if 'get_pos' not in fn:
                #print "sensapex:", rval, fn, args
            if rval < 0:
                err = self.lib.ump_last_error(self.h)
                errstr = self.lib.ump_errorstr(err)
                if err == -1:
                    oserr = self.lib.ump_last_os_errno(self.h)
                    raise UMPError("UMP OS Error %d: %s" % (oserr, os.strerror(oserr)), None, oserr)
                else:
                    raise UMPError("UMP Error %d: %s" % (err, errstr), err, None)
            return rval

    def set_timeout(self, timeout):
        self._timeout = timeout
        self.call('set_timeout', timeout)

    def open(self, address=None):
        """Open the UMP device at the given address.
        
        The default address "169.254.255.255" should suffice in most situations.
        """
        if address is None:
            address = LIBUMP_DEF_BCAST_ADDRESS
        if self.h is not None:
            raise TypeError("UMP is already open.")
        addr = ctypes.create_string_buffer(address)
        ptr = self.lib.ump_open(addr, c_uint(self._timeout), c_int(LIBUMP_DEF_GROUP))
        if ptr == 0:
            raise RuntimeError("Error connecting to UMP:", self.lib.ump_errorstr(ptr))
        self.h = pointer(ump_state.from_address(ptr))
        atexit.register(self.close)
        
    def close(self):
        """Close the UMP device.
        """
        with self.lock:
            self.lib.ump_close(self.h)
            self.h = None

    #def select_dev(self, dev):
        #"""Select a device from the UMP.
        #"""
        #self.call('select_dev', c_int(dev))

    def get_pos(self, dev, timeout=None):
        """Return the absolute position of the specified device (in nm).
        
        If *timeout* == 0, then the position is returned directly from cache
        and not queried from the device.
        """
        if timeout is None:
            timeout = self._timeout
        xyzwe = c_int(), c_int(), c_int(), c_int(), c_int()
        timeout = c_int(timeout)
        r = self.call('get_positions_ext', c_int(dev), timeout, *[byref(x) for x in xyzwe])
        return [x.value for x in xyzwe[:r]]

    def goto_pos(self, dev, pos, speed, block=False):
        """Request the specified device to move to an absolute position (in nm).
        
        *speed* is given in um/sec.
        
        If *block* is True, then this method only returns after ``is_busy()``
        return False.
        """
        pos = list(pos) + [0] * (4-len(pos))
        args = [c_int(int(x)) for x in [dev] + pos + [speed]]
        with self.lock:
            self.call('goto_position_ext', *args)
            self.h.contents.last_status[dev] = 1  # mark this manipulator as busy
            
        if block:
            while True:
                self.receive()
                if not self.is_busy(dev):
                    break
                time.sleep(0.005)

    def is_busy(self, dev):
        """Return True if the specified device is currently moving.
        """
        with self.lock:
            #self.receive()
            status = self.call('get_status_ext', c_int(dev))
            return bool(self.lib.ump_is_busy_status(status))
    
    def stop_all(self):
        """Stop all manipulators.
        """
        self.call('stop_all')
        
    def stop(self, dev):
        """Stop the specified manipulator.
        """
        self.call('stop_ext', c_int(dev))

    def select(self, dev):
        """Select a device on the TCU.
        """
        self.call('cu_select_manipulator', dev)

    def set_active(self, dev, active):
        """Set whether TCU remote control can move a manipulator.
        """
        self.call('cu_set_active', dev, int(active))

    #def receive(self, timelimit=0):
        #"""Receive and cache position updates for all manipulators.
        #"""
        #return self.call('receive', timelimit)

    def recv(self):
        """Receive one position or status update packet and return the ID
        of the device that sent the packet.
        
        Raises UMPError if the recv times out.
        
        Note: packets arrive from the manipulators rapidly while they are
        moving. These packets will quickly accumulate in the socket buffer
        if this method is not called frequently enough (alternatively, use
        recv_all at a slower rate).
        """
        msg = (c_char * LIBUMP_MAX_MESSAGE_SIZE)()
        dev = c_int()
        try:
            self.call('recv', byref(msg), byref(dev))
        except UMPError as exc:
            if exc.errno != -5:
                raise
        return dev.value

    def recv_all(self):
        """Receive all queued position/status update packets and return a list
        of devices that were updated.
        """
        devs = set()
        with self.lock:
            old_timeout = self._timeout
            self.set_timeout(0)
            try:
                while True:
                    try:
                        d = self.recv()
                    except UMPError as exc:
                        if exc.errno == -3:
                            # timeout; no packets remaining
                            break
                    if d > 0:
                        devs.add(d)
                    
            finally:
                self.set_timeout(old_timeout)
        
        return list(devs)


class SensapexDevice(object):
    """UMP wrapper for accessing a single sensapex manipulator.

    Example:
    
        dev = SensapexDevice(1)  # get handle to manipulator 1
        pos = dev.get_pos()
        pos[0] += 10000  # add 10 um to x axis 
        dev.goto_pos(pos, speed=10)
    """
    def __init__(self, devid):
        self.devid = int(devid)
        self.ump = UMP.get_ump()
        
    def get_pos(self, timeout=None):
        return self.ump.get_pos(self.devid, timeout=timeout)
    
    def goto_pos(self, pos, speed, block=False):
        return self.ump.goto_pos(self.devid, pos, speed, block=block)
    
    def is_busy(self):
        return self.ump.is_busy(self.devid)
    
    def stop(self):
        return self.ump.stop(self.devid)

    def select(self):
        return self.ump.select(self.devid)

    def set_active(self, active):
        return self.ump.set_active(self.devid, active)
