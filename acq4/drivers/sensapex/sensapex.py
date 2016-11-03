import os, ctypes, atexit
from ctypes import (c_int, c_uint, c_long, c_ulong, c_short, c_ushort, 
                    c_byte, c_ubyte, c_void_p, c_char, c_char_p, byref,
                    POINTER, pointer, Structure)
path = os.path.abspath(os.path.dirname(__file__))


LIBUMP_MAX_MANIPULATORS = 254
LIBUMP_MAX_LOG_LINE_LENGTH = 256
LIBUMP_DEF_TIMEOUT = 20
LIBUMP_DEF_BCAST_ADDRESS = "169.254.255.255"
LIBUMP_DEF_GROUP = 0

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


class UMP(object):
    def __init__(self):
        self.lib = ctypes.cdll.LoadLibrary(os.path.join(path, 'libump.so.1.0.0'))
        self.lib.ump_errorstr.restype = c_char_p
        self.h = None
        self.open()
        
    def call(self, fn, *args):
        if self.h is None:
            raise TypeError("UMP is not open.")
        rval = getattr(self.lib, 'ump_' + fn)(self.h, *args)
        if rval < 0:
            err = self.lib.ump_last_error(self.h)
            errstr = self.lib.ump_errorstr(err)
            print rval, self.lib.ump_errorstr(rval)
            if err == -1:
                oserr = self.lib.ump_last_os_errno(self.h)
                raise Exception("UMP OS Error %d: %s" % (oserr, os.strerror(oserr)))
            else:
                raise Exception("UMP Error %d: %s" % (err, errstr))
        return rval

    def open(self):
        if self.h is not None:
            raise TypeError("UMP is already open.")
        addr = ctypes.create_string_buffer(LIBUMP_DEF_BCAST_ADDRESS)
        ptr = self.lib.ump_open(addr, c_uint(LIBUMP_DEF_TIMEOUT), c_int(LIBUMP_DEF_GROUP))
        if ptr == 0:
            raise RuntimeError("Error connecting to UMP:", self.lib.ump_errorstr(ptr))
        self.h = pointer(ump_state.from_address(ptr))
        atexit.register(self.close)
        
    def close(self):
        self.lib.ump_close(self.h)
        self.h = None

    def select_dev(self, dev):
        self.call('select_dev', c_int(dev))

    def get_pos(self):
        xyzw = c_int(), c_int(), c_int(), c_int()
        r = self.call('get_positions', *[byref(x) for x in xyzw])
        return [x.value for x in xyzw[:r]]

    def goto_pos(self, pos, speed, block=True):
        pos = list(pos) + [0] * (4-len(pos))
        args = [c_int(x) for x in pos + [speed]]
        self.call('goto_position', *args)
        
        if block:
            while True:
                self.receive()
                if self.is_busy() == 0:
                    break

    def is_busy(self):
        status = self.call('get_status')
        busy = self.lib.ump_is_busy_status(status)
        return busy

    def receive(self):
        self.call('receive', 200)


ump = UMP()
ump.select_dev(1)
print ump.get_pos()
import user