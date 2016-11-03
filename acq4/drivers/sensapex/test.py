from sensapex import UMP
import user

ump = UMP()
ump.select_dev(1)
print ump.get_pos()
