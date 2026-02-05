import sys
import argparse
import logging
import acq4.drivers.dovermotion.motionsynergy_client as ms
import teleprox
from .motionsynergy_client import SERVER_ADDRESS


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
    logging.getLogger().setLevel(logging.DEBUG)
    try:
        from PyQt5 import QtWidgets
    except ImportError:
        from PyQt6 import QtWidgets
    from .motionsynergy_api import get_motionsynergyapi, install_tray_icon, create_smartstage
    from .smartstage import SmartStage

    app = QtWidgets.QApplication([])
    install_tray_icon()
    motionSynergy, instrumentSettings = get_motionsynergyapi(args.dll)
    ss = create_smartstage()

    tx_server = teleprox.RPCServer(address=SERVER_ADDRESS, run_thread=True)
    tx_server['motionSynergy'] = motionSynergy
    tx_server['instrumentSettings'] = instrumentSettings
    tx_server['smartstage'] = ss

    if sys.flags.interactive == 0:
        app.exec_()
else:
    # log to console, start log server
    teleprox.log.basic_config(log_level='DEBUG')

    cli = ms.get_client(dll_path=args.dll)
    ss = cli['smartstage']
    print("Created MotionSynergy client as `cli`, SmartStage as `ss`")
