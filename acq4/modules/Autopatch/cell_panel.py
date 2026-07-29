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
        if self._orchestrator is not None:
            self.unbindOrchestrator()
        self._orchestrator = orchestrator
        orchestrator.sigCurrentCell.connect(self._onCurrentCell)
        orchestrator.sigCellFinished.connect(self._onCellFinished)
        # Cells seeded before a protocol was loaded (self._orchestrator was None)
        # were held here without being enqueued; flush them into the newly bound
        # orchestrator now, exactly once each, so a freshly loaded protocol runs
        # over any cells the operator already seeded.
        for cell in self._cells.values():
            orchestrator.enqueue(cell)

    def unbindOrchestrator(self) -> None:
        """Disconnect everything bindOrchestrator() connected to the currently
        bound orchestrator, and drop the reference to it.

        Shared by bindOrchestrator() (rebinding to a freshly loaded protocol)
        and window teardown (on module/window close), so both paths sever the
        panel<->orchestrator signal wiring the same way -- leaving no dangling
        Qt connection either way.

        Note this does NOT touch onLogAction/sigActionEntry: that path is wired
        through the context factory (ExecutionContext.on_log_action, cell-bound
        per make_context_factory), not through an Orchestrator signal
        connection, so there is nothing here for a rebind or teardown to sever.
        """
        if self._orchestrator is None:
            return
        Qt.disconnect(self._orchestrator.sigCurrentCell, self._onCurrentCell)
        Qt.disconnect(self._orchestrator.sigCellFinished, self._onCellFinished)
        self._orchestrator = None

    def clearCells(self) -> None:
        """Drop every seeded Cell this panel is holding, for window teardown.

        Cell is a QObject; self._cells is the only strong Python reference
        keeping a seeded-but-not-yet-garbage-collected Cell alive once its own
        run finishes (see addCell()), and Cell instances are parented to this
        panel (also set in addCell()) so Qt's ownership cascade destroys them
        deterministically when the window closes. This clears the Python-side
        bookkeeping (and any per-cell signal connections a future change might
        add) to match -- nothing here should still reference a Cell afterward.
        """
        self._cells.clear()
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
        # loaded and bound an orchestrator. If one IS bound, also enqueue the
        # new cell into it immediately; unbound cells are flushed into whatever
        # orchestrator bindOrchestrator() later binds, so this never
        # double-enqueues.
        if self._orchestrator is not None:
            self._orchestrator.enqueue(cell)
        self.addCell(cell)

    def addCell(self, cell) -> None:
        # Cell is a QObject; parenting it to this panel (itself parented into
        # the window's widget tree) lets Qt's ownership cascade destroy it
        # deterministically when the window closes, rather than relying solely
        # on Python holding the last reference (see self._cells below). Guarded
        # with getattr since tests stand in a plain object() for a cell.
        setParent = getattr(cell, "setParent", None)
        if setParent is not None:
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
        item = self._rows.get(id(cell))
        if item is not None:
            item.setText(f"cell {id(cell)} — running")

    def onLogAction(self, cell, entry) -> None:
        """ExecutionContext.on_log_action, cell-bound by the context factory
        (make_context_factory's onLogAction=partial(..., cell)).

        Called from the orchestrator's worker thread the instant an action
        opens `with ctx.log_action(name) as entry:`. Assigns the entry's
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
    _OUTCOME_GLYPHS = {"done": "✓", "error": "✗", "stopped": "⊘"}

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
        item = self._rows.get(id(cell))
        if item is not None:
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
