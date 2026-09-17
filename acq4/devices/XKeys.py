"""P.I. Engineering X-Keys programmable keypads as a :class:`ControlSurface`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyqtgraph as pg

from acq4.devices.ControlSurface import Control, ControlSurface, UnsupportedControlFeature
from acq4.util import Qt

if TYPE_CHECKING:
    import acq4

XKeysDriver = None
pieDevices = None


def __reload__(old):
    # avoid enumerating devices more than once because this seems to generate lots of (potentially dangerous)
    # random input events
    global XKeysDriver, pieDevices, mp
    if 'pieDevices' in old:
        pieDevices = old['pieDevices']
    if 'XKeysDriver' in old:
        XKeysDriver = old['XKeysDriver']


def getDriver():
    global XKeysDriver, mp
    if XKeysDriver is None:
        import acq4.drivers.xkeys as XKeysDriver
    return XKeysDriver


def getDevices():
    global pieDevices, XKeysDriver
    if pieDevices is None:
        # create initial connection to all available devices
        drv = getDriver()
        try:
            pieDevices = [drv.XKeysDevice(h) for h in drv.getDeviceHandles()]
        except mp.NoResultError as e:
            # XKeys can completely lock up the remote process if the device
            # is left in a bad state
            XKeysDriver = None
            raise RuntimeError(
                "No response received from xkeys remote process (try unplugging/replugging your xkeys device)."
            ) from e
    return pieDevices


class UnsupportedColor(UnsupportedControlFeature):
    """Raised by an X-Keys key asked for a colour with a green component.

    A key is lit by one blue and one red LED, so the colours it can show are exactly those
    with no green in them: ``setColor`` lights each LED for whichever of the requested
    colour's blue and red components is non-zero. Green is the one thing two such LEDs
    cannot make, so a request containing it is a consumer mistake rather than something to
    approximate -- nothing here shows a nearby colour and nothing quietly leaves the key
    dark.

    There is deliberately no list of representable colours on this exception, because what
    a key can show is not a list -- it is the rule ``green == 0``. The message states the
    rule, and a consumer that wants to know what was wrong with its request reads
    :attr:`color` and finds green in it.

    Attributes
    ----------
    control : Control or None
        The control that was asked for the colour.
    color : QColor or None
        The colour requested.
    """

    def __init__(self, control: Control | None = None, color=None, message: str | None = None):
        if message is None:
            asked = None if color is None else pg.mkColor(color).name()
            message = (
                f"{control} cannot show {asked}: an X-Keys key is lit by one blue and one"
                f" red LED, so it can show any colour with no green component and no other"
            )
        super().__init__(message)
        self.control = control
        self.color = color


class XKeysControl(Control):
    """One X-Keys key, whose entire output is one blue and one red LED.

    :meth:`setBacklight` is the whole of it: *per key* the hardware switches each LED off,
    on or flashing and offers nothing else -- no brightness, no pixels, no colour beyond
    what two LEDs can make. That is an X-Keys idiosyncrasy and lives here rather than in
    :class:`~acq4.devices.ControlSurface.Control`, because the other surface acq4 drives
    is a grid of little RGB displays with no LEDs to switch at all.

    :meth:`setColor` is a convenience over the same two LEDs for the many consumers that
    think in colours: it lights each LED for whichever of the requested colour's blue and
    red components is non-zero, which covers every colour with no green in it and raises
    :exc:`UnsupportedColor` for the rest. It cannot reach the flash state, and it cannot
    set the two LEDs independently; :meth:`setBacklight` can.

    How bright "on" is, is a property of the whole keypad rather than of one key -- see
    :meth:`XKeys.setIntensity`.

    A dial (the jog wheel, the shuttle ring) is an :class:`XKeysControl` too, and has no
    backlight; both methods refuse it rather than pretending.
    """

    def setBacklight(self, blue: int | None = None, red: int | None = None) -> None:
        """Set this key's two LEDs, each 0=off, 1=on or 2=flash.

        The write is cached like any other appearance, so it survives a software page
        switch, and is coalesced with every other pending backlight write into one driver
        call (see :meth:`XKeys._flushBacklights`).

        Parameters
        ----------
        blue, red : int or None
            0 (off), 1 (on) or 2 (flash). None leaves that LED as it is.

        Raises
        ------
        UnsupportedControlFeature
            If this control has no backlight -- a jog wheel or shuttle ring.
        """
        if not self._capabilities['output'].get('backlight'):
            raise UnsupportedControlFeature(f"{self} has no backlight")
        if blue is None or red is None:
            current = self.surface.dev.backlightState[self.key[0], self.key[1]]
            blue = int(current[0]) if blue is None else blue
            red = int(current[1]) if red is None else red
        self._setAppearance('backlight', blue=int(blue), red=int(red))

    def setColor(self, color) -> None:
        """Light the LED pair that shows *color*.

        Nothing is approximated: a colour this key cannot show raises rather than becoming
        a nearby one or "both off", and raises before anything is cached, so a later
        repaint replays the last colour that did work.

        Parameters
        ----------
        color : QColor or colour spec
            Anything :func:`pyqtgraph.mkColor` accepts. Alpha is ignored, and so is how
            *bright* the components are -- see :meth:`XKeys.backlightForColor`.

        Raises
        ------
        UnsupportedColor
            If *color* has a green component.
        UnsupportedControlFeature
            If this control has no backlight.
        """
        blue, red = self.surface.backlightForColor(color, control=self)
        self.setBacklight(blue, red)

    def _blank(self) -> None:
        """Switch both LEDs off, when this key is released or its page comes up unclaimed.

        A control with no backlight has nothing to switch off, and says so; catching that
        here is what keeps the jog wheel out of a page repaint.
        """
        if self._capabilities['output'].get('backlight'):
            self.setBacklight(0, 0)


class XKeys(ControlSurface):
    """P.I. Engineering X-Keys programmable keypad.

    Every key is a ``'button'`` control addressed by its ``(row, col)`` position and
    exposed as one grid through
    :meth:`~acq4.devices.ControlSurface.ControlSurface.controlGrids`.

    Output
    ------
    A key is lit by one blue and one red LED, and that is the whole of it -- there are no
    pixels and nothing to draw on. The API is :class:`XKeysControl`:
    :meth:`~XKeysControl.setBacklight` sets the two LEDs, each off, on or flashing, and
    :meth:`~XKeysControl.setColor` is a convenience over the same pair for consumers that
    think in colours, lighting each LED for whichever of the requested colour's blue and
    red components is non-zero. That covers every colour with no green in it; green is the
    one thing two such LEDs cannot make, and a request containing it raises
    :exc:`UnsupportedColor` rather than becoming "both off" or "near enough". There is no
    ``setText`` and no ``setImage`` on this surface at all.

    Brightness is *not* per key. :meth:`setIntensity` sets one 0-255 level for every blue
    LED on the keypad and another for every red one, and that is the only brightness control
    the hardware has; a key shows its colour at whatever those two levels currently are.
    ``setColor`` never touches them, so painting one key cannot change how another looks.

    The *flash* state, and lighting the two LEDs independently, are reachable only through
    :meth:`XKeysControl.setBacklight` -- a contract between a consumer and this class,
    which is exactly why it lives here and not on the generic control interface.

    Models with a jog wheel and shuttle ring (the XK-12 JS) additionally offer two
    ``'dial'`` controls, keyed ``'jog'`` and ``'shuttle'``:

    * ``'jog'`` is relative -- the driver reports it only while the wheel is turning, so
      each report is a delta.
    * ``'shuttle'`` is absolute and spring-return, reading 0 at rest.

    Pages are emulated in software by the base class; the hardware has none.

    Configuration options:

    * **index** (int, optional): Device index (0 for the first X-Keys device, etc.).
      Use an out-of-range index to see the available device list in the error message.
      Default: 0

    * **pages** (int, optional): Number of software-emulated pages. Default: 1

    * **intensity** (tuple, optional): ``(blue, red)`` backlight brightness, each 0-255.
      Global to the keypad rather than per key; see :meth:`setIntensity`.
      Default: ``(255, 255)``

    * **shuttleDeadzone** (int, optional): Centre deadzone (evdev ``flat``) for the
      shuttle ring, in raw counts. The ring reads exactly 0 at rest and each detent is one
      count, so a deadzone only swallows real detents; raise it only for a worn ring.
      Default: 0

    Example configuration::

        PIKeyboard:
            driver: 'XKeys'
            index: 0
            pages: 1

    A consumer then claims a key with the canonical control spelling::

        LEDLights:
            driver: 'CoolLEDLightSource'
            sources:
                Blue:
                    control:
                        device: 'PIKeyboard'
                        type: 'button'      # default
                        page: 0             # default
                        key: [7, 8]
    """

    #: Capabilities of every X-Keys key: pressable, with a two-LED backlight. ``output``
    #: is this device's own vocabulary -- the base class passes it through without opinion
    #: -- and ``backlight`` is the only word in it, because the backlight is the only
    #: output a key has.
    BUTTON_CAPS = {
        'input': {'press': True},
        'output': {'backlight': True},
    }

    #: Capabilities of the jog wheel. Relative dials report no range.
    JOG_CAPS = {
        'input': {'press': False, 'mode': 'relative', 'resolution': 1},
        'output': {},
    }

    #: Range of the shuttle ring, as the driver decodes it: one signed byte. The XK-12 JS
    #: hardware only ever produces about -7..7, but nothing clamps it, and a symmetric
    #: range is what puts the ring's rest position exactly at the centre of
    #: ``min``..``max``, where the ``flat`` deadzone is measured from.
    SHUTTLE_RANGE = (-127, 127)

    # internal: coalesce backlight writes onto one setBacklights() per event-loop turn
    _sigFlushBacklights = Qt.Signal()

    _controlClass = XKeysControl

    def __init__(self, man: acq4.Manager.Manager, config: dict, name: str):
        ControlSurface.__init__(self, man, config, name)

        self.dev = self._openDevice(config)
        self.model = self.dev.model
        self.keyshape = self.dev.keyshape

        #: Hardware capabilities reported by the driver: rows, columns, joysticks,
        #: ``'jog/shuttle'`` and touchpad. Unrelated to per-control capabilities, which
        #: live on each :class:`~acq4.devices.ControlSurface.Control`.
        self.deviceCapabilities = self.dev.capabilities.copy()

        # pending per-control backlight writes, flushed together because the driver needs
        # ~60 ms per changed light
        self._pendingBacklights: dict = {}
        self._flushQueued = False
        self._sigFlushBacklights.connect(self._flushBacklights, Qt.Qt.QueuedConnection)

        self._setPageCount(int(config.get('pages', 1)))
        self._addControlBlock('button', self.BUTTON_CAPS, shape=self.keyshape)

        if self.deviceCapabilities.get('jog/shuttle'):
            self._addControl('dial', 'jog', self.JOG_CAPS, name='Jog wheel')
            self._addControl('dial', 'shuttle', self._shuttleCaps(config), name='Shuttle ring')

        self.dev.setCallback(self._stateChanged)
        self.setIntensity(*config.get('intensity', (255, 255)))

    def _openDevice(self, config: dict):
        """Return the driver object for the configured device index.

        Separated from ``__init__`` so that tests can substitute a stand-in without any
        hardware; there is nothing else to override it for.
        """
        index = config.get('index', 0)
        devs = getDevices()
        if len(devs) == 0:
            raise RuntimeError("No X-Keys devices found.")
        try:
            return devs[index]
        except IndexError as e:
            devstr = ", ".join([f"{i}: {devs[i].model}" for i in range(len(devs))])
            raise ValueError(f"No X-Keys with device index {index}. Options are: {devstr}") from e

    def _shuttleCaps(self, config: dict) -> dict:
        """Build the shuttle ring's capability dict from *config*."""
        return {
            'input': {
                'press': False,
                'mode': 'absolute',
                'min': self.SHUTTLE_RANGE[0],
                'max': self.SHUTTLE_RANGE[1],
                'flat': int(config.get('shuttleDeadzone', 0)),
                'fuzz': 0,
                'resolution': 1,
            },
            'output': {},
        }

    # --- native X-Keys extras ---------------------------------------------------------

    def setIntensity(self, b1, b2):
        """Set the brightness of the blue and the red LED bank, each 0-255.

        This is a property of the whole keypad, not of one key: *b1* is how bright every
        lit blue LED on the device is and *b2* the same for red. These 256 levels per
        channel are the only brightness the hardware offers -- per key it gives off, on and
        flashing and nothing in between -- so every key shows its colour at whatever these
        two levels currently are. Nothing in :meth:`XKeysControl.setBacklight` or
        :meth:`XKeysControl.setColor` touches them, because painting one key must not
        change how the rest of the keypad looks.

        Parameters
        ----------
        b1, b2 : int
            Brightness of the blue and the red bank, each 0 (off) to 255 (full).

        Raises
        ------
        ValueError
            If either value falls outside 0-255.
        """
        b1, b2 = int(b1), int(b2)
        for value in (b1, b2):
            if not 0 <= value <= 255:
                raise ValueError(f"Backlight intensity must be 0-255, got {value}")
        self.dev.setIntensity(b1, b2)
        self._intensity = (b1, b2)

    def getIntensity(self) -> tuple[int, int]:
        """Return the ``(blue, red)`` bank brightness in effect, each 0-255.

        The hardware cannot be asked, so this is what :meth:`setIntensity` last wrote --
        starting from the ``intensity`` configuration option.
        """
        return self._intensity

    def getState(self):
        """Return the driver's last known raw device state."""
        return self.dev.state.copy()

    # --- hardware events --------------------------------------------------------------

    def _stateChanged(self, changes):
        """Turn a driver state-change report into control events. Runs on the PIE thread.

        The driver reports key presses *and* releases, a jog delta only while the wheel is
        turning, and a new shuttle position on every change. ``changes['button']`` -- the
        XK-12 JS program switch -- is not exposed as a control and is ignored.
        """
        for key, pressed in changes.get('keys', []):
            self._handleEvent('button', tuple(key), 'press' if pressed else 'release')
        if 'jog' in changes:
            self._handleEvent('dial', 'jog', 'move', value=int(changes['jog']))
        if 'shuttle' in changes:
            self._handleEvent('dial', 'shuttle', 'move', value=int(changes['shuttle']))

    # --- backlights -------------------------------------------------------------------

    @classmethod
    def backlightForColor(cls, color, control: Control | None = None) -> tuple[int, int]:
        """Return the ``(blue, red)`` LED pair that shows *color*.

        Each LED is lit for a non-zero component of *color*, which is everything the
        hardware offers per key: the LEDs go off, on or flashing, never to a brightness. So
        the pair says only *which* LEDs are lit -- how bright they are comes from
        :meth:`setIntensity`, which is global to the keypad.

        Parameters
        ----------
        color : QColor or colour spec
            Anything :func:`pyqtgraph.mkColor` accepts. Alpha is ignored.
        control : Control, optional
            Named in the exception message, for a caller that has one to hand.

        Returns
        -------
        tuple
            ``(blue, red)``, each 0 (off) or 1 (on).

        Raises
        ------
        UnsupportedColor
            If *color* has a green component. That is the only colour an X-Keys key cannot
            show, and there is deliberately no nearest-colour rule: saying so is more
            useful to the consumer than a dark key or a substituted colour.
        """
        red, green, blue = pg.mkColor(color).getRgb()[:3]
        if green > 0:
            raise UnsupportedColor(control=control, color=color)
        return (1 if blue > 0 else 0, 1 if red > 0 else 0)

    def _writeBacklight(self, control: Control, blue: int, red: int):
        """Buffer one key's backlight. Flushed by :meth:`_flushBacklights`.

        The surface's only writer: both :meth:`XKeysControl.setBacklight` and
        :meth:`XKeysControl.setColor` arrive here, because the LED pair *is* the hardware
        state and a colour has already been reduced to one by then.
        """
        self._pendingBacklights[tuple(control.key)] = (int(blue), int(red))
        if not self._flushQueued:
            self._flushQueued = True
            self._sigFlushBacklights.emit()

    def _flushBacklights(self):
        """Send every buffered backlight change in one driver call.

        The driver needs about 60 ms per *changed* light, so a consumer repainting a whole
        bank one control at a time would otherwise block for seconds. Buffering to the end
        of the event-loop turn collapses that into a single ``setBacklights`` whose diff
        touches each light once.
        """
        self._flushQueued = False
        pending, self._pendingBacklights = self._pendingBacklights, {}
        if not pending:
            return
        state = self.dev.backlightState.copy()
        for (row, col), (blue, red) in pending.items():
            state[row, col, 0] = blue
            state[row, col, 1] = red
        try:
            self.dev.setBacklights(state, axis=1)
        except Exception:
            self.logger.exception(f"Failed to write backlights on {self.name()}")

    def quit(self):
        self._pendingBacklights.clear()
        ControlSurface.quit(self)
        self.dev.setBacklightRows(0, 0)
        self.dev.close()
