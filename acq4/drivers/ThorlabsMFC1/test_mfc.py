import os, sys, time
path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(path)

from acq4.drivers.ThorlabsMFC1 import MFC1
import acq4.pyqtgraph as pg


if len(sys.argv) < 2:
    print "Usage:  python test.py device\n  (device may be com3, /dev/ttyACM0, etc.)"
    sys.exit(1)

m = MFC1(sys.argv[1])

m.mcm.stop_program()
m.mcm.stop()

i = 0
m.mcm.start_download(0)
#m.mcm.command('wait', 0, 0, i)
#m.mcm.rotate(100)
#m.mcm.command('wait', 0, 0, i)
#m.mcm.stop()
#m.mcm.command('wait', 0, 0, i)
m.mcm.move(1000, relative=True)
m.mcm.command('wait', 1, 0, 0)
m.mcm.move(-1000, relative=True)
m.mcm.command('wait', 1, 0, 0)


m.mcm.command('ja', 0, 0, 0)
#m.mcm.command('stop', 0, 0, 0) 
m.mcm.stop_download()

m.mcm.start_program(0)
#time.sleep(2)
#m.mcm.stop_program()
#m.mcm.stop()
