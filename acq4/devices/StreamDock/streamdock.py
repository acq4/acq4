import json
import threading
import time

from acq4.devices.Device import Device
from acq4.util import Qt
from .bridge import HANDOFF_FILE
from .plugin import PLUGIN_DIR, PLUGIN_UUID, auto_install_plugin, is_bridge_running, launch_vsdcraft, vsdcraft_is_running

import websocket


class _ButtonRegistration:
    """A button registered with the StreamDock device.

    Created by :meth:`StreamDock.add_button`. The ``context`` attribute is
    ``None`` until VSD Craft sends a ``willAppear`` event for an available key,
    at which point StreamDock assigns this button to that context and pushes the
    title to the hardware.
    """

    def __init__(self, title, on_press, on_release=None, on_appear=None):
        self.title = title
        self.on_press = on_press
        self.on_release = on_release
        self.on_appear = on_appear
        self.context = None  # filled in when willAppear fires


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

        # --- Button registration -----------------------------------------
        self._button_lock = threading.Lock()
        self._buttons = []           # _ButtonRegistration list, in registration order
        self._context_map = {}       # context str -> _ButtonRegistration
        self._unmatched_contexts = []  # contexts with no button yet (FIFO)
        self._configured_interfaces = set()  # interface names already configured

        # Discover existing stream_dock implementers and watch for new ones.
        # The connection to the signal must be made on the main thread (here in
        # __init__) before any devices that might declare 'stream_dock' finish
        # their own __init__.
        self.dm.interfaceDir.sigInterfaceListChanged.connect(
            self._on_interface_list_changed
        )
        self._on_interface_list_changed(['stream_dock'])

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
            self.logger.info(msg)
            self.sigButtonEvent.emit(data)
            # Dispatch to any registered button handler for this context.
            with self._button_lock:
                button = self._context_map.get(context)
            if button is not None:
                if event == 'keyDown' and button.on_press is not None:
                    button.on_press()
                elif event == 'keyUp' and button.on_release is not None:
                    button.on_release()
        elif event in ('willAppear', 'willDisappear'):
            payload = data.get('payload', {})
            coordinates = payload.get('coordinates', {})
            msg = (
                f"[StreamDock] {event}: context={context!r}  "
                f"coordinates={coordinates}  full_payload={payload}"
            )
            self.logger.info(msg)
            controller = payload.get('controller', 'Keypad')
            if event == 'willAppear':
                self._assign_context(context, controller)
            else:
                self._unassign_context(context)
        else:
            self.logger.debug(f"[StreamDock] Unhandled event: {event!r}")

    def _on_error(self, ws, error):
        msg = f"[StreamDock] WebSocket error: {error}"
        self.logger.error(msg)

    def _on_close(self, ws, close_status_code, close_msg):
        msg = f"[StreamDock] Connection closed (code={close_status_code}, msg={close_msg!r})"
        self.logger.info(msg)

    # ------------------------------------------------------------------
    # Button registration
    # ------------------------------------------------------------------

    def add_button(self, title: str, on_press=None, on_release=None, on_appear=None) -> _ButtonRegistration:
        """Register a button with the Stream Dock.

        The button will be assigned to the next available key context in the
        order that ``willAppear`` events arrive from VSD Craft (i.e. in profile
        layout order).  If a context is already waiting (``willAppear`` arrived
        before this call), the button is assigned immediately.

        Parameters
        ----------
        title:
            Label displayed on the key.
        on_press:
            Callable invoked with no arguments on ``keyDown``.
        on_release:
            Callable invoked with no arguments on ``keyUp``.

        Returns
        -------
        _ButtonRegistration
            The registration object; its ``context`` attribute is set once a
            key context has been assigned.
        """
        button = _ButtonRegistration(title, on_press, on_release, on_appear)
        context = None
        with self._button_lock:
            self._buttons.append(button)
            if self._unmatched_contexts:
                context = self._unmatched_contexts.pop(0)
                button.context = context
                self._context_map[context] = button
        if context is not None:
            self.setTitle(context, title)
        self.logger.info(
            f"[StreamDock] Registered button {title!r} (context={context!r})"
        )
        return button

    def _on_interface_list_changed(self, types):
        """Qt slot: called when the interface directory changes."""
        if 'stream_dock' not in types:
            return
        for name in self.dm.listInterfaces('stream_dock'):
            if name in self._configured_interfaces:
                continue
            self._configured_interfaces.add(name)
            obj = self.dm.getInterface('stream_dock', name)
            try:
                obj.configure_dock(self)
                self.logger.info(
                    f"[StreamDock] Configured stream_dock interface: {name!r}"
                )
            except Exception:
                self.logger.exception(
                    f"[StreamDock] Error calling configure_dock on {name!r}"
                )

    def _assign_context(self, context: str, controller: str = 'Keypad'):
        """Map an arriving willAppear context to the next unassigned button.

        Only ``Keypad`` contexts are matched to registered buttons.  Knob,
        SecondaryScreen, and other controller contexts are silently ignored so
        that their ``willAppear`` events do not consume button slots.
        """
        if controller != 'Keypad':
            self.logger.debug(
                f"[StreamDock] Ignoring willAppear for controller={controller!r} "
                f"context={context!r}"
            )
            return
        button = None
        with self._button_lock:
            if context in self._context_map:
                return  # already known
            for btn in self._buttons:
                if btn.context is None:
                    btn.context = context
                    self._context_map[context] = btn
                    button = btn
                    break
            else:
                # No waiting button; remember the context for the next add_button call.
                self._unmatched_contexts.append(context)
        if button is not None:
            self.setTitle(context, button.title)
            if button.on_appear is not None:
                button.on_appear(context)
            self.logger.info(
                f"[StreamDock] Assigned context {context!r} -> button {button.title!r}"
            )
        else:
            self.logger.debug(
                f"[StreamDock] Queued unmatched context {context!r}"
            )

    def _unassign_context(self, context: str):
        """Release a context when willDisappear fires."""
        with self._button_lock:
            button = self._context_map.pop(context, None)
            if button is not None:
                button.context = None
                self.logger.info(
                    f"[StreamDock] Released context {context!r} "
                    f"(button {button.title!r})"
                )

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
        payload = {
            'event': 'setTitle',
            'context': context,
            'payload': {'title': title, 'target': target},
        }
        self.logger.debug(f"[StreamDock] setTitle: context={context!r} title={title!r}")
        self._send(payload)

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
