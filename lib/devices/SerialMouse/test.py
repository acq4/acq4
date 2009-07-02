import serial
sp = serial.Serial(3, baudrate=1200, bytesize=serial.SEVENBITS)
print "Opened", sp.portstr

#def itoa(x, base=10):
   #isNegative = x < 0
   #if isNegative:
      #x = -x
   #digits = []
   #while x > 0:
      #x, lastDigit = divmod(x, base)
      #digits.append('0123456789abcdefghijklmnopqrstuvwxyz'[lastDigit])
   #if isNegative:
      #digits.append('-')
   #digits.reverse()
   #return ''.join(digits) 

#def bin(x):
    #return itoa(x, 2).zfill(8)

## convert int to signed int
def sint(x):
    return ((x+128)%256)-128

def readPacket(sp):
    d = sp.read(3)
    #print "%s %s %s" % (bin(ord(d[0])), bin(ord(d[1])), bin(ord(d[2])))
    xh = (ord(d[0]) & 3) << 6
    yh = (ord(d[0]) & 12) << 4
    xl = (ord(d[1]) & 63)
    yl = (ord(d[2]) & 63)
    #print "%s %s %s %s" % (bin(xh), bin(xl), bin(yh), bin(yl))
    return (sint(xl | xh), sint(yl | yh))

for i in range(100):
    print readPacket(sp)
