import sys

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
