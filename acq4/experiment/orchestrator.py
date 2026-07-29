"""Orchestrator: runs a cell queue serially, calling each cell's protocol
function and converting its flow-signal exceptions into queue control."""
from __future__ import annotations

from collections import deque

from acq4.logging_config import get_logger
from acq4.util import Qt
from acq4.util.task import Stopped, Event, check_stop, asynch_with_qt_signals

from .context import ExecutionContext
from .exceptions import (
    OrchestrationError,
    AdvanceToNextCell,
    RetryCurrentCell,
    AbortExperiment,
    FlowSignal,
)

logger = get_logger(__name__)


class Orchestrator(Qt.QObject):
    sigStatus = Qt.Signal(str)                 # "running"/"waiting"/"paused"/"error"
    sigCurrentCell = Qt.Signal(object)         # cell, or None when idle
    sigCellFinished = Qt.Signal(object, str)   # cell, status

    def __init__(self, protocolFile, manager=None, contextFactory=None, maxRetries=100):
        Qt.QObject.__init__(self)
        self.protocolFile = protocolFile
        self.manager = manager
        self._queue = deque()
        self._pauseEvent = Event()
        self._pauseEvent.set()  # set == running
        self._nextCellRequested = False
        self._contextFactory = contextFactory or self._defaultContext
        # Guard against an unbounded retry loop (a protocol that always raises
        # RetryCurrentCell, or a persistently-failing action). On exhaustion the
        # cell finishes as "retry-exhausted" rather than wedging the queue forever.
        self.maxRetries = maxRetries

    # ---- queue / context ----
    def enqueue(self, cell):
        self._queue.append(cell)

    def _defaultContext(self, cell) -> ExecutionContext:
        return ExecutionContext(cell=cell, manager=self.manager)

    # ---- test / headless entry points ----
    def run_sync_cell(self, cell):
        """Run a single cell through the protocol inline. Used by tests/headless."""
        self._nextCellRequested = False
        self._processCell(cell)

    # ---- controls ----
    def start(self):
        """Launch the queue loop asynchronously; returns the launched task."""
        self._task = asynch_with_qt_signals(
            self._runLoopBody, on_finish=self._onLoopFinished
        )()
        return self._task

    def _onLoopFinished(self, result, exc):
        """Clear self._task once the loop finishes.

        self._task and its QtFriendlyTask hold a mutual reference (the task's
        _fn is the bound method self._runLoopBody, and self._task references
        the task back) -- a QObject reference cycle that only Python's cyclic
        GC could otherwise reclaim, non-deterministically and off Qt's safe
        teardown path. Clearing the reference here, from the task's own
        completion hook, breaks the cycle as soon as a run finishes.
        """
        if exc is not None:
            logger.error("Orchestrator run loop finished with an unhandled exception", exc_info=exc)
        self._task = None

    def run_sync(self):
        """Run the whole queue inline (deterministic; for tests / headless)."""
        self._runLoopBody()

    def pause(self):
        self._pauseEvent.clear()

    def resume(self):
        self._pauseEvent.set()

    def stop(self, reason: str = "stopped by operator"):
        task = getattr(self, "_task", None)
        if task is not None and not task.is_done:
            task.stop(reason)

    def requestNextCell(self):
        # Honored at the next cell boundary (checked at the top of
        # _processCell's retry loop) and, cooperatively, inside actions.fsm's
        # poll loop (via ExecutionContext.next_cell_requested, injected below)
        # -- a cell spends nearly all its wall-clock there. A protocol that
        # never enters an FSM-driving action and never returns has no
        # checkpoint for this to interrupt; use stop() for that.
        self._nextCellRequested = True

    def wait(self, timeout=None):
        task = getattr(self, "_task", None)
        if task is None:
            raise RuntimeError("Orchestrator was not started; nothing to wait on")
        return task.wait(timeout=timeout)

    # ---- loop body ----
    def _runLoopBody(self):
        self.sigStatus.emit("running")
        try:
            while self._queue:
                self._checkPause()
                check_stop()
                cell = self._queue.popleft()
                self._processCell(cell)
        finally:
            self.sigCurrentCell.emit(None)
            self.sigStatus.emit("waiting")

    def _checkPause(self):
        if not self._pauseEvent.is_set():
            self.sigStatus.emit("paused")
            self._pauseEvent.wait()
            self.sigStatus.emit("running")

    def _processCell(self, cell):
        """Run the protocol function for one cell. RetryCurrentCell loops in
        place (bounded by maxRetries, restarting the same cell rather than
        re-queuing it); AdvanceToNextCell skips."""
        retries = 0
        while True:
            if self._nextCellRequested:
                self._nextCellRequested = False
                self.sigCellFinished.emit(cell, "skipped")
                return
            self.sigStatus.emit("running")
            ctx = self._contextFactory(cell)
            # Give the context a way to observe a mid-cell "Next cell" request
            # without handing it a back-reference to the orchestrator itself --
            # a narrow closure over the flag, injected the same way regardless
            # of which contextFactory built ctx (mirroring how log/on_log_action
            # are already bound onto a context by whoever builds one). Guarded
            # since a contextFactory is free to hand back None (e.g. a test
            # deliberately avoiding a self-cycle through a real ExecutionContext).
            if ctx is not None:
                ctx.next_cell_requested = lambda: self._nextCellRequested
            self.sigCurrentCell.emit(cell)
            try:
                self.protocolFile.run(ctx, **self.protocolFile.param_values())
            except AdvanceToNextCell:
                self._nextCellRequested = False
                self.sigCellFinished.emit(cell, "skipped")
                return
            except RetryCurrentCell:
                retries += 1
                if retries > self.maxRetries:
                    self.sigCellFinished.emit(cell, "retry-exhausted")
                    return
                self.sigCellFinished.emit(cell, "retry")
                continue  # loop top re-emits "running" and restarts in place
            except FlowSignal:
                # AdvanceToNextCell/RetryCurrentCell are handled above and never
                # reach here; AbortExperiment (and any future FlowSignal) must
                # keep propagating uncaught, to stop the run loop, rather than
                # being mistaken for an unexpected bug by the broad except below.
                raise
            except Stopped:
                # A cooperative stop (operator-initiated, via check_stop()) is
                # not an unexpected bug either -- the protocol's own try/finally
                # has already unwound the device, so let it keep propagating
                # uncaught.
                raise
            except OrchestrationError as exc:
                # Design §5's catch-all safety net: an uncaught orchestration
                # error halts the run rather than blazing through the remaining
                # queued cells. Handler sub-protocols are gone; a protocol
                # author who wants to recover from this writes their own
                # try/except in run().
                logger.exception("Unhandled orchestration error while processing cell %r", cell)
                self.sigStatus.emit("error")
                self.sigCellFinished.emit(cell, "error")
                raise AbortExperiment(
                    f"unhandled orchestration error while processing cell: {exc}"
                ) from exc
            except Exception as exc:
                # An unexpected bug (not a flow signal, and not an
                # OrchestrationError the protocol chose to let propagate) must
                # fail loud rather than be silently swallowed: log it, surface
                # it as an error to the UI, and abort the run rather than
                # blazing through the remaining queued cells.
                logger.exception("Unexpected exception while processing cell %r", cell)
                self.sigStatus.emit("error")
                self.sigCellFinished.emit(cell, "error")
                raise AbortExperiment(
                    f"unexpected exception while processing cell: {exc}"
                ) from exc
            else:
                if ctx is not None and ctx.pending_flow_signal is not None:
                    # Design §5's safety net: a flow action recorded a signal
                    # on ctx right before raising it, but run() returned
                    # normally anyway -- the protocol's own try/except caught
                    # and swallowed it instead of letting it propagate. That
                    # is a bug (the queue did not actually do what the
                    # protocol thought it told it to), not a success.
                    logger.error(
                        "Flow signal %r was raised but swallowed by the "
                        "protocol while processing cell %r",
                        ctx.pending_flow_signal,
                        cell,
                    )
                    self.sigStatus.emit("error")
                    self.sigCellFinished.emit(cell, "error")
                    raise AbortExperiment(
                        f"flow signal raised but swallowed by the protocol: "
                        f"{ctx.pending_flow_signal!r}"
                    ) from ctx.pending_flow_signal
                self.sigCellFinished.emit(cell, "done")
                return
