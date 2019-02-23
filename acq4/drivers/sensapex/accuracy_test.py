
from __future__ import print_function
import os, sys, time
import numpy as np
import acq4.pyqtgraph as pg
from acq4.drivers.sensapex import SensapexDevice, UMP, UMPError

ump = UMP.get_ump()
devids = ump.list_devices()
devs = {i:SensapexDevice(i) for i in devids}

print("SDK version:", ump.sdk_version())
print("Found device IDs:", devids)

dev = devs[int(sys.argv[1])]

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
times = []

lastupdate = pg.ptime.time()

def update(update_error=False):
    global lastupdate
    p = dev.get_pos()
    s = dev.is_busy()
    bus.append(int(s))
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
        plots[i].addItem(pg.PlotCurveItem(times, bus, pen=(0, 255, 0, 50), brush=(0, 255, 0, 50), fillLevel=0), ignoreBounds=True)
        plots[i].plot(times, tgt[i], pen='r')
        plots[i].plot(times, pos[i])
        errplots[i].plot(times, err[i], clear=True, connect='finite')


p1 = dev.get_pos()
diffs = []
errs = []
targets = []
positions = []
moves = []
for i in range(10):
    d = (np.random.random(size=3) * 1e6).astype(int)
    #d[0] = 0
    #d[1] *= 0.01
    #d[2] *= 0.01
    moves.append(d)
    target = p1 + d
    targets.append(target)
    dev.goto_pos(target, speed=1000, linear=True) 
    while dev.is_busy():
        update()
    waitstart = pg.ptime.time()
    while pg.ptime.time() - waitstart < 2.0:
        update(update_error=True)
        # time.sleep(0.05)
    p2 = dev.get_pos(timeout=200)
    positions.append(p2)
    diff = (p2 - target) * 1e-9
    diffs.append(diff)
    errs.append(np.linalg.norm(diff))
    print(diff, errs[-1])

update_plots()

dev.goto_pos(p1, 1000)
print("mean:", np.mean(errs), " max:", np.max(errs))

# plt = pg.plot(labels={'left': ('error', 'm'), 'bottom': 'trial'})
# plt.plot([abs(e[0]) for e in diffs], pen=None, symbol='o', symbolBrush='r')
# plt.plot([abs(e[1]) for e in diffs], pen=None, symbol='o', symbolBrush='g')
# plt.plot([abs(e[2]) for e in diffs], pen=None, symbol='o', symbolBrush='b')
