
from __future__ import print_function
import os, sys, time, argparse
import numpy as np
import acq4.pyqtgraph as pg
from acq4.drivers.sensapex import SensapexDevice, UMP, UMPError


parser = argparse.ArgumentParser(
    description="Test for sensapex devices; perform a series of random moves while rapidly polling the device position and state.")
parser.add_argument('device', type=int, help="Device ID to test")
parser.add_argument('--group', type=int, default=0, help="Device group number")
parser.add_argument('--speed', type=int, default=1000, help="Movement speed in um/sec")
parser.add_argument('--distance', type=int, default=10, help="Max distance to travel in um (relative to current position)")
parser.add_argument('--iter', type=int, default=10, help="Number of positions to test")
parser.add_argument('--acceleration', type=int, default=0, help="Max speed acceleration")
args = parser.parse_args()

ump = UMP.get_ump(group=args.group)
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
    p = dev.get_pos(timeout=20)
    s = dev.is_busy()
    m = not move_req.finished
    bus.append(int(s))
    mov.append(int(m))
    now = pg.ptime.time() - start
    times.append(now)
    for i in range(3):
        pos[i].append((p[i] - p1[i]) * 1e-9)
        tgt[i].append((target[i] - p1[i]) * 1e-9)
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


p1 = dev.get_pos()
diffs = []
errs = []
targets = []
positions = []
moves = []
for i in range(args.iter):
    d = (np.random.random(size=3) * args.distance*1000).astype(int)
    # d[0] = 0
    # d[1] *= 0.01
    # d[2] *= 0.01
    moves.append(d)
    target = p1 + d
    targets.append(target)
    move_req = dev.goto_pos(target, speed=args.speed, linear=False, max_acceleration=args.acceleration) 
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

dev.goto_pos(p1, args.speed)
print("mean:", np.mean(errs), " max:", np.max(errs))

if sys.flags.interactive == 0:
    app.exec_()
