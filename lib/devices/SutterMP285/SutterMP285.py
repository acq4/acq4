# -*- coding: utf-8 -*-
from __future__ import with_statement
from lib.devices.Device import *
#import serial, struct
from lib.drivers.SutterMP285 import *
from Mutex import Mutex
from debug import *
#import pdb
import devTemplate
import functions as fn
import numpy as np

class SutterMP285(Device):

    sigPositionChanged = QtCore.Signal(object)
    sigLimitsChanged = QtCore.Signal(object)

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.port = config['port']
        self.scale = config.get('scale', [1e-7,1e-7,1e-7]) ## MP285 always uses 0.1um resolution?
        self.baud = config.get('baud', 9600)   ## 9600 is probably factory default
        self.mThread = SutterMP285Thread(self, self.baud, self.scale)
        self.pos = [0, 0, 0]
        #self.posxyz = [0, 0, 0];
        #QtCore.QObject.connect(self.mThread, QtCore.SIGNAL('positionChanged'), self.posChanged)
        self.mThread.sigPositionChanged.connect(self.posChanged)
        #QtCore.QObject.connect(self.mThread, QtCore.SIGNAL('buttonChanged'), self.btnChanged)
        self.mThread.start()

    def quit(self):
        #print "serial SutterMP285 requesting thread exit.."
        self.mThread.stop(block=True)

    def posChanged(self, data):  #potentially have to modify this
        #QtCore.pyqtRemoveInputHook()
        #pdb.set_trace()
        #print "SutterMP285: posChanged"
        with MutexLocker(self.lock):
            #print "SutterMP285: posChanged locked"

            self.pos[:len(data['abs'])] = data['abs']
            rel = [0] * len(self.pos)
            rel[:len(data['rel'])] = data['rel']
        #print "SutterMP285: posChanged emit.."
        #print "position change:", rel, self.pos
        #self.emit(QtCore.SIGNAL('positionChanged'), {'rel': rel, 'abs': self.pos[:]})
        self.sigPositionChanged.emit({'rel': rel, 'abs': self.pos[:]})
        #print "SutterMP285: posChanged done"

    def getPosition(self):
        with MutexLocker(self.lock):
            return self.pos[:]

#    def getPositionxyz(self):
#	with MutexLocker(self.lock):
#            return self.posxyz[:];

    def getState(self):
        with MutexLocker(self.lock):
            return (self.pos[:],)

    def deviceInterface(self, win):
        return SMP285Interface(self, win)

class SMP285Interface(QtGui.QWidget):
    def __init__(self, dev, win):
        QtGui.QWidget.__init__(self)
        self.ui = devTemplate.Ui_Form()
        self.ui.setupUi(self)
        
        self.win = win
        self.dev = dev
        #QtCore.QObject.connect(self.dev, QtCore.SIGNAL('positionChanged'), self.update)
        self.dev.sigPositionChanged.connect(self.update)
        self.update()
        
        self.limitBtns = [
            [self.ui.xMinBtn, self.ui.xMaxBtn],
            [self.ui.yMinBtn, self.ui.yMaxBtn],
            [self.ui.zMinBtn, self.ui.zMaxBtn],
        ]
        self.limitLabels = [
            [self.ui.xMinLabel, self.ui.xMaxLabel],
            [self.ui.yMinLabel, self.ui.yMaxLabel],
            [self.ui.zMinLabel, self.ui.zMaxLabel],
        ]
        for axis in range(3):
            for limit in range(2):
                self.limitBtns[axis][limit].clicked.connect(self.mkLimitCallback(axis, limit))
        
        self.ui.maxSpeedSpin.setOpts(value=1e-3, dec=True, suffix='m/s', step=0.1, minStep=1e-6)
        self.ui.maxSpeedSpin.valueChanged.connect(self.maxSpeedChanged)
        self.ui.monitorPosBtn.clicked.connect(self.monitorClicked)
        self.ui.joyBtn.sigStateChanged.connect(self.joyStateChanged)

    def mkLimitCallback(self, *args):
        return lambda: self.updateLimit(*args)
        
    def updateLimit(self, axis, limit):
        pos = self.dev.getPosition()[axis]
        self.dev.mThread.setLimit(axis, limit, pos)
        self.limitLabels[axis][limit].setText(fn.siFormat(pos, suffix='m', precision=5))
        
    def maxSpeedChanged(self):
        self.dev.mThread.setMaxSpeed(self.ui.maxSpeedSpin.value())
        
    def update(self):
        pos = self.dev.getPosition()
        #for i in [0,1,2]:
            #if pos[i] < self.limit

        text = ', '.join([fn.siFormat(x, suffix='m', precision=5) for x in pos])
        self.ui.posLabel.setText(text)

    def monitorClicked(self):
        self.dev.mThread.setMonitor(self.ui.monitorPosBtn.isChecked())
        
    def joyStateChanged(self, btn, v):
        ms = self.ui.maxSpeedSpin.value()
        self.dev.mThread.setVelocity([v[0]*ms, v[1]*ms, 0])

class TimeoutError(Exception):
    pass
        
class SutterMP285Thread(QtCore.QThread):

    sigPositionChanged = QtCore.Signal(object)
    sigError = QtCore.Signal(object)

    def __init__(self, dev, baud, scale):
        QtCore.QThread.__init__(self)
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.scale = scale
        self.monitor = True
        self.dev = dev
        self.port = self.dev.port
        #self.pos = [0, 0, 0]
        self.baud = baud
        self.velocity = [0,0,0]
        self.limits = [[-0.01,0.01],[-0.01,0.01],[-0.01,0.01]]
        self.maxSpeed = 1e-3
        #self.posxyz = [ 0, 0, 0]
        

    def setLimit(self, axis, limit, pos):
        with self.lock:
            self.limits[axis][limit] = pos
            
    def setMaxSpeed(self, s):
        with self.lock:
            self.maxSpeed = s
            
    def setMonitor(self, mon):
        with self.lock:
            self.monitor = mon
        
    def setVelocity(self, v):
        with self.lock:
            self.velocity = v
        
    def run(self):
        self.stopThread = False
        self.sp = serial.Serial(int(self.port), baudrate=self.baud, bytesize=serial.EIGHTBITS)
        #time.sleep(3) ## Wait a few seconds for the mouse to say hello
        ## clear buffer before starting
        if self.sp.inWaiting() > 0:
            #print "Discarding %d bytes" % self.sp.inWaiting()
            self.sp.read(self.sp.inWaiting())
            
        velocity = np.array([0,0,0])
        pos = [0,0,0]
        while True:
            with self.lock:
                monitor = self.monitor
                limits = [x[:] for x in self.limits]
                maxSpeed = self.maxSpeed
                newVelocity = np.array(self.velocity[:])
                
                
            if np.any(newVelocity != velocity):
                speed = np.clip(np.sum(newVelocity**2)**0.5, 0., 1.)   ## should always be 0.0-1.0
                #print "new velocity:", newVelocity, "speed:", speed
                
                if speed == 0:
                    nv = np.array([0,0,0])
                else:
                    nv = newVelocity/speed
                    
                speed = np.clip(speed, 0, maxSpeed)
                #print "final speed:", speed
                
                ## stop current move, get position, start new move
                self.stopMove()
                pos1 = self.readPosition()
                if pos1 is not None:
                    
                    if speed > 0:
                        self.writeVelocity(speed, nv, limits=limits, pos=pos1)
                        
                    ## report current position
                    
                        
                    velocity = newVelocity
                    
                
            if np.all(velocity == 0):
                if monitor:
                    newPos = self.readPosition()

                    if newPos is not None:
        
                        change = [newPos[i] - pos[i] for i in range(len(newPos))]
                        pos = newPos
        
                        if any(change):
                            #self.emit(QtCore.SIGNAL('positionChanged'), {'rel': change, 'abs': self.pos})
                            self.sigPositionChanged.emit({'rel': change, 'abs': pos})
            else:
                ## moving; make a guess about the current position
                pass

            self.lock.lock()
            if self.stopThread:
                self.lock.unlock()
                break
            self.lock.unlock()
            time.sleep(0.02)


        self.sp.close()

    def stop(self, block=False):
        #print "  stop: locking"
        with MutexLocker(self.lock):
            #print "  stop: requesting stop"
            self.stopThread = True
        if block:
            #print "  stop: waiting"
            if not self.wait(10000):
                raise Exception("Timed out while waiting for thread exit!")
        #print "  stop: done"


    def readPosition(self):
        try:
            sp = self.sp
    
            ## be absolutely sure the buffer is empty
            d = self.read()
            time.sleep(0.1)
            d += self.read()
            if len(d) > 0:
                print "Sutter MP285: Warning: tossed data ", repr(d)
    
            ## request position
            sp.write('c\r')
    
            packet = ''
            c = 0.0
            while True:
                if c > 5.0:
                    raise TimeoutError("Sutter MP285: Timed out waiting for packet. Data so far: %s", repr(packet))
                d = self.read()
                packet += d
    
                if len(packet) == 13 and packet[-1] == '\r':  ## got a whole packet and nothing else is coming..
                    break
                elif len(packet) > 12:
                    print "Sutter MP285: Corrupt packet"
                    print "    data:", repr(packet)
                #print '.'
                time.sleep(0.1) # 100ms loop time
                c += 0.1
            #print repr(packet)
            if len(packet) != 13:
                print "Sutter MP285: bad packet:", repr(packet)
                return
            pos = [packet[-13:-9], packet[-9:-5], packet[-5:-1]]
            pos = np.array([struct.unpack('l', x)[0] for x in pos])
            #print repr(x), repr(y)
            return pos*self.scale
        except TimeoutError:
            self.sigError.emit("Read timeout--press reset button on MP285.")
            return None
        except:
            self.sigError.emit("Read error--see console.")
            printExc("Error getting packet:")
            return None
        
    def writeVelocity(self, spd, v, limits, pos):
        if not self.checkLimits(pos, limits):
            return
        
        ## check all limits for closest stop point
        pt = self.vectorLimit(pos, v, limits)
        if pt is None:
            return
        
        ## set speed
        #print "SPD:", spd, "POS:", pt
        self._setSpd(spd, fineStep=True)
        self._setPos(pt, block=False)
        
                
    def vectorLimit(self, pos, v, limits):
        ## return position of closest limit intersection given starting point and vector
        pts = []
        pos = np.array(pos)
        v = np.array(v)
        for i in  [0,1,2]:
            if v[i] < 0:
                p = self.intersect(pos, v, limits[i][0], i)
            else:
                p = self.intersect(pos, v, limits[i][1], i)
            if p is not None:
                pts.append(p)
        if len(pts) == 0:
            return None
        lengths = [np.sum((p-pos)**2)**0.5 for p in pts]
        i = np.argmin(lengths)
        return pts[i]
        
            
    def intersect(self, pos, v, x, ax):
        ## return the point where vector pos->v intersects plane x along axis ax
        if v[ax] == 0:
            return None
        dx = x-pos[ax]
        return pos + dx * v/v[ax]
            
    def checkLimits(self, pos, limits):
        for i in [0,1,2]:
            if pos[i] < limits[i][0] or pos[i] > limits[i][1]:
                return False
        return True
        
        
    def read(self):
        n = self.sp.inWaiting()
        if n > 0:
            #print "-- read %d bytes" % n
            return self.sp.read(n)

        return ''
    
    def _setPos(self, pos, block=True):
        pos = np.array(pos) / self.scale
        cmd = 'm' + struct.pack('3l', int(pos[0]), int(pos[1]), int(pos[2])) + '\r'
        self.sp.write(cmd)
        while block:
            self.readResponse()
    
    def stopMove(self):
        self.sp.write('\3')
        self.readResponse()
            
    def _setSpd(self, v, fineStep=True):
        ## v in m/s
        ## fineStep==True => 50uSteps/step    False => 10uSteps/step
        
        ## This should be done with a calibrated speed table instead.
        v = int(v*1e6)
        
        if v > 2**14:
            v = 2**14
        if v < 1:
            v = 1
        if fineStep:
            v |= 0x8000
        ## v should be integer, somewhere around 10-4000. (1000 max if fineStep=True)
        cmd = 'V' + struct.pack('H', v) + '\r'
        self.sp.write(cmd)
        self.readResponse()
            
    def readResponse(self):
        start = ptime.time()
        while True:
            s = self.read()
            if len(s) > 0:
                if s != '\r' and s[0] != '=':
                    print "SutterMP285 Error:", s
                #print "return:", repr(s)
                break
            time.sleep(0.01)
            if ptime.time() - start > 10:
                raise TimeoutError("Timeout while waiting for response.")
        
    def stat(self, ):
        self.sp.write('s\r')
        s = self.sp.read(33)
        paramNames = ['flags', 'udirx', 'udiry', 'udirz', 'roe_vari', 'uoffset', 'urange', 'pulse', 
                      'uspeed', 'indevice', 'flags2', 'jumpspd', 'highspd', 'watch_dog',
                      'step_div', 'step_mul', 'xspeed', 'version', 'res1', 'res2']
        vals = struct.unpack('4B5H2B7H2B', s[:32])
        params = collections.OrderedDict()
        for i,n in enumerate(paramNames):
            params[n] = vals[i]
        return params
