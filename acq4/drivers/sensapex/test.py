import os, sys, time
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

print_pos()

# p = devs[1].get_pos()
# p2 = p[:]
# p2[0] += 1000000
# p2[1] += 1000000
# p2[2] += 1000000
# pts = [p, p2]

# for i in range(2):
#     devs[1].goto_pos(pts[1], 1000)
#     pts = pts[::-1]

#     while devs[1].is_busy():
#         print_pos()
#         time.sleep(0.2)

#     print "--done--"

# print ""



