# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import with_statement
from acq4.devices.Device import *
from acq4.devices.OptomechDevice import *
from acq4.drivers.SutterMP285 import *
from acq4.drivers.SutterMP285 import SutterMP285 as SutterMP285Driver  ## name collision with device class
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
import acq4.util.debug as debug
import os, time
from . import devTemplate
import acq4.pyqtgraph as pg
import numpy as np
from copy import deepcopy
import six


class SutterMP285(Device, OptomechDevice):

    sigPositionChanged = Qt.Signal(object)
    sigLimitsChanged = Qt.Signal(object)

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        OptomechDevice.__init__(self, dm, config, name)
        self.config = config
        self.configFile = os.path.join('devices', name + '_config.cfg')
        self.lock = Mutex(Qt.QMutex.Recursive)
        self.port = config['port']  ## windows com ports start at COM1, pyserial ports start at 0

        # whether this device has an arduino interface protecting it from roe/serial collisions
        # (see acq4/drivers/SutterMP285/mp285_hack)
        # If not, then position monitoring is disabled.
        self.useArduino = config.get('useArduino', False)

        self.scale = config.pop('scale', (1, 1, 1))
        # Interpret "COM1" as port 0
        if isinstance(self.port, six.string_types) and self.port.lower()[:3] == 'com':
            self.port = int(self.port[3:]) - 1
        
        self.baud = config.get('baud', 9600)   ## 9600 is probably factory default
        self.pos = [0, 0, 0]
        self.limits = [
            [[0,False], [0,False]],
            [[0,False], [0,False]],
            [[0,False], [0,False]]
        ]
        self.maxSpeed = 1e-3
        self.loadConfig()
        
        self.mp285 = SutterMP285Driver(self.port, self.baud)
        self.driverLock = Mutex(Qt.QMutex.Recursive)
        
        self.mThread = SutterMP285Thread(self, self.mp285, self.driverLock, self.scale, self.limits, self.maxSpeed)
        self.mThread.sigPositionChanged.connect(self.posChanged)
        if self.useArduino:
            self.mThread.start()
        
        dm.declareInterface(name, ['stage'], self)

    def loadConfig(self):
        cfg = self.dm.readConfigFile(self.configFile)
        if 'limits' in cfg:
            self.limits = cfg['limits']
        if 'maxSpeed' in cfg:
            self.maxSpeed = cfg['maxSpeed']

    def storeConfig(self):
        cfg = {
            'limits': self.limits,
            'maxSpeed': self.maxSpeed,
        }
        self.dm.writeConfigFile(cfg, self.configFile)

    def setLimit(self, axis, limit, val=None, enabled=None):
        if val is not None:
            self.limits[axis][limit][0] = val
        elif enabled is not None:
            self.limits[axis][limit][1] = enabled
        
        self.mThread.setLimits(self.limits)
        self.storeConfig()

    def getLimit(self):
        return(self.limits)
        
    def setMaxSpeed(self, val):
        self.mThread.setMaxSpeed(val)
        self.maxSpeed = val
        self.storeConfig()
            
    def setResolution(self, res):
        self.mThread.setResolution(res)
        
    def quit(self):
        #print "serial SutterMP285 requesting thread exit.."
        self.mThread.stop(block=True)

    def posChanged(self, data): 
        with self.lock:
            rel = [0] * len(self.pos)
            if 'rel' in data:
                rel[:len(data['rel'])] = data['rel']
            else:
                rel[:len(data['abs'])] = [data['abs'][i] - self.pos[i] for i in range(len(data['abs']))]
            self.pos[:len(data['abs'])] = data['abs']
        self.sigPositionChanged.emit({'rel': rel, 'abs': self.pos[:]})
        
        tr = pg.SRTTransform3D()
        tr.translate(*self.pos)
        self.setDeviceTransform(tr) ## this informs rigidly-connected devices that they have moved

    def getPosition(self, refresh=False):
        """
        Return the position of the stage.
        If refresh==False, the last known position is returned. Otherwise, the current position is requested from the controller.
        """
        if refresh:
            with self.driverLock:
                pos = np.array(self.mp285.getPos()) * self.scale
        with self.lock:
            if refresh and not np.all(pos == self.pos):
                self.posChanged({'abs': pos})
            return self.pos[:]

    def getState(self):
        with self.lock:
            return (self.pos[:],)

    def deviceInterface(self, win):
        return SMP285Interface(self, win)

    def moveBy(self, pos, speed=400, fine=True, block=True, timeout = 10.):
        """Move by the specified amounts. 
        pos must be a sequence (dx, dy, dz) with values in meters.
        speed will be set before moving unless speed=None
        """
        with self.driverLock:
            if speed is not None:
                self.mp285.setSpeed(speed, fine)
            self.mp285.moveBy(pos, block=block, timeout = timeout)
        self.getPosition(refresh=True)

    def moveTo(self, pos, speed=400, fine=True, block=True, timeout = 10.):
        """Move by the absolute position. 
        pos must be a sequence (dx, dy, dz) with values in meters.
        speed will be set before moving unless speed=None
        """
        with self.driverLock:
            if speed is not None:
                self.mp285.setSpeed(speed, fine)
            self.mp285.setPos(pos, block=block, timeout = timeout)
        self.getPosition(refresh=True)


class SMP285Interface(Qt.QWidget):
    def __init__(self, dev, win):
        Qt.QWidget.__init__(self)
        self.ui = devTemplate.Ui_Form()
        self.ui.setupUi(self)
        
        self.win = win
        self.dev = dev
        #Qt.QObject.connect(self.dev, Qt.SIGNAL('positionChanged'), self.update)
        self.dev.sigPositionChanged.connect(self.update)
        self.update()
        
        self.limitBtns = [
            [self.ui.xMinBtn, self.ui.xMaxBtn],
            [self.ui.yMinBtn, self.ui.yMaxBtn],
            [self.ui.zMinBtn, self.ui.zMaxBtn],
        ]
        self.limitSpins = [
            [self.ui.xMinSpin, self.ui.xMaxSpin],
            [self.ui.yMinSpin, self.ui.yMaxSpin],
            [self.ui.zMinSpin, self.ui.zMaxSpin],
        ]
        self.limitChecks = [
            [self.ui.xMinCheck, self.ui.xMaxCheck],
            [self.ui.yMinCheck, self.ui.yMaxCheck],
            [self.ui.zMinCheck, self.ui.zMaxCheck],
        ]
        def mkLimitCallback(fn, *args):
            return lambda: fn(*args)
        for axis in range(3):
            for limit in range(2):
                self.limitBtns[axis][limit].clicked.connect(mkLimitCallback(self.getLimit, axis, limit))
                self.limitSpins[axis][limit].valueChanged.connect(mkLimitCallback(self.updateLimit, axis, limit))
                self.limitChecks[axis][limit].toggled.connect(mkLimitCallback(self.enableLimit, axis, limit))
                pos, enabled = self.dev.limits[axis][limit]
                #self.limitLabels[axis][limit].setText(pg.siFormat(pos, suffix='m', precision=5))
                self.limitSpins[axis][limit].setValue(pos)
                self.limitChecks[axis][limit].setChecked(enabled)
        
        self.ui.maxSpeedSpin.setOpts(value=self.dev.maxSpeed, siPrefix=True, dec=True, suffix='m/s', step=0.1, minStep=1e-6)
        self.ui.maxSpeedSpin.valueChanged.connect(self.maxSpeedChanged)
        self.ui.updatePosBtn.clicked.connect(self.updateClicked)
        self.ui.joyBtn.sigStateChanged.connect(self.joyStateChanged)
        self.ui.coarseStepRadio.toggled.connect(self.resolutionChanged)
        self.ui.fineStepRadio.toggled.connect(self.resolutionChanged)

        
    def getLimit(self, axis, limit):
        ## called when the limit buttons are pressed in the GUI - gets limit and stores in the spin box
        pos = self.dev.getPosition()[axis]
        self.limitSpins[axis][limit].setValue(pos)
        self.updateLimit(axis, limit)
        #self.dev.setLimit(axis, limit, val=pos)
        #self.limitChecks[axis][limit].setChecked(True)

    def updateLimit(self, axis, limit):
        ## called when the limit buttons are pressed in the GUI
        pos = self.limitSpins[axis][limit].value() 
        #self.dev.getPosition()[axis]
        self.dev.setLimit(axis, limit, val=pos)
        self.limitChecks[axis][limit].setChecked(True)
        

    def enableLimit(self, axis, limit):
        ## called when the limit checks are toggled in the GUI
        en = self.limitChecks[axis][limit].isChecked()
        self.dev.setLimit(axis, limit, enabled=en)
        
        
    def maxSpeedChanged(self):
        self.dev.setMaxSpeed(self.ui.maxSpeedSpin.value())
        
    def resolutionChanged(self):
        self.dev.setResolution("coarse" if self.ui.coarseStepRadio.isChecked() else "fine")
        
    def update(self):
        pos = self.dev.getPosition()
        #for i in [0,1,2]:
            #if pos[i] < self.limit

        text = [pg.siFormat(x, suffix='m', precision=5) for x in pos]
        self.ui.xPosLabel.setText(text[0])
        self.ui.yPosLabel.setText(text[1])
        self.ui.zPosLabel.setText(text[2])

    def updateClicked(self):
        # self.dev.mThread.updatePos()
        self.dev.getPosition(refresh=True)
        
    def joyStateChanged(self, btn, v):
        ms = self.ui.maxSpeedSpin.value()
        self.dev.mThread.setVelocity([v[0]*ms, v[1]*ms, 0])

class TimeoutError(Exception):
    pass
        
class SutterMP285Thread(Thread):

    sigPositionChanged = Qt.Signal(object)
    sigError = Qt.Signal(object)

    def __init__(self, dev, driver, driverLock, scale, limits, maxSpd):
        Thread.__init__(self)
        self.lock = Mutex(Qt.QMutex.Recursive)
        self.scale = scale
        self.mp285 = driver
        self.driverLock = driverLock
        #self.monitor = True
        self.update = False
        self.resolution = 'fine'
        self.dev = dev
        #self.port = port
        #self.pos = [0, 0, 0]
        #self.baud = baud
        self.velocity = [0,0,0]
        self.limits = deepcopy(limits)
        self.limitChanged = False
        self.maxSpeed = maxSpd
        
        #self.posxyz = [ 0, 0, 0]
        
    def setResolution(self, res):
        with self.lock:
            self.resolution = res
        
    def setLimits(self, limits):
        with self.lock:
            self.limits = deepcopy(limits)
            self.limitChanged = True
            
    def setMaxSpeed(self, s):
        with self.lock:
            self.maxSpeed = s
            
    #def setMonitor(self, mon):
        #with self.lock:
            #self.monitor = mon
    def updatePos(self):
        with self.lock:
            self.update = True
        
    def setVelocity(self, v):
        with self.lock:
            self.velocity = v
        
    def run(self):
        self.stopThread = False
        #self.sp = serial.Serial(int(self.port), baudrate=self.baud, bytesize=serial.EIGHTBITS)
        #time.sleep(3) ## Wait a few seconds for the mouse to say hello
        ## clear buffer before starting
        #if self.sp.inWaiting() > 0:
            #print "Discarding %d bytes" % self.sp.inWaiting()
            #self.sp.read(self.sp.inWaiting())
        #import wingdbstub
        print("  Starting MP285 thread: 0x%x" % int(Qt.QThread.currentThreadId()))
        #import sip
        #print "    also known as 0x%x" % sip.unwrapinstance(self)
        velocity = np.array([0,0,0])
        pos = [0,0,0]
        
        try:
            self.getImmediatePos()
            monitor = True
        except:
            debug.printExc("Sutter MP285: Cannot determine position:")
            monitor = False
        
        while True:
            try:
                ## Lock and copy state to local variables
                with self.lock:
                    update = self.update
                    self.update = False
                    limits = deepcopy(self.limits)
                    maxSpeed = self.maxSpeed
                    newVelocity = np.array(self.velocity[:])
                    resolution = self.resolution
                    limitChanged = self.limitChanged
                    self.limitChanged = False
                    
                ## if limits have changed, inform the device
                if monitor and limitChanged:   ## monitor is only true if this is a customized device with limit checking
                    self.sendLimits()
                
                ## If requested velocity is different from the current velocity, handle that.
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
                    #print "stop.."
                    self.stopMove()
                    #print "stop done."
                    
                    #print "getpos..."
                    pos1 = self.readPosition()
                    if pos1 is not None:
                        
                        if speed > 0:
                            #print "   set new velocity"
                            self.writeVelocity(speed, nv, limits=limits, pos=pos1, resolution=resolution)
                            #print "   done"
                            
                        ## report current position
                        
                            
                        velocity = newVelocity
                    #print "done"
                
                ## If velocity is 0, we can do some position checks
                if np.all(velocity == 0):
                    newPos = None
                    if update:
                        newPos = self.readPosition()
                    elif monitor:
                        newPos = self.getImmediatePos()
    
                    if newPos is not None: ## If position has changed, emit a signal.
        
                        change = [newPos[i] - pos[i] for i in range(len(newPos))]
                        pos = newPos
        
                        if any(change):
                            #self.emit(Qt.SIGNAL('positionChanged'), {'rel': change, 'abs': self.pos})
                            self.sigPositionChanged.emit({'rel': change, 'abs': pos})
                else:
                    ## moving; make a guess about the current position
                    pass
            except:
                pass
                debug.printExc("Error in MP285 thread:")
                
            self.lock.lock()
            if self.stopThread:
                self.lock.unlock()
                break
            self.lock.unlock()
            time.sleep(0.02)


        self.mp285.close()

    def stop(self, block=False):
        #print "  stop: locking"
        with self.lock:
            #print "  stop: requesting stop"
            self.stopThread = True
        if block:
            #print "  stop: waiting"
            if not self.wait(10000):
                raise Exception("Timed out while waiting for thread exit!")
        #print "  stop: done"


    def readPosition(self):
        try:
            with self.driverLock:
                pos = np.array(self.mp285.getPos())
            return pos*self.scale
        except TimeoutError:
            self.sigError.emit("Read timeout--press reset button on MP285.")
            return None
        except:
            self.sigError.emit("Read error--see console.")
            debug.printExc("Error getting packet:")
            return None
        
    def writeVelocity(self, spd, v, limits, pos, resolution):
        if not self.checkLimits(pos, limits):
            return
        
        ## check all limits for closest stop point
        pt = self.vectorLimit(pos, v, limits)
        if pt is None:
            return
        
        ## set speed
        #print "      SPD:", spd, "POS:", pt
        self._setSpd(spd, fineStep=(resolution=='fine'))
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
            #print 'pos, limits', pos[i]
            #print limits[i]
            #print limits[i][0]
            #print limits[i][1]
            if pos[i] < limits[i][0] or pos[i] > limits[i][1]:
                return False
        return True
        
    def sendLimits(self):
        limits = []
        for ax in [0,1,2]:
            for lim in [1,0]:
                pos, en = self.limits[ax][lim]
                limits.append(pos/self.scale[ax] if en else None)
        with self.driverLock:
            self.mp285.setLimits(limits)
        
    def _setPos(self, pos, block=True):
        pos = np.array(pos) / self.scale
        with self.driverLock:
            self.mp285.setPos(pos, block=block)
    
    def stopMove(self):
        with self.driverLock:
            self.mp285.stop()
            
    def _setSpd(self, v, fineStep=True):
        ## This should be done with a calibrated speed table instead.
        v = int(v*1e6)
        with self.driverLock:
            self.mp285.setSpeed(v, fineStep)
            
        
    def getImmediatePos(self):
        with self.driverLock:
            pos = np.array(self.mp285.getImmediatePos())
        return pos*self.scale
            
            
