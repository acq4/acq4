"""CellPanel: Area 5's manually-seeded cell queue and its list view, kept in
sync with the Orchestrator's per-cell lifecycle signals."""
from __future__ import annotations

import random

import numpy as np
from coorx import Point

from acq4_automation.feature_tracking.cell import Cell
from acq4.experiment.actions.device import _trackerStack
from acq4.util import Qt

from .details_renderers import buildDetailsWidget
from .sizing import CompactLabel, floorAtRows

# Random scatter radius for the "Scatter fake cells" demo button (meters).
_SCATTER_RADIUS = 40e-6

# The dispositions Orchestrator.sigCellFinished reports for a cell that has
# finished a pass, in any state. "retry" is deliberately absent: it is emitted
# mid-flight and superseded by whichever of these the cell eventually reaches.
# A separate string space from ActionLogEntry.outcome (see _OUTCOME_GLYPHS),
# which describes one action rather than one cell.
TERMINAL = frozenset({"done", "skipped", "stopped", "retry-exhausted", "error"})
# The subset "Check all completed" ticks: only "done" means the protocol ran to
# completion. "error" and "retry-exhausted" are failures, and "stopped" and
# "skipped" are abandonment -- offering any of them up as a completion would
# re-queue cells that never did the work. Each is a manual opt-in instead.
COMPLETED = frozenset({"done"})

# How few rows of a scrolling view in this panel are still worth reading. Area 5
# is a scrolling viewport over the whole panel (see AutopatchWindow._makeArea),
# so every pixel a view in here insists on is a pixel the panel refuses to give
# up when that area is squeezed -- and the queue, the timeline and the log all
# answer their question a few rows at a time, scrolling within themselves for
# the rest.
_VIEW_ROWS = 3

# Row text for the synthetic timeline row _seedReferenceStackRow inserts at
# index 0 for a cell whose tracker is already initialized when its (empty)
# timeline is seeded. Plain and constant, unlike the "running"/outcome rows
# _appendTimelineRow and _finishTimelineRow compose: nothing backs this row
# with an ActionLogEntry to report a status or an outcome for.
_REFERENCE_STACK_ROW_TEXT = "Tracker initialized"


def _liveReferenceStackDetails(cell):
    """("image_stack", payload) read directly off `cell`'s tracker, or None
    if it has no reference stack to show.

    Reads the same attribute chain acq4.experiment.actions.device._trackerStack
    does (cell._tracker.motion_estimator.original_object_stack.data), and
    shapes the payload the same way device._attachStackDetails does, so this
    renders identically to a real Cellfie action's own image_stack details.
    Callers, not this function, are responsible for only calling it where
    that read is safe -- see _seedReferenceStackRow's docstring.
    """
    stack = _trackerStack(cell)
    if stack is None:
        return None
    return (
        "image_stack",
        {
            "stack": stack,
            "center_index": (
                stack.shape[0] // 2 if stack.ndim >= 3 and stack.shape[0] > 1 else None
            ),
            "title": _REFERENCE_STACK_ROW_TEXT,
        },
    )


class _DetailsViewport(Qt.QScrollArea):
    """The scrolling viewport the selected action's details widget is mounted in.

    A details widget is whatever the action that produced it asked for -- a
    z-stack in a pg.ImageView, a test-pulse plot beside its state transitions --
    and several of those insist on a few hundred pixels. Mounted straight into
    the panel, that demand becomes the panel's own minimum: selecting a row with
    a figure in it would push the cell queue and the log off the bottom of a
    squeezed Area 5, and the operator would get scrollbars over a panel they had
    deliberately made small. Insisting on nothing here leaves the demand where
    it belongs -- the pane takes whatever room the panel has to spare, and
    scrolls the figure within itself when that is not enough.

    The preferred size is read back from the mounted container rather than left
    to QAbstractScrollArea, for the same reason _AreaViewport reads its own from
    its content (see Autopatch.py): that hint is computed once per setWidget()
    and cached ever after, and this viewport is handed its container empty and
    filled again on every selection.

    Reading it is only half of keeping up, though. A widget also caches the size
    it last reported *upwards*, and mounting a figure invalidates the layouts
    inside the container without that news ever reaching the panel's layout --
    which would go on offering the hint computed while the pane was empty, and
    mount every figure into a strip a few pixels tall with scrollbars of its
    own. Listening for the container's own layout requests is what closes that
    gap, and it closes it for every path that mounts or clears a widget rather
    than for the ones that remembered to say so.
    """

    def setWidget(self, widget):
        super().setWidget(widget)
        widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self.widget() and event.type() == Qt.QEvent.LayoutRequest:
            self.updateGeometry()
        return super().eventFilter(watched, event)

    def minimumSizeHint(self):
        return Qt.QSize(0, 0)

    def sizeHint(self):
        content = self.widget()
        return super().sizeHint() if content is None else content.sizeHint()


class CellPanel(Qt.QWidget):
    # Emitted by appendLog() so log messages arriving from the orchestrator's
    # worker thread (via ExecutionContext.log) are marshaled onto the GUI thread
    # by Qt's automatic queued connection, rather than touching logView directly
    # from a non-GUI thread.
    sigLogMessage = Qt.Signal(object, str)
    # Emitted by onLogAction() (and the ActionLogEntry callbacks it assigns) so
    # ctx.log_action() activity arriving from the orchestrator's worker thread is
    # marshaled onto the GUI thread the same way -- cell, the ActionLogEntry,
    # and which phase of its life this is: "started" (onLogAction itself, right
    # after ctx.log_action() creates the entry), "status" (entry.set_status()),
    # "widget" (entry.set_details_widget()), "details" (entry.set_details()),
    # or "finished" (entry._finish()).
    sigActionEntry = Qt.Signal(object, object, str)
    # Emitted by discardCells() so a rescan's row removal, arriving from the
    # orchestrator's worker thread the same way appendLog()/onLogAction() do,
    # is marshaled onto the GUI thread by Qt's automatic queued connection
    # rather than touching cellList directly.
    sigCellsDiscarded = Qt.Signal(object)
    # Emitted whenever a cell's row or disposition changes, so a view over this
    # panel's state -- Area 1's progress overlay -- knows to re-read it. Carries
    # nothing on purpose: pushing the state would give that view a second copy
    # to keep in sync, and this panel's whole discipline is having exactly one.
    sigCellStateChanged = Qt.Signal()
    # Carries the selected cell, for Area 1 to frame its view on. The panel
    # knows nothing about views or spans; the window owns that.
    sigZoomToCellRequested = Qt.Signal(object)

    def __init__(self, pipetteGetter=None, cameraGetter=None):
        super().__init__()
        self._orchestrator = None
        # Whether a run is in flight, as reported by
        # StatusPanel.sigInteractionLocked (wired in AutopatchWindow.__init__).
        # Re-queuing a cell mid-run could hand the orchestrator a cell it is
        # working on right now, so the reuse button is gated on this being
        # False.
        self._interactionLocked = False
        self._rows: dict[int, Qt.QListWidgetItem] = {}
        self._timelines: dict[int, list[str]] = {}
        # id(entry) -> (id(cell), row index in self._timelines[id(cell)]),
        # kept only while that entry's action is in flight; removed once it
        # finishes. Never holds a reference to the entry itself -- an
        # ActionLogEntry's on_status/on_widget/on_finish callbacks close over
        # this panel, so this panel must never keep an entry alive itself, or
        # the two would form a reference cycle only Python's cyclic GC could
        # break (see the module docstring in tests/test_teardown.py for why
        # that is exactly the failure mode this module must avoid).
        self._entryTimelineLoc: dict[int, tuple[int, int]] = {}
        # id(entry) -> the live QListWidgetItem for the currently selected
        # cell's row, so a later "finished" phase can update it in place.
        # Cleared (not just overwritten) on every selection change.
        self._timelineItems: dict[int, Qt.QListWidgetItem] = {}
        # id(entry) -> the live widget that entry handed over via
        # set_details_widget(), held only while that entry's action is in
        # flight: dropped the moment it finishes, or earlier still if it hands
        # over a retained payload first (set_details() is documented to be
        # called before finishing, and once it has, that payload is this
        # entry's final word -- see the "details" phase below).
        #
        # Required for row navigation rather than merely convenient: selecting
        # another row clears showContainer, which reparents the live widget out
        # of the GUI tree, and without a reference here Python would collect it
        # before the operator could select its row again. Dropping it by the
        # time the entry finishes is what keeps the module's "no widget
        # outlives its action" invariant (see tests/test_teardown.py).
        self._liveWidgets: dict[int, object] = {}
        self._logs: dict[int, list[str]] = {}
        # (id(cell), timeline row index) -> (kind, payload) from that action's
        # ActionLogEntry.set_details(). Keyed by row rather than by entry
        # because the row key is what outlives the entry, which is the whole
        # point of retaining anything; it is also the key self._timelines
        # already uses. Holds only plain data -- never an entry, a cell, or a
        # widget -- so nothing here can form the reference cycle
        # tests/test_teardown.py exists to prevent (see set_details' docstring).
        self._details: dict[tuple[int, int], tuple[str, object]] = {}
        # (id(cell), timeline row index) -> that action's most recent
        # set_status() text. Retained alongside the payload so a finished row
        # still says what it was doing when it ended; a row absent from here
        # never reported a status.
        self._statuses: dict[tuple[int, int], str] = {}
        # id(cell) -> the first ("image_stack", payload) pair any action ever
        # retained for that cell, cached by _onActionEntry's "details" phase
        # and reseeded into the synthetic "Tracker initialized" row (see
        # _seedReferenceStackRow) whenever that cell's timeline starts empty.
        # Deliberately NOT cleared by _dropDetailsFor: self._details is that
        # pass's UI history and reuse's whole point is discarding it, but the
        # reference stack this backs is the same cube across every pass (the
        # tracker it lives on is the one thing reuse intentionally carries
        # forward) -- so this is the one retained-payload store a reuse pass
        # must not wipe. Holds only plain data, never a cell or a widget, for
        # the same reference-cycle reasons self._details does.
        self._referenceStacks: dict[int, tuple[str, object]] = {}
        # id(cell) -> (exc_type, exc_message, traceback_text) for the most
        # recent action of that cell's that failed. Ids and plain strings,
        # never the entry and never the exception: an ActionLogEntry's
        # on_finish closes over this panel, and an exception holds its
        # traceback's frames and their locals -- either one retained here is
        # the reference-cycle failure this module's teardown path exists to
        # avoid (see tests/test_teardown.py, and
        # acq4.experiment.error_record.describe_exception).
        self._cellErrors: dict[int, tuple[str, str, str]] = {}
        self._cells: dict[int, object] = {}
        # id(cell) for each cell that is not yet running under any
        # orchestrator this panel is bound to, and so is still owed an
        # enqueue. Grows from two places: _enqueueAndAdd(), when a cell is
        # seeded with no orchestrator bound, and unbindOrchestrator(), which
        # salvages whatever bindOrchestrator() has not yet flushed out of the
        # outgoing orchestrator's own queue before that queue goes away with
        # it. Emptied by bindOrchestrator()'s flush into whichever
        # orchestrator is bound next. A cell this panel merely learned about
        # from an orchestrator's announcements is already queued or already
        # finished, so it never belongs here -- self._cells alone cannot tell
        # the two apart, and treating every cell in it as pending is how a
        # coordinate in discarded tissue, or an already-patched cell, gets run
        # again. A list rather than a set so the flush enqueues them in the
        # order they were queued, which is the order they will be patched in.
        self._awaitingEnqueue: list[int] = []
        # Cells the orchestrator has started work on, by id. Recorded from both
        # sigCurrentCell and sigCellFinished: a cell interrupted mid-run may
        # never emit a terminal status, and "retry" is emitted mid-flight
        # without being terminal, so "has work started" is the reliable question
        # and does not depend on the terminal-status vocabulary.
        #
        # Holds ids, never cells: this panel must not be the thing keeping a
        # Cell alive beyond self._cells, and must not add a second store to keep
        # in sync with it on teardown.
        self._attempted = set()
        # id(cell) -> the last TERMINAL disposition sigCellFinished reported for
        # that cell; a cell absent from this dict has never finished a pass.
        # Distinct from self._attempted, which only answers whether work ever
        # started: a cell interrupted mid-run is attempted with no disposition,
        # and a cell re-queued for another pass keeps being attempted while its
        # disposition is cleared. Holds ids and plain strings, never cells, for
        # the same reason _attempted does.
        self._status: dict[int, str] = {}
        # id(cell) -> the disposition _onReuseCheckedCells() took out of
        # self._status when it re-queued that cell, held only until the new pass
        # reports a disposition of its own. _onCellsDiscarded restores it for a
        # reused cell a rescan discards: reuse keeps a cell attempted, so that
        # row is skipped rather than removed, and without the restore it would
        # keep reading "queued" while no queue holds the cell any more --
        # unreachable by Start, by reuse, and by "Check all completed" alike,
        # and still in the density record, so the survey would never re-find
        # that location either. Holds ids and plain strings, never cells, for
        # the same reason _attempted and _status do.
        self._preReuseStatus: dict[int, str] = {}
        # id(entry) of whichever entry's widget currently occupies
        # showContainer, or None if it's empty. An action can nest a
        # log_action block inside another still-open one -- prompt() opens an
        # "Operator Prompt" entry inside cellfie's still-open entry when
        # tracking loses the cell -- so this lets a "finished" phase tell
        # whether it actually owns what's mounted before clearing it -- an
        # inner entry finishing must not tear down an outer entry's still-live
        # widget.
        self._shownEntryId: int | None = None
        # id(cell) of the cell the orchestrator most recently announced as
        # current, or None before it has announced any. What "is the operator
        # still watching the run" is measured against (see
        # _isFollowingCurrentCell); an id rather than the cell for the same
        # reason _attempted holds ids -- this panel must not be what keeps a
        # Cell alive beyond self._cells.
        self._announcedCellId: int | None = None
        # id(cell) of the cell the orchestrator has in hand right now, or None.
        # Distinct from self._announcedCellId, which deliberately survives the
        # run's end so _isFollowingCurrentCell keeps recognising the row the
        # operator was watching; this one is released the moment the
        # orchestrator reports having nothing in hand, because it answers "is a
        # pipette on this cell" for Area 1's one blue marker. An id, not a cell,
        # for the reason _attempted holds ids.
        self._runningCellId: int | None = None
        self._pipetteGetter = pipetteGetter or (lambda: None)
        self._cameraGetter = cameraGetter or (lambda: None)

        self.cellList = Qt.QListWidget()
        self.timelineList = Qt.QListWidget()
        self.logView = Qt.QPlainTextEdit()
        self.logView.setReadOnly(True)
        for view in (self.cellList, self.timelineList, self.logView):
            floorAtRows(view, _VIEW_ROWS)
        self.showContainer = Qt.QWidget()
        self.showContainer.setLayout(Qt.QVBoxLayout())
        # The container is what details widgets mount into and are cleared out
        # of, and stays the panel's own; the viewport around it is nothing but a
        # matter of size (see _DetailsViewport), and only the layout below
        # refers to it.
        self.showViewport = _DetailsViewport()
        self.showViewport.setWidgetResizable(True)
        self.showViewport.setFrameShape(Qt.QFrame.NoFrame)
        self.showViewport.setWidget(self.showContainer)
        # Header above the mounted details widget, carrying the selected
        # action's set_status() text -- which nothing displayed before this,
        # so every FSM state-transition message was thrown away. The timeline
        # rows deliberately do not show it (design doc §7).
        self.statusLabel = CompactLabel()

        self.addFromTargetBtn = Qt.QPushButton("Add from target")
        self.scatterFakeCellsBtn = Qt.QPushButton("Scatter fake cells")
        self.checkAllCompletedBtn = Qt.QPushButton("Check all completed")
        self.reuseCheckedCellsBtn = Qt.QPushButton("Reuse checked cells")
        self.zoomToCellBtn = Qt.QPushButton("Zoom to cell")
        self.zoomToCellBtn.setToolTip(
            "Frame Area 1's view on the selected cell's position."
        )
        self.addFromTargetBtn.clicked.connect(self._onAddFromTargetClicked)
        self.scatterFakeCellsBtn.clicked.connect(self._onScatterFakeCellsClicked)
        self.checkAllCompletedBtn.clicked.connect(self._onCheckAllCompleted)
        self.reuseCheckedCellsBtn.clicked.connect(self._onReuseCheckedCells)
        self.zoomToCellBtn.clicked.connect(self._onZoomToCellClicked)

        btnRow = Qt.QHBoxLayout()
        btnRow.addWidget(self.addFromTargetBtn)
        btnRow.addWidget(self.scatterFakeCellsBtn)
        btnRow.addWidget(self.checkAllCompletedBtn)
        btnRow.addWidget(self.reuseCheckedCellsBtn)
        btnRow.addWidget(self.zoomToCellBtn)

        listsRow = Qt.QHBoxLayout()
        listsRow.addWidget(self.cellList)
        listsRow.addWidget(self.timelineList)

        layout = Qt.QVBoxLayout()
        layout.addLayout(btnRow)
        # Stretch factors, so that room beyond what this panel needs -- and the
        # shortfall when there is less than that -- is shared out rather than
        # landing wherever the layout happens to reach first: the lists are what
        # the operator works in, the log is a running commentary alongside. The
        # details pane deliberately takes no factor, so it asks for exactly what
        # the widget mounted in it asks for and an empty one stays a thin strip
        # rather than a large empty box the lists paid for.
        layout.addLayout(listsRow, 3)
        layout.addWidget(self.statusLabel)
        layout.addWidget(self.showViewport)
        layout.addWidget(self.logView, 2)
        self.setLayout(layout)

        self.cellList.currentItemChanged.connect(self._onCellSelectionChanged)
        self.timelineList.currentItemChanged.connect(self._onTimelineSelectionChanged)
        self.sigLogMessage.connect(self._onLogMessage)
        self.sigActionEntry.connect(self._onActionEntry)
        self.sigCellsDiscarded.connect(self._onCellsDiscarded)
        # setCheckState() (and setText(), harmlessly) emits itemChanged, which
        # is the only signal a QListWidget offers for "a row's checkbox moved".
        self.cellList.itemChanged.connect(self._onItemChanged)
        self._updateCheckAllButton()
        self._updateReuseButton()

    def bindOrchestrator(self, orchestrator) -> None:
        if orchestrator is self._orchestrator:
            # unbindOrchestrator() salvages the outgoing orchestrator's pending
            # cells into _awaitingEnqueue but leaves its queue exactly as it
            # was -- there is nothing to clear it for on the replace-the-whole-
            # Orchestrator path this normally serves. Binding to the very
            # orchestrator already held would flush those same still-queued
            # cells into it a second time, so there is nothing to do: it is
            # already bound to exactly this orchestrator, with its queue
            # exactly as it was.
            return
        if self._orchestrator is not None:
            self.unbindOrchestrator()
        self._orchestrator = orchestrator
        orchestrator.sigCurrentCell.connect(self._onCurrentCell)
        orchestrator.sigCellFinished.connect(self._onCellFinished)
        # Emitted from the orchestrator's worker thread, and _onCellsQueued adds
        # rows to a QListWidget -- yet it is connected here plainly, without the
        # panel-owned re-emit hop sigLogMessage/sigActionEntry/sigCellsDiscarded
        # go through. Those three exist because the worker thread reaches this
        # panel by *calling a method on it*: appendLog/onLogAction are bound into
        # the context factory and discardCells is called from
        # AutopatchWindow._onTissueMoved, all of them plain Python calls with no
        # Qt connection anywhere in the path to marshal them, so the panel has to
        # emit its own signal to get onto its own thread. This one already is a
        # signal on one QObject connected to a slot on another, and an automatic
        # connection settles direct-vs-queued at each emit by comparing the
        # emitting thread with the receiving object's: the orchestrator emits
        # from the worker thread, this panel lives on the GUI thread, so delivery
        # is queued and the slot runs here with the rows it adds.
        orchestrator.sigCellsQueued.connect(self._onCellsQueued)
        # _awaitingEnqueue now holds every cell still owed an enqueue: one
        # seeded before any orchestrator was bound, or one salvaged, just
        # above (this method's own call to unbindOrchestrator(), when this is
        # a rebind), from the outgoing orchestrator's queue before that queue
        # went away with it. Flush exactly those into the newly bound
        # orchestrator now, exactly once each, so a freshly loaded protocol
        # runs over any cell the operator already seeded, whichever of the
        # two ways it ended up unqueued. Deliberately not every cell in
        # self._cells: that dict also holds cells this panel only ever
        # learned about from an orchestrator's announcements (a survey
        # producer's finds, and cells that have already finished), and
        # enqueuing those here would patch a finished cell a second time --
        # or, after a "New slice", drive a pipette to a coordinate in tissue
        # the operator has declared gone.
        pending, self._awaitingEnqueue = self._awaitingEnqueue, []
        for cellId in pending:
            orchestrator.enqueue(self._cells[cellId])
        self._updateReuseButton()

    def unbindOrchestrator(self) -> None:
        """Disconnect everything bindOrchestrator() connected to the currently
        bound orchestrator, and drop the reference to it.

        Shared by bindOrchestrator() (rebinding to a freshly loaded protocol)
        and window teardown (on module/window close), so both paths sever the
        panel<->orchestrator signal wiring the same way -- leaving no dangling
        Qt connection either way.

        Also salvages whatever is still sitting in the outgoing orchestrator's
        queue into _awaitingEnqueue before letting go of it. Autopatch.
        _onProtocolLoaded replaces the whole Orchestrator -- deque included --
        when the operator switches to a different protocol, so a cell that
        was enqueued straight into it (by _enqueueAndAdd, while it was bound,
        or by a survey producer refilling the queue) and never popped for a
        run would otherwise simply vanish along with it, while its row stays
        on screen in Area 5. A cell already popped off the queue -- running,
        finished, or skipped -- is not in pendingCells() any more, so this
        can never resurrect one of those; that is the same distinction
        addCell()'s other callers already rely on to keep a finished or
        discarded cell out of this list. A pending cell this panel has not
        seen before (a survey producer's find, still waiting its turn behind
        whatever is running) gets its row and bookkeeping from addCell()
        here, the same way an announced one gets it, so the id recorded below
        always resolves against self._cells later.

        Note this does NOT touch onLogAction/sigActionEntry: that path is wired
        through the context factory (ExecutionContext.on_log_action, cell-bound
        per make_context_factory), not through an Orchestrator signal
        connection, so there is nothing here for a rebind or teardown to sever.
        """
        if self._orchestrator is None:
            return
        for cell in self._orchestrator.pendingCells():
            if id(cell) not in self._cells:
                self.addCell(cell)
            self._awaitingEnqueue.append(id(cell))
        Qt.disconnect(self._orchestrator.sigCurrentCell, self._onCurrentCell)
        Qt.disconnect(self._orchestrator.sigCellFinished, self._onCellFinished)
        Qt.disconnect(self._orchestrator.sigCellsQueued, self._onCellsQueued)
        self._orchestrator = None
        self._updateReuseButton()

    def clearCells(self) -> None:
        """Drop every seeded Cell this panel is holding, for window teardown.

        Cell is a QObject; self._cells is the only strong Python reference
        keeping a seeded-but-not-yet-garbage-collected Cell alive once its own
        run finishes (see addCell()). Most Cell instances are also parented to
        this panel (also set in addCell()) so Qt's ownership cascade destroys
        them deterministically when the window closes -- except a cell built
        on the orchestrator's worker thread, which addCell() cannot parent
        (see its comment), and for which self._cells is the only thing keeping
        it alive at all. This clears the Python-side bookkeeping (and any
        per-cell signal connections a future change might add) to match --
        nothing here should still reference a Cell afterward.

        A cell still in flight when this runs goes on to finish on tissue the
        caller has declared gone. Keeping its terminal disposition -- and with it
        its eligibility for reuse -- off this list is the orchestrator's job, not
        this method's: AutopatchWindow.newSlice() pairs this call with
        Orchestrator.abandonCellInHand(), which suppresses that disposition at
        the emit, on the worker thread. See that method for why the decision
        cannot be made from here.
        """
        self._cells.clear()
        # Cleared alongside self._cells, which is what the flush resolves these
        # ids against: an id left behind here would either raise a KeyError on
        # the next bind or, if that memory address were reused by an unrelated
        # cell, enqueue that cell instead.
        self._awaitingEnqueue.clear()
        self._attempted.clear()
        # Cleared for the same reason the id-keyed stores above are: an id left
        # behind here names a cell this panel no longer holds, and CPython
        # reuses the addresses of collected objects -- an unrelated cell seeded
        # afterwards could land on it and have its row read as the one the run
        # is on, taking the selection the operator gave it.
        self._announcedCellId = None
        self._runningCellId = None
        self._status.clear()
        self._preReuseStatus.clear()
        self._rows.clear()
        self._timelines.clear()
        self._entryTimelineLoc.clear()
        self._timelineItems.clear()
        self._logs.clear()
        self._details.clear()
        self._statuses.clear()
        self._referenceStacks.clear()
        self.statusLabel.setText("")
        self._cellErrors.clear()
        self.cellList.clear()
        self._clearShowContainer()
        self._shownEntryId = None
        self._updateCheckAllButton()
        self._updateReuseButton()

    def discardCells(self, cells) -> None:
        """Drop the panel-side bookkeeping for `cells` -- rows, timelines,
        logs, and the strong references that keep them alive -- the same
        stores clearCells() drops for every cell, but scoped to this subset.

        A cell isAttempted() already reports as started keeps its row: that row
        is the session record, not a stale queued entry, so it survives even if
        it is passed in here. A reused cell is attempted too, and its row really
        was a live queued entry, so it goes back to the disposition reuse took
        from it (see self._preReuseStatus) -- a session record again, which the
        operator can knowingly reuse once they trust the new coordinates.

        Used by AutopatchWindow._onTissueMoved's rescan branch, which runs on
        the orchestrator's worker thread, so this only ever emits
        sigCellsDiscarded rather than touching cellList directly -- Qt's
        automatic queued connection marshals the update onto the GUI thread,
        the same way appendLog()/onLogAction() do above.
        """
        self.sigCellsDiscarded.emit(list(cells))

    def _onCellsDiscarded(self, cells) -> None:
        for cell in cells:
            cellId = id(cell)
            if self.isAttempted(cell):
                status = self._preReuseStatus.pop(cellId, None)
                if status is not None:
                    self._status[cellId] = status
                    item = self._rows.get(cellId)
                    if item is not None:
                        # The row claims "queued" while this cell has just left
                        # the last queue that held it; it reads as the session
                        # record its disposition now makes it again.
                        item.setText(f"cell {cellId} — {status}")
                continue
            self._cells.pop(cellId, None)
            # Cleared alongside _cells for the same reason clearCells() clears
            # it: a stale id left behind here could be flushed into a later
            # orchestrator by bindOrchestrator(), driving a pipette to a
            # coordinate in tissue the operator has just declared gone.
            if cellId in self._awaitingEnqueue:
                self._awaitingEnqueue.remove(cellId)
            self._attempted.discard(cellId)
            self._status.pop(cellId, None)
            self._preReuseStatus.pop(cellId, None)
            item = self._rows.pop(cellId, None)
            if item is not None:
                self.cellList.takeItem(self.cellList.row(item))
            self._timelines.pop(cellId, None)
            self._logs.pop(cellId, None)
            self._cellErrors.pop(cellId, None)
            self._dropDetailsFor(cellId)
            # Unlike _dropDetailsFor's targets, this cell is gone for good
            # here (the reuse-and-restore branch above never reaches this
            # line), so nothing is left to reseed a synthetic row from later
            # -- and a stale id left behind could hand a future, unrelated
            # cell at a reused memory address a reference stack that was
            # never its own.
            self._referenceStacks.pop(cellId, None)
        self._updateCheckAllButton()
        self._updateReuseButton()
        self.sigCellStateChanged.emit()

    def _onAddFromTargetClicked(self) -> None:
        pipette = self._pipetteGetter()
        if pipette is None:
            return
        # pipette is a PatchPipette; it delegates target position to its
        # manipulator (pipetteDevice) rather than exposing targetPosition() itself.
        position = Point(pipette.pipetteDevice.targetPosition(), "global")
        cell = Cell(position)
        self._enqueueAndAdd(cell)

    def _onScatterFakeCellsClicked(self) -> None:
        camera = self._cameraGetter()
        if camera is None:
            return
        center = np.asarray(camera.globalCenterPosition())
        for _ in range(random.randint(3, 5)):
            offset = np.random.uniform(-_SCATTER_RADIUS, _SCATTER_RADIUS, size=center.shape)
            cell = Cell(Point(center + offset, "global"))
            self._enqueueAndAdd(cell)

    def _enqueueAndAdd(self, cell) -> None:
        # self._cells (via addCell) is the authoritative source of truth for
        # seeded cells, so seeding must work even before a protocol has been
        # loaded and bound an orchestrator. If one IS bound, enqueue the new
        # cell into it immediately; if not, record it as awaiting an enqueue so
        # bindOrchestrator() flushes it into whichever orchestrator it later
        # binds. Exactly one of the two happens per seeded cell, so this never
        # double-enqueues. unbindOrchestrator() is the other place
        # _awaitingEnqueue grows, but only with cells it reads back out of an
        # outgoing orchestrator's own queue -- never with a cell this panel
        # merely has a row for -- so that flush still lands on cells actually
        # owed a run rather than every cell this panel knows about.
        if self._orchestrator is not None:
            self._orchestrator.enqueue(cell)
        else:
            self._awaitingEnqueue.append(id(cell))
        self.addCell(cell)

    def addCell(self, cell) -> None:
        """Give `cell` a row and the panel-side bookkeeping that row needs.

        Display and bookkeeping only: it neither enqueues the cell nor records
        it as awaiting an enqueue. Both the seeding path (_enqueueAndAdd, which
        does one or the other before calling here) and the announcement paths
        (_onCurrentCell/_onCellFinished, for a cell that is already queued,
        already running, or already finished) go through this, and the
        announcement paths must add nothing a later bindOrchestrator() would
        act on.
        """
        # Cell is a QObject; parenting it to this panel (itself parented into
        # the window's widget tree) lets Qt's ownership cascade destroy it
        # deterministically when the window closes, rather than relying solely
        # on Python holding the last reference (see self._cells below) -- but
        # only for a cell that already lives on this (the GUI) thread. Qt
        # refuses setParent() across threads outright (a stderr warning, not
        # an exception, and moveToThread() is not the fix: Qt only allows that
        # call from the thread an object currently lives on, so calling it
        # from here would warn just the same). A cell a survey producer builds
        # on the orchestrator's worker thread (tile_detector.py's _newCell,
        # called from Orchestrator._refillQueue) arrives here still on that
        # thread, so it is never parented; the strong reference this panel
        # keeps in self._cells below is what keeps it alive instead, for as
        # long as this panel exists, and clearCells() is what drops that
        # reference at window teardown. Guarded with getattr since tests stand
        # in a plain object() for a cell.
        setParent = getattr(cell, "setParent", None)
        thread = getattr(cell, "thread", None)
        if setParent is not None and (thread is None or thread() is self.thread()):
            setParent(self)
        item = Qt.QListWidgetItem(f"cell {id(cell)} — queued")
        # ItemIsUserCheckable is already among QListWidgetItem's default
        # flags; set explicitly here so this row's checkability does not
        # depend on that default. setCheckState() is what actually puts a
        # checkbox on the row -- Qt only draws one once CheckStateRole holds
        # a value -- letting the operator pick a set of already-run cells for
        # another pass (_onReuseCheckedCells()). Checking is independent of
        # selection, which is what drives the timeline/log views: one cell
        # can be inspected while a different set is checked.
        item.setFlags(item.flags() | Qt.Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Qt.Unchecked)
        item.setData(Qt.Qt.UserRole, cell)
        self.cellList.addItem(item)
        self._rows[id(cell)] = item
        self._timelines[id(cell)] = []
        self._seedReferenceStackRow(cell)
        self._logs[id(cell)] = []
        # QListWidgetItem.setData() does not keep a strong Python reference to a
        # QObject-derived value (Cell is one): once the orchestrator's queue/worker
        # frame drops its own reference, the cell can be garbage-collected and
        # item.data() comes back re-wrapped as a bare, dangling QObject. Holding a
        # reference here for the panel's lifetime keeps the original object alive.
        self._cells[id(cell)] = cell
        self.sigCellStateChanged.emit()

    def isAttempted(self, cell) -> bool:
        """Whether the orchestrator has ever started work on `cell`.

        Slice.forceRescan takes this as its predicate: attempted cells stay
        registered in the density record through a rescan, never-attempted ones
        are dropped so they can be found again where they now are.
        """
        return id(cell) in self._attempted

    def isRunning(self, cell) -> bool:
        """Whether the orchestrator has `cell` in hand right now.

        The narrow question isAttempted() does not answer: that one stays true
        for the rest of the session once a cell has been started even once, so
        it cannot tell a cell being worked from one re-queued for another pass.
        At most one cell is running at a time -- the orchestrator holds exactly
        one -- so at most one row can answer True here.
        """
        return id(cell) == self._runningCellId

    def cells(self) -> list:
        """Every cell this panel knows about, in the order they were added.

        This panel is the complete registry: Slice.registerCells() is reached
        only from CellProducer, so cells seeded by hand ("Add from target",
        "Scatter fake cells") live here and nowhere else.
        """
        return list(self._cells.values())

    def disposition(self, cell) -> str | None:
        """The last terminal disposition reported for `cell`, or None if it has
        never finished a pass.

        None covers three cases the callers treat alike: never run, still
        running, and re-queued for another pass by _onReuseCheckedCells().
        """
        return self._status.get(id(cell))

    def errorText(self, cell) -> tuple[str, str, str] | None:
        """(exc_type, exc_message, traceback_text) for `cell`'s most recent
        failed action, or None if it has none. Reflects the latest finished
        action only: a later action in the same pass overwrites it, and
        _onCurrentCell/_onReuseCheckedCells clear it once that pass is over --
        but nothing in this pass clears it if the cell goes on to complete
        after the failed action."""
        return self._cellErrors.get(id(cell))

    def detailsFor(self, cell, rowIndex: int):
        """The (kind, payload) an action retained for `cell`'s row `rowIndex`,
        or None if that row's action retained nothing."""
        return self._details.get((id(cell), rowIndex))

    def patchStatesWalked(self, cell) -> set:
        """Every pipette FSM state `cell`'s recorded drives visited this pass.

        Read off the "test_pulse_history" payloads _drive_fsm retains, unioned
        across every drive: a protocol may patch more than once, and how far the
        pipette ever got on this cell is the question Area 1's overlay grades a
        completed run by (see progress_colors._doneBrush). Scoped to this pass
        for the same reason the timeline is -- _onReuseCheckedCells drops these
        payloads along with the rows they belong to.

        Returns states, not progress: which of them count as advancing toward a
        patch is progress_colors' business, not this panel's.
        """
        cellId = id(cell)
        states = set()
        for (owner, _row), (kind, payload) in self._details.items():
            if owner != cellId or kind != "test_pulse_history":
                continue
            for _when, state in payload.get("transitions", ()):
                states.add(state)
        return states

    def _dropDetailsFor(self, cellId: int) -> None:
        """Forget every retained payload and status belonging to `cellId`.

        Scans rather than indexing by cell: the keys are (cell, row) pairs, and
        a per-cell index would be a second store to keep in sync with these two
        on all three of the paths that drop rows.
        """
        for key in [k for k in self._details if k[0] == cellId]:
            del self._details[key]
        for key in [k for k in self._statuses if k[0] == cellId]:
            del self._statuses[key]

    def _onCheckAllCompleted(self) -> None:
        """Tick every row whose cell ran its protocol to completion.

        A convenience for the common "reuse everything that worked" case; it
        only ever checks, never unchecks, so it composes with a selection the
        operator has already started making by hand.
        """
        for index in range(self.cellList.count()):
            item = self.cellList.item(index)
            if self.disposition(item.data(Qt.Qt.UserRole)) in COMPLETED:
                item.setCheckState(Qt.Qt.Checked)

    def _updateCheckAllButton(self) -> None:
        self.checkAllCompletedBtn.setEnabled(self._hasCompletedCell())

    def _hasCompletedCell(self) -> bool:
        return any(status in COMPLETED for status in self._status.values())

    def _onItemChanged(self, _item) -> None:
        self._updateReuseButton()

    def setInteractionLocked(self, locked: bool) -> None:
        """Whether a run is in flight, so re-queuing must wait.

        Connected to StatusPanel.sigInteractionLocked rather than reading the
        orchestrator's sigStatus directly: that connection is made once in the
        window's constructor and never needs re-wiring per protocol load, so it
        cannot leave a bound orchestrator wired into a panel that has stopped
        tracking it -- the same reasoning ProtocolPanel.setInteractionLocked and
        SearchPanel.setInteractionLocked are wired this way for.
        """
        self._interactionLocked = locked
        self._updateReuseButton()

    def _updateReuseButton(self) -> None:
        # A row count, not any(self._checkedCells()): the latter tests whether
        # a checked Cell is truthy, which is only ever true today because Cell
        # has no __len__/__bool__ of its own. This checks check state directly
        # -- and short-circuits on the first hit -- rather than materializing
        # the cell list, since this runs on every itemChanged.
        hasChecked = any(
            self.cellList.item(index).checkState() == Qt.Qt.Checked
            for index in range(self.cellList.count())
        )
        enabled = (
            self._orchestrator is not None
            and not self._interactionLocked
            and hasChecked
        )
        self.reuseCheckedCellsBtn.setEnabled(enabled)

    def _checkedCells(self) -> list:
        """The cells whose rows are ticked, in list order -- which is the order
        they will be patched in once re-queued."""
        return [
            self.cellList.item(index).data(Qt.Qt.UserRole)
            for index in range(self.cellList.count())
            if self.cellList.item(index).checkState() == Qt.Qt.Checked
        ]

    def _onReuseCheckedCells(self) -> None:
        """Re-queue the checked cells for another pass with the current protocol.

        The *same* Cell objects go back into the queue, so each one's tracker
        and reference stack carry into the next pass (design doc 6) -- which is
        what makes "cellfie everything, then patch everything" work. Their rows
        already exist, so this never calls addCell(), and it never records
        anything in _awaitingEnqueue: an orchestrator is bound (the button is
        gated on it), so the enqueue happens here and now, exactly once each.

        A checked cell that has not finished a pass is skipped rather than
        enqueued: it is still sitting in the orchestrator's queue, so a second
        enqueue would run it twice over the same tissue.
        """
        inspected = self._currentSelectedCell()
        reinspect = False
        for cell in self._checkedCells():
            item = self._rows[id(cell)]
            item.setCheckState(Qt.Qt.Unchecked)
            if self.disposition(cell) not in TERMINAL:
                continue
            self._orchestrator.enqueue(cell)
            item.setText(f"cell {id(cell)} — queued")
            # Pass 2 starts with a fresh timeline and log for this cell;
            # earlier-pass UI history is not retained. The tracker and
            # reference stack live on the Cell itself, not in these dicts, so
            # the cell's physical continuity is untouched.
            self._timelines[id(cell)] = []
            self._logs[id(cell)] = []
            # Earlier-pass details are that pass's UI history, cleared with the
            # timeline and log for the same reason (design doc §7).
            self._dropDetailsFor(id(cell))
            # After, not before: this seeds row 0 of the timeline just
            # emptied above by writing into self._details itself, and
            # _dropDetailsFor must not turn around and wipe that seed.
            self._seedReferenceStackRow(cell)
            # A stored error describes the pass that just ended, not the one
            # about to start. errorText() reports it to anything that asks --
            # including a caller reading it after this row already reads
            # "queued" beside an empty timeline -- so it is dropped here with
            # the rest of that pass's UI history rather than left to
            # _onCurrentCell, which a Stop or a queue that never reaches this
            # cell can leave never firing.
            self._cellErrors.pop(id(cell), None)
            # Queued again, so no longer holding a finished disposition -- but
            # remembered, so a rescan that discards this cell before the new
            # pass reaches it can put that disposition back rather than leave a
            # row claiming "queued" with no queue behind it (see
            # self._preReuseStatus). Note _attempted is deliberately NOT
            # cleared: work has started at this coordinate at some point, which
            # is what isAttempted() reports and what keeps a rescan from
            # silently dropping this row.
            self._preReuseStatus[id(cell)] = self._status.pop(id(cell))
            if cell is inspected:
                reinspect = True
        if reinspect:
            self.timelineList.clear()
            self._timelineItems.clear()
            self.logView.clear()
            # Mirrors _onCellSelectionChanged's reset of the same two: a
            # followed cell's live details widget must not linger into its
            # next pass. Relies on the same invariant that makes the loop
            # above skip a non-TERMINAL cell: a cell only reaches a TERMINAL
            # disposition after ActionLogEntry.__exit__ has already emitted
            # that entry's "finished" phase, so by the time a cell is eligible
            # for reuse it has no entry still in flight to hold showContainer
            # or _shownEntryId.
            self._clearShowContainer()
            self._shownEntryId = None
        self._updateCheckAllButton()
        self._updateReuseButton()
        self.sigCellStateChanged.emit()

    def appendLog(self, cell, message: str) -> None:
        # May be called from the orchestrator's worker thread (ExecutionContext.log,
        # bound per-cell by the context factory); emitting rather than touching
        # logView directly lets Qt's automatic queued connection marshal the
        # update onto the GUI thread.
        self.sigLogMessage.emit(cell, message)

    def _onLogMessage(self, cell, message: str) -> None:
        self._logs.setdefault(id(cell), []).append(message)
        if cell is self._currentSelectedCell():
            self.logView.appendPlainText(message)

    def _onCellsQueued(self, cells) -> None:
        """The batch a survey producer has just added to the orchestrator's
        queue (Orchestrator.sigCellsQueued, emitted from its worker thread).

        Rows only. These cells are already sitting in the orchestrator's own
        deque -- that is the whole content of the announcement -- so this must
        never enqueue them, which would run each of them twice, and must never
        record them in self._awaitingEnqueue, which would have the next
        bindOrchestrator() do the same thing one protocol load later. addCell()
        is exactly the call that adds neither, and is what _onCurrentCell and
        _onCellFinished announce their way in through for the same reason.

        A cell that already has a row is left entirely alone, text included: it
        can reach this panel by another route first, either because
        unbindOrchestrator() salvaged it out of an outgoing orchestrator's
        pending queue or because the run has already moved on to it by the time
        this arrives (the announcement crosses threads, so sigCurrentCell for
        the first cell of a batch can be delivered before the batch itself).
        Its row says something more current than "queued" in both cases.
        """
        for cell in cells:
            if id(cell) in self._rows:
                continue
            self.addCell(cell)

    def _isFollowingCurrentCell(self) -> bool:
        """Whether the operator is watching whichever cell the orchestrator is
        working on rather than reading back through a different one.

        The cell-level counterpart of _isFollowingLastRow's auto-scroll rule:
        while the selection is on the cell the run announced, the next cell it
        announces takes the selection with it; once the operator selects a
        different one, it does not, until they select the running cell again. A
        list with nothing selected at all counts as following, so the first cell
        of a run is shown without requiring a click.

        "The operator deliberately selected another cell" is answered by
        comparing the selection against the last cell announced -- not by
        remembering which rows this panel selected itself. The two agree while
        nobody interferes, since the only selection this panel ever makes is
        onto the cell it has just announced, but they differ in the case that
        matters: a record of this panel's own writes would name whichever cell
        was current when the operator wandered off, and the run has moved on
        since, so clicking the row that is running now -- the one obvious way
        back to following, and the exact analogue of selecting the last timeline
        row -- would never be recognized as such.
        """
        selected = self._currentSelectedCell()
        return selected is None or id(selected) == self._announcedCellId

    def _onCurrentCell(self, cell) -> None:
        # sigCurrentCell carries only the cell, not an action identity -- that
        # flows through the log-action entry stream instead (see
        # onLogAction()/sigActionEntry below), which drives the timeline rows
        # and the details container directly.
        if cell is None:
            # The orchestrator reported having no cell in hand -- emitted however
            # its run loop ended, and again before each survey. There is no cell
            # to attribute anything to, and no row of any other cell's to change:
            # a row already reads whatever that cell's own last announcement made
            # it read.
            #
            # The one thing that does change is that nothing is in hand any more.
            # Left set, the last cell worked would keep Area 1's in-flight marker
            # for the rest of the session -- which is what an operator saw after
            # a run died mid-cell. self._announcedCellId is deliberately NOT
            # cleared alongside it: that one names the row the operator is
            # following, which outlives the run.
            if self._runningCellId is not None:
                self._runningCellId = None
                self.sigCellStateChanged.emit()
            return
        self._attempted.add(id(cell))
        self._runningCellId = id(cell)
        # A new pass supersedes the last one's failure: the traceback for a
        # cell that has just been re-queued describes a run that is over.
        if self._cellErrors.pop(id(cell), None) is not None:
            if cell is self._currentSelectedCell():
                self._clearShowContainer()
                self._shownEntryId = None
        item = self._rows.get(id(cell))
        if item is None:
            # A cell the orchestrator announces without this panel ever having
            # seeded it (e.g. found by a survey producer inside
            # Orchestrator._refillQueue) is already enqueued -- addCell() here
            # only creates the row and the panel-side bookkeeping addCell()
            # always sets up (timeline/log stores and the strong self._cells
            # reference; the parenting too, except such a cell was built on
            # the orchestrator's worker thread, so addCell() leaves it
            # unparented and self._cells is what keeps it alive instead -- see
            # addCell()'s own comment); it must never also call
            # orchestrator.enqueue(), which would run the same cell twice, nor
            # record it in self._awaitingEnqueue, which would have a later
            # bindOrchestrator() do the same thing one protocol load later.
            self.addCell(cell)
            item = self._rows[id(cell)]
        item.setText(f"cell {id(cell)} — running")
        # Asked before this cell becomes the announced one, since the question
        # is whether the operator was still following the cell announced
        # *before* it.
        following = self._isFollowingCurrentCell()
        self._announcedCellId = id(cell)
        if following:
            # setCurrentItem rather than anything that reaches past it:
            # _onCellSelectionChanged is what fills the timeline and the log
            # from this cell's stores and picks the row worth looking at
            # (_autoSelectRow), and this path wants all of that. A cell being
            # announced has an empty timeline of its own, so what that leaves is
            # a blank pane -- until its first action opens a row, which
            # _appendTimelineRow's own following rule then selects, again
            # without a click. A no-op when this row is already current.
            self.cellList.setCurrentItem(item)
        # self._attempted already holds this cell (set above), so Area 1's
        # progress overlay -- the view sigCellStateChanged exists for -- can
        # redraw it blue. Unconditional, like _onCellFinished's own emit just
        # below: a cell with no row yet gets one from addCell(), which emits
        # on its own, so this is a second, harmless emit for that path (an
        # extra redraw, not a wrong one) rather than a special case to dodge it.
        self.sigCellStateChanged.emit()

    def onLogAction(self, cell, entry) -> None:
        """ExecutionContext.on_log_action, cell-bound by the context factory
        (make_context_factory's onLogAction=partial(..., cell)).

        Called from the orchestrator's worker thread the instant an action
        opens `with ctx.log_action(name) as action_entry:`. Assigns the entry's
        on_status/on_widget/on_finish callbacks -- themselves also called from
        the worker thread as the action progresses -- so every one of them,
        like this method itself, only ever emits sigActionEntry rather than
        touching timelineList/showContainer directly; Qt's automatic queued
        connection then marshals the update onto the GUI thread. This mirrors
        appendLog()/sigLogMessage above, for the same reason.

        The callbacks are plain closures over `self` and `cell`, not over the
        entry itself, and this panel never stores the entry object anywhere
        (see self._entryTimelineLoc's docstring) -- so an entry's lifetime is
        whatever the action function that created it gives it, and no
        panel<->entry reference cycle is created. on_details is assigned here
        for the same reason and marshaled the same way; like the others it
        closes over `self` and `cell` only, and the payload is read back off
        the entry in the slot rather than carried through the signal, so
        sigActionEntry's signature is unchanged.
        """
        entry.on_status = lambda e: self.sigActionEntry.emit(cell, e, "status")
        entry.on_widget = lambda e, w: self.sigActionEntry.emit(cell, e, "widget")
        entry.on_finish = lambda e: self.sigActionEntry.emit(cell, e, "finished")
        entry.on_details = lambda e, kind, payload: self.sigActionEntry.emit(
            cell, e, "details"
        )
        self.sigActionEntry.emit(cell, entry, "started")

    def _onActionEntry(self, cell, entry, phase: str) -> None:
        if phase == "started":
            self._appendTimelineRow(cell, entry)
        elif phase == "finished":
            self._liveWidgets.pop(id(entry), None)
            # Read before _finishTimelineRow: that method pops this entry's
            # location, and the error payload below needs the row it names.
            loc = self._entryTimelineLoc.get(id(entry))
            self._finishTimelineRow(cell, entry)
            if entry.outcome == "error":
                self._cellErrors[id(cell)] = (
                    entry.exc_type,
                    entry.exc_message,
                    entry.traceback_text,
                )
                # An action that gathered data before failing keeps that data:
                # it says more than the traceback, which the log and this row's
                # own outcome glyph both still carry.
                if loc is not None and loc not in self._details:
                    self._details[loc] = (
                        "error",
                        {
                            "exc_type": entry.exc_type,
                            "exc_message": entry.exc_message,
                            "traceback_text": entry.traceback_text,
                            "cell_repr": repr(cell),
                        },
                    )
            if cell is self._currentSelectedCell():
                self._mountSelectedRow()
        elif phase == "widget":
            widget = entry.details_widget
            if widget is None:
                self._liveWidgets.pop(id(entry), None)
            else:
                self._liveWidgets[id(entry)] = widget
            loc = self._entryTimelineLoc.get(id(entry))
            if loc is not None and self._isSelectedRow(loc):
                self._mountSelectedRow()
        elif phase == "details":
            loc = self._entryTimelineLoc.get(id(entry))
            if loc is not None:
                self._details[loc] = (entry.details_kind, entry.details_payload)
                if entry.details_kind == "image_stack":
                    # The first reference stack any action retains for this
                    # cell becomes the synthetic row's permanent backing (see
                    # _seedReferenceStackRow) -- cached here, rather than read
                    # back off the tracker later, because this payload just
                    # arrived over sigActionEntry and so is already safely on
                    # the GUI thread, the same way every other entry in
                    # self._details is.
                    self._referenceStacks.setdefault(
                        id(cell), (entry.details_kind, entry.details_payload)
                    )
                # A payload is this action's final word for its row (see
                # set_details' docstring: it must be called before the entry
                # finishes), so it supersedes that same entry's live widget from
                # here on -- even though the entry has not reached "finished"
                # yet and _liveWidgets would otherwise still hold it. Without
                # this, _mountSelectedRow's live-widget-first preference would
                # keep showing a plot the action itself has just moved past.
                self._liveWidgets.pop(id(entry), None)
                if self._isSelectedRow(loc):
                    self._mountSelectedRow()
        elif phase == "status":
            # Recorded and shown in the pane's header, but deliberately NOT in
            # the timeline row: rows show "running" then the outcome and
            # nothing else (design doc §7).
            loc = self._entryTimelineLoc.get(id(entry))
            if loc is not None:
                self._statuses[loc] = entry.status
                if self._isSelectedRow(loc):
                    self.statusLabel.setText(entry.status)

    def _seedReferenceStackRow(self, cell) -> None:
        """Insert the synthetic "Tracker initialized" row at index 0 of
        `cell`'s just-emptied timeline, if there is a reference stack to show
        for it. A cell whose tracker was never initialized (Cell.isInitialized
        False) gets no row at all, not an empty placeholder.

        Callers must call this immediately after setting
        self._timelines[id(cell)] = [] -- addCell() and _onReuseCheckedCells()
        are the only two places a cell's timeline starts empty, and doing
        this there means the synthetic row lands at index 0 with no other row
        ever needing to move: every subsequent _appendTimelineRow call
        computes its own index as len(rows), which already counts this one.

        THREAD SAFETY: cell._tracker's reference stack is worker-thread-owned
        data -- the same chain acq4.experiment.actions.device._trackerStack
        reads, but from inside a running action, i.e. from that same worker
        thread. Reading it directly here, on the GUI thread, is only safe for
        a cell nothing has started running yet: a survey producer seeds a
        freshly discovered cell's tracker with its reference cube once, on
        its own worker thread, before ever announcing the cell, and nothing
        touches that tracker again until the orchestrator marks the cell
        attempted and starts running actions against it (_onCurrentCell and
        _onCellFinished both record attempted before either could ever reach
        this method for that cell, via their own addCell() fallback). Past
        that point, a direct read races a worker thread that may still be
        appending to the same tracker -- confirmed for exactly this situation
        by 2794be759's finding that a detached FSM job can still be appending
        to a cell's tracker after its pass is already closed out -- so once a
        cell isAttempted(), this method reads only a payload already cached
        in self._referenceStacks from an earlier action's set_details() call,
        which arrived here over sigActionEntry and so was already safely on
        the GUI thread; it is never read fresh off the tracker again.
        """
        if not getattr(cell, "isInitialized", False):
            return
        cellId = id(cell)
        cached = self._referenceStacks.get(cellId)
        if cached is None and not self.isAttempted(cell):
            cached = _liveReferenceStackDetails(cell)
            if cached is not None:
                self._referenceStacks[cellId] = cached
        if cached is None:
            return
        rows = self._timelines[cellId]
        self._details[(cellId, len(rows))] = cached
        rows.append(_REFERENCE_STACK_ROW_TEXT)

    def _appendTimelineRow(self, cell, entry) -> None:
        text = f"{entry.name} — ⏳ running"
        rows = self._timelines.setdefault(id(cell), [])
        index = len(rows)
        rows.append(text)
        self._entryTimelineLoc[id(entry)] = (id(cell), index)
        if cell is self._currentSelectedCell():
            following = self._isFollowingLastRow()
            item = Qt.QListWidgetItem(text)
            self.timelineList.addItem(item)
            self._timelineItems[id(entry)] = item
            if following:
                self.timelineList.setCurrentItem(item)

    # Glyph shown in a finished timeline row for each ActionLogEntry.outcome
    # value (see ActionLogEntry._finish); an outcome this doesn't recognize
    # falls back to "?" rather than crashing the row.
    _OUTCOME_GLYPHS = {"done": "✓", "error": "✗", "stopped": "⊘", "abandoned": "⊘"}

    def _finishTimelineRow(self, cell, entry) -> None:
        elapsed = (entry.end_time - entry.start_time) if entry.end_time is not None else 0.0
        glyph = self._OUTCOME_GLYPHS.get(entry.outcome, "?")
        text = f"{entry.name} — {glyph} {entry.outcome} ({elapsed:.2f}s)"
        loc = self._entryTimelineLoc.pop(id(entry), None)
        if loc is not None:
            cellId, index = loc
            rows = self._timelines.get(cellId)
            if rows is not None and index < len(rows):
                rows[index] = text
        item = self._timelineItems.pop(id(entry), None)
        if item is not None:
            item.setText(text)

    def _clearShowContainer(self) -> None:
        showLayout = self.showContainer.layout()
        while showLayout.count():
            child = showLayout.takeAt(0)
            if child.widget() is not None:
                child.widget().setParent(None)

    def _isSelectedRow(self, loc) -> bool:
        """Whether (cellId, rowIndex) is the row the operator is looking at."""
        cellId, index = loc
        cell = self._currentSelectedCell()
        return (
            cell is not None
            and id(cell) == cellId
            and self.timelineList.currentRow() == index
        )

    def _mountSelectedRow(self) -> None:
        """Show whatever the currently selected timeline row has to show.

        Preference order: that row's live widget if its action is still in
        flight, else its retained payload, else nothing. A live action's widget
        wins because it is still being updated; the payload only exists once the
        action has something final to say.
        """
        self._clearShowContainer()
        self._shownEntryId = None
        cell = self._currentSelectedCell()
        index = self.timelineList.currentRow()
        if cell is None or index < 0:
            self.statusLabel.setText("")
            return
        loc = (id(cell), index)
        self.statusLabel.setText(self._statuses.get(loc, ""))
        for entryId, entryLoc in self._entryTimelineLoc.items():
            if entryLoc == loc and entryId in self._liveWidgets:
                self.showContainer.layout().addWidget(self._liveWidgets[entryId])
                self._shownEntryId = entryId
                return
        stored = self._details.get(loc)
        if stored is None:
            return
        kind, payload = stored
        self.showContainer.layout().addWidget(buildDetailsWidget(kind, payload))

    def _onTimelineSelectionChanged(self, _current, _previous) -> None:
        self._mountSelectedRow()

    def _isFollowingLastRow(self) -> bool:
        """Whether the operator is watching the newest row rather than reading
        back through earlier ones.

        The auto-scroll rule: while the last row is selected, a new action's row
        takes the selection with it; once the operator selects an earlier row,
        it does not, until they return to the last row. A timeline with no
        selection at all counts as following, so the first row of a freshly
        followed cell is shown rather than requiring a click.
        """
        count = self.timelineList.count()
        return count == 0 or self.timelineList.currentRow() in (-1, count - 1)

    def _autoSelectRow(self, cellId: int) -> None:
        """Select the row worth looking at for the cell just selected: the
        action still running, else the most recent one that failed, else the
        last one.

        Without this, switching to a cell would leave the pane blank until the
        operator clicked a row -- and, for a failed cell, would lose the
        traceback that used to mount on cell selection alone.
        """
        count = self.timelineList.count()
        if count == 0:
            self.timelineList.setCurrentRow(-1)
            return
        running = {
            index
            for entryId, (locCellId, index) in self._entryTimelineLoc.items()
            if locCellId == cellId
        }
        if running:
            self.timelineList.setCurrentRow(max(running))
            return
        failed = [
            index
            for (storeCellId, index), (kind, _payload) in self._details.items()
            if storeCellId == cellId and kind == "error"
        ]
        self.timelineList.setCurrentRow(max(failed) if failed else count - 1)

    def _onCellFinished(self, cell, status: str) -> None:
        # A cell can finish (e.g. the "skipped" outcome in
        # Orchestrator._processCell) without sigCurrentCell ever having fired
        # for it, so this cannot assume _onCurrentCell already gave it a row --
        # same reasoning as _onCurrentCell above: add one via addCell() only,
        # never re-enqueue and never mark it as awaiting one. A cell that has
        # finished is the clearest case of all: enqueuing it again patches a
        # cell that has already been worked.
        self._attempted.add(id(cell))
        if status in TERMINAL:
            self._status[id(cell)] = status
            # The pass just finished supersedes whatever reuse remembered for
            # the discard path; left behind, that value would restore a
            # disposition a pass out of date.
            self._preReuseStatus.pop(id(cell), None)
        item = self._rows.get(id(cell))
        if item is None:
            self.addCell(cell)
            item = self._rows[id(cell)]
        item.setText(f"cell {id(cell)} — {status}")
        self._updateCheckAllButton()
        self.sigCellStateChanged.emit()

    def selectCell(self, cell) -> None:
        """Make `cell`'s row current, so Area 5 shows its timeline and log.

        A no-op for a cell with no row. Area 1's overlay can report a click for
        a cell a rescan has since discarded, and raising out of a Qt slot over
        a stale selection is not an option.
        """
        item = self._rows.get(id(cell))
        if item is None:
            return
        self.cellList.setCurrentItem(item)

    def _onCellSelectionChanged(self, current, _previous) -> None:
        self.timelineList.clear()
        self._timelineItems.clear()
        self.logView.clear()
        # A followed cell's live details widget must not linger once the
        # operator switches away; only a fresh entry (via sigActionEntry) may
        # repopulate this container.
        self._clearShowContainer()
        self._shownEntryId = None
        if current is None:
            return
        cell = current.data(Qt.Qt.UserRole)
        cellId = id(cell)
        # Any entry still in flight for this cell needs its live QListWidgetItem
        # re-registered (by entry id) against the freshly created row below, so
        # that entry's eventual "finished" phase can keep updating it in place
        # even though the operator switched away and back in the meantime.
        pendingByIndex = {
            index: entryId
            for entryId, (locCellId, index) in self._entryTimelineLoc.items()
            if locCellId == cellId
        }
        for index, line in enumerate(self._timelines.get(cellId, [])):
            item = Qt.QListWidgetItem(line)
            self.timelineList.addItem(item)
            entryId = pendingByIndex.get(index)
            if entryId is not None:
                self._timelineItems[entryId] = item
        for line in self._logs.get(cellId, []):
            self.logView.appendPlainText(line)
        self._autoSelectRow(cellId)

    def _currentSelectedCell(self):
        item = self.cellList.currentItem()
        return None if item is None else item.data(Qt.Qt.UserRole)

    def _onZoomToCellClicked(self) -> None:
        item = self.cellList.currentItem()
        if item is None:
            return
        cell = item.data(Qt.Qt.UserRole)
        if cell is None:
            return
        self.sigZoomToCellRequested.emit(cell)
