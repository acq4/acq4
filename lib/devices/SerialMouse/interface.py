# -*- coding: utf-8 -*-
from lib.devices.Device import *
import serial

class SerialMouse(Device):
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.port = config['port']
        self.scale = config['scale']
        self.mThread = MouseThread(self)
        self.pos = [0, 0]
        QtCore.QObject.connect(self.mThread, QtCore.SIGNAL('positionChanged'), self.posChanged)
        self.mThread.start()
        
    def quit(self):
        self.mThread.stop(block=True)
        
    def posChanged(self, data):
        self.pos = [data['abs'][0] * self.scale, data['abs'][1] * self.scale]
        rel = [data['rel'][0] * self.scale, data['rel'][1] * self.scale]
        self.emit(QtCore.SIGNAL('positionChanged'), {'rel': rel, 'abs': self.pos[:]})
        
    def getPosition(self):
        return self.pos[:]
        
    
    
    
class MouseThread(QtCore.QThread):
    def __init__(self, dev):
        QtCore.QThread.__init__(self)
        self.lock = QtCore.QMutex()
        self.dev = dev
        self.port = self.dev.port
        self.pos = [0, 0]
        
    def run(self):
        self.stopThread = False
        self.sp = serial.Serial(int(self.port), baudrate=1200, bytesize=serial.SEVENBITS)
        while True:
            if self.sp.inWaiting() >= 3:
                (dx, dy) = self.readPacket()
                self.pos = [self.pos[0] + dx, self.pos[1] + dy]
                self.emit(QtCore.SIGNAL('positionChanged'), {'rel': (dx, dy), 'abs': self.pos})
            self.lock.lock()
            if self.stopThread:
                self.lock.unlock()
                break
            self.lock.unlock()
            time.sleep(100)
            
    ## convert byte to signed byte
    @staticmethod
    def sint(x):
        return ((x+128)%256)-128

    def readPacket(self):
        d = self.sp.read(3)
        #print "%s %s %s" % (bin(ord(d[0])), bin(ord(d[1])), bin(ord(d[2])))
        xh = (ord(d[0]) & 3) << 6
        yh = (ord(d[0]) & 12) << 4
        xl = (ord(d[1]) & 63)
        yl = (ord(d[2]) & 63)
        
        #print "%s %s %s %s" % (bin(xh), bin(xl), bin(yh), bin(yl))
        return (MouseThread.sint(xl | xh), MouseThread.sint(yl | yh))
    
    def stop(self, block=False):
        l = QtCore.QMutexLocker(self.lock)
        self.stopThread = True
        l.unlock()
        if block:
          self.wait()
        