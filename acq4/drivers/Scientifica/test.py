import sys, os
from acq4.drivers.Scientifica import Scientifica

if len(sys.argv) < 2:
    print("Usage: python -i test.py com4 [9600|38400]\n       python -i test.py PatchStar1")
    os._exit(-1)

baudrate = int(sys.argv[2]) if len(sys.argv) > 2 else None
devname = sys.argv[1]
if devname.lower().startswith('com') or devname.startswith('/dev/'):
    dev = Scientifica(port=devname, baudrate=baudrate, ctrl_version=None)
else:
    dev = Scientifica(name=devname, baudrate=baudrate, ctrl_version=None)
    
print("Device type:  %s  Description:  %s" % (dev.getType(), dev.getDescription()))
print("COM port:", dev.port, " baudrate:", dev.getBaudrate())
print("Firmware version: %r" % dev.getFirmwareVersion())
print("Position: %r" % dev.getPos())
print("Max speed: %r um/sec" % dev.getSpeed())
if dev._version < 3:
    print("Min speed: %r um/sec" % (dev.getParam('minSpeed') / (2. * dev.getAxisScale(0))))
    print("Acceleration: %r um^2/sec" % (dev.getParam('accel') * 250. / dev.getAxisScale(0)))
else:
    print("Min speed: %r um/sec" % dev.getParam('minSpeed'))
    print("Acceleration: %r um^2/sec" % dev.getParam('accel'))

def pos_changed(pos):
    print("position changed:", pos)
dev.setPositionCallback(pos_changed)

print("""
----------
Move manipulator to see position updates
Examples:
    dev.getPos()
    f = dev.moveTo([x, y, z], speed=100)
    f.wait()
    dev.stop()
""")