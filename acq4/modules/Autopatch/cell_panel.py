"""CellPanel: Area 5's manually-seeded cell queue and its list view, kept in
sync with the Orchestrator's per-cell lifecycle signals."""
from __future__ import annotations

import random

import numpy as np
from coorx import Point

from acq4_automation.feature_tracking.cell import Cell
from acq4.util import Qt

# Random scatter radius for the "Scatter fake cells" demo button (meters).
_SCATTER_RADIUS = 40e-6


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

    def __init__(self, pipetteGetter=None, cameraGetter=None):
        super().__init__()
        self._orchestrator = None
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
        # id(entry) of whichever entry's widget currently occupies
        # showContainer, or None if it's empty. No action nests log_action
        # blocks today, but if one did, this lets a "finished" phase tell
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
        self.addFromTargetBtn.clicked.connect(self._onAddFromTargetClicked)
        self.scatterFakeCellsBtn.clicked.connect(self._onScatterFakeCellsClicked)

        btnRow = Qt.QHBoxLayout()
        btnRow.addWidget(self.addFromTargetBtn)
        btnRow.addWidget(self.scatterFakeCellsBtn)

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
        """
        self._cells.clear()
        # Cleared alongside self._cells, which is what the flush resolves these
        # ids against: an id left behind here would either raise a KeyError on
        # the next bind or, if that memory address were reused by an unrelated
        # cell, enqueue that cell instead.
        self._awaitingEnqueue.clear()
        self._attempted.clear()
        self._rows.clear()
        self._timelines.clear()
        self._entryTimelineLoc.clear()
        self._timelineItems.clear()
        self._logs.clear()
        self.cellList.clear()
        self._clearShowContainer()
        self._shownEntryId = None

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
            return
        self._attempted.add(id(cell))
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

    def _onCellFinished(self, cell, status: str) -> None:
        # A cell can finish (e.g. the "skipped" outcome in
        # Orchestrator._processCell) without sigCurrentCell ever having fired
        # for it, so this cannot assume _onCurrentCell already gave it a row --
        # same reasoning as _onCurrentCell above: add one via addCell() only,
        # never re-enqueue and never mark it as awaiting one. A cell that has
        # finished is the clearest case of all: enqueuing it again patches a
        # cell that has already been worked.
        self._attempted.add(id(cell))
        item = self._rows.get(id(cell))
        if item is None:
            self.addCell(cell)
            item = self._rows[id(cell)]
        item.setText(f"cell {id(cell)} — {status}")

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

    def _currentSelectedCell(self):
        item = self.cellList.currentItem()
        return None if item is None else item.data(Qt.Qt.UserRole)
