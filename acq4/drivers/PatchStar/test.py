import sys, os, time
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from acq4.drivers.PatchStar import PatchStar

if len(sys.argv) < 2:
	print("Usage: test.py com4")
	sys.exit(-1)

ps = PatchStar(sys.argv[1])
ps.reset()

print("Firmware version: %s" % ps.getFirmwareVersion())
print("Max speed: %s um/sec" % ps.getSpeed())

pos1 = ps.getPos()
pos2 = [None, None, pos1[2]]
pos2[2] += 1000
print("Move %s => %s" % (pos1, pos2))
ps.moveTo(pos2, speed=300)
c = 0
while ps.isMoving():
    pos = ps.getPos()
    print("time: %s position: %s" % (time.time(), pos))
    time.sleep(0.01)
    c += 1

ps.moveTo(pos1, speed=30000)
while ps.isMoving():
    pass


print("Move %s => %s" % (pos1, pos2))
ps.moveTo(pos2, speed=300)
c2 = 0
while ps.isMoving():
    pos = ps.getPos()
    print("time: %s position: %s" % (time.time(), pos))
    if c2 > c//2:
        print("Stopping early..")
        ps.stop()
    time.sleep(0.01)
    c2 += 1

time.sleep(0.5)
pos = ps.getPos()
print("time: %s position: %s" % (time.time(), pos))

