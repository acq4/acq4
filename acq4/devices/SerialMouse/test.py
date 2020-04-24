# -*- coding: utf-8 -*-
from __future__ import print_function
import serial
sp = serial.Serial(3, baudrate=1200, bytesize=serial.SEVENBITS)
print("Opened", sp.portstr)

## convert byte to signed byte
def sint(x):
    return ((x+128)%256)-128

def readPacket(sp):
    d = sp.read(3)
    print("%x %x %x" % (ord(d[0]), ord(d[1]), ord(d[2])))
    xh = (ord(d[0]) & 3) << 6
    yh = (ord(d[0]) & 12) << 4
    xl = (ord(d[1]) & 63)
    yl = (ord(d[2]) & 63)
    #print "%s %s %s %s" % (bin(xh), bin(xl), bin(yh), bin(yl))
    return (sint(xl | xh), sint(yl | yh))

while True:
    print(readPacket(sp))
