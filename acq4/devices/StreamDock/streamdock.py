import json
import threading
import time

from acq4.devices.Device import Device
from acq4.util import Qt
from .bridge import HANDOFF_FILE
from .plugin import PLUGIN_DIR, PLUGIN_UUID, auto_install_plugin, is_bridge_running, launch_vsdcraft, vsdcraft_is_running

import websocket


class StreamDock(Device):
    """
    VSDInside Stream Dock device for acq4.

    This device integrates with the VSDInside Stream Dock hardware via the
    Stream Dock software's WebSocket plugin interface (the same protocol used by
    the Elgato Stream Deck plugin SDK).

    How it works
    ------------
    The Stream Dock software acts as a WebSocket server. When a plugin is launched
    it connects to that server, registers itself, and then receives events for
    every button/dial interaction. The plugin can also send commands back to update
    what is shown on each key's display.

    For acq4, this device handles the WebSocket connection in a background thread
    and exposes:
    - ``sigButtonEvent`` Qt signal — emitted for every user interaction
    - ``setTitle(context, title)`` — update a key's text label
    - ``setImage(context, image)`` — update a key's image (base64 data URI)

    Configuration
    -------------
    ::

        MyStreamDock:
            driver: 'StreamDock'

    Optional keys
    ~~~~~~~~~~~~~
    * ``autoInstall`` (bool, default ``true``): copy the bridge plugin into the
    Stream Dock plugins directory on startup if it is not already there.
    * ``installTimeout`` (int, default ``30``): seconds to wait for bridge.py to
    write the handoff file before giving up.

    First-time setup
    ~~~~~~~~~~~~~~~~
    1. Download and install the VSDInside Stream Dock software from
    https://www.vsdinside.com/pages/download
    2. Start acq4 — the device will detect the software and automatically copy
    ``bridge.py`` and ``manifest.json`` into the Stream Dock plugins folder.
    3. Restart the Stream Dock software so it picks up the new plugin.
    4. From then on, launching acq4 first and then Stream Dock (or vice versa)
    will result in the two connecting automatically.
    """

    #: Emitted with the raw event dict from Stream Dock on every user interaction.
    sigButtonEvent = Qt.Signal(object)

    _INTERACTION_EVENTS = frozenset({
        'keyDown', 'keyUp',
        'dialPress', 'dialRelease', 'dialRotate',
        'touchTap',
    })

    def __init__(self, man, config, name):
        super().__init__(man, config, name)

        try:
            import websocket
        except ImportError:
            raise ImportError(
                "The 'websocket-client' package is required for the StreamDock device. "
                "Install it with: pip install websocket-client"
            )

        self._ws = None
        self._ws_thread = None
        self._lock = threading.Lock()
        self._handoff_timeout = config.get('installTimeout', 30)

        # --- Auto-install bridge plugin into Stream Dock ----------------
        if config.get('autoInstall', True):
            auto_install_plugin()

        # --- Ensure VSD Craft is running --------------------------------
        if not vsdcraft_is_running():
            self.logger.info("[StreamDock] VSD Craft not running; launching it now.")
            launch_vsdcraft()

        # --- Connect ---------------------------------------------------
        self.logger.info(
            f"[StreamDock] Waiting up to {self._handoff_timeout}s for "
            f"handoff file: {HANDOFF_FILE}"
        )
        t = threading.Thread(
            target=self._wait_for_handoff,
            daemon=True,
            name='StreamDock-handoff',
        )
        t.start()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    # How long to wait before first checking whether bridge.py is actually running.
    # VSD Craft needs a moment to start up and launch plugins.
    _BRIDGE_CHECK_GRACE = 10.0

    def _wait_for_handoff(self):
        """Poll for the handoff file written by bridge.py, then connect.

        After a short grace period, checks whether bridge.py is actually running
        and gives up immediately if it is not, rather than waiting out the full timeout.
        """
        deadline = time.monotonic() + self._handoff_timeout
        bridge_check_at = time.monotonic() + self._BRIDGE_CHECK_GRACE
        bridge_confirmed = False

        while time.monotonic() < deadline:
            if HANDOFF_FILE.exists():
                try:
                    params = json.loads(HANDOFF_FILE.read_text(encoding='utf-8'))
                    self._port = params['port']
                    self._plugin_uuid = params.get('pluginUUID', PLUGIN_UUID)
                    self._register_event = params.get('registerEvent', 'registerPlugin')
                    self.logger.info(
                        f"[StreamDock] Handoff received: "
                        f"port={self._port}  uuid={self._plugin_uuid!r}"
                    )
                    self._connect()
                    return
                except Exception as exc:
                    self.logger.warning(f"[StreamDock] Could not read handoff file: {exc}")

            # Once the grace period has passed, verify the bridge is actually running.
            if not bridge_confirmed and time.monotonic() >= bridge_check_at:
                if is_bridge_running():
                    bridge_confirmed = True
                else:
                    self.logger.error(
                        "[StreamDock] bridge.py is not running. "
                        "VSD Craft may not have loaded the ACQ4 plugin yet. "
                        "Open VSD Craft, add an 'ACQ4 Button' action to your profile, "
                        f"and ensure the plugin is enabled at {PLUGIN_DIR}."
                    )
                    return

            time.sleep(0.5)

        self.logger.error(
            f"[StreamDock] Timed out after {self._handoff_timeout}s waiting for "
            f"handoff file {HANDOFF_FILE}."
        )

    def _connect(self):
        """Open the WebSocket connection to the Stream Dock software."""
        assert websocket is not None
        url = f"ws://127.0.0.1:{self._port}"
        self.logger.info(f"[StreamDock] Connecting to {url}")

        ws = websocket.WebSocketApp(
            url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        with self._lock:
            self._ws = ws

        t = threading.Thread(target=ws.run_forever, daemon=True, name='StreamDock-ws')
        self._ws_thread = t
        t.start()

    def _on_open(self, ws):
        msg = f"[StreamDock] Connected on port {self._port}"
        print(msg)
        self.logger.info(msg)
        ws.send(json.dumps({
            'event': self._register_event,
            'uuid': self._plugin_uuid,
        }))

    def _on_message(self, _ws, raw):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self.logger.warning(f"[StreamDock] Non-JSON message: {raw!r}")
            return

        event = data.get('event', '')
        context = data.get('context', '')

        if event in self._INTERACTION_EVENTS:
            payload = data.get('payload', {})
            coordinates = payload.get('coordinates', {})
            msg = (
                f"[StreamDock] User interaction: event={event!r}  "
                f"context={context!r}  coordinates={coordinates}"
            )
            print(msg)
            self.logger.info(msg)
            self.sigButtonEvent.emit(data)
        else:
            self.logger.debug(f"[StreamDock] Event: {event!r}")

    def _on_error(self, ws, error):
        msg = f"[StreamDock] WebSocket error: {error}"
        print(msg)
        self.logger.error(msg)

    def _on_close(self, ws, close_status_code, close_msg):
        msg = f"[StreamDock] Connection closed (code={close_status_code}, msg={close_msg!r})"
        print(msg)
        self.logger.info(msg)

    # ------------------------------------------------------------------
    # Display update methods
    # ------------------------------------------------------------------

    def setTitle(self, context: str, title: str, target: int = 0):
        """Update the text shown on a Stream Dock key.

        Parameters
        ----------
        context:
            The key context identifier (from the ``'context'`` field of any
            received event dict).
        title:
            Text string to display on the key.
        target:
            0 = hardware + software (default), 1 = hardware only,
            2 = software only.
        """
        self._send({
            'event': 'setTitle',
            'context': context,
            'payload': {'title': title, 'target': target},
        })

    def setImage(self, context: str, image: str, target: int = 0):
        """Update the image shown on a Stream Dock key.

        Parameters
        ----------
        context:
            The key context identifier.
        image:
            A base64-encoded image data URI, e.g.
            ``'data:image/png;base64,iVBORw0KGgo...'``.
            Use :func:`imageFromFile` to build this from a file.
        target:
            0 = hardware + software (default), 1 = hardware only,
            2 = software only.
        """
        self._send({
            'event': 'setImage',
            'context': context,
            'payload': {'image': image, 'target': target},
        })

    @staticmethod
    def imageFromFile(path: str) -> str:
        """Return a base64 data URI for the image at *path* (PNG or JPEG).

        The returned string can be passed directly to :meth:`setImage`.
        """
        import base64
        import mimetypes
        mime, _ = mimetypes.guess_type(path)
        if mime is None:
            mime = 'image/png'
        with open(path, 'rb') as fh:
            data = base64.b64encode(fh.read()).decode('ascii')
        return f'data:{mime};base64,{data}'

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _send(self, payload: dict):
        """Send a JSON message to Stream Dock (thread-safe)."""
        with self._lock:
            ws = self._ws
        if ws is None:
            self.logger.warning("[StreamDock] Cannot send: not connected")
            return
        try:
            ws.send(json.dumps(payload))
        except Exception as exc:
            self.logger.error(f"[StreamDock] Send failed: {exc}")

    # ------------------------------------------------------------------
    # Device lifecycle
    # ------------------------------------------------------------------

    def quit(self):
        with self._lock:
            ws = self._ws
            self._ws = None
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        self.logger.info("[StreamDock] Device shut down")
