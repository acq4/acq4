import argparse
import acq4.drivers.dovermotion.motionsynergy_client as ms
import teleprox.log

parser = argparse.ArgumentParser(
    description="Start a MotionSynergy client connected to a MotionSynergy server."
)
parser.add_argument(
    "dll",
    type=str,
    help="Path to the MotionSynergyAPI.dll file",
)
parser.add_argument(
    "--direct",
    action="store_true",
    help="Load MotionSynergyAPI directly in this process, rather than connecting to a server.",
)
args = parser.parse_args()

if args.direct:
    from .motionsynergy_api import get_motionsynergyapi
    from .smartstage import SmartStage

    motionSynergy, instrumentSettings = get_motionsynergyapi(args.dll)
    ss = SmartStage()
else:
    # log to console, start log server
    teleprox.log.basic_config(log_level='DEBUG')

    cli = ms.get_client(dll_path=args.dll)
    ss = cli['smartstage']
    print("Created MotionSynergy client as `cli`, SmartStage as `ss`")

