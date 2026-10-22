"""Panic Lock — the rig-wide safety interlock (see ``Panic Lock Spec.md``).

When triggered, the Panic Lock halts every device capable of motion or energy
delivery and then *latches*: it refuses all further unsafe commands until a human
explicitly resumes. Panic is not "abort the current operation"; it is "the rig is
unsafe; nothing moves until a human says so."

This module holds ``GlobalHaltException`` and the ``GlobalHalt`` state object.
The live instance lives on the Manager as ``Manager.globalHalt``.
"""

from __future__ import annotations

import threading
from typing import Callable

from acq4.util import Qt
from acq4.util.task import asynch


__all__ = ["GlobalHaltException", "GlobalHalt"]


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
