"""CellPanel: Area 5's manually-seeded cell queue and its list view, kept in
sync with the Orchestrator's per-cell lifecycle signals."""
from __future__ import annotations

import random

import numpy as np
from coorx import Point

from acq4_automation.feature_tracking.cell import Cell
from acq4.util import Qt

from .error_display import ErrorBlock

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
    # "widget" (entry.set_details_widget()), or "finished" (entry._finish()).
    sigActionEntry = Qt.Signal(object, object, str)
    # Emitted by discardCells() so a rescan's row removal, arriving from the
    # orchestrator's worker thread the same way appendLog()/onLogAction() do,
    # is marshaled onto the GUI thread by Qt's automatic queued connection
    # rather than touching cellList directly.
    sigCellsDiscarded = Qt.Signal(object)

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
        self._logs: dict[int, list[str]] = {}
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
        self._pipetteGetter = pipetteGetter or (lambda: None)
        self._cameraGetter = cameraGetter or (lambda: None)

        self.cellList = Qt.QListWidget()
        self.timelineList = Qt.QListWidget()
        self.logView = Qt.QPlainTextEdit()
        self.logView.setReadOnly(True)
        self.showContainer = Qt.QWidget()
        self.showContainer.setLayout(Qt.QVBoxLayout())

        self.addFromTargetBtn = Qt.QPushButton("Add from target")
        self.scatterFakeCellsBtn = Qt.QPushButton("Scatter fake cells")
        self.checkAllCompletedBtn = Qt.QPushButton("Check all completed")
        self.reuseCheckedCellsBtn = Qt.QPushButton("Reuse checked cells")
        self.addFromTargetBtn.clicked.connect(self._onAddFromTargetClicked)
        self.scatterFakeCellsBtn.clicked.connect(self._onScatterFakeCellsClicked)
        self.checkAllCompletedBtn.clicked.connect(self._onCheckAllCompleted)
        self.reuseCheckedCellsBtn.clicked.connect(self._onReuseCheckedCells)

        btnRow = Qt.QHBoxLayout()
        btnRow.addWidget(self.addFromTargetBtn)
        btnRow.addWidget(self.scatterFakeCellsBtn)
        btnRow.addWidget(self.checkAllCompletedBtn)
        btnRow.addWidget(self.reuseCheckedCellsBtn)

        listsRow = Qt.QHBoxLayout()
        listsRow.addWidget(self.cellList)
        listsRow.addWidget(self.timelineList)

        layout = Qt.QVBoxLayout()
        layout.addLayout(btnRow)
        layout.addLayout(listsRow)
        layout.addWidget(self.showContainer)
        layout.addWidget(self.logView)
        self.setLayout(layout)

        self.cellList.currentItemChanged.connect(self._onCellSelectionChanged)
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
        self._status.clear()
        self._preReuseStatus.clear()
        self._rows.clear()
        self._timelines.clear()
        self._entryTimelineLoc.clear()
        self._timelineItems.clear()
        self._logs.clear()
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
        self._updateCheckAllButton()
        self._updateReuseButton()

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
        self._logs[id(cell)] = []
        # QListWidgetItem.setData() does not keep a strong Python reference to a
        # QObject-derived value (Cell is one): once the orchestrator's queue/worker
        # frame drops its own reference, the cell can be garbage-collected and
        # item.data() comes back re-wrapped as a bare, dangling QObject. Holding a
        # reference here for the panel's lifetime keeps the original object alive.
        self._cells[id(cell)] = cell

    def isAttempted(self, cell) -> bool:
        """Whether the orchestrator has ever started work on `cell`.

        Slice.forceRescan takes this as its predicate: attempted cells stay
        registered in the density record through a rescan, never-attempted ones
        are dropped so they can be found again where they now are.
        """
        return id(cell) in self._attempted

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
            # A stored error describes the pass that just ended, not the one
            # about to start. Left in place, _onCellSelectionChanged would
            # re-mount it beside a row that now reads "queued" and a timeline
            # that is empty -- and it would stay mounted until _onCurrentCell
            # eventually fires for this cell, which a Stop or a queue that
            # never reaches it can leave never happening.
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
            return
        self._attempted.add(id(cell))
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
        panel<->entry reference cycle is created.
        """
        entry.on_status = lambda e: self.sigActionEntry.emit(cell, e, "status")
        entry.on_widget = lambda e, w: self.sigActionEntry.emit(cell, e, "widget")
        entry.on_finish = lambda e: self.sigActionEntry.emit(cell, e, "finished")
        self.sigActionEntry.emit(cell, entry, "started")

    def _onActionEntry(self, cell, entry, phase: str) -> None:
        if phase == "started":
            self._appendTimelineRow(cell, entry)
        elif phase == "finished":
            self._finishTimelineRow(cell, entry)
            if cell is self._currentSelectedCell() and self._shownEntryId == id(entry):
                self._clearShowContainer()
                self._shownEntryId = None
            if entry.outcome == "error":
                self._cellErrors[id(cell)] = (
                    entry.exc_type,
                    entry.exc_message,
                    entry.traceback_text,
                )
                if cell is self._currentSelectedCell():
                    self._showErrorBlock(cell)
        elif phase == "widget":
            if cell is self._currentSelectedCell():
                self._clearShowContainer()
                self._shownEntryId = None
                widget = entry.details_widget
                if widget is not None:
                    self.showContainer.layout().addWidget(widget)
                    self._shownEntryId = id(entry)
        # "status" intentionally leaves the timeline row and details container
        # alone: Area 5's timeline only ever shows "running" then the finished
        # outcome, never each intermediate ctx.log_action status message (see
        # module docstring / design doc §7).

    def _appendTimelineRow(self, cell, entry) -> None:
        text = f"{entry.name} — ⏳ running"
        rows = self._timelines.setdefault(id(cell), [])
        index = len(rows)
        rows.append(text)
        self._entryTimelineLoc[id(entry)] = (id(cell), index)
        if cell is self._currentSelectedCell():
            item = Qt.QListWidgetItem(text)
            self.timelineList.addItem(item)
            self._timelineItems[id(entry)] = item

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

    def _showErrorBlock(self, cell) -> None:
        """Mount the stored error block for `cell` in the details container.

        Built fresh from the stored text on every mount rather than kept as a
        widget: _onCellSelectionChanged clears showContainer on every selection
        change, so a retained widget would be reparented away and would also be
        one more thing to drop on teardown.
        """
        stored = self._cellErrors.get(id(cell))
        if stored is None:
            return
        exc_type, exc_message, traceback_text = stored
        self._clearShowContainer()
        self._shownEntryId = None
        self.showContainer.layout().addWidget(
            ErrorBlock(exc_type, exc_message, traceback_text, repr(cell))
        )

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
        self._showErrorBlock(cell)

    def _currentSelectedCell(self):
        item = self.cellList.currentItem()
        return None if item is None else item.data(Qt.Qt.UserRole)
