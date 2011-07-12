# -*- coding: utf-8 -*-
import serial, struct, time, sys, collections
sp = serial.Serial(3, baudrate=9600, bytesize=serial.EIGHTBITS)
print "Opened", sp.portstr

## convert byte to signed byte
def sint(x):
    return ((x+128)%256)-128

def getPos():
    global sp
    ## be absolutely sure the buffer is empty
    d = read()
    #time.sleep(0.1)
    #d += read()
    if len(d) > 0:
        print "Warning: tossed data ", repr(d)
    
    ## request position
    sp.write('c\r')
    
    packet = ''
    c = 0.0
    while True:
        if c > 5.0:
            raise Exception("Timed out waiting for packet. Data so far: %s", repr(packet))
        d = read()
        packet += d
        
        if len(packet) == 13 and packet[-1] == '\r':  ## got a whole packet and nothing else is coming..
            break
        elif len(packet) > 12:
            print "Corrupt packet!"
            print "    data:", repr(packet)
        #print '.'
        time.sleep(0.1) # 10ms loop time
        c += 0.1
    #print repr(packet)
    if len(packet) != 13:
        print "  bad packet:", repr(packet)
        return
    x = packet[-13:-9]
    y = packet[-9:-5]
    #print repr(x), repr(y)
    print struct.unpack('i', x)[0], struct.unpack('i', y)[0]

def read():
    n = sp.inWaiting()
    if n > 0:
        return sp.read(n)
    return ''


def setPos(x, y):
    cmd = 'm' + struct.pack('3l', x, y, 0) + '\r'
    sp.write(cmd)
    while True:
        s = read()
        if len(s) > 0:
            print "return:", repr(s)
            break

        
def setVel(v):  ## mm/s
    if v > 2**14:
        v = 2**14
    cmd = 'V' + struct.pack('H', v) + '\r'
    sp.write(cmd)
    while True:
        s = read()
        if len(s) > 0:
            print "return:", repr(s)
            break
    
def stat():
    global sp
    sp.write('s\r')
    s = sp.read(33)
    paramNames = ['flags', 'udirx', 'udiry', 'udirz', 'roe_vari', 'uoffset', 'urange', 'pulse', 
                  'uspeed', 'indevice', 'flags2', 'jumpspd', 'highspd', 'watch_dog',
                  'step_div', 'step_mul', 'xspeed', 'version', 'res1', 'res2']
    vals = struct.unpack('4B5H2B7H2B', s[:32])
    params = collections.OrderedDict()
    for i,n in enumerate(paramNames):
        params[n] = vals[i]
    print params
    
        
#c = 0
#while True:
    #print "===============", c
    #try:
        
        #readPacket(sp)
    #except KeyboardInterrupt:
        #break
    #except:
        #sys.excepthook(*sys.exc_info())
    #c += 1



