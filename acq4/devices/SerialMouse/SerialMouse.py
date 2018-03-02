# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import with_statement
from acq4.devices.Device import *
from acq4.pyqtgraph.SignalProxy import SignalProxy
import serial, os, time
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
#import pdb

class SerialMouse(Device):
    
    sigSwitchChanged = Qt.Signal(object, object)
    sigPositionChanged = Qt.Signal(object)
    
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.config = config
        self.lock = Mutex(Qt.QMutex.Recursive)
        self.port = config['port']
        self.scale = config['scale']
        self.pos = [0, 0]
        self.buttons = [0, 0]
        
        ## Reload the last known state of the mouse if it was last modified recently enough 
        self.stateFile = os.path.join('devices', self.name + "_last_state.cfg")
        state = dm.readConfigFile(self.stateFile)
        if state != {} and time.time() - state.get('time', 0) < 36000:
            self.pos = state['pos']
            self.buttons = state['buttons']
        
        self.mThread = MouseThread(self, {'pos': self.pos[:], 'btns': self.buttons[:]})
        self.mThread.sigPositionChanged.connect(self.posChanged)
        self.mThread.sigButtonChanged.connect(self.btnChanged)
        #self.proxy1 = proxyConnect(None, self.sigPositionChanged, self.storeState, 3.0) ## wait 3 seconds before writing changes 
        #self.proxy2 = proxyConnect(None, self.sigSwitchChanged, self.storeState, 3.0) 
        self.proxy1 = SignalProxy(self.sigPositionChanged, slot=self.storeState, delay=3.0)
        self.proxy2 = SignalProxy(self.sigSwitchChanged, slot=self.storeState, delay=3.0)
        
        self.mThread.start()
        
    def quit(self):
        #print "serial mouse requesting thread exit.."
        self.mThread.stop(block=True)
        
    def posChanged(self, data):
        #Qt.pyqtRemoveInputHook()
        #pdb.set_trace()
        #print "Mouse: posChanged"
        with self.lock:
            #print "Mouse: posChanged locked"
            self.pos = [data['abs'][0] * self.scale, data['abs'][1] * self.scale]
            rel = [data['rel'][0] * self.scale, data['rel'][1] * self.scale]
            ab = self.pos[:]
        #print "Mouse: posChanged emit.."
        #self.emit(Qt.SIGNAL('positionChanged'), {'rel': rel, 'abs': ab})
        self.sigPositionChanged.emit({'rel': rel, 'abs': ab})
        #print "Mouse: posChanged done"

    def storeState(self, *args):
        self.dm.writeConfigFile({'pos': self.pos, 'buttons': self.buttons, 'time': time.time()}, self.stateFile)

    def btnChanged(self, btns):
        #print "Mouse: btnChanged"
        with self.lock:
            change = {}
            for i in [0, 1]:
                if btns[i] != self.buttons[i]:
                    change[i] = btns[i]
                    self.buttons[i] = btns[i]
        #self.emit(Qt.SIGNAL('switchChanged'), change)
        self.sigSwitchChanged.emit(self, change)
        #print "Mouse: btnChanged done"
        
    def getPosition(self):
        with self.lock:
            return self.pos[:]
        
    def getSwitches(self):
        with self.lock:
            return self.buttons[:]

    def getSwitch(self, swid):
        with self.lock:
            return self.buttons[swid]
        

    def getState(self):
        with self.lock:
            return (self.pos[:], self.buttons[:])
        
    def deviceInterface(self, win):
        return SMInterface(self, win)
    
class SMInterface(Qt.QLabel):
    def __init__(self, dev, win):
        Qt.QLabel.__init__(self)
        self.win = win
        self.dev = dev
        #Qt.QObject.connect(self.dev, Qt.SIGNAL('positionChanged'), self.update)
        self.dev.sigPositionChanged.connect(self.update)
        #Qt.QObject.connect(self.dev, Qt.SIGNAL('switchChanged'), self.update)
        self.dev.sigSwitchChanged.connect(self.update)
        self.update()
        
    def update(self):
        (pos, btn) = self.dev.getState()
        
        self.setText(u"%0.4f, %0.4f  Btn0: %d  Btn1: %d" % (pos[0], pos[1], btn[0], btn[1]))
        
    
    
class MouseThread(Thread):
    
    sigButtonChanged = Qt.Signal(object)
    sigPositionChanged = Qt.Signal(object)
    
    def __init__(self, dev, startState=None):
        Thread.__init__(self)
        self.lock = Mutex(Qt.QMutex.Recursive)
        self.dev = dev
        self.port = self.dev.port
        if startState is None:
            self.pos = [0, 0]
            self.btns = [0, 0]
        else:
            self.pos = startState['pos']
            self.btns = startState['btns']
        
    def run(self):
        self.stopThread = False
        self.sp = serial.Serial(int(self.port), baudrate=1200, bytesize=serial.SEVENBITS)
        time.sleep(3) ## Wait a few seconds for the mouse to say hello
        if self.sp.inWaiting() > 0:
            #print "Discarding %d bytes" % self.sp.inWaiting()
            self.sp.read(self.sp.inWaiting())
        while True:
            tdx = tdy = 0
            if self.sp.inWaiting() > 0:
                if self.sp.inWaiting() < 3:  ## could be in the middle of a packet, wait for more bytes to arrive
                    time.sleep(100e-3)
                    
                bytesWaiting = self.sp.inWaiting()
                if bytesWaiting < 3:  ## More bytes have not arrived, probably there is data corruption!
                    print("WARNING: possible corrupt data from serial mouse.")
                    self.sp.read(bytesWaiting)
                    
                elif self.sp.inWaiting() >= 3: ## at least one packet is available.
                    while self.sp.inWaiting() >= 3:
                        (dx, dy, b0, b1) = self.readPacket()
                        tdx += dx
                        tdy += dy
                    self.pos = [self.pos[0] + tdx, self.pos[1] + tdy]
                    if tdx != 0 or tdy != 0:
                        #self.emit(Qt.SIGNAL('positionChanged'), {'rel': (tdx, tdy), 'abs': self.pos})
                        self.sigPositionChanged.emit({'rel': (tdx, tdy), 'abs': self.pos})
                    if b0 != self.btns[0] or b1 != self.btns[1]:
                        self.btns = [b0, b1]
                        #self.emit(Qt.SIGNAL('buttonChanged'), self.btns)
                        self.sigButtonChanged.emit(self.btns)
                        
            self.lock.lock()
            if self.stopThread:
                self.lock.unlock()
                break
            self.lock.unlock()
            time.sleep(1e-3)
        self.sp.close()
            
    ## convert byte to signed byte
    @staticmethod
    def sint(x):
        return ((x+128)%256)-128

    def readPacket(self):
        d = self.sp.read(3)
        #print "%s %s %s" % (bin(ord(d[0])), bin(ord(d[1])), bin(ord(d[2])))
        b0 = (ord(d[0]) & 32) >> 5
        b1 = (ord(d[0]) & 16) >> 4
        xh = (ord(d[0]) & 3) << 6
        yh = (ord(d[0]) & 12) << 4
        xl = (ord(d[1]) & 63)
        yl = (ord(d[2]) & 63)
        
        #print "%s %s %s %s" % (bin(xh), bin(xl), bin(yh), bin(yl))
        return (MouseThread.sint(xl | xh), MouseThread.sint(yl | yh), b0, b1)
    
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
            
        