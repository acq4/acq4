import subprocess
import teleprox


SERVER_PORT = 60738
SERVER_ADDRESS = f"tcp://localhost:{SERVER_PORT}"
DLL_PATH = "C:\\Users\\lukec\\Desktop\\Devices\\Dover Stages\\MotionSynergyAPI_SourceCode_3.6.12025\\MotionSynergyAPI.dll"

ms_client = None
ms_process = None  # only exists if it was started this time



def get_motionsynergy():
    """Connect to server and return a remote reference to the motionSynergy object.
    
    If necessary, start the server process.
    """
    client = get_client()
    return client['motionSynergy']


def initialize():
    """Request that the motionSynergy server initialize the stage.
    """
    cli = get_client()
    ms = cli['motionsynergy_module']
    return ms.initialize()


def get_client():
    """Return an RPCClient connected to the motionSynergy server.
    """
    global ms_client
    if ms_client is None:
        try:
            ms_client = teleprox.RPCClient.get_client(address=SERVER_ADDRESS)
            print("Connected to motionSynergy server.")
        except ConnectionRefusedError:
            ms_client = start_server()
            
    return ms_client


def start_server():
    global ms_process
    print("Starting motionSynergy server..")
    ms_process = teleprox.start_process('motionsynergy_server', qt=True, address=SERVER_ADDRESS, daemon=True)
    ms_server = ms_process.client._import('acq4.drivers.dovermotion.motionsynergy_server')

    motionSynergy, instrumentSettings = ms_server.get_motionsynergyapi(DLL_PATH)
    ms_process.client['motionsynergy_module'] = ms_server
    ms_process.client['motionSynergy'] = motionSynergy
    ms_process.client['instrumentSettings'] = instrumentSettings
    return ms_process.client


"""
import acq4.drivers.dovermotion.motionsynergy as ms
c = ms.get_client()

"""