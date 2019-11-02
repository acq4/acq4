from __future__ import print_function
import os, sys, time, argparse
from sensapex import SensapexDevice, UMP, UMPError


parser = argparse.ArgumentParser(
    description="Test for sensapex devices; prints position and status updates continuously.")
parser.add_argument('--group', type=int, default=0, help="Device group number")
args = parser.parse_args()

ump = UMP.get_ump(group=args.group)
devids = ump.list_devices()
devs = {i:SensapexDevice(i) for i in devids}

print("SDK version:", ump.sdk_version())
print("Found device IDs:", devids)

def print_pos(timeout=None):
    line = ""
    for i in devids:
        dev = devs[i]
        try:
            pos = str(dev.get_pos(timeout=timeout))
        except Exception as err:
            pos = str(err.args[0])
        pos = pos + " " * (30 - len(pos))
        line += "%d:  %s" % (i, pos)
    print(line)


t = time.time()
while True:
    t1 = time.time()
    dt = t1 - t
    t = t1
    line = "%3f" % dt
    for id in sorted(list(devs.keys())):
        line += "   %d: %s busy: %s" % (id, devs[id].get_pos(timeout=0), devs[id].is_busy())
    line += "                           \r"
    print(line, end=" ")
    sys.stdout.flush()
    time.sleep(0.01)
