from __future__ import print_function
import serial, struct, time, collections, threading
from ..SerialDevice import SerialDevice

ErrorVals = {
    0: ('SP Over-run', 'The previous character was not unloaded before the latest was received.'),
    1: ('Frame Error', 'A valid stop bit was not received during the appropriate time period.'), 
    2: ('Buffer Over-run', 'The input buffer is filled and CR has not been received.'),
    4: ('Bad Command', 'Input can not be interpreted -- command byte not valid.'),
    8: ('Move Interrupted', 'A requested move was interrupted by input on the serial port.'),
    16:('Arduino error', 'Error was reported by arduino interface.'),
    32:('MP285 Timeout', 'Arduino timed out waiting for response from MP285.'),
    64:('Command timeout', 'Arduino timed out waiting for full command from computer.'),
}
    

class TimeoutError(Exception):
    pass

class MP285Error(Exception):
    pass

class SutterMP285(SerialDevice):
    """
    Class for communicating with Sutter MP-285 via serial port.
    
    Note that this class is NOT thread-safe.
    """
    def __init__(self, port, baud=9600):
        """
        port: serial COM port (0 => com1)"""
        #self.port = port
        #self.baud = baud
        #self.sp = serial.Serial(int(self.port), baudrate=self.baud, bytesize=serial.EIGHTBITS, timeout=0)
        SerialDevice.__init__(self, port=port, baudrate=baud)
        self._scale = None
        self.moving = False
        
        time.sleep(1.0)  ## Give devices a moment to chill after opening the serial line.
        self.clearBuffer()
        self.setSpeed(777) ## may be required to be sure Sutter is behaving (voodoo...)
        self.clearBuffer()
        

    def getPos(self, scaled=True):
        """Get current position reported by controller. Returns a tuple (x,y,z); values given in m."""
        ## request position
        self.write('c\r') # request is directly to Sutter MP285 in this case.
        packet = self.read(length=13, timeout=8.0, term='\r')
        if len(packet) != 12:
            raise Exception("Sutter MP285: getPos: bad position packet: <%s> expected 12, got %d" % (repr(packet), len(packet)))
        
        pos = [packet[:4], packet[4:8], packet[8:]]
        pos = [struct.unpack('=l', x)[0] for x in pos]
        if not scaled:
            return pos
        scale = self.scale()
        pos = [x*scale for x in pos]
        return pos

    def getImmediatePos(self, returnButtons=False):
        """This is a non-standard command provided by custom hardware (Arduino controller).
        It returns an estimated position even while the ROE is in use. 
        (if getPos() is called while the ROE is in use, the MP285 will very likely crash.)
        """
       # self.readPacket(block=False)
        self.write('p')  # talks to Arduino only.
        packet = self.read(length=13, timeout=5.0, term='\r')
        if len(packet) != 12:
            raise Exception("Sutter MP285: getImmediatePos: bad position packet: <%s> (%d)" % (repr(packet),len(packet)))
     
        pos = [packet[:4], packet[4:8], packet[8:12]]
        pos = [struct.unpack('=l', x)[0] for x in pos]
        scale = self.scale()
        pos = [x*scale for x in pos]
        if returnButtons:
            btn = packet[12]
            btns = [ord(btn) & x == 0 for x in [1, 4, 16, 64]]
            return pos, btns
        return pos
        
    def getButtonState(self):
        p,b = self.getImmediatePos(returnButtons=True)
        return b
    
    
    def setPos(self, pos, block=True, timeout=10.):
        """Set the position. 
        Arguments:
            pos: tuple (x, y, z) values must be given in meters.
                 Setting a coordinate to None leaves it unchanged.
            block: bool, if true then the function does not return until the move is complete.
        """
        scale = self.scale()
        if len(pos) < 3:
            pos = list(pos) + [None] * (3-len(pos))
            
        if None in pos:
            currentPos = self.getPos(scaled=False)
        pos = [(pos[i]/scale if pos[i] is not None else currentPos[i]) for i in range(3)]
            
        cmd = 'm' + struct.pack('=3l', int(pos[0]), int(pos[1]), int(pos[2])) + '\r'
        self.write(cmd)
        self.moving = True
        if block:
            self.blockWhileMoving(timeout=timeout)

    def checkMoving(self):
        """
        Return bool whether the stage is currently moving. 
        """
        if self.sp.inWaiting() > 0:
            self.read(length=1, term='\r') 
            self.moving = False
        if not self.moving:
            return False
        return True

    def blockWhileMoving(self, timeout=10.0):
        """
        Blocks until stage is done moving, or until timeour.
        """
        if not self.moving:
            return
        self.read(length=1, timeout=timeout, term='\r')
        self.moving = False        

    def moveBy(self, pos, block=True, timeout=10.):
        """Move by the specified distance. 
        Arguments:
            pos: tuple (dx, dy, dz) values must be given in meters.
            block: bool, if true then the function does not return until the move is complete.
        """
        scale = self.scale()
        if len(pos) < 3:
            pos = list(pos) + [0.0] * (3-len(pos))
            
        currentPos = self.getPos(scaled=False)
        pos = [pos[i]/scale + currentPos[i] for i in range(3)]
            
        cmd = 'm' + struct.pack('=3l', int(pos[0]), int(pos[1]), int(pos[2])) + '\r'
        self.write(cmd)
        if block:
            self.blockWhileMoving(timeout=timeout)

    def scale(self):
        ## Scale of position values in msteps/m
        ## Does this value change during operation?
        ## Should I be using step_mul for anything?
        if self._scale is None:
            stat = self.stat()
            self._scale = 1e-6 / stat['step_div']
        return self._scale
    
    def stop(self):
        self.write('\3')
        try:
            self.readPacket()
        except MP285Error as err:
            for e in err.args[0]:
                if e[0] == 8:   ## move interrupted, like we asked for
                    return
            raise
                     
    def setSpeed(self, speed, fine=True, timeout=10.):
        """Set the speed of movements used when setPos is called.
        
        Arguments:
            speed: integer from 1 to 6550 in coarse mode, 1310 in fine mode. 
                   Note that small numbers can result in imperceptibly slow movement.
            fine:  bool; True => 50uSteps/step    False => 10uSteps/step
        """
        v = int(speed)
        
        ## arbitrary speed limits.. do these apply to all devices?
        maxSpd = 6550
        if fine:
            maxSpd = 1310
            
        v = max(min(v, maxSpd), 1)
        #print "MP285 speed:", v
        if fine:
            v |= 0x8000
        cmd = 'V' + struct.pack('=H', v) + '\r'

        self.write(cmd)
        self.read(1, term='\r', timeout=timeout)
            
        
    def stat(self, ):
        self.write('s\r')
        packet = self.read(33, timeout=5.0, term='\r')
        if len(packet) != 32:
            raise Exception("Sutter MP285: bad stat packet: '%s'" % repr(packet))
            
        paramNames = ['flags', 'udirx', 'udiry', 'udirz', 'roe_vari', 'uoffset', 'urange', 'pulse', 
                      'uspeed', 'indevice', 'flags2', 'jumpspd', 'highspd', 'dead', 'watch_dog',
                      'step_div', 'step_mul', 'xspeed', 'version']
        vals = struct.unpack('=4B5H2B8H', packet)
        params = collections.OrderedDict()
        for i,n in enumerate(paramNames):
            params[n] = vals[i]
            
        flags = params['flags']
        params['setup_num'] = flags & 0xF
        params['roe_dir']   = -1 if (flags & 2**4) else 1
        params['rel_abs_f'] = 'abs' if (flags & 2**5) else 'rel'
        params['mode_f']    = 'cont' if (flags & 2**6) else 'pulse'
        params['store_f']   = 'stored' if (flags & 2**7) else 'erased'
        
        flags2 = params['flags2']
        params['loop_mode']  = bool(flags2 &   1)
        params['learn_mode'] = bool(flags2 &   2)
        params['step_mode']  = 50 if (flags2 & 4) else 10
        params['sw2_mode']   = bool(flags2 &   8)
        params['sw1_mode']   = bool(flags2 &  16)
        params['sw3_mode']   = bool(flags2 &  32)
        params['sw4_mode']   = bool(flags2 &  64)
        params['reverse_it'] = bool(flags2 & 128)
        
        params['resolution'] = 50 if (params['xspeed'] & 2**15) else 10
        params['speed'] = params['xspeed'] & 0x7FFF
        
        return params
    
    def setLimits(self, limits):
        """Set position limits on the device which may not be exceeded.
        This command is only available when using custom hardware.
        limits = [+x, -x, +y, -y, +z, -z]
        If a limit is None, it will be ignored.
        """
        scale = self.scale()
        useLims = [(1 if x is not None else 0) for x in limits]
        limits = [(0 if x is None else int(x/scale)) for x in limits]
        data = struct.pack("=6l6B", *(limits + useLims))
        self.write('l'+data+'\r');
        self.readPacket()
        

    def reset(self, hard=False):
        """Reset the controller. 
        Arguments:
            hard: If False, then a soft-reset "r" command is sent
                  If True, then a hard-reset "R" command is sent (not supported by all hardware)"""
        cmd = 'r\r'
        if hard:
            cmd = 'R\r'
        self.write(cmd)
        
        ## wait for reset, check for error
        s = self.clearBuffer()
        if len(s) == 2 and s[1] == '\r':
            self.raiseError(s[0])
            
        ## clear out anything else in the buffer (reset may generate garbage)
        if s == '\x00':
            return True  ## successful reset

        return False
            
    def setOrigin(self):
        self.write('o\r')
        self.readPacket()
        
    def setAbsolute(self):
        self.write('a\r')
        self.readPacket()
    
    def setRelative(self):
        self.write('b\r')
        self.readPacket()
        
    def continueAfterPause(self):
        self.write('e\r')
        self.readPacket()
    
    def refresh(self):
        self.write('n\r')
        self.readPacket()

    def readPacket(self):
        return self.readUntil('\r')

    #def clearBuffer(self):
        #d = self.readAll()
        #time.sleep(0.1)
        #d += self.readAll()
        #if len(d) > 0:
            #print "Sutter MP285: Warning: tossed data ", repr(d)
        #return d
    
    #def readAll(self):
        ### read all bytes waiting in buffer; non-blocking.
        #n = self.sp.inWaiting()
        #if n > 0:
            #return self.sp.read(n)
        #return ''
    
    #def write(self, data, timeout=10.0):
        #self.blockWhileMoving(timeout=timeout) # If the stage is still moving, wait until it is done before sending another packet.
        ##self.readAll()  ## always empty buffer before sending command
        #self.sp.write(data)
        
    #def close(self):
        #self.sp.close()

    def raiseError(self, errVals):
        ## errVals should be list of error codes
        errors = []
        for err in errVals:
            hit = False
            for k in ErrorVals:
                if ord(err) & k:
                    hit = True
                    errors.append((k,)+ErrorVals[k])
            if not hit:
                errors.append((ord(err), "Unknown error code", ""))
        raise MP285Error(errors)

    #def read(self, length, timeout=5, term=None):
        ### Read *length* bytes or raise exception on timeout.
        ### if *term* is given, check that the last byte is *term* and remove it
        ### from the returned packet.
        ##self.sp.setTimeout(timeout) #broken!
        #packet = self.readWithTimeout(length, timeout)
        #if len(packet) < length:
            #raise Exception("MP285: Timed out waiting for serial data (received so far: %s)" % repr(packet))
        #if term is not None:
            #if packet[-len(term):] != term:
                #self.clearBuffer()
                #raise Exception("MP285: Packet corrupt: %s (len=%d)" % (repr(packet), len(packet)))
            #return packet[:-len(term)]
        #return packet
        
    #def readWithTimeout(self, nBytes, timeout):
        #start = time.time()
        #packet = ''
        #while len(packet) < nBytes and time.time()-start < timeout:
            #packet += self.sp.read(1)
        #return packet
                    
    #def readPacket(self, expect=0, timeout=5, block=True):
        ### Read until a carriage return is encountered (or timeout).
        ### If expect is >0, then try to get a packet of that length, ignoring \r within that data
        ### if block is False, then return immediately if no data is available.
        #start = time.time()
        #res = ''
        #errors = []
        #packets = []
        
        #while True:
            #s = self.readAll()
            #if not block and len(s) == 0:
                #return
            
            #if expect > 0:  ## move bytes into result without checking for \r
                #nb = expect-len(res)
                #res += s[:nb]
                #s = s[nb:]
            
            #try:
                #while len(s) > 0:  ## pull packets out of s one at a time
                    #res += s[:s.index('\r')]
                    #s = s[s.index('\r')+1:]
                    #if len(res) == 1:  ## error packet was sent
                        #errors.append(res)
                    #else:
                        #packets.append(res)
                    #res = ''
            #except ValueError:   ## partial packet; append and wait for more data
                #res += s  
                
            #if len(res) > 32:  ## no valid packets are longer than 32 bytes; give up
                #raise Exception("Got junk data while reading for packet: '%s'" % str(res))
            
            #if len(res) == 0:
                #if len(errors) > 0:
                    #self.raiseError(errors)
                #if len(packets) == 1:  ## success
                    #return packets[0]
                #if len(packets) > 1:
                    #raise Exception("Too many packets read.", packets)
            
            ##if len(s) > 0:
                ##if s != '\r' and s[0] != '=':
                    ##print "SutterMP285 Error: '%s'" % s
                ###print "return:", repr(s)
                ##break
            #time.sleep(0.01)
            #if time.time() - start > timeout:
                #raise TimeoutError("Timeout while waiting for response. (Data so far: %s)" % repr(res))
        

        
if __name__ == '__main__':
    import sys
    s = SutterMP285(port=sys.argv[1], baud=int(sys.argv[2])) # Arduino baud rate, NOT MP285 baud rate.
    #s = SutterMP285(port=2, baud=9600)
    def pos():
        p = s.getPos()
        print("<mp285> x: %0.2fum  y: %0.2fum,  z: %0.2fum" % (p[0]*1e6, p[1]*1e6, p[2]*1e6))
        
    def ipos():
        p = s.getImmediatePos()
        print("x: %0.2fum  y: %0.2fum,  z: %0.2fum" % (p[0]*1e6, p[1]*1e6, p[2]*1e6))
        
    def stat():
        st = s.stat()
        for k in st:
            print("%s:%s%s" % (k, " "*(15-len(k)), str(st[k])))
            
    def monitor():
        while True:
            pos()

    def clock(speed, fine=False, runtime=2.0):
        s.setSpeed(6500, fine=False)
        s.setPos([-0.01, 0, 0])
        pos = s.getPos()
        s.setSpeed(speed, fine)
        time.clock()
        t = time.clock()
        dist = runtime*speed*1e-6
        s.setPos([pos[0]+dist, pos[1], pos[2]], timeout=runtime*2)
        s.setPos(pos, timeout=runtime*2)
        dt = 0.5*(time.clock()-t)
        print("%d: dt=%0.2gs, dx=%0.2gm, %0.2f mm/s" % (int(speed), dt, dist, dist*1e3/dt))
        
    def saw(dx, dz, zstep=5e-6):
        p1 = s.getPos()
        z = p1[2]
        p1 = p1[:2]
        p2 = [p1[0] + dx, p1[1]]
        
        n = int(dz/zstep)
        for i in range(n):
            print("step:", i)
            s.setPos(p2)
            s.setPos(p1)
            if i < n-1:
                z += zstep
                s.setPos([None,None,z])
        
    ipos()
    pos()
        