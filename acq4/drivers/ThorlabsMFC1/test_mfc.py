from __future__ import print_function
import os, sys, time
path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(path)

from acq4.drivers.ThorlabsMFC1 import MFC1
import acq4.pyqtgraph as pg


if len(sys.argv) < 2:
    print("Usage:  python test.py device\n  (device may be com3, /dev/ttyACM0, etc.)")
    sys.exit(1)

mfc = MFC1(sys.argv[1])

print("pos:", mfc.position())

def plot_motion(delta=30000):
    """Rotate to a new position and plot the position, speed, and other parameters measured during motion.

    This is used to debug motion control when moving the motor to hit a specific encoder value.
    """
    global win
    win = pg.GraphicsWindow()
    p1 = win.addPlot(title='position')
    p2 = win.addPlot(title='speed', row=1, col=0)
    p3 = win.addPlot(title='target speed', row=2, col=0)
    p4 = win.addPlot(title='distance, <span style="color: green">distance-until-decel</span>', row=3, col=0)
    p2.setXLink(p1)
    p3.setXLink(p1)
    p4.setXLink(p1)

    t = []
    x = []
    v = []
    vt = []
    dx = []
    dxt = []
    start = time.time()
    started = False
    while True:
        now = time.time()
        pos = mfc.position()
        if not started and now - start > 0.2:
            move = pos + delta
            print("move:", move)
            mfc.move(move)
            started = True
        if now - start > 2:
            break
        t.append(now-start)
        x.append(pos)
        v.append(mfc.mcm['actual_speed'])
        vt.append(mfc.mcm['target_speed'])
        dx.append(mfc.mcm.get_global('gp1'))
        dxt.append(mfc.mcm.get_global('gp2'))
    p1.plot(t, x, clear=True)
    p2.plot(t, v, clear=True)
    p3.plot(t, vt, clear=True)
    p4.plot(t, dx, clear=True)
    p4.plot(t, dxt, pen='g')

    print("Final:", mfc.position())