from __future__ import print_function
import os, sys, time
path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(path)

from acq4.drivers.ThorlabsMFC1.tmcm import TMCM140
import acq4.pyqtgraph as pg


if len(sys.argv) < 2:
    print("Usage:  python test.py device\n  (device may be com3, /dev/ttyACM0, etc.)")
    sys.exit(1)

s = TMCM140(port=sys.argv[1], baudrate=9600)

s.stop()
s['maximum_current'] = 50
s['encoder_position'] = 0
s['actual_position'] = 0


def step_curve(decay_threshold=-1):
    """Measure encoder following single steps at all microstep resolutions.
    """
    s['mixed_decay_threshold'] = decay_threshold
    s['stall_detection_threshold'] = 0
    plt = pg.plot()
    for res in range(7):
        x = []
        s['microstep_resolution'] = res
        #s['encoder_prescaler'] = int(2**res * 100)
        s['encoder_prescaler'] = 6400
        for i in range(150):
            s.move(1, relative=True)
            while s['target_pos_reached'] == 0:
                pass
            x.append(s['encoder_position'])
            x.append(s['encoder_position'])
            x.append(s['encoder_position'])
            print(i, x[-1])
        plt.plot(x, symbol='o')
        pg.QtGui.QApplication.processEvents()

def test_stall(threshold=7, ustep=3, speed=800):
    s['microstep_resolution'] = ustep
    s['mixed_decay_threshold'] = 2047
    s['stall_detection_threshold'] = threshold
    while True:
        s.rotate(speed)
        time.sleep(0.5)
        s.stop()
        time.sleep(0.2)

def test_seek():
    global x, t
    ures = 6
    s.stop()
    s['microstep_resolution'] = ures
    s['encoder_prescaler'] = 8192
    s['encoder_position'] = 0
    s['standby_current'] = 0
    s['maximum_speed'] = 50
    s['power_down_delay'] = 1200
    #s['freewheeling'] = 1000
    #s['actual_position'] = 0
    
    s.move(600, relative=True)
    start = time.time()
    t = []
    x = []
    while True:
        now = time.time()
        if now - start > 3:
            print("QUIT")
            break
        t.append(now-start)
        x.append(s['encoder_position'])
        
    pg.plot(t, x)
    
def test_encoder():
    plt = pg.plot()
    pos = []
    while True:
        pos.append(s['encoder_position'])
        while len(pos) > 300:
            pos.pop(0)
        plt.plot(pos, clear=True)
        pg.QtGui.QApplication.processEvents()


def test_load():
    plt = pg.plot()
    load = []
    s['mixed_decay_threshold'] = 2047
    s.rotate(200)
    
    def update():
        load.append(s['actual_load_value'])
        while len(load) > 300:
            load.pop(0)
        plt.plot(load, clear=True)
    global t
    t = pg.QtCore.QTimer()
    t.timeout.connect(update)
    t.start(0)

    
#step_curve()
#test_seek()

    