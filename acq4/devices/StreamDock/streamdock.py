"""VSDInside Stream Dock as an acq4 :class:`~acq4.devices.ControlSurface.ControlSurface`."""

from __future__ import annotations

import collections
import json
import threading
import time
from typing import TYPE_CHECKING

from acq4.devices.ControlSurface import Control, ControlSurface, UnsupportedControlFeature
from acq4.util import Qt

from . import install, profile, render

if TYPE_CHECKING:
    import acq4

try:
    import websocket
except ImportError:  # pragma: no cover - reported at construction, not at import
    websocket = None


#: Seconds between connection attempts. Disconnects are routine, not exceptional.
RECONNECT_DELAY = 2.0

#: Seconds to wait, after registering, for VSD Craft to report the keys on the visible
#: page. It normally takes well under a second; this only has to be longer than that.
#: A registration that is accepted and then never followed by ``willAppear`` is the one
#: failure mode that otherwise looks completely healthy from inside acq4.
BINDING_TIMEOUT = 10.0

#: How long a metadata problem must persist before acq4 restarts VSD Craft over it. VSD
#: Craft takes a few seconds to launch its plugins, and for that window the metadata
#: legitimately describes a session that does not exist yet.
PROBLEM_GRACE = 30.0

#: Shortest interval between recovery attempts. Restarting VSD Craft is heavy and visible
#: to the user, so a panel that stays unusable backs off to this rather than cycling the
#: application in a loop.
RECOVERY_INTERVAL = 120.0

#: Shortest interval between repeated "that appearance went nowhere" warnings.
UNDELIVERABLE_WARNING_INTERVAL = 30.0

#: Events that arrive for reasons of their own and need no handling.
IGNORED_EVENTS = frozenset(
    {
        'titleParametersDidChange',
        'didReceiveSettings',
        'didReceiveGlobalSettings',
        'deviceDidConnect',
        'deviceDidDisconnect',
        'applicationDidLaunch',
        'applicationDidTerminate',
        'systemDidWakeUp',
        'propertyInspectorDidAppear',
        'propertyInspectorDidDisappear',
        'sendToPlugin',
    }
)


class StreamDockControl(Control):
    """One Stream Dock key or knob strip: a little RGB display and nothing else.

    Every output a Stream Dock has is pixels, so everything here ends up as an image or as
    the protocol's own key title. That is this device's idiosyncrasy and lives here rather
    than in :class:`~acq4.devices.ControlSurface.Control`: the other surface acq4 drives is
    a keypad whose whole output per key is one blue and one red LED, which has no use for
    any of it.

    Nothing approximates. A control asked for something its declared output cannot express
    raises :exc:`~acq4.devices.ControlSurface.UnsupportedControlFeature` rather than showing
    something else, and the request is not cached, so a later repaint replays the last
    appearance that did work.
    """

    def __init__(self, *args, **kwds):
        Control.__init__(self, *args, **kwds)
        self._animation = None  # None | (frames, interval)

    def imageSize(self) -> tuple:
        """Return this control's display size as ``(width, height)``.

        Raises
        ------
        UnsupportedControlFeature
            If this control declares no display. Nothing on the panels acq4 supports is
            like that, but a future block might be, and every method here needs the size.
        """
        size = self._capabilities['output'].get('image')
        if not size:
            raise UnsupportedControlFeature(f"{self} has no display")
        return tuple(size)

    def setImage(self, image) -> None:
        """Display *image* on this control.

        Parameters
        ----------
        image : QImage | ndarray | str
            See :func:`.render.toQImage`. The image is scaled to :meth:`imageSize` on the
            way to the hardware.
        """
        self._setAppearance('image', image=render.toQImage(image))

    def setText(self, text, color=None, background=None) -> None:
        """Display *text* on this control.

        The text is drawn into the control's display at the largest size that fits, so a
        label looks the same whether or not a colour is asked for. See
        :meth:`StreamDock._writeText`.

        Parameters
        ----------
        text : str
            Text to show. Newlines are honoured.
        color, background : optional
            Anything :func:`pyqtgraph.mkColor` accepts, or None for the panel's own
            default.
        """
        if not self._capabilities['output'].get('text'):
            raise UnsupportedControlFeature(f"{self} cannot show text")
        self._setAppearance('text', text=text, color=color, background=background)

    def setColor(self, color) -> None:
        """Fill this control's display with *color*.

        A key has no light of its own, so a colour is a solid image -- an exact rendering
        of the request rather than an approximation of it.

        Parameters
        ----------
        color : QColor or colour spec
            Anything :func:`pyqtgraph.mkColor` accepts.
        """
        self._setAppearance('image', image=render.renderSolidImage(color, self.imageSize()))

    def clear(self) -> None:
        """Blank this control: black display, empty title, animation stopped."""
        self.stopAnimation()
        self._setAppearance('clear')

    def setAnimation(self, frames, interval: float) -> None:
        """Animate this control's display.

        The surface drives every animated control from one timer and drops frames while its
        send queue is busy, so a slow link costs frame rate rather than latency.

        Parameters
        ----------
        frames : sequence
            Frames, each acceptable to :meth:`setImage`.
        interval : float
            Seconds between frames.

        Raises
        ------
        ValueError
            If *frames* is empty.
        """
        self.imageSize()  # refuse up front rather than on the first tick
        frames = [render.toQImage(frame) for frame in frames]
        if len(frames) == 0:
            raise ValueError("Animation needs at least one frame")
        self._animation = (frames, interval)
        self.surface._startAnimation(self, frames, interval)

    def stopAnimation(self) -> None:
        """Stop any animation on this control, leaving the last frame displayed."""
        self._animation = None
        self.surface._stopAnimation(self)

    def replayAppearance(self) -> None:
        """Re-send the cached appearance, and restart an animation that was running.

        An animation is not an appearance the opaque cache can hold -- it is a whole
        sequence plus a timer -- so it is replayed here rather than by the base class.
        """
        Control.replayAppearance(self)
        if self._animation is not None:
            frames, interval = self._animation
            self.surface._startAnimation(self, frames, interval)

    def _blank(self) -> None:
        """Blank this control when it is released or its page comes up unclaimed."""
        self.clear()


class StreamDock(ControlSurface):
    """A VSDInside Stream Dock panel: a grid of image keys over a row of rotary knobs.

    The Stream Dock software (VSD Craft) runs a websocket server and speaks the Elgato
    Stream Deck plugin protocol. ACQ4 ships a tiny Node plugin whose only job is to publish
    the websocket address and the ``-info`` device description that VSD Craft hands it;
    ACQ4 then connects to that address itself, so all rendering and device state stay in
    this interpreter.

    Layout is not something the protocol can set: there is no command to place an action on
    a key, so :mod:`.profile` writes the profile JSON directly and bakes each key's acq4
    address into its per-instance ``Settings``, which ``willAppear`` reports back. That is
    what makes ``(type, page, key)`` reproducible; nothing depends on the order keys appear
    in.

    Output
    ------
    Every key and knob strip is a small display, so everything this panel can show is
    pixels or the protocol's own key title. That API is
    :class:`StreamDockControl` -- ``setImage``, ``setText``, ``setColor``, ``clear`` and
    the animation pair -- not anything the generic control interface promises. A consumer
    holding a control from an unknown surface checks for the method it wants (or reads
    ``capabilities()['output']``) before calling it.

    Addressing
    ----------
    ``key`` is ``(row, col)`` **within the control type's own block**: button ``(0, 0)`` is
    the first button of the top button row, not panel row 0, which is the knob strip along
    the bottom of the panel. Block rows are numbered from the top, as a written layout
    reads; :class:`~acq4.devices.StreamDock.profile.GridSpec` documents how that maps onto
    the panel, whose own row index counts up from the bottom. :meth:`controlGrids` returns
    the button grid first, then the dial grid.

    Pages
    -----
    VSD Craft owns pages, so ``_hardwarePages`` is True and page changes are *reported*
    rather than emulated. ``page`` is the ordinal of a generated page, matching
    ``Settings['pageIndex']``. The user pages with whatever page-change control they set up
    in VSD Craft and this device follows; there is no command to switch page, so
    :meth:`canSetCurrentPage` is False and :meth:`setCurrentPage` raises. acq4 does not
    switch pages by any other route either: it never rewrites the profile's stored current
    page except to stop it pointing at a page it has just removed.

    Page switching is configured in VSD Craft, not here: acq4 places no page-change action
    and reserves no panel position for one. A page-change control the user adds to a
    generated page is carried forward when acq4 rewrites that page, unless the configured
    ``buttons``/``dials`` blocks need its position, in which case the configured control
    wins and the collision is logged.

    Startup
    -------
    Everything slow happens on a daemon thread, so constructing this device never blocks
    ACQ4's startup: plugin install, profile reconciliation (which stops and restarts VSD
    Craft if it has to write), then a connect loop that re-reads the published address
    before every attempt, because VSD Craft hands out a new port and plugin UUID on every
    restart.

    Configuration options:

    * **pages** (int, optional): Number of generated pages to reconcile the device's
      profile to. Hand-built pages, including the profile's first page, are left alone.
      Default: 1

    * **buttons** (dict, optional): Shape of the key block as ``{'rows': int,
      'cols': int}``. Default: ``{'rows': 2, 'cols': 5}``

    * **dials** (dict, optional): Shape of the rotary knob block as ``{'rows': int,
      'cols': int}``, occupying the panel's rotary knob strip along the bottom. Default:
      ``{'rows': 1, 'cols': 3}``

    * **pageLabel** (str, optional): Human label baked into generated pages, which appear
      in VSD Craft as ``"<pageLabel> 1"``, ``"<pageLabel> 2"``... Default: ``'acq4'``

    * **autoInstall** (bool, optional): Copy the ACQ4 plugin into the Stream Dock plugins
      directory at startup if it is missing or out of date. Default: True

    * **device** (str, optional): Stream Dock device UUID, e.g. ``'VSDN4Pro'``. Default:
      whichever device VSD Craft currently has selected.

    Example configuration::

        Dock:
            driver: 'StreamDock'
            pages: 3
            buttons: {'rows': 2, 'cols': 5}
            dials: {'rows': 1, 'cols': 3}
            pageLabel: 'acq4'
            autoInstall: True
    """

    #: VSD Craft routes pages itself, so the base class must not emulate them.
    _hardwarePages = True

    #: VSD Craft exposes no plugin-to-application page-change command -- the shipped
    #: command reference lists setTitle/setImage/setState/set-getSettings/showAlert/
    #: showOk/openUrl/logMessage/sendToPropertyInspector/switchToProfile and nothing
    #: else. The active page is still *reported*, inferred from the ``willAppear``
    #: events that follow a page change, so :meth:`currentPage` and
    #: :attr:`sigPageChanged` are accurate.
    _canSetPage = False

    #: The control class carrying this surface's display API.
    _controlClass = StreamDockControl

    #: A key: a 72x72 display, and text drawn into it. ``output`` is this device's own
    #: vocabulary -- the base class passes it through without opinion -- and says nothing
    #: about a light, because a key has none: :meth:`StreamDockControl.setColor` fills the
    #: display.
    BUTTON_CAPS = {
        'input': {'press': True},
        'output': {'image': render.KEY_SIZE, 'text': True},
    }

    #: A knob: pressable, unbounded relative rotation, 200x100 touch strip.
    DIAL_CAPS = {
        'input': {'press': True, 'mode': 'relative', 'resolution': 1},
        'output': {'image': render.DIAL_SIZE, 'text': True},
    }

    #: ``Settings['role']`` -> acq4 control type. ``'knob'`` is accepted for pages written
    #: by an older generator.
    _TYPE_BY_ROLE = {'button': 'button', 'dial': 'dial', 'knob': 'dial'}

    #: Hardware event name -> (acq4 event, whether it carries a value).
    _EVENT_MAP = {
        'keyDown': 'press',
        'keyUp': 'release',
        'dialDown': 'press',
        'dialUp': 'release',
        'dialRotate': 'move',
        'touchTap': 'touch',
    }

    #: Internal: hop context binding to the GUI thread, where appearance is replayed.
    _sigLink = Qt.Signal(object)

    def __init__(self, deviceManager: acq4.Manager.Manager, config: dict, name: str):
        ControlSurface.__init__(self, deviceManager, config, name)
        if websocket is None:
            raise ImportError(
                "The 'websocket-client' package is required for the StreamDock device. "
                "Install it with: pip install websocket-client"
            )

        buttons = config.get('buttons', {'rows': 2, 'cols': 5})
        dials = config.get('dials', {'rows': 1, 'cols': 3})
        self.spec = profile.GridSpec(
            button_rows=int(buttons.get('rows', 0)),
            button_cols=int(buttons.get('cols', 0)),
            dial_rows=int(dials.get('rows', 0)),
            dial_cols=int(dials.get('cols', 0)),
        )
        self._pageLabel = str(config.get('pageLabel', profile.GENERATOR_TAG))
        self._autoInstall = bool(config.get('autoInstall', True))
        self._deviceUuid = config.get('device', None)
        pages = int(config.get('pages', 1))
        if pages < 1:
            raise ValueError(f"{name}: 'pages' must be at least 1 (got {pages})")

        # Raise here rather than on the startup thread: a layout that does not fit the
        # panel is a configuration error, and silently writing off-panel keys that simply
        # never appear is a far worse failure. Both sources are cheap local file reads, so
        # this does not make construction slow. The check is skipped the very first time,
        # before the plugin has ever published a panel size.
        profile.check_geometry(self.spec, self._currentDeviceUuid(), profile.WS_META_FILE)

        # --- declare the layout ---------------------------------------------------
        self._setPageCount(pages, names=[f'{self._pageLabel} {n + 1}' for n in range(pages)])
        for role, caps in (('button', self.BUTTON_CAPS), ('dial', self.DIAL_CAPS)):
            shape = self.spec.shape(role)
            if 0 in shape:
                continue
            self._addControlBlock(role, caps, keys=self.spec.keys(role), shape=shape)

        # --- link state -----------------------------------------------------------
        # These two dicts are written from the websocket thread and read from both, which
        # is safe because each mutation is a single dict operation. Appearance replay is
        # deferred to the GUI thread over _sigLink.
        self._addressByContext: dict = {}
        self._contextByAddress: dict = {}
        self._sigLink.connect(self._handleLinkEvent, Qt.Qt.QueuedConnection)

        # --- send queue -----------------------------------------------------------
        # Outgoing messages are coalesced per (context, event) and drained by a sender
        # thread, so PNG encoding stays off the GUI thread and a slow link loses frames
        # rather than backing up.
        self._queueLock = threading.Lock()
        self._queued: dict = {}
        self._queueOrder: collections.deque = collections.deque()
        self._queueReady = threading.Event()

        # --- animation ------------------------------------------------------------
        self._animations: dict = {}  # StreamDockControl -> dict(frames, interval, index, last)
        self._animTimer = None

        self._ws = None
        self._register = ('registerPlugin', None)
        self._connected = threading.Event()
        self._stopped = threading.Event()

        # --- link health ----------------------------------------------------------
        # Whether the session acq4 is connected to turned out to be one VSD Craft had
        # forgotten, when it was last asked for keys and produced none.
        self._staleSession = False
        self._bindingTimer = None
        self._lastSessionUuid = None
        self._problemSince = None
        self._lastRecovery = 0.0
        self._lastUndeliverableWarning = 0.0

        self._senderThread = threading.Thread(
            target=self._sendLoop, name=f'{name}-send', daemon=True
        )
        self._senderThread.start()
        self._startupThread = threading.Thread(
            target=self._startup, name=f'{name}-startup', daemon=True
        )
        self._startupThread.start()

    # --- startup ------------------------------------------------------------------------

    def _startup(self):
        """Install, reconcile and connect. Runs on a daemon thread; never blocks startup."""
        # VSD Craft leaves the plugin processes it starts running, and every one of them
        # published ws-meta.json at launch, so an orphan is free to be advertising a
        # session that is gone. Clear all but the newest before anything trusts that file.
        # Failing here is worth reporting but not worth giving up over: the validation in
        # _connectLoop catches whatever this leaves behind.
        try:
            bridges = profile.plugin_processes()
            if len(bridges) > 1:
                self.logger.info(
                    f"{len(bridges)} ACQ4 Stream Dock bridge processes are running; "
                    f"keeping the newest (pid {bridges[-1]['pid']}) and clearing the rest"
                )
                profile.reap_plugin_processes(keep_pid=bridges[-1]['pid'])
            # The search above is the expensive half of validation, so spend it: this is
            # the one place a rival the metadata never mentioned gets reported. Only the
            # newest survived the reap, and the search is handed over rather than redone.
            conflict = profile.meta_problem(profile.read_meta(), bridges=bridges[-1:])
            if conflict is not None:
                self.logger.warning(f"Stream Dock metadata is not yet usable: {conflict}")
        except Exception:
            self.logger.exception("Could not clear orphaned Stream Dock bridge processes")

        try:
            written = install.ensure_plugin() if self._autoInstall else []
            if written and profile.vsd_craft_running():
                # VSD Craft only loads a plugin at launch, so a fresh payload needs a cycle.
                self.logger.info("Plugin payload updated; cycling VSD Craft to load it")
                profile.stop_vsd_craft()

            metaBefore = self._metaMtime()
            result = profile.ensure_pages(
                self.pageCount(),
                spec=self.spec,
                label=self._pageLabel,
                device_uuid=self._deviceUuid,
            )
            self.logger.info(
                f"Stream Dock profile {result['profile']} holds {len(result['pages'])} "
                f"generated page(s) for {result['device']}"
            )
            if result['changed'] or result['restarted'] or written:
                if not profile.wait_for_plugin(newer_than=metaBefore):
                    self.logger.warning(
                        f"The ACQ4 plugin did not republish {profile.WS_META_FILE} after "
                        f"VSD Craft restarted; connecting with whatever address is there."
                    )
        except Exception:
            self.logger.exception(
                "Stream Dock setup failed; trying to connect with the existing profile"
            )
        self._connectLoop()

    def _currentDeviceUuid(self):
        """Best effort device UUID, for the geometry check before the profile is resolved."""
        try:
            return profile.find_device_profile(self._deviceUuid)[1]
        except profile.ProfileError:
            return ''

    @staticmethod
    def _metaMtime() -> float:
        try:
            return profile.WS_META_FILE.stat().st_mtime
        except OSError:
            return 0.0

    # --- connection ---------------------------------------------------------------------

    def _connectLoop(self):
        """Connect and serve events until :meth:`quit`, reconnecting as often as needed.

        ``ws-meta.json`` is re-read **and re-validated** before every attempt: VSD Craft
        cycles its plugins during its own startup and whenever pages are rewritten, and
        hands out a new port and plugin UUID each time. The validation is what keeps acq4
        from registering against a session that no longer exists -- see
        :func:`.profile.meta_problem` for why that failure is otherwise invisible.
        """
        complained = None
        while not self._stopped.is_set():
            meta = profile.read_meta()
            problem = profile.meta_problem(meta)
            if problem is not None:
                now = time.monotonic()
                if self._problemSince is None:
                    self._problemSince = now
                if complained != problem:
                    if not meta:
                        # No file at all: the ordinary state before VSD Craft has ever
                        # started the plugin, rather than a fault to shout about.
                        self.logger.info(
                            f"Waiting for the ACQ4 plugin to publish "
                            f"{profile.WS_META_FILE}. Is VSD Craft running with the ACQ4 "
                            f"plugin installed?"
                        )
                    else:
                        self.logger.warning(
                            f"Not connecting to the Stream Dock software: {problem}. "
                            f"Registering against a plugin session VSD Craft has "
                            f"forgotten would leave the panel blank with no further "
                            f"error, so acq4 will restart VSD Craft if this does not "
                            f"clear by itself."
                        )
                    complained = problem
                if now - self._problemSince >= PROBLEM_GRACE:
                    self._recoverSession(problem)
                self._stopped.wait(RECONNECT_DELAY)
                continue
            complained = None
            self._problemSince = None

            url, uuid = meta['ws'], meta['pluginUUID']
            self._reportSession(meta, uuid)
            self._register = (meta.get('registerEvent') or 'registerPlugin', uuid)
            self.logger.debug(f"Connecting to {url} as {uuid}")
            app = websocket.WebSocketApp(
                url,
                on_open=self._onOpen,
                on_message=self._onMessage,
                on_error=self._onError,
                on_close=self._onClose,
            )
            self._ws = app
            try:
                app.run_forever()  # blocks until the connection closes
            except Exception:
                self.logger.exception("Stream Dock websocket loop failed")
            self._ws = None
            self._onDisconnected()
            if self._staleSession:
                # The watchdog has already waited BINDING_TIMEOUT for keys that never
                # came, so this does not wait out the grace period as well.
                self._staleSession = False
                self._recoverSession(
                    "the Stream Dock software accepted the registration but reported no keys"
                )
            self._stopped.wait(RECONNECT_DELAY)

    def _reportSession(self, meta: dict, uuid: str):
        """Log what the bridge reported about itself, once per plugin session.

        ``bootstrap.js`` records the predecessors it cleared and anything that went wrong
        while clearing them, because its console output goes nowhere a user will look. A
        bridge that could not clear an orphan is the exact condition that makes
        ``ws-meta.json`` ambiguous, so it belongs in the acq4 log.
        """
        if uuid == self._lastSessionUuid:
            return
        self._lastSessionUuid = uuid
        reaped = meta.get('reaped') or []
        if reaped:
            self.logger.info(
                f"The ACQ4 bridge cleared {len(reaped)} stale predecessor(s) on launch: "
                f"{', '.join(str(pid) for pid in reaped)}"
            )
        for message in meta.get('errors') or []:
            self.logger.warning(f"The ACQ4 Stream Dock bridge reported a problem: {message}")

    def _recoverSession(self, reason: str):
        """Restart VSD Craft so it publishes a plugin session acq4 can actually use.

        Rate-limited to :data:`RECOVERY_INTERVAL`: a restart is heavy and visible, and a
        panel that is unusable for some reason this cannot fix must not become a restart
        loop.
        """
        now = time.monotonic()
        if now - self._lastRecovery < RECOVERY_INTERVAL:
            self.logger.debug(
                f"Not restarting VSD Craft again yet; last attempt was "
                f"{now - self._lastRecovery:.0f}s ago"
            )
            return
        self._lastRecovery = now
        self._problemSince = None
        self.logger.warning(f"Restarting VSD Craft to recover the Stream Dock: {reason}")

        metaBefore = self._metaMtime()
        try:
            profile.restart_vsd_craft()
        except Exception:
            self.logger.exception(
                "Could not restart VSD Craft to recover the Stream Dock; the panel will "
                "stay blank until VSD Craft is restarted by hand"
            )
            return
        if profile.wait_for_plugin(newer_than=metaBefore):
            self.logger.info(
                "VSD Craft restarted and its ACQ4 bridge republished the websocket address"
            )
        else:
            self.logger.error(
                f"VSD Craft was restarted but no ACQ4 bridge republished "
                f"{profile.WS_META_FILE} within the timeout; the panel will stay blank "
                f"until the ACQ4 plugin loads. Check that the plugin is enabled in VSD "
                f"Craft."
            )

    def _startBindingWatchdog(self, uuid: str):
        """Arm the check that turns an ignored registration into an error.

        See :meth:`_checkBindings`; this only exists to keep :meth:`_onOpen` short.
        """
        timer = threading.Timer(BINDING_TIMEOUT, self._checkBindings, args=(uuid,))
        timer.name = f'{self.name()}-binding-watchdog'
        timer.daemon = True
        self._bindingTimer = timer
        timer.start()

    def _checkBindings(self, uuid: str):
        """Fail loudly if VSD Craft accepted the registration but reported no keys.

        Until something tries to draw, such a session is indistinguishable from a healthy
        one: the socket is open, the send queue drains, and every appearance is discarded
        for want of a context. This turns that silence into an error and drops the link,
        which sends :meth:`_connectLoop` on to a restart.
        """
        if self._stopped.is_set() or not self._connected.is_set():
            return
        if self._addressByContext:
            return  # keys arrived; the session is real
        self._staleSession = True
        self.logger.error(
            f"Registered with the Stream Dock software as {uuid}, but it reported none of "
            f"this panel's {len(self._controls)} keys within {BINDING_TIMEOUT:g}s. Nothing "
            f"acq4 draws can reach the panel in that state, so the session is being "
            f"dropped and VSD Craft restarted."
        )
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                self.logger.exception("Could not close the unusable Stream Dock connection")

    def _cancelBindingWatchdog(self):
        timer = self._bindingTimer
        self._bindingTimer = None
        if timer is not None:
            timer.cancel()

    def _onOpen(self, ws):
        registerEvent, uuid = self._register
        try:
            ws.send(json.dumps({'event': registerEvent, 'uuid': uuid}))
        except Exception:
            self.logger.exception("Could not register with the Stream Dock software")
            return
        self._connected.set()
        self._queueReady.set()
        self.logger.info(f"Connected to the Stream Dock software as {uuid}")
        self._startBindingWatchdog(uuid)

    def _onError(self, ws, error):
        self.logger.debug(f"Stream Dock websocket error: {type(error).__name__}: {error}")

    def _onClose(self, ws, code, message):
        self.logger.info(f"Stream Dock connection closed (code={code}, msg={message!r})")

    def _onDisconnected(self):
        """Drop every context binding and queued send; keep the controls and their cache.

        Contexts are only valid for one VSD Craft session. The :class:`Control` objects and
        the appearance each one last requested survive, and are replayed when the matching
        address reappears.
        """
        self._cancelBindingWatchdog()
        self._connected.clear()
        self._addressByContext = {}
        self._contextByAddress = {}
        with self._queueLock:
            self._queued.clear()
            self._queueOrder.clear()

    # --- incoming events (websocket thread) ---------------------------------------------

    def _onMessage(self, ws, raw):
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            self.logger.warning(f"Non-JSON message from the Stream Dock software: {raw!r}")
            return
        try:
            self._routeEvent(event)
        except Exception:
            self.logger.exception(f"Error routing Stream Dock event {event.get('event')!r}")

    def _routeEvent(self, event: dict):
        """Turn one protocol event into a base-class call. Runs on the websocket thread."""
        name = event.get('event')
        context = event.get('context') or ''
        payload = event.get('payload') or {}

        if name == 'willAppear':
            self._bindContext(context, payload)
            return
        if name == 'willDisappear':
            address = self._addressByContext.pop(context, None)
            if address is not None:
                self._contextByAddress.pop(address, None)
            return

        address = self._addressByContext.get(context)
        if address is None:
            if name not in IGNORED_EVENTS:
                self.logger.debug(f"Ignoring {name!r} for unbound context {context!r}")
            return

        controlType, page, key = address
        acq4Event = self._EVENT_MAP.get(name)
        if acq4Event is None:
            if name not in IGNORED_EVENTS:
                self.logger.debug(f"Unhandled Stream Dock event {name!r}")
            return

        value = None
        if acq4Event == 'move':
            # The rotation amount is in payload['ticks'], signed. The old ACQ4 code listened
            # for dialPress/dialRelease, which the hardware never sends.
            value = int(payload.get('ticks') or 0)
            if value == 0:
                return
        elif acq4Event == 'touch':
            value = payload.get('tapPos') or payload.get('coordinates')

        self._handleEvent(controlType, key, acq4Event, value=value, page=page)

    def _bindContext(self, context: str, payload: dict):
        """Bind a ``willAppear`` context to the control its ``Settings`` name."""
        address = self._addressFromSettings(payload.get('settings'))
        if address is None:
            return
        self._addressByContext[context] = address
        self._contextByAddress[address] = context
        self._sigLink.emit({'kind': 'appear', 'address': address})

    def _addressFromSettings(self, settings) -> tuple | None:
        """Resolve a key's baked-in ``Settings`` to ``(type, page, key)``, or None.

        None means this key is not ours -- placed by hand in VSD Craft, or left behind by a
        profile that no longer matches the configuration.
        """
        if not isinstance(settings, dict):
            return None
        if settings.get('generator') != profile.GENERATOR_TAG:
            return None  # hand-placed key; it is the user's, not ours
        controlType = self._TYPE_BY_ROLE.get(settings.get('role'))
        page, row, col = settings.get('pageIndex'), settings.get('row'), settings.get('column')
        if controlType is None or page is None or row is None or col is None:
            self.logger.warning(f"Stream Dock key has unusable ACQ4 settings: {settings!r}")
            return None
        address = (controlType, int(page), (int(row), int(col)))
        try:
            self.getControl(*address)
        except KeyError:
            self.logger.warning(
                f"The Stream Dock profile places {controlType} {address[2]} on page "
                f"{address[1]}, which this device's configuration does not offer. The "
                f"profile is stale; restart ACQ4 to have it regenerated."
            )
            return None
        return address

    def _handleLinkEvent(self, event: dict):
        """Repaint a control whose hardware address just reappeared. GUI thread."""
        controlType, page, key = event['address']
        if page != self.currentPage() and 0 <= page < self.pageCount():
            # willAppear only fires for keys on the page now being shown, so a key
            # reporting another page means the hardware changed page.
            self._handlePageChanged(page)
        try:
            self.getControl(controlType, page, key).replayAppearance()
        except Exception:
            self.logger.exception(f"Could not repaint {controlType} {key!r} on page {page}")

    # --- outgoing appearance (GUI thread -> sender thread) ------------------------------

    def _writeImage(self, control: StreamDockControl, image: Qt.QImage):
        self._enqueue(control, 'setImage', {'image': image})

    def _writeText(self, control: StreamDockControl, text, color, background):
        """Draw a key's label into its display, whether or not a colour was asked for.

        Every label goes through :func:`.render.renderTextImage`, so that a key looks the
        same highlighted as unhighlighted. The protocol's ``setTitle`` would be cheaper for
        the uncoloured case, but the panel firmware draws a title at its own fixed size and
        offers no way to match it, so using it there made a label change size and shape at
        the moment it was highlighted -- and left acq4 unable to guarantee that a bound key
        is legible at all.

        The traffic it costs is affordable. A 72x72 label is a base64 PNG of under 2 kB
        (under 4 kB for a 200x100 knob strip) against about 100 bytes for ``setTitle``,
        and the fastest repainting consumer is a :class:`~acq4.devices.Stage.Stage` axis
        readout, throttled to 4 Hz, so a panel full of them is a few tens of kB/s on a
        loopback socket. :meth:`_enqueue` coalesces per ``(control, event)`` and
        :meth:`_send` encodes on the sender thread, so a link that cannot keep up loses
        intermediate labels instead of falling behind -- and the same queue already
        carries whole animation frames at up to 100 Hz.

        ``setTitle`` is still used by :meth:`_writeClear`, which has to blank any native
        title left on a key by the profile or by a hand-built page, and here for a control
        that reports no display at all: nothing acq4 supports is like that, but the
        capability dictionary allows it, and a fixed-size title beats no label.
        """
        try:
            size = control.imageSize()
        except UnsupportedControlFeature:
            self._enqueue(control, 'setTitle', {'title': '' if text is None else str(text)})
            return
        self._writeImage(
            control, render.renderTextImage(text, size, color=color, background=background)
        )

    def _writeClear(self, control: StreamDockControl):
        """Blank a key: black display *and* an empty title.

        Both, because they are two independent things on this hardware -- a black image
        under a leftover title is still a labelled key.
        """
        self._writeImage(control, render.renderSolidImage('k', control.imageSize()))
        self._enqueue(control, 'setTitle', {'title': ''})

    def _enqueue(self, control: Control, event: str, payload: dict):
        """Queue one message for *control*, replacing any of the same kind still pending.

        Last-write-wins coalescing is what makes a slow link degrade frame rate instead of
        accumulating stale frames; the payload is only turned into JSON (and an image into
        a PNG data URI) on the sender thread.
        """
        context = self._contextByAddress.get((control.type, control.page, control.key))
        if context is None:
            # A control on a page the panel is not showing has no context by design, and
            # its appearance is cached for replay when the page comes back. One on the
            # *visible* page should always have a context, so a missing one there means
            # the link is not carrying what acq4 draws -- silently, until now.
            if control.page == self.currentPage():
                self._warnUndeliverable(control)
            return
        with self._queueLock:
            key = (context, event)
            if key not in self._queued:
                self._queueOrder.append(key)
            self._queued[key] = (control, payload)
        self._queueReady.set()

    def _warnUndeliverable(self, control: Control):
        """Warn that a visible control's appearance went nowhere, at most occasionally.

        Rate-limited to :data:`UNDELIVERABLE_WARNING_INTERVAL` because the fastest
        repainting consumer is a :class:`~acq4.devices.Stage.Stage` axis readout at 4 Hz:
        a panel full of them would otherwise bury the log in a fault already described.
        """
        now = time.monotonic()
        if now - self._lastUndeliverableWarning < UNDELIVERABLE_WARNING_INTERVAL:
            return
        self._lastUndeliverableWarning = now
        self.logger.warning(
            f"Cannot draw {control}: it is on the page the panel is showing, but the "
            f"Stream Dock software never reported it, so its appearance is being dropped. "
            f"{len(self._contextByAddress)} of {len(self._controls)} controls are bound."
        )

    def backlog(self) -> int:
        """Return the number of messages waiting to be sent."""
        with self._queueLock:
            return len(self._queueOrder)

    # --- animation ----------------------------------------------------------------------
    # One timer drives every animated control on the panel. This lives here rather than in
    # the base class because a display is the only thing acq4 animates: an X-Keys key's
    # flash state is the hardware's own, set once and forgotten.

    def _startAnimation(self, control: StreamDockControl, frames: list[Qt.QImage], interval: float):
        """Register *control* with this surface's single animation timer."""
        self._animations[control] = {
            'frames': frames,
            'interval': interval,
            'index': 0,
            'last': None,
        }
        if self._animTimer is None:
            self._animTimer = Qt.QTimer(self)
            self._animTimer.timeout.connect(self._animationTick)
        newInterval = max(10, int(1000 * min(a['interval'] for a in self._animations.values())))
        self._animTimer.start(newInterval)

    def _stopAnimation(self, control: StreamDockControl):
        """Take *control* off the animation timer, stopping it if it is the last."""
        self._animations.pop(control, None)
        if not self._animations and self._animTimer is not None:
            self._animTimer.stop()

    def _animationTick(self):
        """Advance every animated control, or skip the turn if a send is still queued.

        Dropping the frame rather than queueing it is what makes a slow link cost frame
        rate instead of accumulating stale frames. Runs on the GUI thread.
        """
        if self.backlog() > 0:
            return
        now = time.perf_counter()
        for control, anim in list(self._animations.items()):
            if anim['last'] is not None and now - anim['last'] < anim['interval']:
                continue
            anim['last'] = now
            frame = anim['frames'][anim['index'] % len(anim['frames'])]
            anim['index'] += 1
            try:
                self._applyAppearance(control, 'image', image=frame)
            except Exception:
                self.logger.exception(f"Failed to draw animation frame on {control}")
                self._stopAnimation(control)

    def _sendLoop(self):
        """Drain the send queue. Runs on its own daemon thread for the device's lifetime."""
        while not self._stopped.is_set():
            self._queueReady.wait(0.5)
            if not self._connected.is_set():
                self._queueReady.clear()
                continue
            with self._queueLock:
                if not self._queueOrder:
                    self._queueReady.clear()
                    continue
                key = self._queueOrder.popleft()
                control, payload = self._queued.pop(key)
            context, event = key
            try:
                self._send(context, event, control, payload)
            except Exception:
                self.logger.exception(f"Could not send {event} for {control}")

    def _send(self, context: str, event: str, control: Control, payload: dict):
        """Encode and transmit one message. Runs on the sender thread."""
        if 'image' in payload:
            # QImage (unlike QPixmap) may be used off the GUI thread, so PNG encoding
            # happens here rather than in the caller.
            size = control.capabilities()['output']['image']
            payload = {'image': render.imageToDataUri(payload['image'], size=size)}
        message = {'event': event, 'context': context, 'payload': {**payload, 'target': 0}}
        ws = self._ws
        if ws is None or not self._connected.is_set():
            return
        try:
            ws.send(json.dumps(message))
        except Exception as exc:
            if self._connected.is_set():
                self.logger.warning(
                    f"Could not send {event} for {control} to the Stream Dock software: "
                    f"{type(exc).__name__}: {exc}"
                )
            else:
                # The link dropped between the check and the send, and the connect loop is
                # already dealing with it. Routine, unlike the case above.
                self.logger.debug(
                    f"Stream Dock send abandoned mid-disconnect: {type(exc).__name__}: {exc}"
                )

    # --- lifecycle ----------------------------------------------------------------------

    def quit(self):
        self._stopped.set()
        self._queueReady.set()
        self._cancelBindingWatchdog()
        if self._animTimer is not None:
            self._animTimer.stop()
        self._animations.clear()
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        ControlSurface.quit(self)
