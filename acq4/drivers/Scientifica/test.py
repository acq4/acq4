import sys, os, time
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from acq4.drivers.Scientifica import Scientifica

if len(sys.argv) < 2:
	print("Usage: test.py com4")
	sys.exit(-1)

ps = Scientifica(sys.argv[1])

print("Device type:  %s  Description:  %s" % (ps.getType(), ps.getDescription()))
print("Firmware version: %r" % ps.getFirmwareVersion())
print("Position: %r" % ps.getPos())
print("Max speed: %r um/sec" % ps.getSpeed())
print("Min speed: %r um/sec" % (ps.getParam('minSpeed') / (2. * ps.getAxisScale(0))))
print("Acceleration: %r um^2/sec" % (ps.getParam('maxSpeed') * 250. / ps.getAxisScale(0)))

# pos1 = ps.getPos()
# pos2 = [None, None, pos1[2]]
# pos2[2] += 1000
# print("Move %s => %s" % (pos1, pos2))
# ps.moveTo(pos2, speed=300)
# c = 0
# while ps.isMoving():
#     pos = ps.getPos()
#     print("time: %s position: %s" % (time.time(), pos))
#     time.sleep(0.01)
#     c += 1

# ps.moveTo(pos1, speed=30000)
# while ps.isMoving():
#     pass


# print("Move %s => %s" % (pos1, pos2))
# ps.moveTo(pos2, speed=300)
# c2 = 0
# while ps.isMoving():
#     pos = ps.getPos()
#     print("time: %s position: %s" % (time.time(), pos))
#     if c2 > c//2:
#         print("Stopping early..")
#         ps.stop()
#     time.sleep(0.01)
#     c2 += 1

# time.sleep(0.5)
# pos = ps.getPos()
# print("time: %s position: %s" % (time.time(), pos))

