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

    def __init__(self, pipetteGetter=None, cameraGetter=None):
        super().__init__()
        self._orchestrator = None
        self._rows: dict[int, Qt.QListWidgetItem] = {}
        self._timelines: dict[int, list[str]] = {}
        self._logs: dict[int, list[str]] = {}
        self._cells: dict[int, object] = {}
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

    def bindOrchestrator(self, orchestrator) -> None:
        if self._orchestrator is not None:
            self.unbindOrchestrator()
        self._orchestrator = orchestrator
        orchestrator.sigCurrentAction.connect(self._onCurrentAction)
        orchestrator.sigCellFinished.connect(self._onCellFinished)
        orchestrator.sigActionFinished.connect(self._onActionFinished)
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
        """
        if self._orchestrator is None:
            return
        Qt.disconnect(self._orchestrator.sigCurrentAction, self._onCurrentAction)
        Qt.disconnect(self._orchestrator.sigCellFinished, self._onCellFinished)
        Qt.disconnect(self._orchestrator.sigActionFinished, self._onActionFinished)
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
        self._logs.clear()
        self.cellList.clear()

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

    def _onCurrentAction(self, cell, action) -> None:
        if cell is None:
            return
        item = self._rows.get(id(cell))
        if item is not None:
            item.setText(f"cell {id(cell)} — running: {action.name}")

        self._clearShowContainer()
        if cell is self._currentSelectedCell():
            widget = action.show()
            if widget is not None:
                self.showContainer.layout().addWidget(widget)

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

    def _onActionFinished(self, cell, action, outcome: str) -> None:
        line = f"{action.name}: {outcome}"
        self._timelines.setdefault(id(cell), []).append(line)
        if cell is self._currentSelectedCell():
            self.timelineList.addItem(line)

    def _onCellSelectionChanged(self, current, _previous) -> None:
        self.timelineList.clear()
        self.logView.clear()
        # A followed cell's live show() widget must not linger once the
        # operator switches away; only the selected cell's current action (via
        # the next sigCurrentAction) may repopulate this container.
        self._clearShowContainer()
        if current is None:
            return
        cell = current.data(Qt.Qt.UserRole)
        for line in self._timelines.get(id(cell), []):
            self.timelineList.addItem(line)
        for line in self._logs.get(id(cell), []):
            self.logView.appendPlainText(line)

    def _currentSelectedCell(self):
        item = self.cellList.currentItem()
        return None if item is None else item.data(Qt.Qt.UserRole)
