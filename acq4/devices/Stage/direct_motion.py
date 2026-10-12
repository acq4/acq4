from __future__ import annotations

import functools
import queue
import threading
import time
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .Stage import MoveFuture, Stage



_DELTA = 'delta'
_FINISHED = 'finished'
_IDLE = 'idle'
_QUIT = 'quit'
_VELOCITY = 'velocity'
_WAKE = 'wake'


def _isJog(task) -> bool:
    """Whether *task* is a velocity task rather than an ordinary move."""
    from .Stage import VelocityFuture  # imported late: Stage imports this module

    return isinstance(task, VelocityFuture)


class DirectMotionController:
    """Scheduler for direct user motion (knob, stick, arrow key) on one stage.

    Requests are stepped (:meth:`requestDelta`, accumulated into a target and issued as
    :meth:`Stage.move`) or continuous (:meth:`requestVelocity`, issued as
    :meth:`Stage.setVelocity`). Both bypass the motion planner. One control thread serves
    both, so only one drives the stage at a time, and a request of one kind ends what the
    other has in progress.

    Requests are fire-and-forget: the call posts and returns; the decision is taken on the
    control thread. They are dropped while the stage is busy with a task this controller
    did not issue. Stepped requests collapse into one target, which re-aims a running move
    no more often than :attr:`Stage.retargetInterval`, or waits for it to complete when
    that is ``inf``. A target held back is issued when the interval elapses or the move
    completes, whichever is first.
    """

    def __init__(self, stage: "Stage"):
        self.stage = stage
        self._queue = queue.Queue()
        self._running = True
        # Everything below is owned by the control thread.
        self._desired = None  # desired target in device coords, or None between gestures
        self._desiredSpeed = None
        self._desiredVelocity = None  # m/s per axis asked for but not yet issued
        self._inFlight: "MoveFuture | None" = None
        self._lastIssue = -np.inf  # time.monotonic() of the last stepped move issued
        self._wakeAt = None  # time.monotonic() at which to issue a held target
        self._thread = threading.Thread(
            target=self._run, name=f"{stage.name()}-direct-motion", daemon=True
        )
        self._thread.start()

    # ------------------------------------------------------------------- public API

    def requestDelta(self, axis, delta, speed=None) -> None:
        """Ask for one axis to move by *delta* device units, counting from the gesture so far.

        *axis* is an index into :meth:`Stage.axes` or one of its names. Returns once the
        request is queued; successive deltas accumulate while an earlier one is still
        being driven. *speed* is as for :meth:`Stage.move`, or ``'auto'`` to scale with the
        distance left to travel (see :attr:`Stage.dialMoveTime`).
        """
        if isinstance(axis, str):
            axis = list(self.stage.axes()).index(axis)
        self._post((_DELTA, axis, float(delta), speed))

    def requestVelocity(self, vel) -> None:
        """Ask for the stage to travel at *vel* until the gesture ends.

        *vel* is m/s per axis in :meth:`Stage.axes` order, or None for an axis that stays
        put. Level-triggered: post the velocity currently asked for, and a zero or
        all-None velocity to end the jog. Returns once the request is queued. Raises
        :class:`ValueError` if *vel* is not finite.
        """
        self._post((_VELOCITY, self.stage._normalizeVelocity(vel)))

    def waitUntilIdle(self, timeout=5.0) -> bool:
        """Block until every request posted before this call has been decided.

        Test support. A decided request may still be held for a later move's completion,
        so this does not imply the gesture is finished or the stage has arrived. Returns
        False if *timeout* seconds elapsed first.
        """
        if not self._running:
            return True
        handled = threading.Event()
        self._post((_IDLE, handled))
        return handled.wait(timeout)

    def shutdown(self, timeout=2.0) -> None:
        """Stop the control thread, end any jog, and ignore every later request.

        A stepped move in flight is left to finish. Blocks up to *timeout* seconds for
        the thread to join.
        """
        if not self._running:
            return
        self._running = False
        self._queue.put((_QUIT,))
        self._thread.join(timeout)
        if self._thread.is_alive():
            self.stage.logger.warning(
                "%s: direct motion thread did not stop within %ss", self.stage.name(), timeout
            )
        # After the join: touches control-thread state.
        self._endJog("direct motion shut down")

    # -------------------------------------------------------------- the control thread

    def _post(self, item) -> None:
        if not self._running:
            self.stage.logger.debug(
                "%s: direct request after shutdown ignored", self.stage.name()
            )
            return
        self._queue.put(item)

    def _run(self) -> None:
        while True:
            timeout = None if self._wakeAt is None else max(0.0, self._wakeAt - time.monotonic())
            try:
                item = self._queue.get(timeout=timeout)
            except queue.Empty:
                item = (_WAKE,)
            kind = item[0]
            if kind is _QUIT:
                return
            try:
                self._handle(kind, item)
            except Exception:
                self.stage.logger.exception(
                    "%s: direct motion failed to handle %s", self.stage.name(), kind
                )

    def _handle(self, kind, item) -> None:
        if kind is _DELTA:
            self._accumulate(item[1], item[2], item[3])
        elif kind is _VELOCITY:
            self._velocityRequested(item[1])
        elif kind is _FINISHED:
            self._finished(item[1], item[2])
        elif kind is _WAKE:
            self._wakeAt = None
            self._decide()
        elif kind is _IDLE:
            item[1].set()

    def _accumulate(self, axis, delta, speed) -> None:
        """Fold one delta into the desired target, then decide what to do about it."""
        self._endJog("a stepped request took the gesture")
        base = self._desired
        if base is None:
            # New gesture: count from the commanded position, not the measured one.
            base = self.stage.targetPosition()
        target = np.array(base, dtype=float)
        target[axis] += delta
        self._desired = target
        self._desiredSpeed = speed
        self._decide()

    def _velocityRequested(self, vel) -> None:
        """Take *vel* (m/s per axis) as what the input is asking for, then act on it."""
        if not np.any(vel):
            self._endJog("velocity request ended")
            return
        self._desired = None
        self._desiredSpeed = None
        self._desiredVelocity = vel
        self._decide()

    def _endJog(self, reason) -> None:
        """Drop any velocity being asked for, and end the jog this controller has running."""
        self._desiredVelocity = None
        jog = self._inFlight
        if jog is None or jog.is_done or not _isJog(jog):
            return
        self._inFlight = None
        self.stage.stopVelocity(reason)

    def _decide(self) -> None:
        """Issue what is being asked for, hold it, or drop it."""
        if self._desired is None and self._desiredVelocity is None:
            return
        task = self.stage._activeTask
        if task is not None and not task.is_done and task is not self._inFlight:
            self._desired = None
            self._desiredVelocity = None
            self.stage.logger.debug(
                "%s: direct request ignored while %s is in flight", self.stage.name(), task
            )
            return
        if self._desiredVelocity is not None:
            self._issueVelocity()
            return
        if self._inFlight is not None and not self._inFlight.is_done:
            if np.array_equal(self._desired, np.asarray(self._inFlight.targetPos, dtype=float)):
                self._desired = None  # the gesture came back to where it is already going
                return
            readyAt = self._lastIssue + self.stage.retargetInterval
            if time.monotonic() < readyAt:
                # Held: issued on wake-up, or by _finished() if the move completes first.
                if np.isfinite(readyAt):
                    self._wakeAt = readyAt
                return
        # A move finished but whose completion is still queued falls through to here; the
        # queued completion is then discarded on identity in _finished().
        self._issue()

    def _issue(self) -> None:
        """Hand the desired target to the stage and watch the move it becomes."""
        target, speed = self._desired, self._desiredSpeed
        self._desired = None
        self._wakeAt = None
        self._lastIssue = time.monotonic()
        if speed == 'auto':
            speed = self._autoSpeed(target)
        try:
            fut = self.stage.move(list(target), speed=speed)
        except Exception as exc:
            self.stage.logger.debug(
                "%s: direct move to %s refused: %s", self.stage.name(), list(target), exc
            )
            return
        self._inFlight = fut
        fut.add_finish_callback(functools.partial(self._moveFinished, fut))

    def _autoSpeed(self, target) -> float:
        """Speed (m/s) covering the distance to *target* in ``dialMoveTime``, within slow..fast."""
        stage = self.stage
        scale = np.abs(np.asarray(stage.getAxisScale(), dtype=float))
        delta = (np.asarray(target, dtype=float) - np.asarray(stage.getPosition(), dtype=float)) * scale
        speed = float(np.linalg.norm(delta)) / stage.dialMoveTime
        return min(max(speed, stage.slowSpeed), stage.fastSpeed)

    def _issueVelocity(self) -> None:
        """Hand the desired velocity to the stage and watch the jog it becomes."""
        vel = self._desiredVelocity
        self._desiredVelocity = None
        running = self._inFlight
        if (
            running is not None
            and not running.is_done
            and _isJog(running)
            and np.array_equal(running.velocity, vel)
        ):
            return  # already travelling at this velocity
        try:
            fut = self.stage.setVelocity(list(vel))
        except Exception as exc:
            self.stage.logger.debug(
                "%s: direct velocity %s refused: %s", self.stage.name(), list(vel), exc
            )
            return
        self._inFlight = fut
        fut.add_finish_callback(functools.partial(self._moveFinished, fut))

    def _moveFinished(self, fut, result, exc) -> None:
        """Queue *fut*'s completion for the control thread.

        Runs on whichever thread completed the task, possibly under a driver lock, so it
        only queues.
        """
        self._queue.put((_FINISHED, fut, exc))

    def _finished(self, fut, exc) -> None:
        """Carry the gesture across the ending of *fut*.

        Ignores *fut* if it is no longer the task in flight. Issues whatever accumulated
        meanwhile, unless *exc* is set -- any ending other than arrival ends the gesture.
        """
        if fut is not self._inFlight:
            return
        self._inFlight = None
        if exc is not None:
            self._desired = None
            return
        self._decide()
