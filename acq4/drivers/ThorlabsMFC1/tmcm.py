"""
Low-level serial communication for Trinamic TMCM-140-42-SE controller
(used internally for the Thorlabs MFC1)
"""


import serial, struct, time, collections

try:
    # this is nicer because it provides deadlock debugging information
    from acq4.util.Mutex import RecursiveMutex as RLock
except ImportError:
    from threading import RLock

try:
    from ..SerialDevice import SerialDevice, TimeoutError, DataError
except ValueError:
    ## relative imports not allowed when running from command prompt, so
    ## we adjust sys.path when running the script for testing
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



COMMANDS = {
    'rol': 2,
    'ror': 1,
    'mvp': 4,
    'mst': 3,
    'rfs': 13,
    'sco': 30,
    'cco': 32,
    'gco': 31,
    
    'sap': 5,
    'gap': 6,
    'stap': 7,
    'rsap': 8,
    'sgp': 9,
    'ggp': 10,
    'stgp': 11,
    'rsgp': 12,
    
    'sio': 14,
    'gio': 15,
    'sac': 29,
}

PARAMETERS = {
    'target_position': 0,
    'position': 1,
    'target_speed': 2,
    'speed': 3,
    'max_speed': 4,
    'max_acceleration': 5,
    'max_current': 6,
    'standby_current': 7,
    'target_pos_reached': 8,
    'ref_switch_status': 9,
    'right_limit_switch_status': 10,
    'left_limit_switch_status': 11,
    'right_limit_switch_disable': 12,
    'left_limit_switch_disable': 13,
    'acceleration': 135,
    'ramp_mode': 138,
    'microstep_resolution': 140,
    'soft_stop_flag': 149,
    'ramp_divisor': 153,
    'pulse_divisor': 154,
    'referencing_mode': 193,
    'referencing_search_speed': 194,
    'referencing_switch_speed': 195,
    'distance_end_switches': 196,
    'mixed_decay_threshold': 203,
    'freewheeling': 204,
    'stall_detection_threshold': 205,
    'actual_load_value': 206,
    'driver_error_flags': 208,
    'encoder_position': 209,
    'encoder_prescaler': 210,
    'fullstep_threshold': 211,
    'maximum_encoder_deviation': 212,
    'power_down_delay': 214,
    'absolute_encoder_value': 215,
}

STATUS = {
    1: "Wrong checksum",
    2: "Invalid command",
    3: "Wrong type",
    4: "Invalid value",
    5: "Configuration EEPROM locked",
    6: "Command not available",
}


class TMCMError(Exception):
    def __init__(self, status):
        self.status = status
        msg = STATUS[status]
        
        Exception.__init__(msg)
        

class TMCM140(SerialDevice):

    def __init__(self, port, baudrate=9600, module_addr=1):
        """
        port: serial COM port (eg. COM3 or /dev/ttyACM0)
        baudrate: 9600 by default
        module_addr: 1 by default
        """
        self.lock = RLock()
        self.port = port
        assert isinstance(module_addr, int)
        assert module_addr > 0
        self.module_addr = module_addr
        self.module_str = chr(module_addr+64)
        self._waiting_for_reply = False
        SerialDevice.__init__(self, port=self.port, baudrate=baudrate)

    @threadsafe
    def command(self, cmd, type, motor, value, block=True):
        """Send a command to the controller.
        
        If block is True, then wait until the controller becomes available if
        it is currently busy.
        """
        if self._waiting_for_reply:
            raise Exception("Cannot send command; previous reply has not been "
                            "received yet.")
        cmd_num = COMMANDS[cmd]
        assert isinstance(type, int)
        assert isinstance(motor, int)
        
        # Try packing the value first as unsigned, then signed. (the overlapping
        # integer ranges have identical bit representation, so there is no 
        # ambiguity)
        try:
            cmd = struct.pack('>BBBBI', self.module_addr, cmd_num, type, motor, value)
        except struct.error:
            cmd = struct.pack('>BBBBi', self.module_addr, cmd_num, type, motor, value)
            
        chksum = sum(bytearray(cmd)) % 256
        self.write(cmd + struct.pack('B', chksum))
        self._waiting_for_reply = True
        
    @threadsafe
    def get_reply(self):
        """Read and parse a reply from the controller.
        
        Raise an exception if an error was reported.
        """
        if not self._waiting_for_reply:
            raise Exception("No reply expected.")
        
        try:
            d = self.read(9)
        finally:
            self._waiting_for_reply = False
        d2 = self.readAll()
        if len(d2) > 0:
            raise Exception("Error: extra data while reading reply.")
        
        parts = struct.unpack('>BBBBiB', d)
        reply_addr, module_addr, status, cmd_num, value, chksum = parts
        
        if chksum != sum(bytearray(d[:-1])) % 256:
            raise Exception("Invalid checksum reading from controller.")
        
        if status < 100:
            raise TMCMError(status)        
        
        return parts
        
    @threadsafe
    def rotate(self, direction, velocity):
        """Begin rotating motor.
        
        direction: 'r' or 'l'
        velocity: 0-2047
        """
        assert isinstance(velocity, int)
        assert 0 <= velocity < 2048
        assert direction in ('r', 'l')
        self.command('ro'+direction, 0, 0, velocity)
        self.get_reply()

    @threadsafe
    def stop(self):
        self.command('mst', 0, 0, 0)
        self.get_reply()
        
    @threadsafe
    def move_to(self, pos, relative=False, velocity=None):
        """Rotate until reaching *pos*.
        
        pos: The target position
        relative: If True, then *pos* is interpreted as relative to the current 
                  position
        velocity: Optionally set the target velocity before moving 
        """
        assert isinstance(pos, int)
        assert -2**32 <= pos < 2**32
        if velocity is not None:
            assert isinstance(velocity, int) 
            assert 0 <= velocity < 2048
            raise NotImplementedError()
        
        type = 1 if relative else 0
        self.command('mvp', type, 0, pos)
        self.get_reply()
        
    @threadsafe
    def get_pos(self):
        """Return the current position of the motor.
        
        This value is stored when the motor is powered off ?
        """
        return self._get_param('position')
    
    def _get_param(self, param):
        pnum = PARAMETERS[param]
        self.command('gap', pnum, 0, 0)
        return self.get_reply()[4]
        
        
        
    
if __name__ == '__main__':
    import time
    s = TMCM140(port='/dev/ttyACM0', baudrate=9600)
    s.rotate('l', 100)
    time.sleep(0.2)
    s.stop()
