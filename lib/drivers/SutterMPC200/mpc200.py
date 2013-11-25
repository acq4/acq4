import serial, struct, time, collections, threading
try:
    from ..SerialDevce import SerialDevice, TimeoutError, DataError
except ValueError:
    ## relative imports not allowed when running from command prompt
    if __name__ == '__main__':
        import sys, os
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
        from SerialDevice import SerialDevice, TimeoutError, DataError


# ErrorVals = {
#     0: ('SP Over-run', 'The previous character was not unloaded before the latest was received.'),
#     1: ('Frame Error', 'A valid stop bit was not received during the appropriate time period.'), 
#     2: ('Buffer Over-run', 'The input buffer is filled and CR has not been received.'),
#     4: ('Bad Command', 'Input can not be interpreted -- command byte not valid.'),
#     8: ('Move Interrupted', 'A requested move was interrupted by input on the serial port.'),
#     16:('Arduino error', 'Error was reported by arduino interface.'),
#     32:('MP285 Timeout', 'Arduino timed out waiting for response from MP285.'),
#     64:('Command timeout', 'Arduino timed out waiting for full command from computer.'),
# }


class MPC200Error(Exception):
    pass


def threadsafe(method):
    # decorator for automatic mutex lock/unlock
    def lockMutex(self, *args, **kwds):
        with self.lock:
            return method(self, *args, **kwds)
    return lockMutex

def resetDrive(method):
    # decorator to reset any changes to currently active drive
    def resetDrive(self, *args, **kwds):
        try:
            active = self.getActiveDrive()
            return method(self, *args, **kwds)
        finally:
            self.setDrive(active)
    return resetDrive


class SutterMPC200(SerialDevice):

    def __init__(self, port):
        """
        port: serial COM port (eg. COM3 or /dev/ttyACM0)
        """
        self.lock = threading.RLock()
        self.port = port
        self.pos = [None]*4  # used to remember position of each drive
        SerialDevice.__init__(self, port=self.port, baudrate=128000)
        self.scale = [0.0625e-6]*3  # default is 16 usteps per micron
        # time.sleep(1.0)  ## Give devices a moment to chill after opening the serial line.
        # self.read()      ## and toss any junk in the buffer

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
        res = struct.unpack('=BBBBB', packet)
        return res[0], res[1:]

    @threadsafe
    def getActiveDrive(self):
        self.write('K')
        packet = self.read(4, term='\r')
        return struct.unpack('=B', packet[0])[0]
    
    @threadsafe
    def getFirmwareVersion(self):
        self.write('K')
        packet = self.read(4, term='\r')
        return struct.unpack('=BB', packet[1:])

    @threadsafe
    def getPos(self, scaled=True, drive=None):
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
        packet = self.read(length=14, timeout=2.0, term='\r')
        
        drive, x, y, z = struct.unpack('=Blll', packet)
        pos = (x, y, z)

        if self.pos[drive] != pos:
            self.posChanged(drive, pos)
        self.pos[drive] = pos, time.time()  # record new position

        if not scaled:
            return drive, pos
        pos = [pos[i]*self.scale[i] for i in [0,1,2]]
        return drive, pos

    def posChanged(self, drive, pos):
        """
        Method called whenever the position of a drive has changed. This is initiated by calling getPos().
        Override this method to respond to position changes; the default does nothing.
        """
        pass

    @threadsafe
    @resetDrive
    def _getDrivePos(self, drive, scaled=True):
        ## read the position of a specific drive
        self.setDrive(drive)
        return self.getPos(scaled=scaled)

    @threadsafe
    @resetDrive
    def moveTo(self, drive, pos, speed, timeout=2.0, scaled=True):
        """Set the position of *driver*.
        Returns a generator that yields the position and percent done until the
        move is complete. This function should be invoked in a for-loop::
        
            for pos, percent in mpc.moveTo((x,y,z)):
                print "Moving %d percent done" % percent
        
        Any item in the position may be set as None to leave it unchanged.
        Raises an exception if the move is cancelled before it completes.
        The move may also be cancelled while in-progress by sending "stop" 
        to the generator::
        
            gen = mpc.moveTo((x,y,z))
            for pos, percent in gen:
                if user_requested_stop():
                    gen.send('stop')
                    
        *speed* may be specified as an integer 0-15 for constant speed, or 
        'fast' indicating that the drive should use acceleration to move as
        quickly as possible. For constant speeds, a value of 15 is maximum,
        about 1.3mm/sec for the _fastest moving axis_, not for the net speed
        of all three axes. 
        
        Positions must be specified in meters unless *scaled* = False, in which 
        case position is specified in motor steps. 
        """
        
        if drive is not None:
            self.setDrive(drive)
        
        # Convert pos argument to motor steps
        if None in pos:
            currentPos = self.getPos(scaled=False)
        pos = [(pos[i]/self.scale[i] if pos[i] is not None else currentPos[i]) for i in range(3)]
        
        # Decide on move command
        if speed == 'fast':
            cmd = b'M' + struct.pack('=lll', (x,y,z))
        else:
            cmd = b'S' + struct.pack('=Blll', (s,x,y,z))
            
        # go!
        self.sp.write(cmd)
        
        # watch for updates



# class MPC200Drive(object):
#     """
#     Represents a single drive on a Sutter MPC-200.
#     """
#     def __init__(self, mpc200, drive):
#         self.mpc200 = mpc200
#         self.drive = drive
#         self.pos = None

#     def getPos(self, scaled=True):
#         if self.pos is not None:
#             return self.pos
    
        
        
        
        

    #def setPos(self, pos, block=True, timeout=10.):
        #"""Set the position. 
        #Arguments:
            #pos: tuple (x, y, z) values must be given in meters.
                 #Setting a coordinate to None leaves it unchanged.
            #block: bool, if true then the function does not return until the move is complete.
        #"""
        #scale = self.scale()
        #if len(pos) < 3:
            #pos = list(pos) + [None] * (3-len(pos))
            
        #if None in pos:
            #currentPos = self.getPos(scaled=False)
        #pos = [(pos[i]/scale if pos[i] is not None else currentPos[i]) for i in range(3)]
            
        #cmd = 'm' + struct.pack('=3l', int(pos[0]), int(pos[1]), int(pos[2])) + '\r'
        #self.write(cmd)
        #if block:
            #self.readPacket(timeout=timeout)  ## could take a long time..


    #def moveBy(self, pos, block=True, timeout=10.):
        #"""Move by the specified distance. 
        #Arguments:
            #pos: tuple (dx, dy, dz) values must be given in meters.
            #block: bool, if true then the function does not return until the move is complete.
        #"""
        #scale = self.scale()
        #if len(pos) < 3:
            #pos = list(pos) + [0.0] * (3-len(pos))
            
        #currentPos = self.getPos(scaled=False)
        #pos = [pos[i]/scale + currentPos[i] for i in range(3)]
            
        #cmd = 'm' + struct.pack('=3l', int(pos[0]), int(pos[1]), int(pos[2])) + '\r'
        #self.write(cmd)
        #if block:
            #self.readPacket(timeout=timeout)  ## could take a long time..





    #def scale(self):
        ### Scale of position values in msteps/m
        ### Does this value change during operation?
        ### Should I be using step_mul for anything?
        #if self._scale is None:
            #stat = self.stat()
            #self._scale = 1e-6 / stat['step_div']
        #return self._scale
    
    #def stop(self):
        #self.write('\3')
        #try:
            #self.readPacket()
        #except MP285Error as err:
            #for e in err.args[0]:
                #if e[0] == 8:   ## move interrupted, like we asked for
                    #return
            #raise
                    
            
    #def setSpeed(self, speed, fine=True):
        #"""Set the speed of movements used when setPos is called.
        
        #Arguments:
            #speed: integer from 1 to 6550 in coarse mode, 1310 in fine mode. 
                   #Note that small numbers can result in imperceptibly slow movement.
            #fine:  bool; True => 50uSteps/step    False => 10uSteps/step
        #"""
        #v = int(speed)
        
        ### arbitrary speed limits.. do these apply to all devices?
        #maxSpd = 6550
        #if fine:
            #maxSpd = 1310
            
        #v = max(min(v, maxSpd), 1)
        ##print "MP285 speed:", v
        #if fine:
            #v |= 0x8000
        #cmd = 'V' + struct.pack('=H', v) + '\r'
        #self.write(cmd)
        #self.readPacket()
            
        
    #def setLimits(self, limits):
        #"""Set position limits on the device which may not be exceeded.
        #This command is only available when using custom hardware.
        #limits = [+x, -x, +y, -y, +z, -z]
        #If a limit is None, it will be ignored.
        #"""
        #scale = self.scale()
        #useLims = [(1 if x is not None else 0) for x in limits]
        #limits = [(0 if x is None else int(x/scale)) for x in limits]
        #data = struct.pack("=6l6B", *(limits + useLims))
        #self.write('l'+data+'\r');
        #self.readPacket()
        


        
if __name__ == '__main__':
    s = SutterMPC200(port='COM3')
    
    def pos():
        d, p = s.getPos()
        print "<mpc200> x: %0.2fum  y: %0.2fum,  z: %0.2fum" % (p[0]*1e6, p[1]*1e6, p[2]*1e6)
        
    #def ipos():
        #p = s.getImmediatePos()
        #print "x: %0.2fum  y: %0.2fum,  z: %0.2fum" % (p[0]*1e6, p[1]*1e6, p[2]*1e6)
        
    #def stat():
        #st = s.stat()
        #for k in st:
            #print "%s:%s%s" % (k, " "*(15-len(k)), str(st[k]))
            
    def monitor():
        while True:
            pos()

    #def clock(speed, fine=False, runtime=2.0):
        #s.setSpeed(6500, fine=False)
        #s.setPos([-0.01, 0, 0])
        #pos = s.getPos()
        #s.setSpeed(speed, fine)
        #time.clock()
        #t = time.clock()
        #dist = runtime*speed*1e-6
        #s.setPos([pos[0]+dist, pos[1], pos[2]], timeout=runtime*2)
        #s.setPos(pos, timeout=runtime*2)
        #dt = 0.5*(time.clock()-t)
        #print "%d: dt=%0.2gs, dx=%0.2gm, %0.2f mm/s" % (int(speed), dt, dist, dist*1e3/dt)
        
    #def saw(dx, dz, zstep=5e-6):
        #p1 = s.getPos()
        #z = p1[2]
        #p1 = p1[:2]
        #p2 = [p1[0] + dx, p1[1]]
        
        #n = int(dz/zstep)
        #for i in range(n):
            #print "step:", i
            #s.setPos(p2)
            #s.setPos(p1)
            #if i < n-1:
                #z += zstep
                #s.setPos([None,None,z])
        
    #ipos()
    #pos()
        
