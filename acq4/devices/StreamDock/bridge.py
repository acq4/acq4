"""
ACQ4 Stream Dock bridge plugin.

This script is launched by the VSDInside Stream Dock software as a plugin.
Stream Dock passes connection parameters via command-line arguments::

    bridge.py -port PORT -pluginUUID UUID -registerEvent EVENT -info JSON

The bridge does two things:

1. Writes the connection parameters to a well-known handoff file
   (~/.acq4_streamdock_port.json) so that the acq4 StreamDock device can
   discover which port to connect to.

2. Maintains its own WebSocket connection to the Stream Dock software so the
   software does not think the plugin has crashed. Events received here are
   *not* acted on — acq4's StreamDock device is the second connected client
   and handles them directly.

This file is copied into the Stream Dock plugins directory automatically by the
StreamDock acq4 device on first startup.  Do not run it manually.
"""

import argparse
import json
import logging
import pathlib
import sys

# websocket-client is a dependency of this package; it must be importable from
# the Python interpreter that runs this script (the one embedded in bridge.bat).
try:
    import websocket
except ImportError:
    sys.exit(
        "ERROR: 'websocket-client' is not installed in the Python environment "
        "used by bridge.bat.\n"
        "Run:  pip install websocket-client"
    )

HANDOFF_FILE = pathlib.Path.home() / '.acq4_streamdock_port.json'

logging.basicConfig(
    level=logging.INFO,
    format='[StreamDock bridge] %(levelname)s %(message)s',
)
log = logging.getLogger(__name__)


def main():
    p = argparse.ArgumentParser(description='ACQ4 Stream Dock bridge plugin')
    p.add_argument('-port', type=int, required=True,
                   help='WebSocket port assigned by Stream Dock')
    p.add_argument('-pluginUUID', required=True,
                   help='Plugin UUID as registered in manifest.json')
    p.add_argument('-registerEvent', required=True,
                   help='Registration event name (usually "registerPlugin")')
    p.add_argument('-info', default='{}',
                   help='JSON info blob from Stream Dock (informational only)')
    args = p.parse_args()

    # --- Write handoff file so acq4 knows which port to connect to -------
    handoff = {
        'port': args.port,
        'pluginUUID': args.pluginUUID,
        'registerEvent': args.registerEvent,
    }
    try:
        HANDOFF_FILE.write_text(json.dumps(handoff), encoding='utf-8')
        log.info(f"Handoff file written: {HANDOFF_FILE}")
    except OSError as exc:
        log.error(f"Could not write handoff file {HANDOFF_FILE}: {exc}")

    # --- Keep a WebSocket connection alive so Stream Dock doesn't exit ----
    url = f"ws://127.0.0.1:{args.port}"
    log.info(f"Connecting to {url}")

    def on_open(ws):
        log.info("Connected; registering plugin")
        ws.send(json.dumps({
            'event': args.registerEvent,
            'uuid': args.pluginUUID,
        }))

    def on_message(ws, message):
        # Events are handled by acq4's StreamDock device, not here.
        log.debug(f"Received: {message}")

    def on_error(ws, error):
        log.error(f"WebSocket error: {error}")

    def on_close(ws, code, msg):
        log.info(f"Connection closed (code={code})")
        # Remove the handoff file so acq4 knows the session ended.
        try:
            HANDOFF_FILE.unlink(missing_ok=True)
        except OSError:
            pass

    ws = websocket.WebSocketApp(
        url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    ws.run_forever()


if __name__ == '__main__':
    main()
