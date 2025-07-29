import logging

import teleprox

# This is a custom level for MotionSynergy messages, so they can be filtered separately.
logging.addLevelName(
    logging.INFO,
    "MOTIONSYNERGY",
)

SERVER_PORT = 60738
SERVER_ADDRESS = f"tcp://localhost:{SERVER_PORT}"

ms_client = None
ms_process = None  # only exists if it was started this time
local_server = None  # local RPC server for callback proxying
logger = logging.getLogger('motionsynergy_server')
logger.setLevel(logging.INFO)
log_server = teleprox.log.remote.LogServer(logger=logger)


def get_client(dll_path):
    """Return an RPCClient connected to the motionSynergy server.
    """
    global ms_client, local_server
    if ms_client is None:
        try:
            ms_client = teleprox.RPCClient.get_client(address=SERVER_ADDRESS)
            ms_client._import('teleprox.log').set_logger_address(log_server.address)
            logger.info("Connected to motionSynergy server.")
        except ConnectionRefusedError as exc:
            exc.add_note("No motionsynergy server running; starting one now..")
            ms_client = start_server(dll_path=dll_path, log_addr=log_server.address)
        local_server = teleprox.RPCServer()
        teleprox.RPCServer.register_server(local_server)
    return ms_client


def start_server(dll_path, log_addr):
    global ms_process
    print("Starting motionSynergy server..")
    ms_process = teleprox.start_process(
        'motionsynergy_server',
        qt=True,
        address=SERVER_ADDRESS,
        daemon=True,
        log_addr=log_addr,
        log_level='INFO',
        start_local_server=True,
    )

    ms_server = ms_process.client._import('acq4.drivers.dovermotion.motionsynergy_api')
    ms_server.install_tray_icon()
    motionSynergy, instrumentSettings = ms_server.get_motionsynergyapi(dll_path)
    ms_process.client['motionsynergy_module'] = ms_server
    ms_process.client['motionSynergy'] = motionSynergy
    ms_process.client['instrumentSettings'] = instrumentSettings

    ss = ms_process.client._import('acq4.drivers.dovermotion.smartstage').SmartStage(_timeout=90)
    ms_process.client['smartstage'] = ss

    return ms_process.client
