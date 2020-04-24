
from __future__ import print_function, absolute_import
import os, sys, time, argparse
import numpy as np
import acq4.pyqtgraph as pg
from acq4.drivers.sensapex import SensapexDevice, UMP, UMPError
from six.moves import map
from six.moves import range


parser = argparse.ArgumentParser(
    description="Test for sensapex devices; perform a series of random moves while rapidly polling the device position and state.")
parser.add_argument('device', type=int, help="Device ID to test")
parser.add_argument('--group', type=int, default=0, help="Device group number")
parser.add_argument('--x', action='store_true', default=False, dest='x', help="True = Random X axis values. False = keep start position")
parser.add_argument('--y', action='store_true', default=False, dest='y', help="True = Random Y axis values. False = keep start position")
parser.add_argument('--z', action='store_true', default=False, dest='z', help="True = Random Z axis values. False = keep start position")

parser.add_argument('--speed', type=int, default=1000, help="Movement speed in um/sec")
parser.add_argument('--distance', type=int, default=10, help="Max distance to travel in um (relative to current position)")
parser.add_argument('--iter', type=int, default=10, help="Number of positions to test")
parser.add_argument('--acceleration', type=int, default=0, help="Max speed acceleration")
parser.add_argument('--high-res', action='store_true', default=False, dest='high_res', help="Use high-resolution time sampling rather than poller's schedule")
parser.add_argument('--start-pos', type=str, default=None, dest='start_pos', help="x,y,z starting position (by default, the current position is used)")
parser.add_argument('--test-pos', type=str, default=None, dest='test_pos', help="x,y,z position to test (by default, random steps from the starting position are used)")
args = parser.parse_args()

ump = UMP.get_ump(group=args.group)
time.sleep(2)
devids = ump.list_devices()
devs = {i:SensapexDevice(i) for i in devids}

print("SDK version:", ump.sdk_version())
print("Found device IDs:", devids)

dev = devs[args.device]

app = pg.mkQApp()
win = pg.GraphicsLayoutWidget()
win.show()
plots = [
    win.addPlot(labels={'left': ('x position', 'm'), 'bottom': ('time', 's')}), 
    win.addPlot(labels={'left': ('y position', 'm'), 'bottom': ('time', 's')}), 
    win.addPlot(labels={'left': ('z position', 'm'), 'bottom': ('time', 's')}),
]
plots[1].setYLink(plots[0])
plots[2].setYLink(plots[0])
plots[1].setXLink(plots[0])
plots[2].setXLink(plots[0])

win.nextRow()
errplots = [
    win.addPlot(labels={'left': ('x error', 'm'), 'bottom': ('time', 's')}), 
    win.addPlot(labels={'left': ('y error', 'm'), 'bottom': ('time', 's')}), 
    win.addPlot(labels={'left': ('z error', 'm'), 'bottom': ('time', 's')}),
]
errplots[1].setYLink(errplots[0])
errplots[2].setYLink(errplots[0])
errplots[0].setXLink(plots[0])
errplots[1].setXLink(plots[0])
errplots[2].setXLink(plots[0])




start = pg.ptime.time()
pos = [[], [], []]
tgt = [[], [], []]
err = [[], [], []]
bus = []
mov = []
times = []

lastupdate = pg.ptime.time()

def update(update_error=False):
    global lastupdate
    timeout = -1 if args.high_res else 0
    p = dev.get_pos(timeout=timeout)
    s = dev.is_busy()
    m = not move_req.finished
    bus.append(int(s))
    mov.append(int(m))
    now = pg.ptime.time() - start
    times.append(now)
    for i in range(3):
        pos[i].append((p[i] - start_pos[i]) * 1e-9)
        tgt[i].append((target[i] - start_pos[i]) * 1e-9)
        if update_error:
            err[i].append(pos[i][-1] - tgt[i][-1])
        else:
            err[i].append(np.nan)

def update_plots():
    for i in range(3):
        plots[i].clear()
        plots[i].addItem(pg.PlotCurveItem(times, bus[:-1], stepMode=True, pen=None, brush=(0, 255, 0, 40), fillLevel=0), ignoreBounds=True)
        plots[i].addItem(pg.PlotCurveItem(times, mov[:-1], stepMode=True, pen=None, brush=(255, 0, 0, 40), fillLevel=0), ignoreBounds=True)
        plots[i].plot(times, tgt[i], pen='r')
        plots[i].plot(times, pos[i], symbol='o', symbolSize=5)
        errplots[i].plot(times, err[i], clear=True, connect='finite')


if args.start_pos is None:
    start_pos = dev.get_pos()
else:
    start_pos = np.array(list(map(float, args.start_pos.split(','))))

print (start_pos)
diffs = []
errs = []
positions = []
if args.test_pos is None:
    xmoves=[]
    ymoves=[]
    zmoves=[]

    if  args.x:
        xmoves = (np.random.random(size=(args.iter, 1)) * args.distance*1000).astype(int)
    else:
        xmoves = np.zeros(args.iter)

    if  args.y:
        ymoves = (np.random.random(size=(args.iter, 1)) * args.distance*1000).astype(int)
    else:
        ymoves = np.zeros(args.iter)

    if  args.z:
        zmoves = (np.random.random(size=(args.iter, 1)) * args.distance*1000).astype(int)
    else:
        zmoves = np.zeros(args.iter)

    moves = np.column_stack((xmoves,ymoves,zmoves))
    
#    moves = (np.random.random(size=(args.iter, 3)) * args.distance*1000).astype(int)
    targets = np.array(start_pos)[np.newaxis, :] + moves
    print (moves)
    print (targets)
else:
    # just move back and forth between start and test position
    test_pos = np.array(list(map(float, args.test_pos.split(','))))
    targets = np.zeros((args.iter, 3))
    targets[::2] = start_pos[None, :]
    targets[1::2] = test_pos[None, :]
speeds = [args.speed] * args.iter

# targets = np.array([[15431718, 7349832, 17269820], [15432068, 7349816, 17249852]] * 5)
# speeds = [100, 2] * args.iter

# targets = np.array([[13073580, 13482162, 17228380], [9280157.0, 9121206.0, 12198605.]] * 5)
# speeds = [1000] * args.iter

# targets = np.array([[9335078, 10085446, 12197238], [14793665.0, 11658668.0, 17168934.]] * 5)
# speeds = [1000] * args.iter


dev.stop()

for i in range(args.iter):
    target = targets[i]
    move_req = dev.goto_pos(target, speed=speeds[i], linear=False, max_acceleration=args.acceleration) 
    while not move_req.finished:
        update(update_error=False)
        time.sleep(0.002)
    waitstart = pg.ptime.time()
    while pg.ptime.time() - waitstart < 1.0:
        update(update_error=True)
        time.sleep(0.002)
        # time.sleep(0.05)
    p2 = dev.get_pos(timeout=200)
    positions.append(p2)
    diff = (p2 - target) * 1e-9
    diffs.append(diff)
    errs.append(np.linalg.norm(diff))
    print(i, diff, errs[-1])

update_plots()

dev.goto_pos(start_pos, args.speed)
print("mean:", np.mean(errs), " max:", np.max(errs))

if sys.flags.interactive == 0:
    app.exec_()
