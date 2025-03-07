import acq4.drivers.dovermotion.motionsynergy_client as ms
import teleprox.log

# log to console, start log server
teleprox.log.basic_config(log_level='DEBUG')

cli = ms.get_client()
ss = cli['smartstage']
print("Created MotionSynergy client as `cli`, SmartStage as `ss`")
