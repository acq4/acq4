import os, sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from sensapex import SensapexDevice
import user

if len(sys.argv) != 2:
    print "USAGE: python test.py <device_id>"
    sys.exit(-1)
devid = int(sys.argv[1])
dev = SensapexDevice(devid)

print dev.get_pos()
