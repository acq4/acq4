"""Orchestrator: runs a cell queue serially, setting each cell up (pipette
target, data directory) and closing it out (tracking history) around its
protocol function, and converting the flow-signal exceptions that come back
into queue control."""
from __future__ import annotations

from collections import deque

from acq4.logging_config import get_logger
from acq4.util import Qt
from acq4.util.task import Stopped, Event, check_stop, asynch_with_qt_signals

from .actions.storage import new_data_dir
from .context import ExecutionContext
from .error_record import RunErrorRecord
from .exceptions import (
    OrchestrationError,
    AdvanceToNextCell,
    RetryCurrentCell,
    AbortExperiment,
    FlowSignal,
)

logger = get_logger(__name__)

# What a Cell directory is named by, beyond the tracking history: the detector's
# own description of the cell, the reference cube it was seeded with, and the
# positions it was seen at. Spelled with their extensions so the names read the
# same here as they do in the directory -- YamlFile's own default extension is
# ".yml", and a mix of the two spellings across the tree would be a nuisance to
# glob for.
CELL_METADATA_FILE = "cell_metadata.yaml"
REFERENCE_STACK_FILE = "reference_stack.ma"
POSITION_HISTORY_FILE = "position_history.yaml"


def _trackingResultCount(cell) -> int:
    """How many tracking results `cell`'s tracker has recorded; 0 for a cell
    that was never tracked.

    The measure of "is there anything new on this tracker since the last time it
    was written to disk" -- see _saveOutgoingCellTracking, the one caller that
    has to ask. Reads through getattr rather than the Cell API because the cells
    a run works are only ever duck-typed here: the engine has no import of
    acq4_automation's Cell, and a queue of bare sentinels is what most of the
    tests hand it.
    """
    tracker = getattr(cell, "_tracker", None)
    if tracker is None:
        return 0
    results = getattr(tracker, "tracking_results", None)
    return 0 if results is None else len(results)


def _saveTrackingHistory(cell, dirHandle, autoIncrement=False) -> None:
    """Write `cell`'s .acqtrack tracking history into `dirHandle`.

    Nothing is raised out of here, at any call site: every one of them is on a
    path that is closing a cell out or handing the pipette a new one, where a
    bookkeeping failure must not replace the thing that actually ended the pass
    (nor halt a run over a file that could not be written). Both the deferred
    import -- which reaches an internal repository that need not be installed --
    and the save itself are covered.

    Nowhere to write is not a failure either: a headless run has no manager, so
    no directory, and there is genuinely nothing this can do. It is the one
    silent path.
    """
    if dirHandle is None:
        return
    try:
        # Imported here, not at module scope: feature_tracking reaches
        # acq4_automation (an internal repository) at its own module scope, so a
        # top-level import would stop every test under acq4/experiment from
        # collecting where it is absent -- the same reason tile_detector and
        # actions.device defer theirs. It is also a module, not the engine, so
        # importing it here keeps that dependency at the one place that has it.
        from acq4.modules.AutomationDebug.feature_tracking import saveTrackingHistory

        saveTrackingHistory(cell, dirHandle, autoIncrement=autoIncrement)
    except Exception:
        logger.exception("Failed to save the tracking history for cell %r", cell)


def _plainFloat(value):
    """`value` as a builtin float, or None if it is not a number.

    Everything written from here goes into a YAML file or a repr/eval index
    file, and neither has any representation for a numpy scalar: a detector's
    score arrives as a numpy float, and yaml.dump refuses it outright. The
    conversion has to be total rather than best-effort, because a single
    unconvertible value costs the whole file.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _plainString(value):
    """`value` as a builtin string, or None. A path may arrive as a pathlib
    Path, which yaml.dump has no representation for either."""
    return None if value is None else str(value)


def _plainBool(value):
    """`value` as a builtin bool, or None if there was no value at all -- which
    is a third answer, not a false one: a cell with no tracker has no policy."""
    return None if value is None else bool(value)


def _plainPoint(position):
    """`position` as a list of builtin floats, or None.

    coorx Points, numpy arrays and plain tuples all arrive here -- a cell's
    positions are coorx Points, a tile centre is a pair of floats -- and neither
    of the first two survives yaml.dump. Iterating and coercing covers all three
    without this having to know which it was handed.
    """
    if position is None:
        return None
    try:
        return [float(v) for v in position]
    except (TypeError, ValueError):
        return None


def _detectionTime(cell):
    """When `cell` came into existence, in ptime seconds, or None.

    A Cell records its construction time as the first key of its position
    history, and for a detected cell construction *is* detection: tile_detector
    builds one per candidate the instant the detector returns. Nothing else
    records it -- the .acqtrack's own `saved_at` is when the file was written,
    which for a cell that sat in the queue and was then abandoned can be a long
    time later.
    """
    positions = getattr(cell, "_positions", None)
    if not positions:
        return None
    try:
        return float(min(positions))
    except (TypeError, ValueError):
        return None


def _referenceStack(cell):
    """The `(data, transform)` of the first reference cube on `cell`'s tracker,
    or `(None, None)`.

    The same attribute chain actions.device._trackerStack reads for Area 5's
    image pane, and with the same tolerance: a cell with no tracker, a tracker
    whose estimator holds no reference yet, and a cell that is a bare sentinel
    all answer None rather than raising. Read through getattr and a broad except
    for the reason _trackingResultCount gives -- the cells a run works are only
    ever duck-typed in this engine.

    The array is left in the orientation the tracker holds it in, rather than
    swapped for display the way the Area 5 payload is. The transform saved
    alongside maps that array's own indices to global coordinates, so swapping
    the axes would quietly invalidate the one thing that says where the cube is.
    """
    tracker = getattr(cell, "_tracker", None)
    if tracker is None:
        return None, None
    try:
        objstack = tracker.motion_estimator.original_object_stack
        data = objstack.data
        if data is None:
            return None, None
        return data, getattr(objstack, "transform", None)
    except Exception:
        return None, None


def _cellMetadata(cell) -> dict:
    """The plain-data description of `cell`: what found it, where, and with what.

    Every read goes through getattr with a default, and not merely out of
    caution. `volume` and the three provenance fields tile_detector attaches are
    genuinely not declared on Cell, so a cell the operator seeded by hand raises
    AttributeError on the attribute rather than answering None. The cells a run
    works are duck-typed throughout the engine besides, so a queue of bare
    sentinels has to produce a dict here rather than an exception.

    The four model paths are in here for the reason that is easiest to overlook:
    `score` is a raw model output, and what it means depends entirely on which
    checkpoint produced it. A score recorded without that checkpoint cannot be
    compared against a score from any other run, so the two belong in one file.

    `use_cellpose` is derived from the tracker's class rather than recorded at
    detection, so that it has an answer for every cell however it arrived -- a
    cell seeded by hand and tracked from the patch FSM included. The class
    *name* rather than an isinstance test because this module deliberately has
    no import of acq4_automation (see _saveTrackingHistory); acquiring one for a
    boolean would put an internal repository on the engine's import path.
    """
    tracker = getattr(cell, "_tracker", None)
    trackerClass = None if tracker is None else type(tracker).__name__
    return {
        "score": _plainFloat(getattr(cell, "score", None)),
        "volume": _plainFloat(getattr(cell, "volume", None)),
        "initial_position": _plainPoint(getattr(cell, "initialPosition", None)),
        "detected_at": _detectionTime(cell),
        "tile_center": _plainPoint(getattr(cell, "tile_center", None)),
        "detection_prefix": _plainString(getattr(cell, "detection_prefix", None)),
        "detection_models": {
            name: _plainString(path)
            for name, path in (getattr(cell, "detection_models", None) or {}).items()
        },
        "tracker_class": trackerClass,
        "segmenter": _plainString(getattr(tracker, "_segmenter", None)),
        "use_cellpose": (
            None if trackerClass is None else trackerClass == "CellposeCellTracker"
        ),
        "allow_refresh_reference": _plainBool(
            getattr(cell, "allow_refresh_reference", None)
        ),
    }


def _cellDirInfo(metadata) -> dict:
    """The handful of metadata fields worth putting on the Cell directory's own
    index, where the Data Manager shows them beside the operator's notes.

    `location` is a field folderTypes.cfg already declares for a Cell, and a
    detected cell's location is a coordinate rather than a description, so it is
    written as one -- in micrometres, which is the scale an operator reads
    positions in. `score` and `volume` are not in that schema; they are extra
    keys in the same index, where `dirType` and `expUnit` already sit.

    Deliberately a subset, and deliberately scalars. The .index is a repr/eval
    config file, so what goes into it has to survive a round trip through repr,
    and the nested model-path dict would only duplicate the YAML file in a form
    that is harder to read. The schema's `depth` field is left for the operator:
    it means depth into the tissue, and what a run knows is a stage coordinate,
    which is a different number.
    """
    info = {}
    position = metadata.get("initial_position")
    if position is not None:
        info["location"] = "(%s) um" % ", ".join(f"{v * 1e6:.1f}" for v in position)
    for key in ("score", "volume"):
        if metadata.get(key) is not None:
            info[key] = metadata[key]
    return info


def _saveCellMetadata(cell, dirHandle) -> None:
    """Write what is known about `cell` into `dirHandle` as cell_metadata.yaml,
    and mirror its headline numbers onto the directory's index.

    Called the moment the directory exists -- before the protocol has run,
    before the pipette has been pointed anywhere -- because this is the one save
    that has to survive a pass that dies. Everything it records is already
    settled by then: it describes what the detector found, not what the run made
    of it.

    YAML rather than the index alone because the index is a repr/eval config
    file and this is a nested structure a human should be able to read; and
    `fileType` is passed explicitly because YamlFile and PyQTGraphConfigFile
    both claim `dict` at the same priority, so leaving the choice to
    suggestWriteType picks arbitrarily between them.

    Nothing is raised out of here. It is bookkeeping done on the way into a
    cell's protocol, and a cell whose metadata file could not be written is
    still a cell worth patching.
    """
    if dirHandle is None:
        return
    try:
        metadata = _cellMetadata(cell)
        dirHandle.writeFile(metadata, CELL_METADATA_FILE, fileType="YamlFile")
        dirHandle.setInfo(_cellDirInfo(metadata))
    except Exception:
        logger.exception("Failed to save the metadata for cell %r", cell)


def _saveReferenceStack(cell, dirHandle) -> None:
    """Write the reference cube `cell`'s tracker cut out of the stack it was
    found in into `dirHandle`, as a MetaArray.

    Unconditional -- not gated on the cell having been tracked -- because this
    cube is what the detector actually saw, and a cell that was queued and then
    abandoned before a single tracking frame is precisely the one an operator
    wants to look at. It is also the only imagery specific to this cell: the
    tile stack it was cut from covers a whole field of view and lives under the
    slice's tiles/ directory, shared with every other cell in that tile.

    The array also rides inside the .acqtrack's object_stacks group, and the
    duplication is deliberate. That file is a tracking recording, opened by the
    replay visualizer through acq4_automation's own loader; this is one array
    the Data Manager can open on its own. A megabyte against a tile stack of
    tens is not the cost worth optimising here.

    The transform goes onto the file's index rather than into the array, where
    the index's serializer already knows how to write a coorx Transform. Without
    it the cube is a picture of nowhere in particular.
    """
    if dirHandle is None:
        return
    data, transform = _referenceStack(cell)
    if data is None:
        return
    try:
        info = {} if transform is None else {"transform": transform}
        dirHandle.writeFile(
            data, REFERENCE_STACK_FILE, info=info, fileType="MetaArray"
        )
    except Exception:
        logger.exception("Failed to save the reference stack for cell %r", cell)


def _savePositionHistory(cell, dirHandle) -> None:
    """Write `cell`'s position time-series into `dirHandle` as YAML: a list of
    `[timestamp, [x, y, z]]` pairs in time order.

    The .acqtrack carries a position on each tracking result, but only for the
    frames that produced one, and never the detection position the cell was
    created at -- the first entry here is that position, and for an untracked
    cell it is the only entry there is. A cell with no .acqtrack at all has
    nowhere else this appears.

    Nothing is raised out of here, for the same reason as every other save on
    the close-out path.
    """
    if dirHandle is None:
        return
    positions = getattr(cell, "_positions", None)
    if not positions:
        return
    try:
        history = [
            [float(when), _plainPoint(positions[when])] for when in sorted(positions)
        ]
        dirHandle.writeFile(history, POSITION_HISTORY_FILE, fileType="YamlFile")
    except Exception:
        logger.exception("Failed to save the position history for cell %r", cell)


class Orchestrator(Qt.QObject):
    sigStatus = Qt.Signal(str)                 # "running"/"surveying"/"waiting"/"paused"/"error"
    sigCurrentCell = Qt.Signal(object)         # cell, or None when idle
    sigCellFinished = Qt.Signal(object, str)   # cell, status
    sigRunError = Qt.Signal(object)            # RunErrorRecord for the halt
    sigCellsQueued = Qt.Signal(object)         # list of cells just queued (worker thread)

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
        # The cell _processCell is working on right now, or None when none is.
        # Recorded by _processCell on entry and dropped by its finally, so it is
        # the orchestrator's own answer to "which cell is in hand" rather than
        # "which cell has been announced" -- see currentCell().
        self._currentCell = None
        # The cell abandonCellInHand() marked as belonging to tissue that no
        # longer exists, or None. Set on the GUI thread, read on the worker
        # thread at each terminal emit site (see _reportFinished), and dropped
        # by _processCell's finally alongside self._currentCell.
        self._abandonedCell = None
        # Per-run: set once the producer reports exhaustion, cleared by
        # _runLoopBody's finally. See setCellProducer for why it is not
        # simply "has the producer ever returned None".
        self._producerExhausted = False
        # What the last tracking-history save wrote: (cell, directory, number of
        # tracking results the cell's tracker held at the time), or
        # (None, None, 0) before the first one. Written by _closeCellDataDir as
        # each pass ends and read at the next cell's handover, which is where a
        # tracker that kept recording after its cell was closed out gets one
        # last chance to reach disk -- see _saveOutgoingCellTracking. One slot
        # rather than a per-cell map: only one cell is ever in hand, and only
        # the most recently closed-out one can still be on the pipette.
        #
        # It holds that one cell (and its directory) until the next cell is
        # closed out, including past the end of a run: the record has to outlive
        # the run loop, since the pipette is still holding that cell when the
        # next run's first handover displaces it. A pipette keeps every cell it
        # has ever been given (PatchPipette.previousCells) for the life of the
        # session, so one more reference here retains nothing that was going to
        # be freed anyway.
        self._savedTracking = (None, None, 0)
        # The managed Cell directory already made for a given cell, keyed by
        # id(cell) rather than held on the cell itself: cells reaching this
        # engine are only ever duck-typed (a bare str stands in for one in most
        # of this module's own tests), so nothing guarantees a cell can carry an
        # attribute. Each entry keeps a strong reference to the cell alongside
        # its directory -- with the cell kept alive by this dict, id(cell)
        # cannot be recycled onto a different object for as long as its entry
        # survives, which is what makes id() safe to key on here. Read by
        # _makeCellDataDir so a cell CellPanel re-enqueues after it reaches a
        # terminal disposition (see CellPanel._onReuseCheckedCells) re-enters
        # the directory it already has on its next pass instead of a sibling.
        # Never emptied: a cell keeps its entry for the life of the
        # orchestrator, the same trade its pipette already makes by never
        # releasing a cell from previousCells.
        self._cellDataDirs = {}

    # ---- queue / context ----
    def enqueue(self, cell):
        # Deliberately does not emit sigCellsQueued, where _refillQueue does.
        # This is the hand-seeded path: it runs on the GUI thread, called by
        # something that knows exactly which cell it is adding and adds that
        # cell's row itself as it calls (CellPanel._enqueueAndAdd). Announcing
        # here too would give that cell a second row, or push the panel into
        # de-duplicating rows it created a moment earlier. The signal exists for
        # the cells that appear with nobody watching -- the ones the survey
        # producer discovers on the worker thread, mid-run.
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

    def currentCell(self):
        """The cell being processed right now, or None if none is.

        Set the instant _processCell takes the cell -- before its context is
        built, and before sigCurrentCell announces it -- and dropped by that
        method's finally however the pass ends. So this answers "which cell is
        being processed right now", which is strictly earlier and more current
        than what sigCurrentCell has delivered: that signal reaches a GUI-thread
        slot through a queued connection, so a caller acting on the operator's
        behalf can run before the announcement for a cell the worker thread
        already popped. Asking here does not depend on that delivery, which is
        what abandonCellInHand() -- its one consumer -- needs of it.

        It does not say the protocol has begun, that the cell is still
        physically being worked (a worker thread wedged inside a protocol leaves
        it named here for as long as it stays wedged), or anything about the
        cells still queued behind it -- pendingCells() is that question. A
        single attribute read, so a GUI-thread caller can never see a
        half-updated answer while the worker thread assigns one.
        """
        return self._currentCell

    def abandonCellInHand(self) -> None:
        """Record that the cell being processed right now belongs to tissue that
        no longer exists, suppressing its terminal sigCellFinished.

        AutopatchWindow.newSlice() is the caller: the operator has swapped the
        tissue, so every coordinate on the old slice is a place not to drive a
        pipette. That path deliberately lets the cell already in flight run to
        completion -- yanking a pipette out mid-protocol is its own hazard -- but
        its terminal disposition would otherwise be reported to a panel that has
        just wiped its list, giving a discarded coordinate a row, an attempted
        flag and a disposition. A terminal disposition is what makes a cell
        re-queueable, so that row would be offered to "Check all completed" and
        from there to reuse.

        Deliberately NOT wired into clearQueue(), whose other caller --
        AutopatchWindow._onTissueMoved's rescan branch -- means "the tissue
        moved", not "the tissue is gone". The cell that lost tracking there must
        keep reporting its disposition: it stays attempted, stays in the tissue
        density record, and its Area 5 row is the session record.

        What makes this work where a panel-side filter did not: the decision is
        made on the worker thread at emit time (_reportFinished), against a
        single attribute this method assigns, so between deciding and acting
        there is no interval for a wipe to land in. Two orderings are covered:

        - This lands while the cell is still in hand, so the emit that follows is
          suppressed. This is the case where the pipette is mid-protocol, which
          is what a New slice click during a run means.
        - The terminal emit already happened *and was already delivered*. Nothing
          is marked (the cell is no longer in hand), but the row it created
          exists before the wipe, so CellPanel.clearCells() removes it.

        Matched by identity rather than by a flag, so a marking made when the
        worker thread has just moved on cannot suppress the next cell's
        disposition -- swallowing a legitimate disposition is the mirror-image
        defect, and a worse one. With nothing in hand this records nothing at
        all.

        What it does NOT cover, stated plainly because a reader must not assume
        otherwise: the ordering where the terminal emit has already happened but
        its queued delivery is still pending when this runs. The cell is already
        released, so nothing is marked, and the delivery then builds the row and
        its disposition after the wipe -- reachable by reuse. Qt posts the emit
        and the operator's click to the same GUI-thread queue in order, so a
        click made after the emit is always dispatched behind it and lands in the
        covered case above; what is left is the emit falling inside the interval
        between the click being posted and the GUI thread dispatching it.
        Closing that needs the orchestrator to remember an abandonment across the
        release, which this deliberately does not do.

        Also not covered, and cosmetic: sigCurrentCell and the non-terminal
        "retry" disposition are not suppressed, so a row for an abandoned cell
        can still appear reading "running" or "retry". Such a row carries no
        terminal disposition, so it is not re-queueable and "Check all completed"
        will not tick it.
        """
        self._abandonedCell = self.currentCell()

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
        self.clearProducerExhausted()

    def clearProducerExhausted(self) -> None:
        """Ask the producer again, even though it already reported exhaustion.

        The flag is a per-run cache of "there is nothing left to find". Anything
        that puts uncovered tiles back on the slice -- installing a producer, or
        a forced rescan after the tissue moved -- invalidates it, and leaving it
        set ends the run on a queue that could have been refilled.
        """
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
            self._runLoopBody, name="autopatch queue loop", on_finish=self._onLoopFinished
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
                # the same thing, the run is done. The pop is what takes the
                # cell in hand; _processCell records it as such on entry, so
                # currentCell() covers it from here on regardless of which
                # entry point reached this loop.
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
            # And the pause request, for the same reason and with the sharpest
            # consequence of the three: a run stopped while parked at a pause
            # check -- or stopped/aborted with a pause requested but not yet
            # honored -- would otherwise leave the event cleared, so the next
            # start() reports "running" and then "paused" without the operator
            # touching Pause. Area 3's button would come back reading "Resume"
            # for a pause belonging to a run that is over, and the run they
            # just started would sit there doing nothing.
            self._pauseEvent.set()
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
            self._reportRunError(exc)
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
        if cells:
            # Announced only once the batch is actually queued, and only for a
            # batch that was: without this the only thing that ever says a
            # survey found cells is one of them starting to run, so the operator
            # watches an empty list while a queue's worth of found cells sits
            # behind it. Neither of the two paths above reaches here -- a
            # discarded batch belongs to tissue the operator has declared gone,
            # and exhaustion queued nothing -- and an empty batch is skipped for
            # the same reason as exhaustion: a barren tile queued no cells, so
            # there is nothing to put in front of anyone.
            #
            # A copy of the batch rather than the producer's own list: this is
            # emitted from the worker thread, so a GUI-thread receiver reads it
            # through a queued connection, well after this call has returned and
            # the producer is free to reuse or mutate what it handed over.
            self.sigCellsQueued.emit(list(cells))

    def _reportRunError(self, exc: BaseException, cell=None) -> None:
        """Publish the failure that is about to halt this run, then set status.

        Called at every halt site, immediately before the AbortExperiment that
        wraps `exc`. Carries a RunErrorRecord -- plain formatted strings -- so
        nothing downstream can retain the exception and the frames behind it
        (see error_record.describe_exception).

        `exc` is the original failure rather than the AbortExperiment wrapper:
        the wrapper does not exist yet here, and its own frames would say only
        that the orchestrator gave up. The chain is preserved anyway, since
        the wrapper is raised `from exc`.

        Not every failure has a cell -- a producer raising during a refill is
        attributed to none, and there is no log entry for it either. That is why
        this is a run-level report and not simply more fields on ActionLogEntry.

        Emitted before sigStatus so a slot reacting to "error" already has the
        record. The two emits are sequential statements in one call, and Qt
        preserves emit order to any one receiver as long as both signals reach
        it over the same connection type -- true of every receiver today, since
        none mixes a direct connection to one of these two signals with a
        queued connection to the other. A receiver that did would not get this
        guarantee for free.
        """
        self.sigRunError.emit(RunErrorRecord.from_exception(exc, cell))
        self.sigStatus.emit("error")

    def _reportFinished(self, cell, status: str) -> None:
        """Announce `cell`'s terminal disposition, unless it has been abandoned.

        Every terminal sigCellFinished emit goes through here; the non-terminal
        "retry" emits directly, since a retry loops in place and the pass it
        belongs to still has a terminal disposition of its own to come.

        Runs on the worker thread, so the identity test and the emit are one
        step from the point of view of a GUI-thread abandonCellInHand() -- see
        that method for why that is what makes the suppression sound.
        """
        if cell is self._abandonedCell:
            return
        self.sigCellFinished.emit(cell, status)

    def _makeCellDataDir(self, ctx, cell):
        """Create the managed "Cell" directory this cell's data is saved into,
        and make it the current one -- or, if this cell already has one from an
        earlier pass, re-enter that directory instead.

        Everything a run writes -- the cellfie stack, the patch log, a
        TaskRunner sequence -- lands under the manager's current directory, so
        without this every cell in a run would save into whichever directory the
        operator last set: one Cell directory holding an unseparable pile of
        every cell's data, with each cellfie overwriting the last. Done here for
        the same reason the target is (see _giveCellToPipette): a protocol that
        omitted the call would still run, and the loss would only be discovered
        in the data.

        Before the target rather than after, so an operator who has not chosen a
        storage directory finds out before the pipette has been pointed anywhere.

        A cell CellPanel re-enqueues once it reaches a terminal disposition (see
        CellPanel._onReuseCheckedCells) is the same Cell object, tracker
        included, arriving at a second _processCell pass -- minting it a fresh
        sibling directory here would split one physical cell's data across two
        folders, with the tracker's cumulative history landing in whichever
        directory the last pass made and the folder actually named after the
        cell holding only whatever an earlier pass wrote before that. See
        self._cellDataDirs for how this tells that case apart from a genuinely
        new cell.

        A directory recorded for this cell that has since stopped existing (a
        storage-dir change mid-run, most plausibly) halts the run rather than
        falling back to a new sibling: a silent fallback would reproduce the
        very split this reuse exists to prevent, only now by this method's own
        choice instead of by the oversight that caused it in the first place.

        Nothing to create it under is not a failure -- a headless run has no
        manager -- but a manager that cannot make (or re-enter) the directory
        halts the run: the alternative is patching cell after cell into a
        directory that names another cell.

        The cell's metadata is (re)written into it as soon as it is current,
        rather than alongside the tracking history at close-out. Everything in
        that file is already settled by now -- it is what the detector found --
        and writing it here is what makes it survive a protocol that dies on its
        first move, which is the pass whose inputs an operator most wants to
        read. Rewriting it on a reused directory is harmless rather than a
        second, competing observation: it is the same cell's own settled facts,
        recomputed from the same attributes, so the second write is either
        identical to the first or a strict update of it.

        Returns the directory (None when there was no manager to make one), which
        _closeCellDataDir needs: by the time the pass ends the protocol may have
        moved the current directory elsewhere.
        """
        manager = getattr(ctx, "manager", None) if ctx is not None else None
        if manager is None:
            return None
        reused = self._cellDataDirs.get(id(cell))
        if reused is not None:
            _, savedDir = reused
            if not savedDir.exists():
                raise OrchestrationError(
                    f"the data directory previously made for cell {cell!r} no "
                    f"longer exists: {savedDir.name()}"
                )
            try:
                manager.setCurrentDir(savedDir)
            except (Stopped, FlowSignal):
                raise
            except Exception as exc:
                raise OrchestrationError(
                    f"could not re-enter the data directory for cell {cell!r}: {exc}"
                ) from exc
            _saveCellMetadata(cell, savedDir)
            return savedDir
        try:
            # Through the protocol-facing action rather than create_data_dir, for
            # its log_action entry: the operator has to be able to find a cell's
            # data, and Area 5's timeline is where this run says where it went.
            cellDir = new_data_dir(ctx, level="Cell")
        except (Stopped, FlowSignal):
            # Same pass-through as _giveCellToPipette below.
            raise
        except Exception as exc:
            raise OrchestrationError(
                f"could not create a data directory for cell {cell!r}: {exc}"
            ) from exc
        # Deliberately not inside the try above: a directory that could not be
        # made halts the run, and a metadata file that could not be written must
        # not be mistaken for one. _saveCellMetadata swallows its own.
        _saveCellMetadata(cell, cellDir)
        self._cellDataDirs[id(cell)] = (cell, cellDir)
        return cellDir

    @staticmethod
    def _giveCellToPipette(ctx, cell) -> None:
        """Hand `cell` to the pipette bound on `ctx`, which sets its target.

        The protocol's moves are all named positions -- "approach", "target",
        "aboveTarget" -- and every one of them is derived from the pipette's
        target. Nothing in a protocol establishes that target, so without this
        every cell after the first would be approached at the previous cell's
        coordinate: a pipette driven into tissue nowhere near the cell whose row
        the operator is watching. Done here rather than left to the protocol
        because a protocol that forgot the call would not fail, it would patch
        the wrong place.

        setCell() rather than pipetteDevice.setTarget(): the patch FSM reads the
        cell off the pipette (to follow it while approaching, and to stop when
        tracking is lost), so a target set without the cell behind it would have
        the FSM tracking whatever the last run left there.

        Nothing to hand the cell to is not a failure: the engine's own default
        context carries no pipette, which is what a headless run or a test that
        only exercises the queue looks like.

        A pipette that cannot take the cell halts the run (the caller's
        OrchestrationError handler reports it and aborts) rather than letting the
        protocol move against a stale target -- the precise failure this exists
        to prevent, and one the protocol has no way to notice.
        """
        pipette = getattr(ctx, "pipette", None) if ctx is not None else None
        if pipette is None or cell is None:
            return
        try:
            pipette.setCell(cell)
        except (Stopped, FlowSignal):
            # Same pass-through as every other call site in this file: a
            # cooperative stop and a flow signal are decisions, not failures to
            # be re-labelled as an inability to target the cell.
            raise
        except Exception as exc:
            raise OrchestrationError(
                f"could not set the pipette target for cell {cell!r}: {exc}"
            ) from exc

    def _closeCellDataDir(self, ctx, cell, cellDir) -> None:
        """Save `cell`'s tracking history into `cellDir` and step the manager's
        current directory back out of it.

        Runs however the pass ended -- done, skipped, retry-exhausted, error,
        stopped, abandoned -- because a cell whose protocol failed is exactly the
        one whose tracking history an operator wants: it is the record of what
        the tracker saw before things went wrong. An abandoned cell keeps its
        file too; what abandonCellInHand suppresses is a panel row, not the data
        already on disk.

        Written into `cellDir` rather than the manager's current directory: a
        protocol is free to move that (a TaskRunner sequence does), and the
        history belongs to the cell, not to wherever the run left off.

        A pass that ended without a directory of its own still gets its history
        written, into whatever current directory there is. There are two ways to
        arrive here that way and both carry a tracked cell: the manager could
        not make the Cell directory (a storage failure, which halts the run), and
        the context was built without a manager at all while the orchestrator has
        one. Either way the cell can already be carrying results -- the survey
        tracked it into existence, and a re-queued cell arrives with its earlier
        attempt's -- and losing them because the directory that names the cell is
        missing is the loss this exists to prevent. Auto-incremented there,
        because that directory is shared by every cell that lands in it: the
        second cell's history must not be written over the first's.

        Stepping the current directory back out is what keeps the *next* thing
        the run does from landing inside a finished cell -- the survey imaging a
        tile between cells, most of all. Creating the next cell's directory would
        not nest (create_data_dir walks up), but a tile stack saved in the
        meantime would.

        Nothing is raised out of here. This runs from _processCell's finally, so
        an exception would replace whatever actually ended the pass -- the halt
        the operator needs to see -- with a bookkeeping failure. _saveTrackingHistory
        already logs and swallows its own; this covers the rest.
        """
        try:
            manager = getattr(ctx, "manager", None) if ctx is not None else None
            if manager is None:
                # The orchestrator's own manager, which is what the engine's
                # default context would have carried: a context built without one
                # is a thin context, not a run with nowhere to save.
                manager = self.manager
            if cellDir is None:
                if _trackingResultCount(cell) == 0:
                    # A cell that was never tracked has nothing to place, so
                    # there is no reason to go looking for somewhere to put it.
                    # Asking is not free: a manager raises outright when the
                    # operator has not chosen a storage directory, which would
                    # log a failure for every untracked cell of such a run.
                    return
                fallback = manager.getCurrentDir() if manager is not None else None
                self._writeTrackingHistory(cell, fallback, autoIncrement=True)
                return
            self._writeTrackingHistory(cell, cellDir)
            # The reference cube and the position series go in whatever the
            # tracking history amounted to, including nothing at all. A cell
            # that was detected, seeded from its tile's stack and then abandoned
            # has no tracking results and no .acqtrack worth speaking of, and
            # these two are the whole of what is left to say about it.
            _saveReferenceStack(cell, cellDir)
            _savePositionHistory(cell, cellDir)
            if manager is not None:
                manager.setCurrentDir(cellDir.parent())
        except Exception:
            logger.exception(
                "Failed to close out the data directory for cell %r", cell
            )

    def _writeTrackingHistory(self, cell, dirHandle, autoIncrement=False) -> None:
        """Write `cell`'s tracking history into `dirHandle`, and record what was
        written.

        The record -- which cell, into which directory, and how much history it
        had at the time -- is what lets the next handover tell a tracker that has
        kept recording since from one that is already fully on disk, and lets it
        put the difference in the same directory as the rest of that cell's
        history rather than in the next cell's. See _saveOutgoingCellTracking.

        Nothing is recorded when there was nowhere to write: a run with no
        manager wrote no file, and claiming otherwise would have a later save
        aim at a directory that was never used.
        """
        if dirHandle is None:
            return
        _saveTrackingHistory(cell, dirHandle, autoIncrement=autoIncrement)
        self._savedTracking = (cell, dirHandle, _trackingResultCount(cell))

    def _saveOutgoingCellTracking(self, ctx, cell) -> None:
        """Save the tracking history of whatever cell the pipette is still
        holding, before `cell` displaces it.

        PatchPipette.setCell() closes the cell it is holding: tracking is turned
        off and the cell is pushed onto previousCells, out of reach of anything
        that would save it. For a cell this orchestrator worked that is usually
        harmless -- _closeCellDataDir wrote its history as its pass ended -- but
        "usually" is doing real work there. A pipette's FSM state job is detached
        from the protocol that asked for it, so it can still be tracking, and
        still appending to that cell's tracker, after the pass was closed out;
        and the pipette may be holding a cell this orchestrator never processed
        at all, one AutomationDebug or a manual newCell() left there, whose
        history nothing else is going to write.

        The tracker is saved whole, so the file written here is a superset of the
        one the close-out wrote rather than only the results that came after it.
        Auto-incremented so it lands beside that earlier file instead of over it,
        and written into the same directory, so a cell's history stays in the
        directory that names the cell. A cell this orchestrator has no record of
        goes to the manager's current directory instead -- called before the next
        cell's own directory is made, so "current" is still the storage directory
        the run is working in rather than a directory named after another cell.

        Skipped when the tracker has gained nothing since it was last written,
        which is the ordinary cell-to-cell handover: a duplicate file in every
        cell directory of every run is noise an operator has to read past.

        Nothing is raised out of here, for the same reason as _closeCellDataDir:
        this is bookkeeping done on the way into a cell's protocol, and a run
        must not be halted by it. Asking a manager for its current directory is
        itself one of the ways that can fail -- it raises outright when the
        operator has not chosen a storage directory.
        """
        pipette = getattr(ctx, "pipette", None) if ctx is not None else None
        if pipette is None:
            return
        outgoing = getattr(pipette, "cell", None)
        if outgoing is None or outgoing is cell:
            return
        try:
            savedCell, savedDir, savedCount = self._savedTracking
            if outgoing is savedCell:
                if _trackingResultCount(outgoing) <= savedCount:
                    return
                dirHandle = savedDir
            else:
                manager = getattr(ctx, "manager", None) if ctx is not None else None
                if manager is None:
                    manager = self.manager
                dirHandle = manager.getCurrentDir() if manager is not None else None
            self._writeTrackingHistory(outgoing, dirHandle, autoIncrement=True)
        except Exception:
            logger.exception(
                "Failed to save the tracking history of cell %r before handing "
                "the pipette cell %r",
                outgoing,
                cell,
            )

    def _processCell(self, cell):
        """Run the protocol function for one cell. RetryCurrentCell loops in
        place (bounded by maxRetries, restarting the same cell rather than
        re-queuing it); AdvanceToNextCell skips."""
        # Recorded before anything at all is done with this cell -- before its
        # context is built and before sigCurrentCell announces it -- and dropped
        # by the finally below however this pass ends, including the paths that
        # leave by raising. Every route that takes a cell in hand comes through
        # here (_runLoopBody's popleft, and run_sync_cell's direct call), so this
        # one pair is what makes currentCell() honest for all of them. A retry
        # loops in place inside the try, so the cell stays in hand across it.
        self._currentCell = cell
        # Pre-bound so the finally below can reach both however this pass ends,
        # including the routes that leave before the first attempt has built a
        # context (a "Next cell" request observed at the top of the loop).
        ctx = None
        cellDir = None
        try:
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
                    self._reportFinished(cell, "skipped")
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
                    if retries == 0:
                        # Set up once per cell, not once per attempt: a retry
                        # restarts the protocol in place for a cell that is
                        # already set up.
                        #
                        # Its data belongs with the first attempt's rather than
                        # in a second directory that reads as another cell; and
                        # handing the cell to the pipette again would close the
                        # one it is holding (dropping the tracking the first
                        # attempt established) only to hand back the same cell.
                        # The pipette also has the better of the two targets by
                        # then -- tracking moves it as the cell drifts, so
                        # re-setting it from the queued coordinate would throw
                        # that away.
                        #
                        # The outgoing cell is saved before the directory is
                        # made, not as part of the handover that displaces it,
                        # so a cell this orchestrator has no record of does not
                        # have its history filed inside a directory named after
                        # the cell that displaced it.
                        self._saveOutgoingCellTracking(ctx, cell)
                        cellDir = self._makeCellDataDir(ctx, cell)
                        self._giveCellToPipette(ctx, cell)
                    self.protocolFile.run(ctx, **self.protocolFile.param_values())
                except AdvanceToNextCell:
                    # Same boundary as the top-of-loop check above: this cell is
                    # done, and the request that caused it must not ride along to
                    # whichever cell the queue processes next.
                    self._nextCellRequested = False
                    self._reportFinished(cell, "skipped")
                    return
                except RetryCurrentCell:
                    retries += 1
                    if retries > self.maxRetries:
                        # Same boundary again: retries on this cell are over, and
                        # a request observed during them must not carry into the
                        # next queued cell.
                        self._nextCellRequested = False
                        self._reportFinished(cell, "retry-exhausted")
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
                    self._reportFinished(cell, "stopped")
                    raise
                except OrchestrationError as exc:
                    # Design §5's catch-all safety net: an uncaught orchestration
                    # error halts the run rather than blazing through the remaining
                    # queued cells. Handler sub-protocols are gone; a protocol
                    # author who wants to recover from this writes their own
                    # try/except in run().
                    logger.exception(
                        "Unhandled orchestration error while processing cell %r", cell
                    )
                    self._reportRunError(exc, cell)
                    self._reportFinished(cell, "error")
                    raise AbortExperiment(
                        f"unhandled orchestration error while processing cell: {exc}"
                    ) from exc
                except Exception as exc:
                    # An unexpected bug (not a flow signal, and not an
                    # OrchestrationError the protocol chose to let propagate) must
                    # fail loud rather than be silently swallowed: log it, surface
                    # it as an error to the UI, and abort the run rather than
                    # blazing through the remaining queued cells.
                    logger.exception(
                        "Unexpected exception while processing cell %r", cell
                    )
                    self._reportRunError(exc, cell)
                    self._reportFinished(cell, "error")
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
                        self._reportRunError(signal, cell)
                        self._reportFinished(cell, "error")
                        raise AbortExperiment(
                            "flow signal raised but swallowed by the protocol: "
                            f"{signal!r}"
                        ) from signal
                    # Same boundary again: this cell finished normally, and a
                    # request the protocol set but never itself acted on must not
                    # carry into the next queued cell.
                    self._nextCellRequested = False
                    self._reportFinished(cell, "done")
                    return
        finally:
            self._closeCellDataDir(ctx, cell, cellDir)
            # The abandoned marking is dropped with the cell in hand it was read
            # from, so it never outlives it and never reaches a later pass. This
            # is the only clear either one needs: every route into this method is
            # covered by the comment above, and a retry loops in place inside the
            # try, so both survive it.
            self._currentCell = self._abandonedCell = None
