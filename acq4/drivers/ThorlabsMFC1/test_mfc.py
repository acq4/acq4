import os, sys, time
path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(path)

from acq4.drivers.ThorlabsMFC1 import MFC1
import acq4.pyqtgraph as pg


if len(sys.argv) < 2:
    print "Usage:  python test.py device\n  (device may be com3, /dev/ttyACM0, etc.)"
    sys.exit(1)

mfc = MFC1(sys.argv[1])

m = mfc.mcm
m.stop_program()
m.stop()
m['encoder_position'] = 0


i = 0
with m.write_program():
    # start with a brief wait because sometimes the first command may be ignored.
    m.command('wait', 0, 0, 1)    
    m.get_param('encoder_position')
    m.calc('sub', 10000)
    m.comp(-4000)
    m.jump('gt', 7)
    m.set_param('target_speed', 2000)
    m.jump(1)
    
    m.comp(-100)
    m.jump('gt', 12)
    m.calc('mul', -1)
    m.set_param('target_speed', 'accum')
    m.jump(1)

    m.calc('div', -2)
    m.set_param('target_speed', 'accum')
    m.jump(1)


plt = pg.plot()
data = []
t= []
start = time.time()
started = False
while True:
    now = time.time()
    if not started and now - start > 0.2:
        m.start_program(0)
        started = True
    if now - start > 1.5:
        break
    data.append(m['encoder_position'])
    t.append(now-start)
plt.plot(t, data, clear=True)


time.sleep(1.5)
m.stop_program()
m.stop()
