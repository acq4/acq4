"""Panic Lock — the rig-wide safety interlock (see ``Panic Lock Spec.md``).

When triggered, the Panic Lock halts every device capable of motion or energy
delivery and then *latches*: it refuses all further unsafe commands until a human
explicitly resumes. Panic is not "abort the current operation"; it is "the rig is
unsafe; nothing moves until a human says so."

This module holds ``GlobalHaltException`` and the ``GlobalHalt`` state object.
The live instance lives on the Manager as ``Manager.globalHalt``.
"""

from __future__ import annotations

import sys
import threading
from typing import Callable

from acq4.util.debug import logger

from acq4.util import Qt
from acq4.util.task import asynch


__all__ = ["GlobalHaltException", "GlobalHalt", "GlobalPanicHotkey"]


class GlobalHaltException(Exception):
    """Raised by globalHalt.check() when an unsafe operation is attempted while halted."""


# Sentinel stored in GlobalHalt._reason while ARMED. A dedicated object (rather
# than None) keeps `halted` well defined even if someone halts with a falsy
# reason, and it is what makes `halted` derivable from the single `_reason`
# attribute -- see the lock-free read note on GlobalHalt.
_ARMED = object()


def _callbackName(cb: Callable[[], None]) -> str:
    """Best-effort human-readable label for an abort callback.

    Used when the caller does not supply a *name*. It labels the abort task and
    therefore every failure message it produces, so it should identify the
    participant; but it is only ever a label, never an identity, so anything
    printable will do.
    """
    for attr in ("__qualname__", "__name__"):
        value = getattr(cb, attr, None)
        # Not isinstance-free: a Mock (or any auto-attribute object) answers
        # every getattr with something that is not a name.
        if isinstance(value, str):
            return value
    return repr(cb)


class GlobalHalt(Qt.QObject):
    """Owns the panic state (§3) and the abort-callback registry (§5).

    Two states, ARMED and HALTED. ``halt()`` sets the state flag synchronously
    *before* starting the fan-out, so there is no window in which a device has
    been halted but is not yet guarded (§3).

    Threading (§10.1): ``halted`` and ``reason`` are read from every device
    thread and are both derived from a single attribute, so they can be read
    without a lock and cannot be seen torn relative to one another. The callback
    registry is a plain list -- ``append``/``remove`` are atomic and
    ``_fanOut()`` snapshots the list before iterating, so a concurrent
    registration is either included in the sweep or not; it cannot corrupt one in
    progress.
    """

    sigPanicStateChanged = Qt.Signal(object)  # reason str, or None on resume
    # Every halt(), including a repeat that changes no state. This is what
    # drives the panic dialog (§9.1): a second ESC press means "I mean it", and
    # the operator must see the rig respond to it, but it is not a state
    # transition, so sigPanicStateChanged does not fire for it.
    sigHaltRequested = Qt.Signal()

    def __init__(self, parent=None):
        Qt.QObject.__init__(self, parent)
        # Single source of truth for the state: _ARMED, or the halt reason.
        self._reason = _ARMED
        # (name, cb) pairs. No mutex -- see the class docstring.
        self._abortCallbacks = []
        # Guards only the ARMED <-> HALTED transition decision, so that a
        # concurrent double-halt cannot emit sigPanicStateChanged twice or
        # overwrite the first reason. Readers never take it.
        self._transitionLock = threading.Lock()

    @property
    def halted(self) -> bool:
        """True while the rig is halted."""
        return self._reason is not _ARMED

    @property
    def reason(self) -> "str | None":
        """Why the halt was initiated; None when armed."""
        reason = self._reason
        return None if reason is _ARMED else reason

    def halt(self, reason: str = "User pressed ESC") -> None:
        """Initiate the halt state, then invoke every registered abort callback.

        *reason* is recorded only when this call transitions ARMED -> HALTED; a
        repeat halt re-runs the fan-out and leaves the original reason intact
        (§3). The state flag is set before the fan-out starts, so a device
        commanded concurrently from another thread is refused even if its own
        abort callback has not run yet.

        Emits ``sigHaltRequested`` every time and ``sigPanicStateChanged`` only
        on a real ARMED -> HALTED transition (§9.1).

        Safe to call from any thread. The signals are emitted on the calling
        thread; a receiver that must run on the GUI thread -- the panic dialog
        -- gets there through its own queued connection, so ``halt()`` itself
        never waits on the event loop (§4.1).
        """
        with self._transitionLock:
            transitioned = self._reason is _ARMED
            if transitioned:
                # One assignment sets `halted` and `reason` together.
                self._reason = reason

        self._fanOut()

        # Order per §5.1: state, then fan-out, then UI. Both emissions happen
        # after _fanOut() has *started* every abort task -- it is fire-and-forget
        # (§5.3), so a hung device cannot delay the dialog.
        if transitioned:
            self.sigPanicStateChanged.emit(self.reason)
        self.sigHaltRequested.emit()

    def resume(self) -> None:
        """End the halt state. GUI thread, explicit user action only (§8).

        Devices are not restored to their pre-panic state. No-op while ARMED.
        """
        with self._transitionLock:
            if self._reason is _ARMED:
                return
            self._reason = _ARMED

        self.sigPanicStateChanged.emit(None)

    def check(self) -> None:
        """Raise GlobalHaltException if halted. Called by device guards."""
        reason = self._reason
        if reason is not _ARMED:
            raise GlobalHaltException(f"Rig is halted: {reason}")

    def add_abort_callback(self, cb: Callable[[], None], name: str = None) -> None:
        """Register cb to be invoked on halt. Idempotent.

        *name* labels the task and its failure messages; it defaults to a name
        derived from cb. Registering while halted does NOT invoke cb -- a
        participant created during a halt is already subject to the guards.
        """
        # Equality, not identity: a bound method is a fresh object on every
        # attribute access, so `dev.abort` registered twice must still be caught
        # as a duplicate. This matches how remove_abort_callback finds entries.
        for _, existing in list(self._abortCallbacks):
            if existing == cb:
                return
        if name is None:
            name = _callbackName(cb)
        self._abortCallbacks.append((name, cb))

    def remove_abort_callback(self, cb: Callable[[], None]) -> None:
        """Unregister cb. Silent if not registered."""
        for entry in list(self._abortCallbacks):
            if entry[1] == cb:
                try:
                    self._abortCallbacks.remove(entry)
                except ValueError:
                    pass  # already removed by a concurrent caller
                return

    def _fanOut(self):
        """Start an abort task for every registered callback. Returns immediately."""
        callbacks = list(self._abortCallbacks)   # snapshot: a callback may register or remove
        for name, cb in callbacks:
            asynch(
                cb,
                name=f"abort({name})",
                detach=True,
                raise_errors="{name} failed: {error}",
            )()


# ---------------------------------------------------------------------------
# Focus-independent panic key
# ---------------------------------------------------------------------------

# Virtual-key codes for the keys a panic hotkey may plausibly use.
_VK = {
    "esc": 0x1B, "escape": 0x1B,
    "pause": 0x13, "scrolllock": 0x91, "insert": 0x2D, "delete": 0x2E,
    "home": 0x24, "end": 0x23, "space": 0x20,
}
_VK.update({f"f{n}": 0x6F + n for n in range(1, 13)})          # F1..F12
_VK.update({c: ord(c.upper()) for c in "abcdefghijklmnopqrstuvwxyz0123456789"})

_VK_CTRL, _VK_SHIFT, _VK_ALT = 0x11, 0x10, 0x12
_MODS = {"ctrl": _VK_CTRL, "control": _VK_CTRL, "shift": _VK_SHIFT,
         "alt": _VK_ALT, "menu": _VK_ALT}


def parse_hotkey(spec):
    """Turn a config value into ``(vk, modifier_vks)``, or None if disabled.

    Accepts ``True`` (bare Esc), a string such as ``"Esc"`` or ``"Ctrl+Alt+Esc"``,
    or a falsy value for "no global hotkey".
    """
    if not spec:
        return None
    if spec is True:
        spec = "Esc"
    if not isinstance(spec, str):
        raise ValueError(f"panicHotkey must be True, False, or a key string; got {spec!r}")

    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError(f"panicHotkey {spec!r} names no key")
    *mods, key = parts
    try:
        modVks = [_MODS[m] for m in mods]
    except KeyError as exc:
        raise ValueError(f"panicHotkey {spec!r}: unknown modifier {exc.args[0]!r}") from None
    if key not in _VK:
        raise ValueError(
            f"panicHotkey {spec!r}: unknown key {key!r}; known keys are "
            f"{', '.join(sorted(_VK))}"
        )
    return _VK[key], modVks


class GlobalPanicHotkey:
    """A panic key that works when ACQ4 does not have focus.

    The ESC ``QShortcut`` only fires when an ACQ4 window is active and only while
    the Qt event loop is servicing it. This watches the keyboard directly from a
    plain daemon thread instead, so it works with another application in front and
    does not depend on the event loop at all -- which is the whole point, since a
    wedged GUI thread is exactly when a panic key matters most.

    Windows only. ``GetAsyncKeyState`` was chosen over the two obvious alternatives:

    * ``RegisterHotKey`` **consumes** the key system-wide, so binding Esc would
      break Esc in every other application on the desktop.
    * ``SetWindowsHookEx(WH_KEYBOARD_LL)`` does not consume it, but needs its own
      message pump, is silently unhooked by Windows if the callback is ever slow,
      and is routinely flagged by security software.

    Polling one key costs nothing measurable and has neither problem: it never
    swallows the keystroke, so Esc keeps working normally everywhere else.

    **This fires on the key wherever it is pressed** -- in a browser, in an editor,
    anywhere. With a bare Esc binding that is very easy to hit by accident, and an
    accidental panic latches the rig and stops the experiment. Prefer a chord such
    as ``Ctrl+Alt+Esc`` unless the rig is on a dedicated machine.
    """

    #: How often to sample the key. 30 ms is imperceptible to a human and is
    #: roughly one thousandth of one core.
    pollInterval = 0.03

    def __init__(self, globalHalt, spec, reason="User pressed the global panic key"):
        self._globalHalt = globalHalt
        self._reason = reason
        self._spec = spec
        self._stop = threading.Event()
        self._thread = None

        parsed = parse_hotkey(spec)
        if parsed is None:
            self._vk = self._mods = None
            return
        self._vk, self._mods = parsed

        if sys.platform != "win32":
            logger.warning(
                f"panicHotkey {spec!r} ignored: the focus-independent panic key is "
                f"implemented for Windows only. The Esc shortcut still works while "
                f"an ACQ4 window has focus."
            )
            self._vk = None
            return

        import ctypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.GetAsyncKeyState.restype = ctypes.c_short
        self._getKeyState = user32.GetAsyncKeyState

    @property
    def enabled(self):
        return self._vk is not None

    def start(self):
        if not self.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="panic-hotkey", daemon=True
        )
        self._thread.start()
        logger.info(f"Global panic key active: {self._spec!r} (works without ACQ4 focus)")

    def stop(self):
        self._stop.set()

    def _isDown(self, vk):
        # High bit set means the key is down *now*. The low bit ("pressed since
        # last call") is deliberately not used: it is consumed by whoever reads it
        # first, so two readers would steal each other's edges.
        return bool(self._getKeyState(vk) & 0x8000)

    def _run(self):
        wasDown = False
        while not self._stop.is_set():
            try:
                down = self._isDown(self._vk) and all(self._isDown(m) for m in self._mods)
                # Edge-triggered: holding the key must not re-halt every 30 ms.
                if down and not wasDown:
                    self._globalHalt.halt(self._reason)
                wasDown = down
            except Exception:
                # Never let this thread die: it is the panic key.
                logger.exception("Error polling the global panic key")
            self._stop.wait(self.pollInterval)
