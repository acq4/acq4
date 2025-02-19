import sys
from acq4.drivers.Scientifica import Scientifica


all_devs = Scientifica.enumerateDevices()

if len(sys.argv) == 2:
    dev_name = sys.argv[1]
else:
    print("Usage: python -m acq4.drivers.Scientifica <device_name>")
    print("  available devices:", list(all_devs.keys()))
    sys.exit(-1)


dev = Scientifica(name=dev_name)
print(dev.getPos())

def change_cb(last_pos, new_pos):
    print("Moved: ", new_pos)

dev.setPositionCallback(change_cb)


