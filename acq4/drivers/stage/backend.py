"""StageBackend: the per-device hardware layer under StageDriver."""
from __future__ import annotations

from typing import Protocol

from .futures import MoveState


class StageBackend(Protocol):
    """Hardware I/O and device logic for one stage, driven by a StageDriver's control thread.

    Every method is called only from that control thread (StageControlThread), one at a
    time and never reentrantly; methods may block. Not thread-safe. Positions and targets
    are dicts of axis name -> driver units.

    Attributes
    ----------
    axes : tuple[str, ...]
        Axis names.
    stop_before_move : bool
        True if the device must stop moving before it accepts a new move; the control
        thread then sends :meth:`stop` and waits for :meth:`is_moving` to go False.
    """

    axes: tuple[str, ...]
    stop_before_move: bool

    def open(self) -> None:
        """Open the hardware link; called first. Raising aborts ``StageDriver.connect``."""

    def close(self) -> None:
        """Close the hardware link; called last, also after :meth:`open` raised."""

    def read_position(self) -> dict:
        """Read the position from hardware; called every poll.

        Raise instead of returning a value for any axis not read from hardware on this call.
        """

    def poll_extra(self) -> None:
        """Extra per-poll hardware reads. Exceptions are logged and ignored."""

    def start_move(self, target: dict, speed, **kwds) -> object:
        """Command an absolute move; return an opaque handle passed back to the methods below.

        *kwds* are the extra keyword arguments given to ``StageDriver.move_to``. Must re-issue
        speed if the device zeroes it on stop.
        """

    def stop(self, reason: str) -> None:
        """Command a stop of all axes. Need not wait for motion to cease."""

    def check_move(self, handle) -> tuple[MoveState, str | None]:
        """Return (state, failure reason) for an active move; called once per poll while it is active."""

    def is_moving(self, handle) -> bool:
        """Whether the axes of a stopped or superseded move are still in motion (stop_before_move only)."""

    def final_position(self, handle) -> dict:
        """Position once :meth:`check_move` returned DONE; becomes ``MoveRequest.final_position``.

        Covers every axis, not only the handle's, and raises like :meth:`read_position`
        for any axis not read from hardware: the control thread publishes it as the
        stage's position.
        """
