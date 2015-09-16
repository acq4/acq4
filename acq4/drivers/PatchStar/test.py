import sys, os, time
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from acq4.drivers.PatchStar import PatchStar

if len(sys.argv) < 2:
	print("Usage: test.py com4")
	sys.exit(-1)

ps = PatchStar(sys.argv[1])

print("Firmware version: %s" % ps.getFirmwareVersion())
print("Max speed: %s um/sec" % ps.getSpeed())
pos = ps.getPos()
print("Position: %s" % pos)
ps.moveTo([None, None, pos[2] + 100000])
while ps.isMoving():
	pos = ps.getPos()
	print("Position: %s" % pos)
	time.sleep(0.2)

ps.moveTo([None, None, pos[2] - 100000])


