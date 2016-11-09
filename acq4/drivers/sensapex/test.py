import os, sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from sensapex import SensapexDevice, UMP, UMPError
import user

devids = UMP.get_ump().list_devices()
devs = {i:SensapexDevice(i) for i in devids}

print "Found device IDs:", devids

def print_pos():
    line = ""
    for i in devids:
        dev = devs[i]
        try:
            pos = str(dev.get_pos())
        except Exception as err:
            pos = str(err.args[0])
        pos = pos + " " * (30 - len(pos))
        line += "%d:  %s" % (i, pos)
    print line

import time
for i in range(10):
    print_pos()
    time.sleep(0.05)

print ""


