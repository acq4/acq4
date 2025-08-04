import sys
import time

import acq4.drivers.dovermotion.motionsynergy_client as ms
import teleprox.log

if len(sys.argv) < 2:
    print("Usage: python -m acq4.drivers.dovermotion <path to MotionSynergyAPI.dll>")
    sys.exit(1)

# log to console, start log server
teleprox.log.basic_config(log_level='DEBUG')

cli = ms.get_client(sys.argv[1])
ss = cli['smartstage']
print("Created MotionSynergy client as `cli`, SmartStage as `ss`")

cb_called = False


def cb(mfut):
    global cb_called
    cb_called = True
    print(f"move finished {mfut}")


mov = ss.move((21, -26, -16), 10)
mov.set_callback(cb)
while not mov.done():
    time.sleep(1)
assert cb_called
