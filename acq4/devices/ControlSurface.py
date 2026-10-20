"""Device-agnostic control-surface abstraction.

A *control surface* is any device offering assignable physical controls -- buttons, knobs,
jog wheels, shuttle rings, joystick axes -- whose meaning is decided by the rig integrator
rather than by the hardware. :class:`ControlSurface` owns page bookkeeping, control
enumeration and exclusive acquisition; :class:`Control` is the handle a consumer receives,
carrying signals for user action.

Addressing is ``(type, page, key)``:

* ``type`` is an open vocabulary of control kinds. ``'button'`` and ``'dial'`` are defined
  now; a surface may invent more.
* ``page`` is an integer index into the surface's pages (see `Pages`_).
* ``key`` is an **opaque, device-defined** address. It may be a tuple of grid coordinates,
  a string, an integer -- anything hashable. Nothing in this module and nothing in any
  consumer may index into it or assume a shape.

Output
------
Output is entirely the surface's own business, and this module declares **no** output API.
A :class:`Control` carries identity, capabilities, a value and its input signals, and
nothing else. What a control can be made to show, and how to ask for it, is a contract
between the consumer and that surface's :class:`Control` subclass: an X-Keys key's two
LEDs through :meth:`acq4.devices.XKeys.XKeysControl.setBacklight`, a Stream Dock key's
display through :meth:`acq4.devices.StreamDock.streamdock.StreamDockControl.setImage` and
its neighbours. A consumer asks :meth:`Control.capabilities` what a control offers -- or
simply whether it has the method it means to call -- and then speaks that surface's own
language. There is deliberately no lowest common denominator spanning the two, because a
keypad whose entire output is one blue and one red LED per key and a grid of little RGB
displays have almost nothing in common to generalise from; a vocabulary stretched over
both only makes every consumer reason about a fiction.

What this module does provide is the machinery any output needs and none of the vocabulary.
:meth:`Control._setAppearance` takes an **opaque** ``(op, kwds)`` request, caches it and
dispatches it to the surface's ``_write<Op>`` method. The cache is replayed when a hardware
address reappears (:meth:`Control.replayAppearance`) and when a software page becomes
active (:meth:`ControlSurface._repaintPage`), and a write to a control on an inactive
software page is suppressed until then. Nothing here knows what any ``op`` means. Blanking
is the one thing this module needs to ask for by name -- on release, and for an unclaimed
control when its page comes up -- and it asks through :meth:`Control._blank`, which does
nothing at all unless a subclass overrides it.

Input, by contrast, *is* generic: every surface reports presses, releases, dial motion and
touches, and reports them through the same four signals.

.. _Pages:

Pages
-----
Pages are a base-class feature. By default the base class *emulates* them in software:
N logical pages are multiplexed onto one physical control set, hardware events are routed
only to the active page's controls, and controls repaint from their cached appearance when
the page changes. A subclass whose hardware routes pages itself sets ``_hardwarePages =
True``; the base class then only reports and sets the page and leaves routing alone.

How many pages a surface has is fixed when it is constructed -- it comes from the device's
configuration (``pages: N``) -- so a consumer may cache :meth:`ControlSurface.pageCount`
and address any page by index for the life of the device.

Threads
-------
Every :class:`Control` signal is emitted on the GUI thread. Subclasses call
:meth:`ControlSurface._handleEvent` from whatever thread their hardware runs on; the base
class hops to the GUI thread over an internal queued-connection signal. Subclasses never
need to think about it.

Config ordering
---------------
A surface must be declared **before** its clients in ``devices.cfg``, matching the existing
``parentDevice:`` convention -- devices are constructed in file order, and
:func:`acquireControlFromConfig` resolves the surface with ``getManager().getDevice(name)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import numpy as np

from acq4.devices.Device import Device
from acq4.logging_config import get_logger
from acq4.util import Qt

if TYPE_CHECKING:
    import acq4

__all__ = [
    'Control',
    'ControlInUse',
    'ControlSurface',
    'ControlSurfaceError',
    'UnknownControl',
    'UnsupportedControlFeature',
    'acquireControlFromConfig',
    'parseControlConfig',
]

logger = get_logger(__name__)


# ----------------------------------------------------------------------------- exceptions


class ControlSurfaceError(Exception):
    """Base class for all control-surface errors."""


class ControlInUse(ControlSurfaceError):
    """Raised when a control is claimed while it is already held.

    A control is claimed once and stays claimed until released, so this is raised against
    *every* second claim -- including one from the owner that already holds it.

    Attributes
    ----------
    control : Control or None
        The control that could not be claimed.
    owner : object or None
        The owner currently holding it.
    """

    def __init__(self, control: Control | None = None, owner=None, message: str | None = None):
        if message is None:
            message = f"{control} is already claimed by {owner!r}"
        super().__init__(message)
        self.control = control
        self.owner = owner


class UnknownControl(ControlSurfaceError, KeyError):
    """Raised for an address the surface does not offer.

    Subclasses :exc:`KeyError` so that ``except KeyError`` -- the behaviour specified for
    an unknown address -- catches it.
    """


class UnsupportedControlFeature(ControlSurfaceError):
    """Raised when a control cannot do what it was asked to do.

    Nothing in this module raises it, because nothing in this module asks a control for
    anything. It lives here so that a consumer prepared to lose an indicator on some
    surfaces has one exception to catch whatever surface it is talking to -- an X-Keys key
    asked for a colour with green in it, a control asked to draw text where there is
    nothing to draw on. A surface whose limits are worth describing raises a subclass of
    its own, as :exc:`acq4.devices.XKeys.UnsupportedColor` does.
    """


# -------------------------------------------------------------------------------- Control


class Control(Qt.QObject):
    """A handle on one physical control of a :class:`ControlSurface`.

    Controls are created by the surface for *every* addressable address up front, unowned
    and never yet drawn on, so that a consumer can inspect :meth:`capabilities` before
    claiming anything. Never construct one directly; use :meth:`ControlSurface.getControl`
    or :meth:`ControlSurface.acquireControl`.

    This class declares no output API; what a control can be asked to show is defined by
    the surface's own :class:`Control` subclass. See the module docstring.

    Attributes
    ----------
    surface : ControlSurface
        The surface this control belongs to.
    type : str
        Control kind, e.g. ``'button'`` or ``'dial'``.
    page : int
        Page index this control lives on; fixed when the surface declares its layout.
    key : hashable
        Opaque, device-defined address within ``(type, page)``. Do not interpret it.
    owner : object or None
        Whatever was passed to :meth:`acquire`, or None while unclaimed. Ownership *is*
        the claim -- :meth:`acquire` requires a non-None owner -- so ``owner is not None``
        means exactly "claimed".
    name : str or None
        Optional semantic name, for logs and UI only -- never used for addressing.

    Signals
    -------
    sigPressed(control)
        The control was pressed.
    sigReleased(control)
        The control was released.
    sigMoved(control, value)
        A dial moved. For ``mode: 'relative'`` *value* is a delta; for
        ``mode: 'absolute'`` it is the new absolute value in the device's own units.
    sigTouched(control, value)
        The control's touch surface was touched. *value* is device-defined and may be None.
    """

    sigPressed = Qt.Signal(object)  # control
    sigReleased = Qt.Signal(object)  # control
    sigMoved = Qt.Signal(object, object)  # control, delta (relative) or value (absolute)
    sigTouched = Qt.Signal(object, object)  # control, device-defined payload

    def __init__(
        self,
        surface: ControlSurface,
        type: str,
        page: int,
        key,
        capabilities: dict,
        name: str | None = None,
    ):
        Qt.QObject.__init__(self)
        self.surface = surface
        self.type = type
        self.page = page
        self.key = key
        self.name = name
        self.owner = None
        self._capabilities = capabilities

        # last appearance requested by the owner, so that a surface can repaint this
        # control when its hardware address reappears (see replayAppearance)
        self._appearance = None  # None | (op, kwds)

        # dial state
        self._value = None  # last value reported to consumers
        self._rawValue = None  # last raw value, for fuzz comparison

    # --- identity / capabilities ------------------------------------------------------

    def capabilities(self) -> dict:
        """Return this control's capabilities, split by direction.

        Capabilities belong to the control rather than the surface, because they differ by
        type and may differ between controls of one type.

        Returns
        -------
        dict
            ``{'input': {...}, 'output': {...}}``.

            ``input`` is a shared vocabulary, because input really is generic. Recognised
            keys are ``press`` (bool), and for dials ``mode``
            (``'relative'`` | ``'absolute'``), ``resolution``, plus for absolute dials the
            evdev-style ``min``, ``max``, ``flat`` (centre deadzone) and ``fuzz`` (noise
            floor below which a change is ignored).

            ``output`` is the **surface's own vocabulary**, passed through untouched. This
            module has no opinion about its contents and blesses no keys: an X-Keys key
            says ``{'backlight': True}`` and a Stream Dock key says
            ``{'image': (72, 72), 'text': True}``, because those are the things those two
            devices do. A consumer reads it to decide what to ask of a control, alongside
            or instead of checking for the device-specific method it means to call.
        """
        return {
            'input': dict(self._capabilities['input']),
            'output': dict(self._capabilities['output']),
        }

    def value(self):
        """Return the most recent value reported by this control, or None.

        For an absolute dial this is its position, after ``flat`` handling. For a relative
        dial it is the last delta, which is rarely useful.
        """
        return self._value

    # --- acquisition ------------------------------------------------------------------

    def acquire(self, owner) -> Control:
        """Claim this control exclusively for *owner*.

        A control can be claimed once and stays claimed until :meth:`release`. A second
        claim raises, whoever makes it -- the current owner included: an owner that cannot
        tell whether it already holds a control has a bookkeeping bug of its own, and
        tolerating the second claim would only move that accounting into every consumer.

        Parameters
        ----------
        owner : object
            Whatever holds the control -- the device or window that claimed it. Required,
            and not None: ownership is the claim, so an anonymous claim would leave the
            control looking free and freely re-acquirable.

        Raises
        ------
        ControlInUse
            If this control is already claimed, by any owner including *owner*.
        ValueError
            If *owner* is None.
        """
        if owner is None:
            raise ValueError(f"{self} cannot be acquired without an owner")
        if self.owner is not None:
            raise ControlInUse(self, self.owner)
        self.owner = owner
        return self

    def release(self) -> None:
        """Release this control, severing the owner's slots and blanking what it showed.

        Ownership is exclusive, so a released owner must stop hearing this control: the
        four input signals below are the base class's, so they are the base class's to
        disconnect. Without that, an owner that forgets to disconnect for itself keeps
        driving a key the next owner now holds, and one press reaches both.

        Blanking goes through :meth:`_blank`, because this class has no idea what an
        output is; on a surface whose :class:`Control` subclass does not override that
        hook, the next owner inherits the last one's indicator. A failure to blank is
        logged rather than raised: the control is freed either way, and an owner shutting
        down has nothing useful to do about it. It is also blanked after the disconnect,
        so a surface that cannot blank still hands over a control nobody else is on.
        """
        self.owner = None
        for signal in (self.sigPressed, self.sigReleased, self.sigMoved, self.sigTouched):
            try:
                signal.disconnect()
            except TypeError:
                # nothing was connected, which is the state disconnect() is asking for
                pass
        try:
            self._blank()
        except Exception:
            self.surface.logger.exception(f"Failed to blank {self} on release")

    # --- output (subclass territory) --------------------------------------------------

    def _blank(self) -> None:
        """Switch off whatever this control shows. Nothing, by default.

        This is the *only* output operation the base class asks for by name, and the
        default does nothing because a generic control has no output to switch off. A
        :class:`Control` subclass with output overrides it -- an X-Keys key turns both its
        LEDs off, a Stream Dock key blanks its display -- normally by going through
        :meth:`_setAppearance`, so that the blank is cached and replayed like any other
        appearance.

        Called by :meth:`release`, and by :meth:`ControlSurface._repaintPage` for a
        control that has nothing cached when its software page becomes active, so that the
        previous page's graphics do not linger under the new page's unclaimed controls.
        """

    # --- appearance caching -----------------------------------------------------------

    def cachedAppearance(self) -> Optional[tuple]:
        """Return this control's last requested appearance as ``(op, kwds)``, or None.

        *op* names the surface's ``_write*`` method that drew it -- ``'image'``,
        ``'text'``, ``'color'``, ``'clear'``, or whatever a subclass has added -- and
        *kwds* are that method's arguments.

        Surfaces whose hardware addresses come and go -- Stream Dock, where the profile
        application may restart -- use this, or the more convenient
        :meth:`replayAppearance`, to repaint a control when its address reappears.
        """
        return self._appearance

    def replayAppearance(self) -> None:
        """Re-send this control's cached appearance to the hardware.

        A no-op if nothing has ever been drawn on this control. Safe to call whenever a
        hardware address (re)appears or a software page becomes active. A subclass with
        state the opaque cache does not cover -- a running animation, say -- extends this
        rather than replacing it.
        """
        if self._appearance is not None:
            op, kwds = self._appearance
            self.surface._applyAppearance(self, op, **kwds)

    def _setAppearance(self, op: str, **kwds) -> None:
        """Cache an appearance request and apply it if the control is live.

        This is how a :class:`Control` subclass implements an output call: *op* names a
        ``_write<Op>`` method on the surface (``'backlight'`` -> ``_writeBacklight``) and
        *kwds* are its arguments. The pair is opaque to the base class, which never looks
        inside either. Going through here rather than calling the surface directly buys the
        call caching for replay when a hardware address reappears, suppression while the
        control's software page is inactive, and whatever coalescing the surface does.

        The request is cached only once the surface has accepted it, so a writer that
        rejects it leaves the previous appearance in place instead of poisoning the cache
        with something that will fail again on replay.
        """
        self.surface._applyAppearance(self, op, **kwds)
        self._appearance = (op, kwds)

    def __repr__(self):
        name = '' if self.name is None else f' {self.name!r}'
        surface = self.surface.name()
        return f'<Control{name} {surface}.{self.type} page={self.page} key={self.key!r}>'


# ------------------------------------------------------------------------- ControlSurface


class _ControlBlock:
    """Declared layout of a group of controls repeated on every page.

    Internal bookkeeping for :meth:`ControlSurface._addControlBlock`.
    """

    def __init__(self, type: str, keys, capabilities, shape=None, names=None, grid: bool = True):
        self.type = type
        self.keys = list(keys)
        self.capabilities = capabilities
        self.shape = shape
        self.names = names
        self.grid = grid

    def capabilitiesFor(self, key) -> dict:
        caps = self.capabilities(key) if callable(self.capabilities) else self.capabilities
        return _normalizeCapabilities(self.type, key, caps)

    def nameFor(self, key):
        if self.names is None:
            return None
        if callable(self.names):
            return self.names(key)
        return self.names.get(key)


def _normalizeCapabilities(controlType, key, caps) -> dict:
    """Validate and copy a capability dict."""
    if not isinstance(caps, dict):
        raise TypeError(
            f"Capabilities for {controlType} {key!r} must be a dict, " f"not {type(caps).__name__}"
        )
    unknown = set(caps) - {'input', 'output'}
    if unknown:
        raise ValueError(
            f"Capabilities for {controlType} {key!r} have unknown top-level key(s) "
            f"{sorted(unknown)}; expected 'input' and/or 'output'"
        )
    caps = {'input': dict(caps.get('input', {})), 'output': dict(caps.get('output', {}))}
    inp = caps['input']
    if controlType == 'dial':
        mode = inp.get('mode')
        if mode not in ('relative', 'absolute'):
            raise ValueError(
                f"Dial {key!r} must declare input mode 'relative' or 'absolute', not {mode!r}"
            )
        if mode == 'absolute':
            missing = {'min', 'max'} - set(inp)
            if missing:
                raise ValueError(f"Absolute dial {key!r} is missing {sorted(missing)}")
        else:
            extra = {'min', 'max', 'flat'} & set(inp)
            if extra:
                raise ValueError(
                    f"Relative dial {key!r} must report no range, but has {sorted(extra)}"
                )
    return caps


class ControlSurface(Device):
    """Base class for devices offering assignable physical controls.

    A surface owns page bookkeeping, control enumeration and exclusive acquisition. It
    creates a :class:`Control` for every addressable ``(type, page, key)`` up front, blank
    and unowned, so consumers can inspect capabilities before claiming.

    Subclass responsibilities
    -------------------------
    1. Declare the layout in ``__init__`` with :meth:`_setPageCount` *first* and then
       :meth:`_addControlBlock` -- a block is built on the pages that exist when it is
       declared, so that order is enforced and the wrong one raises.
    2. Call :meth:`_handleEvent` from the hardware thread when the user does something.
       The base class hops to the GUI thread.
    3. Implement a ``_write<Op>(control, ...)`` method for every appearance operation its
       controls ask for through :meth:`Control._setAppearance`. Which operations exist is
       up to the surface: the base class routes them by name, caches the last one and
       suppresses writes to a control on an inactive software page, without knowing what
       any of them mean.
    4. Set ``_hardwarePages = True`` and implement :meth:`_setHardwarePage` if the hardware
       routes pages itself. Otherwise pages are emulated in software for free.
    5. Set ``_controlClass`` to a :class:`Control` subclass carrying the surface's output
       API, since the generic :class:`Control` declares none, and override
       :meth:`Control._blank` on it so that releasing a control and switching software
       page switch its output off.
    6. Set ``_canSetPage = False`` if the hardware reports its active page but cannot be
       commanded to change it, so that :meth:`setCurrentPage` raises rather than lying.

    This class is abstract; see :class:`acq4.devices.MockControlSurface.MockControlSurface`
    for a complete, hardware-free implementation.
    """

    sigPageChanged = Qt.Signal(object, object)  # self, page

    # internal: hop hardware events to the GUI thread
    _sigEvent = Qt.Signal(object)  # event dict

    #: Set True in a subclass whose hardware routes pages itself, so that the base class
    #: only reports and sets the current page instead of emulating pages in software.
    _hardwarePages = False

    #: The class used to instantiate this surface's controls. This is where a surface's
    #: output API lives -- ``XKeysControl.setBacklight``, ``StreamDockControl.setImage`` --
    #: because the generic :class:`Control` declares none.
    _controlClass: type[Control] | None = None

    #: Set False in a subclass that can report the active page but cannot be commanded to
    #: change it, so that :meth:`setCurrentPage` raises instead of pretending. Reading
    #: :meth:`currentPage` and reacting to :attr:`sigPageChanged` still work.
    _canSetPage = True

    def __init__(self, deviceManager: acq4.Manager.Manager, config: dict, name: str):
        Device.__init__(self, deviceManager, config, name)
        self._controls: dict = {}  # (type, page, key) -> Control
        self._gridsByPage: list = [[]]  # indexed by page -> list[ndarray]
        self._pageNames: list = ['Page 1']
        self._pageCountDeclared = False  # whether _setPageCount has been called
        self._currentPage = 0

        # use a queued connection so that subclasses may call _handleEvent from any thread
        # and every Control signal is still emitted on the GUI thread
        self._sigEvent.connect(self._dispatchEvent, Qt.Qt.QueuedConnection)

    # --- layout declaration (for subclasses) ------------------------------------------

    def _setPageCount(self, count, names=None):
        """Declare how many pages this surface has.

        **Call this before declaring any controls**, and only once. Pages exist only as
        declared here -- a surface's page count comes from its configuration (``pages: N``
        in ``devices.cfg``) and never changes afterwards -- and :meth:`_addControlBlock`
        builds its controls on every page that exists at the moment it is called. So
        declaring the page count after a block would leave that block present only on page
        0, which is why both orderings below raise rather than quietly producing a surface
        with missing controls.

        A surface that never calls this has exactly one page.

        Parameters
        ----------
        count : int
            Number of pages; at least 1.
        names : list, optional
            Page names; defaults to ``'Page 1'``, ``'Page 2'``, ...

        Raises
        ------
        ValueError
            If *count* is less than 1.
        RuntimeError
            If any control has already been declared, or if the page count has already
            been declared.
        """
        count = int(count)
        if count < 1:
            raise ValueError("A control surface must have at least one page")
        if self._controls:
            raise RuntimeError(
                f"{self.name()} declared controls before its page count; call "
                "_setPageCount() before _addControlBlock() or the blocks already declared "
                "would exist only on page 0"
            )
        if self._pageCountDeclared:
            raise RuntimeError(
                f"{self.name()} already declared a page count of {self.pageCount()}; the "
                "page count of a control surface is declared once, at construction"
            )
        self._pageCountDeclared = True
        self._pageNames = [f'Page {page + 1}' for page in range(count)]
        self._gridsByPage = [[] for _ in range(count)]
        if names is not None:
            for page, pageName in enumerate(names[:count]):
                self.setPageName(page, pageName)

    def _addControlBlock(
        self, type: str, capabilities, keys=None, shape=None, names=None, grid: bool | None = None
    ) -> list:
        """Declare a group of controls that exists on every page.

        The block's controls are built immediately, on every page that exists now, so
        :meth:`_setPageCount` must already have been called; calling it afterwards raises
        rather than leaving this block on page 0 alone.

        Parameters
        ----------
        type : str
            Control kind, e.g. ``'button'`` or ``'dial'``. Open vocabulary.
        capabilities : dict or callable
            Capability dict (see :meth:`Control.capabilities`) shared by the whole block,
            or a callable taking a key and returning one.
        keys : sequence, optional
            The device-defined keys in this block. Each must be hashable and unique within
            ``(type, page)``. If omitted, *shape* must be given and keys default to
            ``(row, col)`` tuples.
        shape : tuple, optional
            ``(rows, cols)`` if this block is rectangular. Makes the block appear in
            :meth:`controlGrids`. *keys* if given are taken in row-major order.
        names : dict or callable, optional
            Optional semantic names, by key.
        grid : bool, optional
            Whether to expose this block through :meth:`controlGrids`. Defaults to True
            when *shape* is given.

        Returns
        -------
        list
            The keys declared, in order.
        """
        if keys is None:
            if shape is None:
                raise ValueError("_addControlBlock needs either keys or shape")
            keys = [(row, col) for row in range(shape[0]) for col in range(shape[1])]
        else:
            keys = list(keys)
            if shape is not None and len(keys) != int(np.prod(shape)):
                raise ValueError(f"{len(keys)} keys given for a block of shape {shape}")
        for key in keys:
            try:
                hash(key)
            except TypeError:
                raise TypeError(
                    f"Control key {key!r} is not hashable; use a tuple rather than a list"
                )
        if grid is None:
            grid = shape is not None

        block = _ControlBlock(type, keys, capabilities, shape=shape, names=names, grid=grid)
        for page in range(self.pageCount()):
            self._buildBlock(block, page)
        return keys

    def _addControl(self, type: str, key, capabilities, name: str | None = None) -> Control:
        """Declare a single control, present on every page.

        Convenience wrapper around :meth:`_addControlBlock` for a control that is not part
        of a grid -- a joystick axis, a named jog wheel.
        """
        self._addControlBlock(
            type, capabilities, keys=[key], names={key: name} if name else None, grid=False
        )
        return self.getControl(type, self._currentPage, key)

    def _buildBlock(self, block: _ControlBlock, page: int):
        """Instantiate *block*'s controls on *page* and register its grid."""
        controls = []
        for key in block.keys:
            address = (block.type, page, key)
            if address in self._controls:
                raise ValueError(f"Control {address} is already declared on {self.name()}")
            controlClass = self._controlClass or Control
            control = controlClass(
                self, block.type, page, key, block.capabilitiesFor(key), name=block.nameFor(key)
            )
            self._controls[address] = control
            controls.append(control)
        if block.grid and block.shape is not None:
            grid = np.empty(block.shape, dtype=object)
            grid.flat[:] = controls
            self._gridsByPage[page].append(grid)

    # --- enumeration ------------------------------------------------------------------

    def controls(self, page=None) -> dict[str, list]:
        """Return the addressable control keys on *page*, grouped by type.

        Parameters
        ----------
        page : int, optional
            Defaults to the current page.

        Returns
        -------
        dict
            e.g. ``{'button': [(0, 0), (0, 1), ...], 'dial': ['jog', 'shuttle']}``. The
            keys are opaque device addresses; do not interpret them.
        """
        page = self._checkPage(page)
        out: dict = {}
        for controlType, ctlPage, key in self._controls:
            if ctlPage == page:
                out.setdefault(controlType, []).append(key)
        return out

    def allControls(self, page=None) -> list[Control]:
        """Return every :class:`Control` on *page* (default: the current page)."""
        page = self._checkPage(page)
        return [c for (_, ctlPage, _), c in self._controls.items() if ctlPage == page]

    def getControl(self, type, page, key) -> Control:
        """Return the :class:`Control` at ``(type, page, key)`` without claiming it.

        Raises
        ------
        KeyError
            If this surface offers no such address.
        """
        try:
            return self._controls[(type, page, key)]
        except KeyError:
            raise UnknownControl(f"{self.name()} has no {type} {key!r} on page {page}") from None

    def acquireControl(self, type, page, key, owner) -> Control:
        """Claim the control at ``(type, page, key)`` exclusively for *owner*.

        Raises
        ------
        KeyError
            If this surface offers no such address.
        ControlInUse
            If the control is already claimed; see :meth:`Control.acquire`.
        ValueError
            If *owner* is None.
        """
        return self.getControl(type, page, key).acquire(owner)

    def releaseControl(self, control: Control):
        """Release *control*, blanking it and making it available to other owners."""
        control.release()

    def controlGrids(self, page=None) -> list[np.ndarray]:
        """Return object arrays of :class:`Control`, one per rectangular block.

        e.g. ``[array([[button00, button01, ...], ...]), array([[dial0, dial1, dial2]])]``.
        A surface with no grid layout -- a joystick -- returns ``[]``.

        The arrays are plain numpy, so the common "claim these columns" pattern is just
        slicing::

            grid = surface.controlGrids(page=0)[0]
            for ctl in grid[:, 4:4 + n].flat:
                ctl.acquire(self)
        """
        page = self._checkPage(page)
        return list(self._gridsByPage[page])

    # --- pages ------------------------------------------------------------------------

    def pageCount(self) -> int:
        """Return the number of pages this surface has."""
        return len(self._pageNames)

    def pageNames(self) -> list[str]:
        """Return the page names, indexed by page."""
        return list(self._pageNames)

    def setPageName(self, page, name):
        """Set the display name of *page*."""
        self._pageNames[self._checkPage(page, allowNone=False)] = str(name)

    def currentPage(self) -> int:
        """Return the index of the active page."""
        return self._currentPage

    def canSetCurrentPage(self) -> bool:
        """Whether :meth:`setCurrentPage` can command a page change on this surface.

        False on hardware that reports its active page but offers no way to set it. Check
        this before offering the user a page control; :meth:`currentPage` and
        :attr:`sigPageChanged` work either way.
        """
        return self._canSetPage

    def setCurrentPage(self, page):
        """Make *page* active.

        With software pages this re-routes events and repaints every control from its
        cached appearance, then emits :attr:`sigPageChanged` -- even if *page* was already
        current, so a consumer can rely on the signal to resynchronize.

        With hardware pages the switch is only requested here. The active page is not
        updated and :attr:`sigPageChanged` is not emitted until the hardware reports the
        change through :meth:`_handlePageChanged`, so that this surface never claims a page
        the panel is not actually showing.

        Raises
        ------
        IndexError
            If *page* is out of range.
        ValueError
            If *page* is None.
        NotImplementedError
            If :meth:`canSetCurrentPage` is False. Checked after *page* is validated.
        """
        page = self._checkPage(page, allowNone=False)
        if not self.canSetCurrentPage():
            raise NotImplementedError(
                f"{self.name()} ({type(self).__name__}) cannot be commanded to change page; "
                f"it reports the active page but does not accept a page change."
            )
        if self._hardwarePages:
            self._setHardwarePage(page)
            return
        previous = self._currentPage
        self._currentPage = page
        if page != previous:
            self._repaintPage(page)
        self.sigPageChanged.emit(self, page)

    def _repaintPage(self, page: int):
        """Repaint every control on *page*.

        Called when a software page becomes active. Because the pages of an emulated
        surface share one set of physical controls, a control with a cached appearance is
        replayed and one without is blanked -- otherwise the previous page's graphics would
        linger under the new page's unclaimed controls. Blanking goes through
        :meth:`Control._blank`, so what it means, and whether there is anything to blank
        at all, stays the control's business rather than becoming this class's opinion.
        """
        for control in self.allControls(page):
            try:
                if control.cachedAppearance() is not None:
                    control.replayAppearance()
                else:
                    control._blank()
            except Exception:
                self.logger.exception(f"Failed to repaint {control}")

    def _setHardwarePage(self, page: int):
        """Ask the hardware to switch to *page*. Only called when ``_hardwarePages``."""
        raise NotImplementedError(f"{type(self).__name__} must implement _setHardwarePage")

    def _checkPage(self, page, allowNone=True) -> int:
        if page is None:
            if not allowNone:
                raise ValueError("A page index is required here")
            return self._currentPage
        page = int(page)
        if not 0 <= page < self.pageCount():
            raise IndexError(f"{self.name()} has no page {page} (page count is {self.pageCount()})")
        return page

    # --- events (called by subclasses, from any thread) -------------------------------

    def _handleEvent(self, type, key, event, value=None, page=None):
        """Report a hardware event. Safe to call from any thread.

        The event is queued to the GUI thread, where it is routed to the matching
        :class:`Control` and turned into a signal. Subclasses call this and nothing else.

        Parameters
        ----------
        type : str
            Control type, e.g. ``'button'`` or ``'dial'``.
        key : hashable
            Device-defined key within ``(type, page)``.
        event : str
            One of ``'press'``, ``'release'``, ``'move'``, ``'touch'``.
        value : optional
            For ``'move'``: a delta on a relative dial, an absolute value on an absolute
            dial. For ``'touch'``: a device-defined payload.
        page : int, optional
            Only for a surface with ``_hardwarePages``, which knows which page the event
            came from. With software pages the event belongs to the active page and this
            must be left None.
        """
        if event not in ('press', 'release', 'move', 'touch'):
            raise ValueError(f"Unknown control event {event!r}")
        self._sigEvent.emit(
            {
                'kind': 'control',
                'type': type,
                'key': key,
                'event': event,
                'value': value,
                'page': page,
                # Which software page was showing when this happened. Recorded here
                # rather than read in the queued callback because setCurrentPage() moves
                # the active page on the GUI thread, which can happen between an event
                # being queued and that callback running -- and then a press on the key
                # the operator actually touched invokes whatever the next page binds at
                # the same address. A surface with hardware pages reports its own page
                # changes through this same queue, in order, so it has nothing to record.
                'activePage': None if self._hardwarePages else self._currentPage,
            }
        )

    def _handlePageChanged(self, page):
        """Report that the hardware switched to *page*. Safe to call from any thread."""
        self._sigEvent.emit({'kind': 'page', 'page': page})

    def _dispatchEvent(self, event):
        """Route a queued hardware event. Always runs on the GUI thread."""
        try:
            if event['kind'] == 'page':
                self._dispatchPageEvent(event)
            else:
                self._dispatchControlEvent(event)
        except Exception:
            self.logger.exception(f"Error handling control surface event {event}")

    def _dispatchPageEvent(self, event):
        page = event['page']
        if page == self._currentPage:
            return
        self._currentPage = self._checkPage(page, allowNone=False)
        if not self._hardwarePages:
            self._repaintPage(self._currentPage)
        self.sigPageChanged.emit(self, self._currentPage)

    def _dispatchControlEvent(self, event):
        page = event['page']
        if page is None:
            page = event['activePage']
            if page is None:
                page = self._currentPage
        elif not self._hardwarePages and page != self._currentPage:
            # software pages route to the active page only
            return
        try:
            control = self.getControl(event['type'], page, event['key'])
        except KeyError:
            self.logger.warning(
                f"{self.name()} reported an event for unknown control "
                f"{event['type']} {event['key']!r} on page {page}"
            )
            return

        name = event['event']
        if name == 'press':
            control.sigPressed.emit(control)
        elif name == 'release':
            control.sigReleased.emit(control)
        elif name == 'touch':
            control.sigTouched.emit(control, event['value'])
        elif name == 'move':
            value = self._filterMove(control, event['value'])
            if value is not None:
                control.sigMoved.emit(control, value)

    def _filterMove(self, control: Control, value):
        """Apply absolute-dial fuzz and flat handling. Return None to suppress the event.

        Relative dials pass their delta through untouched. For an absolute dial, a change
        smaller than ``fuzz`` from the last raw reading is suppressed, and a value within
        ``flat`` of the centre of ``min``..``max`` reads as exactly the centre.
        """
        caps = control._capabilities['input']
        if caps.get('mode') != 'absolute':
            control._value = value
            return value

        fuzz = caps.get('fuzz', 0) or 0
        if control._rawValue is not None and fuzz > 0 and abs(value - control._rawValue) < fuzz:
            return None
        control._rawValue = value

        flat = caps.get('flat', 0) or 0
        center = (caps['min'] + caps['max']) / 2
        if flat > 0 and abs(value - center) <= flat:
            value = center
        control._value = value
        return value

    # --- appearance routing -----------------------------------------------------------

    def _applyAppearance(self, control: Control, op: str, **kwds) -> bool:
        """Send one cached appearance request to the hardware.

        *op* names the ``_write<Op>`` method that performs it, so the set of appearance
        operations is entirely the surface's: it implements a writer per operation its
        controls offer and gets caching, replay and page suppression for free (see
        :meth:`Control._setAppearance`). Nothing here interprets *op* or *kwds*. Writes to
        a control on an inactive software page are skipped -- the appearance stays cached
        and is replayed by :meth:`_repaintPage` when that page becomes active.

        Returns
        -------
        bool
            Whether the request reached the hardware.
        """
        if not self._hardwarePages and control.page != self._currentPage:
            return False
        writer = None
        if isinstance(op, str) and op.isidentifier():
            name = f'_write{op[0].upper()}{op[1:]}'
            writer = getattr(self, name, None)
        else:
            name = f'_write<Op> for {op!r}'
        if writer is None:
            raise ValueError(
                f"{type(self).__name__} has no writer for appearance operation {op!r}; "
                f"it needs a {name}(control, ...) method"
            )
        writer(control, **kwds)
        return True


# --------------------------------------------------------------------------- config glue


def parseControlConfig(conf) -> dict:
    """Normalize a control address from device configuration.

    Parameters
    ----------
    conf : dict or sequence
        The canonical spelling is::

            control:
                device: 'Dock'
                type:   'dial'      # default 'button'
                page:   0           # default 0
                key:    [0, 0]      # device-defined

        Extra keys (a consumer's own ``step:``, say) are ignored. Two deprecated aliases
        are also accepted, and log a warning: ``{'hotkey': {'device': ..., 'key': ...}}``
        and ``{'xkey': (deviceName, row, col)}`` -- the latter also as a bare 3-element
        sequence.

    Returns
    -------
    dict
        ``{'device': str, 'type': str, 'page': int, 'key': hashable}``. A list ``key`` from
        YAML is converted to a tuple, since keys must be hashable.
    """
    if isinstance(conf, dict):
        if 'hotkey' in conf:
            logger.warning(
                "The 'hotkey' config spelling is deprecated; use "
                "control: {'device': ..., 'type': ..., 'page': ..., 'key': ...} instead"
            )
            conf = conf['hotkey']
        elif 'xkey' in conf:
            logger.warning(
                "The 'xkey' config spelling is deprecated; use "
                "control: {'device': ..., 'type': 'button', 'page': 0, "
                "'key': [row, col]} instead"
            )
            return parseControlConfig(conf['xkey'])
        if not isinstance(conf, dict) or 'device' not in conf:
            raise ValueError(f"Control configuration needs a 'device' key: {conf!r}")
        spec = {
            'device': conf['device'],
            'type': conf.get('type', 'button'),
            'page': int(conf.get('page', 0)),
            'key': conf.get('key'),
        }
    elif isinstance(conf, (tuple, list)) and len(conf) == 3:
        logger.warning(
            "The 'xkey' (device, row, col) config spelling is deprecated; use "
            "control: {'device': ..., 'type': 'button', 'page': 0, "
            "'key': [row, col]} instead"
        )
        spec = {'device': conf[0], 'type': 'button', 'page': 0, 'key': (conf[1], conf[2])}
    else:
        raise TypeError(f"Cannot interpret {conf!r} as a control address")

    if isinstance(spec['key'], list):
        spec['key'] = tuple(spec['key'])
    if spec['key'] is None:
        raise ValueError(f"Control configuration needs a 'key': {conf!r}")
    return spec


def acquireControlFromConfig(conf, owner) -> Control:
    """Resolve a configured control address and claim it.

    The surface is looked up by name on the global :class:`~acq4.Manager.Manager`, so it must
    be declared *before* its clients in ``devices.cfg``, matching the existing
    ``parentDevice:`` convention.

    Parameters
    ----------
    conf : dict or sequence
        See :func:`parseControlConfig`.
    owner : object
        Recorded on the control and named in a :exc:`ControlInUse` raised against a later
        claim. Required and not None; see :meth:`Control.acquire`.

    Returns
    -------
    Control

    Raises
    ------
    KeyError
        If the surface offers no such address.
    ControlInUse
        If the control is already claimed. Two config entries naming one address are the
        usual cause, and the message names the address and the owner that got there first.
    TypeError
        If the named device is not a :class:`ControlSurface`.
    ValueError
        If *owner* is None.
    """
    # Local import: acq4.Manager imports the acq4.devices package, so importing it at module
    # scope here closes that loop. It happens to resolve today only because
    # acq4/devices/__init__.py imports device modules lazily; Device.py takes the same
    # precaution with its own runtime ``import acq4``.
    from acq4.Manager import getManager

    spec = parseControlConfig(conf)
    surface = getManager().getDevice(spec['device'])
    if not isinstance(surface, ControlSurface):
        raise TypeError(
            f"Device {spec['device']!r} is a {type(surface).__name__}, not a ControlSurface"
        )
    return surface.acquireControl(spec['type'], spec['page'], spec['key'], owner=owner)
