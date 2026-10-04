from __future__ import annotations

import functools
import queue
import threading
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .Stage import MoveFuture, Stage



_DELTA = 'delta'
_FINISHED = 'finished'
_IDLE = 'idle'
_QUIT = 'quit'
_VELOCITY = 'velocity'


def _isJog(task) -> bool:
    """Whether *task* is a velocity task rather than an ordinary move."""
    from .Stage import VelocityFuture  # imported late: Stage imports this module

    return isinstance(task, VelocityFuture)


class DirectMotionController:
    """Scheduler for direct user motion on one stage.

    Direct motion is a knob detent, a gamepad stick, an arrow key. Requests come in two
    kinds, sharing one control thread so that only one of them drives the stage at a
    time: stepped (:meth:`requestDelta`, accumulated into a target and issued as
    :meth:`Stage.move`) and continuous (:meth:`requestVelocity`, issued as
    :meth:`Stage.setVelocity`). Both bypass the motion planner, and a request of one
    kind ends what the other has in progress.

    Requests are fire-and-forget: the call posts and returns, and the decision is taken
    afterwards.

    If a stage is capable of retargeting in-flight moves, the controller will take
    advantage of that capability. Otherwise, it will combine requests together to
    reduce the number of moves.

    Requests of either kind are dropped while the stage is busy with a task this
    controller did not issue.
    """

    #: Fraction of the in-flight move's remaining distance that the gesture must have run
    #: past that move's target by before a retarget-capable stage is interrupted to re-aim
    #: it. Below it the request is held, and the move's completion issues whatever
    #: accumulated.
    #:
    #: Both distances are Euclidean norms in device coordinates, so a stage whose axes count
    #: in different units would mix them in the ratio. None in the tree does.
    #:
    #: 0.1 is a guess, not a measurement, and is deliberately low: it errs toward re-aiming
    #: often, which is the responsive failure and the cheap one on a device that really
    #: blends. ``DoverStage`` is the first device in the tree to set
    #: :attr:`Stage.canRetargetInFlight`, and on it the command costs ~1.3ms for three
    #: axes, so what this wants tuned against is the trajectory rather than the command:
    #: how far past the held target a dial gesture overshoots at each candidate fraction,
    #: and how much of the gesture's travel the blend through zero (~196ms at 5mm/s^2)
    #: eats on a reversal.
    RETARGET_DIVERGENCE_FRACTION = 0.1


    def __init__(self, stage: "Stage"):
        self.stage = stage
        self._queue = queue.Queue()
        self._running = True
        # Everything below belongs to the control thread. Nothing else writes it, and
        # nothing outside the tests reads it.
        self._desired = None  # desired target in device coords, or None between gestures
        self._desiredSpeed = None
        self._desiredVelocity = None  # m/s per axis asked for but not yet issued
        self._inFlight: "MoveFuture | None" = None
        self._thread = threading.Thread(
            target=self._run, name=f"{stage.name()}-direct-motion", daemon=True
        )
        self._thread.start()

    # ------------------------------------------------------------------- public API

    def requestDelta(self, axis, delta, speed=None) -> None:
        """Ask for one axis to move by *delta* device units, counting from the gesture so far.

        *axis* is an index into :meth:`Stage.axes` or one of its names. Returns as soon
        as the request is queued; whether it becomes a move, and when, is decided on the
        control thread. Successive deltas accumulate even while an earlier one is still
        being driven.
        """
        if isinstance(axis, str):
            axis = list(self.stage.axes()).index(axis)
        self._post((_DELTA, axis, float(delta), speed))

    def requestVelocity(self, vel) -> None:
        """Ask for the stage to travel at *vel* until the gesture ends.

        *vel* is metres per second along each axis, as :meth:`Stage.setVelocity` takes
        it: one value per axis in :meth:`Stage.axes`, or None for an axis that stays
        put. Level-triggered -- post whatever the input is asking for now, and a zero
        (or all-None) velocity to end the jog. Returns as soon as the request is queued;
        whether it becomes a jog, and when, is decided on the control thread. Raises
        :class:`ValueError` if *vel* is not finite.
        """
        self._post((_VELOCITY, self.stage._normalizeVelocity(vel)))

    def waitUntilIdle(self, timeout=5.0) -> bool:
        """Block until every request posted before this call has been decided.

        Test support. It says nothing about the gesture being finished or the stage
        having arrived: a request held under wait-and-collapse, and the completion that
        will eventually issue it, are both still to come.

        Returns False if *timeout* seconds elapsed first.
        """
        if not self._running:
            return True
        handled = threading.Event()
        self._post((_IDLE, handled))
        return handled.wait(timeout)

    def shutdown(self, timeout=2.0) -> None:
        """Stop the control thread, end any jog, and ignore every later request.

        A stepped move is left to finish, but a jog has no end of its own on a device
        that holds a velocity, and nothing would be left to stop it.
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
        # After the join: the thread that owns this state is gone.
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
            item = self._queue.get()
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
        elif kind is _IDLE:
            item[1].set()

    def _accumulate(self, axis, delta, speed) -> None:
        """Fold one delta into the desired target, then decide what to do about it."""
        self._endJog("a stepped request took the gesture")
        base = self._desired
        if base is None:
            # No gesture in progress, so this one starts from wherever the stage is
            # commanded to be: its own position, unless a task is running.
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
            if not self.stage.canRetargetInFlight:
                return
            if not self._worthInterrupting():
                return
        # A move that has finished but whose completion is still on the queue falls
        # through to here. Issuing now is what that completion would have done, and it
        # is discarded on identity when it does arrive.
        self._issue()

    def _worthInterrupting(self) -> bool:
        """Whether the gesture has run far enough past the move in flight to re-aim it."""
        inFlightTarget = np.asarray(self._inFlight.targetPos, dtype=float)
        position = np.asarray(self.stage.getPosition(), dtype=float)
        divergence = np.linalg.norm(self._desired - inFlightTarget)
        remaining = np.linalg.norm(inFlightTarget - position)
        return divergence > self.RETARGET_DIVERGENCE_FRACTION * remaining

    def _issue(self) -> None:
        """Hand the desired target to the stage and watch the move it becomes."""
        target, speed = self._desired, self._desiredSpeed
        self._desired = None
        try:
            fut = self.stage.move(list(target), speed=speed)
        except Exception as exc:
            self.stage.logger.debug(
                "%s: direct move to %s refused: %s", self.stage.name(), list(target), exc
            )
            return
        self._inFlight = fut
        fut.add_finish_callback(functools.partial(self._moveFinished, fut))

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

        Runs on whichever thread completed the task: a driver's monitor thread, or this
        one when :meth:`_issue` or :meth:`_issueVelocity` supersedes the task before it.
        Queueing is all it does, so a driver completing a move under its own lock never
        waits on us.
        """
        self._queue.put((_FINISHED, fut, exc))

    def _finished(self, fut, exc) -> None:
        """Carry the gesture across the ending of *fut*.

        A move that is no longer the one in flight has been superseded, and its late
        completion says nothing. Otherwise whatever accumulated is issued, unless *fut*
        ended any way other than by arriving -- a stop, a failure, a halt -- which ends
        the gesture.
        """
        if fut is not self._inFlight:
            return
        self._inFlight = None
        if exc is not None:
            self._desired = None
            return
        self._decide()
