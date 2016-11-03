import sys
from sensapex import UMP
import user

ump = UMP.get_ump()

dev = int(sys.argv[1])
print ump.get_pos(dev)
