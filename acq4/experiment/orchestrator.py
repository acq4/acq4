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
    sigStatus = Qt.Signal(str)                 # "running"/"surveying"/"waiting"/"paused"/"error"
    sigCurrentCell = Qt.Signal(object)         # cell, or None when idle
    sigCellFinished = Qt.Signal(object, str)   # cell, status

    def __init__(
        self,
        protocolFile,
        manager=None,
        contextFactory=None,
        maxRetries=100,
        cellProducer=None,
    ):
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
        self._cellProducer = cellProducer
        # Per-run: set once the producer reports exhaustion, cleared by
        # _runLoopBody's finally. See setCellProducer for why it is not
        # simply "has the producer ever returned None".
        self._producerExhausted = False

    # ---- queue / context ----
    def enqueue(self, cell):
        self._queue.append(cell)

    def pendingCells(self) -> list:
        """Return a snapshot of the cells still waiting in the queue, in the
        order they will run.

        A copy, not the live deque: the deque is popped from the worker
        thread as a run proceeds, so a caller salvaging cells from an
        orchestrator that is about to be replaced (see
        CellPanel.unbindOrchestrator) must not be able to mutate the run's
        own queue by holding onto it.
        """
        return list(self._queue)

    def clearQueue(self) -> None:
        """Drop every cell waiting in the queue, leaving any running cell alone.

        The caller that seeded these cells is discarding them -- the operator
        has swapped the tissue, so every queued position is a place not to
        drive a pipette. Clearing the panel's own bookkeeping is not enough:
        the deque is a separate strong reference and would otherwise keep
        handing those positions to the protocol.
        """
        self._queue.clear()

    def setCellProducer(self, producer):
        """Install (or clear, with None) the callback that refills the queue.

        `producer()` takes no arguments, runs on the worker thread, and returns
        either a sequence of new cells -- possibly empty, meaning "made
        progress, found none here, ask again" -- or None, meaning exhausted.

        Installing a producer clears the exhausted flag: a caller swapping in a
        fresh producer (a new survey region) is declaring there is more to find,
        and would otherwise be ignored for the rest of the run.
        """
        self._cellProducer = producer
        self._producerExhausted = False

    def _defaultContext(self, cell) -> ExecutionContext:
        return ExecutionContext(cell=cell, manager=self.manager)

    # ---- test / headless entry points ----
    def run_sync_cell(self, cell):
        """Run a single cell through the protocol inline. Used by tests/headless.

        The lower-level single-cell primitive: unlike run_sync()/start(), a
        cooperative Stopped from _processCell still propagates to the caller
        here, since there is no _runLoopBody frame around this call to end the
        run normally instead.
        """
        self._nextCellRequested = False
        try:
            self._processCell(cell)
        finally:
            # A request set (or left set) while processing this cell cannot
            # outlive this call -- whether _processCell returns normally or
            # raises (FlowSignal, Stopped, OrchestrationError, or an
            # unexpected exception all propagate straight through this call,
            # with no _runLoopBody frame around it to catch them on the way
            # out). Without this, a request left set by a raising call would
            # be silently consumed against an unrelated cell the next time
            # run_sync()/start() runs on this instance.
            self._nextCellRequested = False

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
        """Run the whole queue inline (deterministic; for tests / headless).

        Same run-loop scope as start(): a cooperative Stopped (operator-
        initiated, via check_stop()) ends this call normally rather than
        raising -- see _runLoopBody. Contrast run_sync_cell(), the lower-level
        single-cell primitive below, which still lets Stopped propagate to its
        caller.
        """
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

    def wait(self, timeout=None, updates=False):
        task = getattr(self, "_task", None)
        if task is None:
            raise RuntimeError("Orchestrator was not started; nothing to wait on")
        return task.wait(timeout=timeout, updates=updates)

    # ---- loop body ----
    def _runLoopBody(self):
        self.sigStatus.emit("running")
        try:
            while True:
                self._checkPause()
                check_stop()
                if self._shouldRefill():
                    # Surveying is not patching, and the operator watching a
                    # slow, barren stretch of region must not read a stale
                    # "running" as "a cell is being worked". Clearing the
                    # current cell first is the same honesty: leaving the
                    # just-finished cell named here made Area 5 attribute
                    # survey time to it.
                    self.sigCurrentCell.emit(None)
                    self.sigStatus.emit("surveying")
                    self._refillQueue()
                    # Refill only ever runs against an empty queue, so a
                    # request that arrived while the producer was working had
                    # no cell to advance past: nothing was running and nothing
                    # was queued. Consuming it against the first cell the
                    # producer then returned would skip a cell the operator
                    # never saw, without it ever being attempted.
                    self._nextCellRequested = False
                    # Back to the top rather than falling through to a cell:
                    # re-checks pause and stop between refills, and lets a
                    # producer returning [] be asked again next pass. Imaging
                    # a tile is slow, so an operator pressing Stop mid-survey
                    # must not have to wait out a refill that already started.
                    continue
                # clearQueue() runs on the GUI thread while this loop runs on
                # the worker thread, so the deque's emptiness cannot be
                # checked and then acted on as two separate steps -- a clear
                # landing in between would turn a plain empty-queue finish
                # into an IndexError out of popleft(). Popping directly and
                # catching that IndexError makes the check and the pop one
                # step: an empty deque at either the check or the pop means
                # the same thing, the run is done.
                try:
                    cell = self._queue.popleft()
                except IndexError:
                    break
                self._processCell(cell)
        except Stopped as exc:
            # An operator-initiated stop is a normal way for the run loop to
            # end, not an unhandled exception: check_stop()/_processCell's own
            # Stopped propagation has already unwound whatever action was
            # running (and, for an FSM-driving action, _safe_abort has already
            # put the pipette in its declared fallback state). Returning here
            # instead of re-raising means _onLoopFinished sees exc=None rather
            # than logging an operator-initiated stop as a failure. A problem
            # encountered *during* that cleanup is a different exception (not
            # Stopped) raised from inside _safe_abort/_drive_fsm's own except
            # clause, so it is not caught here -- it keeps propagating.
            logger.info("Orchestrator run loop stopped: %s", str(exc) or "no reason given")
        finally:
            # A "Next cell" request cannot outlive the run loop it was made
            # during -- whether that loop exits by returning (the queue
            # drained) or by raising (FlowSignal/Stopped propagating,
            # OrchestrationError/an unexpected exception aborting). Without
            # this, a request left over from a cell abandoned mid-run would
            # be silently consumed against an unrelated cell the next time
            # the queue is started.
            self._nextCellRequested = False
            # Per-run, exactly like the next-cell request above: a producer
            # that exhausted during this run must not leave the orchestrator
            # permanently convinced there is nothing left to find. A later run
            # -- over a new survey region, or over cells still queued after a
            # stop -- has to ask again. Unlike the next-cell flag, this one
            # needs no per-exit clears: it is only ever read by the refill
            # check at the top of this method's own loop, so there is no
            # equivalent of _processCell's inner retry loop running past the
            # reach of this finally.
            self._producerExhausted = False
            self.sigCurrentCell.emit(None)
            self.sigStatus.emit("waiting")

    def _checkPause(self):
        if not self._pauseEvent.is_set():
            self.sigStatus.emit("paused")
            self._pauseEvent.wait()
            self.sigStatus.emit("running")

    def _shouldRefill(self) -> bool:
        return (
            self._cellProducer is not None
            and not self._producerExhausted
            and not self._queue
        )

    def _refillQueue(self):
        """Ask the producer for more cells; record exhaustion when it has none."""
        # setCellProducer() runs on the GUI thread (a "New slice" mid-run, for
        # instance, clearing it to None) while this loop runs on the worker
        # thread, so "there is a producer" (_shouldRefill's check, just above)
        # and "call the producer" cannot be treated as two separate steps -- a
        # clear landing in between would turn a legitimate operator action
        # into a TypeError out of calling None. Reading it into a local once
        # makes the two one step for this call: if it is gone by the time
        # this runs, there is simply nothing to ask -- not exhaustion, and not
        # a bug to report. The same clear (or a swap to a different producer)
        # can just as easily land while producer() is off running -- itself
        # slow, seconds-to-minutes tile imaging -- rather than only before it
        # starts, so the local is checked against self._cellProducer again
        # below, right before the batch it returned is queued: a batch called
        # for under a producer the operator has since moved on from belongs to
        # tissue already declared gone, and must land nowhere rather than in
        # the next protocol's queue.
        producer = self._cellProducer
        if producer is None:
            return
        try:
            cells = producer()
        except (Stopped, FlowSignal):
            # Same pass-through as _processCell: a cooperative stop is a normal
            # end to the run, and a producer that raises AbortExperiment means
            # it -- neither is a bug to be wrapped by the clause below.
            raise
        except Exception as exc:
            # An unexpected bug in the producer must fail loud rather than
            # quietly ending the survey and letting the run look complete.
            # There is no cell to attribute it to, so no sigCellFinished.
            logger.exception("Cell producer raised while refilling the queue")
            self.sigStatus.emit("error")
            raise AbortExperiment(f"cell producer failed: {exc}") from exc
        if cells is None:
            self._producerExhausted = True
            return
        if self._cellProducer is not producer:
            # The batch is neither "found nothing, ask again" nor exhaustion --
            # it is real cells this call was in the middle of fetching when the
            # operator cleared or replaced the producer it was fetching them
            # for. Dropping it here, rather than setting _producerExhausted or
            # leaving it to be asked for again, is what keeps this discard from
            # being mistaken for either of the producer contract's two actual
            # outcomes.
            logger.info(
                "Discarding a batch of %d cell(s): the producer that returned "
                "them is no longer the installed one",
                len(cells),
            )
            return
        # One deque.extend rather than a loop of enqueue() calls: clearQueue()
        # runs on the GUI thread while this runs on the worker thread, and a
        # clear landing part-way through a loop would leave a partial batch of
        # coordinates queued in tissue the operator has already declared gone.
        # extend() is a single C-level call, so the whole batch lands either
        # before or after such a clear, never across it. enqueue() remains the
        # public single-cell entry point.
        self._queue.extend(cells)

    def _processCell(self, cell):
        """Run the protocol function for one cell. RetryCurrentCell loops in
        place (bounded by maxRetries, restarting the same cell rather than
        re-queuing it); AdvanceToNextCell skips."""
        retries = 0
        while True:
            # A retry restarts the protocol from the top of this loop, not
            # through _runLoopBody's own loop -- so Pause must be checked
            # here too, or a protocol retrying against a persistent failure
            # ignores Pause completely.
            self._checkPause()
            if self._nextCellRequested:
                # Consumed here, against this cell, rather than left for
                # whichever cell _runLoopBody's own while loop pops next --
                # that next iteration is still inside this same call, past
                # the reach of either entry point's finally.
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
                # Same boundary as the top-of-loop check above: this cell is
                # done, and the request that caused it must not ride along to
                # whichever cell the queue processes next.
                self._nextCellRequested = False
                self.sigCellFinished.emit(cell, "skipped")
                return
            except RetryCurrentCell:
                retries += 1
                if retries > self.maxRetries:
                    # Same boundary again: retries on this cell are over, and
                    # a request observed during them must not carry into the
                    # next queued cell.
                    self._nextCellRequested = False
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
                # uncaught. Reported "stopped" first so the interrupted cell's
                # row doesn't read "running" forever once the run has ended.
                self.sigCellFinished.emit(cell, "stopped")
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
                    signal = ctx.pending_flow_signal
                    # Captured into a local and cleared on ctx before raising.
                    # signal.__traceback__ already holds _raise_flow_signal's own
                    # frame, whose `self` is ctx, so ctx stays reachable from the
                    # chained exception regardless of this clear. What the clear
                    # achieves is breaking ctx's own reference to signal, turning
                    # ctx -> signal -> traceback -> frame -> ctx from a reference
                    # cycle into a one-way chain -- reclaimable by plain
                    # refcounting instead of needing the cyclic GC.
                    ctx.pending_flow_signal = None
                    logger.error(
                        "Flow signal %r was raised but swallowed by the "
                        "protocol while processing cell %r",
                        signal,
                        cell,
                    )
                    # This path always raises AbortExperiment rather than
                    # returning, so it is caught by _runLoopBody's finally (for
                    # the queue loop) or run_sync_cell's finally (for the
                    # direct path) on the way out -- no separate clear needed
                    # here.
                    self.sigStatus.emit("error")
                    self.sigCellFinished.emit(cell, "error")
                    raise AbortExperiment(
                        f"flow signal raised but swallowed by the protocol: {signal!r}"
                    ) from signal
                # Same boundary again: this cell finished normally, and a
                # request the protocol set but never itself acted on must not
                # carry into the next queued cell.
                self._nextCellRequested = False
                self.sigCellFinished.emit(cell, "done")
                return
