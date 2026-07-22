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
    def __init__(self, pipetteGetter=None, cameraGetter=None):
        super().__init__()
        self._orchestrator = None
        self._rows: dict[int, Qt.QListWidgetItem] = {}
        self._pipetteGetter = pipetteGetter or (lambda: None)
        self._cameraGetter = cameraGetter or (lambda: None)

        self.cellList = Qt.QListWidget()

        self.addFromTargetBtn = Qt.QPushButton("Add from target")
        self.scatterFakeCellsBtn = Qt.QPushButton("Scatter fake cells")
        self.addFromTargetBtn.clicked.connect(self._onAddFromTargetClicked)
        self.scatterFakeCellsBtn.clicked.connect(self._onScatterFakeCellsClicked)

        btnRow = Qt.QHBoxLayout()
        btnRow.addWidget(self.addFromTargetBtn)
        btnRow.addWidget(self.scatterFakeCellsBtn)

        layout = Qt.QVBoxLayout()
        layout.addLayout(btnRow)
        layout.addWidget(self.cellList)
        self.setLayout(layout)

    def bindOrchestrator(self, orchestrator) -> None:
        if self._orchestrator is not None:
            Qt.disconnect(self._orchestrator.sigCurrentAction, self._onCurrentAction)
            Qt.disconnect(self._orchestrator.sigCellFinished, self._onCellFinished)
        self._orchestrator = orchestrator
        orchestrator.sigCurrentAction.connect(self._onCurrentAction)
        orchestrator.sigCellFinished.connect(self._onCellFinished)

    def _onAddFromTargetClicked(self) -> None:
        pipette = self._pipetteGetter()
        if pipette is None:
            return
        position = Point(pipette.targetPosition(), "global")
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
        self._orchestrator.enqueue(cell)
        self.addCell(cell)

    def addCell(self, cell) -> None:
        item = Qt.QListWidgetItem(f"cell {id(cell)} — queued")
        item.setData(Qt.Qt.UserRole, cell)
        self.cellList.addItem(item)
        self._rows[id(cell)] = item

    def _onCurrentAction(self, cell, action) -> None:
        if cell is None:
            return
        item = self._rows.get(id(cell))
        if item is not None:
            item.setText(f"cell {id(cell)} — running: {action.name}")

    def _onCellFinished(self, cell, status: str) -> None:
        item = self._rows.get(id(cell))
        if item is not None:
            item.setText(f"cell {id(cell)} — {status}")
