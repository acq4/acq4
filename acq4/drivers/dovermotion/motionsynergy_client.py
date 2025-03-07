import logging
import teleprox


SERVER_PORT = 60738
SERVER_ADDRESS = f"tcp://localhost:{SERVER_PORT}"
DLL_PATH = "C:\\Users\\lukec\\Desktop\\Devices\\Dover Stages\\MotionSynergyAPI_SourceCode_3.6.12025\\MotionSynergyAPI.dll"

ms_client = None
ms_process = None  # only exists if it was started this time
logging.getLogger('motionsynergy_server').setLevel(logging.INFO)
log_server = teleprox.log.remote.LogServer(logger='motionsynergy_server')


def get_client():
    """Return an RPCClient connected to the motionSynergy server.
    """
    global ms_client
    if ms_client is None:
        try:
            ms_client = teleprox.RPCClient.get_client(address=SERVER_ADDRESS)
            ms_client._import('teleprox.log').set_logger_address(log_server.address)
            print("Connected to motionSynergy server.")
        except ConnectionRefusedError as exc:
            # no server running already
            exc.add_note("No motionsynergy server running; starting one now..")
            ms_client = start_server(log_addr=log_server.address)
    return ms_client


def start_server(log_addr):
    global ms_process
    print("Starting motionSynergy server..")
    ms_process = teleprox.start_process(
        'motionsynergy_server', 
        qt=True, 
        address=SERVER_ADDRESS, 
        daemon=True,
        log_addr=log_addr,
        log_level='INFO',
    )

    ms_server = ms_process.client._import('acq4.drivers.dovermotion.motionsynergy_server')
    ms_server.install_tray_icon()
    motionSynergy, instrumentSettings = ms_server.get_motionsynergyapi(DLL_PATH)
    ms_process.client['motionsynergy_module'] = ms_server
    ms_process.client['motionSynergy'] = motionSynergy
    ms_process.client['instrumentSettings'] = instrumentSettings

    ss = ms_process.client._import('acq4.drivers.dovermotion.smartstage').SmartStage(_timeout=90)
    ms_process.client['smartstage'] = ss

    return ms_process.client

import logging
logging.addLevelName