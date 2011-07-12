# -*- coding: utf-8 -*-
from __future__ import with_statement
from lib.devices.Device import *
import serial, struct
from Mutex import Mutex, MutexLocker
from debug import *
#import pdb

class SutterMP285(Device):

    sigPositionChanged = QtCore.Signal(object)

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.port = config['port']
        self.scale = config['scale']
        self.baud = config.get('baud', 9600)
        self.mThread = SutterMP285Thread(self, self.baud)
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

            self.pos[:len(data['abs'])] = [data['abs'][i] * self.scale for i in range(len(data))]
            rel = [0] * len(self.pos)
            rel[:len(data['rel'])] = [data['rel'][i] * self.scale for i in range(len(data))]
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

class SMP285Interface(QtGui.QLabel):
    def __init__(self, dev, win):
        QtGui.QWidget.__init__(self)
        self.win = win
        self.dev = dev
        #QtCore.QObject.connect(self.dev, QtCore.SIGNAL('positionChanged'), self.update)
        self.dev.sigPositionChanged.connect(self.update)
        self.update()

    def update(self):
        pos = self.dev.getState()[0]

        self.setText(u"%0.4f, %0.4f" % (pos[0], pos[1]))



class SutterMP285Thread(QtCore.QThread):

    sigPositionChanged = QtCore.Signal(object)

    def __init__(self, dev, baud):
        QtCore.QThread.__init__(self)
        self.lock = Mutex(QtCore.QMutex.Recursive)
        self.dev = dev
        self.port = self.dev.port
        self.pos = [0, 0, 0]
        self.baud = baud
        self.velocity = [0,0]
        #self.posxyz = [ 0, 0, 0]

    def setVelocity(self, x, y):
        pass
        
    def run(self):
        self.stopThread = False
        self.sp = serial.Serial(int(self.port), baudrate=self.baud, bytesize=serial.EIGHTBITS)
        #time.sleep(3) ## Wait a few seconds for the mouse to say hello
        ## clear buffer before starting
        if self.sp.inWaiting() > 0:
            #print "Discarding %d bytes" % self.sp.inWaiting()
            self.sp.read(self.sp.inWaiting())

        while True:
            try:
                newPos = self.readPosition()
            except:
                printExc("Error getting packet:")
                print "MP285: timeout (press reset button?)"
                newPos = None

            if newPos is not None:

                change = [newPos[i] - self.pos[i] for i in range(len(newPos))]
                self.pos = newPos

                if any(change):
                    #self.emit(QtCore.SIGNAL('positionChanged'), {'rel': change, 'abs': self.pos})
                    self.sigPositionChanged.emit({'rel': change, 'abs': self.pos})


            self.lock.lock()
            if self.stopThread:
                self.lock.unlock()
                break
            self.lock.unlock()
            time.sleep(1)


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
        sp = self.sp

        ## be absolutely sure the buffer is empty
        d = self.read()
        #time.sleep(0.1)
        #d += self.read()
        if len(d) > 0:
            print "Sutter MP285: Warning: tossed data ", repr(d)

        ## request position
        sp.write('c\r')

        packet = ''
        c = 0.0
        while True:
            if c > 5.0:
                raise Exception("Sutter MP285: Timed out waiting for packet. Data so far: %s", repr(packet))
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
        x = packet[-13:-9]
        y = packet[-9:-5]
        #print repr(x), repr(y)
        return struct.unpack('i4', x)[0], struct.unpack('i4', y)[0]

    def read(self):
        n = self.sp.inWaiting()
        if n > 0:
            #print "-- read %d bytes" % n
            return self.sp.read(n)

        return ''
    
    def setPos(x, y):
        cmd = 'm' + struct.pack('3l', x, y, 0) + '\r'
        self.sp.write(cmd)
        while True:
            s = read()
            if len(s) > 0:
                if s != '\r':
                    print "SutterMP285 Error:", s
                #print "return:", repr(s)
                break
    
            
    def setSpd(v):  ## mm/s
        if v > 2**14:
            v = 2**14
        cmd = 'V' + struct.pack('H', v) + '\r'
        self.sp.write(cmd)
        while True:
            s = self.read()
            if len(s) > 0:
                if s != '\r':
                    print "SutterMP285 Error:", s
                #print "return:", repr(s)
                break
        
    def stat():
        global sp
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
