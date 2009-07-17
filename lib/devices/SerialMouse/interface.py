# -*- coding: utf-8 -*-
from lib.devices.Device import *
import serial
#import pdb

class SerialMouse(Device):
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.lock = QtCore.QMutex(QtCore.QMutex.Recursive)
        self.port = config['port']
        self.scale = config['scale']
        self.mThread = MouseThread(self)
        self.pos = [0, 0]
        self.buttons = [0, 0]
        QtCore.QObject.connect(self.mThread, QtCore.SIGNAL('positionChanged'), self.posChanged)
        QtCore.QObject.connect(self.mThread, QtCore.SIGNAL('buttonChanged'), self.btnChanged)
        self.mThread.start()
        
    def quit(self):
        #print "serial mouse requesting thread exit.."
        self.mThread.stop(block=True)
        
    def posChanged(self, data):
        #QtCore.pyqtRemoveInputHook()
        #pdb.set_trace()
        #print "Mouse: posChanged"
        l = QtCore.QMutexLocker(self.lock)
        #print "Mouse: posChanged locked"
        self.pos = [data['abs'][0] * self.scale, data['abs'][1] * self.scale]
        rel = [data['rel'][0] * self.scale, data['rel'][1] * self.scale]
        #print "Mouse: posChanged emit.."
        self.emit(QtCore.SIGNAL('positionChanged'), {'rel': rel, 'abs': self.pos[:]})
        #print "Mouse: posChanged done"
        
    def btnChanged(self, btns):
        #print "Mouse: btnChanged"
        l = QtCore.QMutexLocker(self.lock)
        change = {}
        for i in [0, 1]:
            if btns[i] != self.buttons[i]:
                change[i] = btns[i]
                self.buttons[i] = btns[i]
        self.emit(QtCore.SIGNAL('switchChanged'), change)
        #print "Mouse: btnChanged done"
        
    def getPosition(self):
        l = QtCore.QMutexLocker(self.lock)
        return self.pos[:]
        
    def getSwitches(self):
        l = QtCore.QMutexLocker(self.lock)
        return self.buttons[:]

    def getSwitch(self, swid):
        l = QtCore.QMutexLocker(self.lock)
        return self.buttons[swid]
        

    def getState(self):
        l = QtCore.QMutexLocker(self.lock)
        return (self.pos[:], self.buttons[:])
        
    def deviceInterface(self):
        return SMInterface(self)
    
class SMInterface(QtGui.QLabel):
    def __init__(self, dev):
        QtGui.QWidget.__init__(self)
        self.dev = dev
        QtCore.QObject.connect(self.dev, QtCore.SIGNAL('positionChanged'), self.update)
        QtCore.QObject.connect(self.dev, QtCore.SIGNAL('switchChanged'), self.update)
        self.update()
        
    def update(self):
        (pos, btn) = self.dev.getState()
        
        self.setText(u"%0.4f, %0.4f  Btn0: %d  Btn1: %d" % (pos[0], pos[1], btn[0], btn[1]))
        
    
    
class MouseThread(QtCore.QThread):
    def __init__(self, dev):
        QtCore.QThread.__init__(self)
        self.lock = QtCore.QMutex()
        self.dev = dev
        self.port = self.dev.port
        self.pos = [0, 0]
        self.btns = [0, 0]
        
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
                    print "WARNING: possible corrupt data from serial mouse."
                    self.sp.read(bytesWaiting)
                    
                elif self.sp.inWaiting() >= 3: ## at least one packet is available.
                    while self.sp.inWaiting() >= 3:
                        (dx, dy, b0, b1) = self.readPacket()
                        tdx += dx
                        tdy += dy
                    self.pos = [self.pos[0] + tdx, self.pos[1] + tdy]
                    if tdx != 0 or tdy != 0:
                        self.emit(QtCore.SIGNAL('positionChanged'), {'rel': (tdx, tdy), 'abs': self.pos})
                    if b0 != self.btns[0] or b1 != self.btns[1]:
                        self.btns = [b0, b1]
                        self.emit(QtCore.SIGNAL('buttonChanged'), self.btns)
                        
            self.lock.lock()
            if self.stopThread:
                self.lock.unlock()
                break
            self.lock.unlock()
            time.sleep(100e-3)
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
        l = QtCore.QMutexLocker(self.lock)
        #print "  stop: requesting stop"
        self.stopThread = True
        l.unlock()
        if block:
            #print "  stop: waiting"
            self.wait()
        #print "  stop: done"
            
        