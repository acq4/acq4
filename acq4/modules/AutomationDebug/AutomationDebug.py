from __future__ import annotations

import os
from pathlib import Path

import numpy as np

import pyqtgraph as pg
from acq4.devices.Camera import Camera
from acq4.devices.Microscope import Microscope
from acq4.devices.PatchPipette import PatchPipette
from acq4.devices.Pipette import Pipette
from acq4.motion import (
    DefaultMotionPlanner,
    GeometryAwareMotionPlanner,
    MinirigV1MotionPlanner,
)
from acq4.logging_config import get_logger
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.task import Task, check_stop, asynch_with_qt_signals
from pyqtgraph.units import µm, m
from .autopatch import Autopatcher
from .detection import CellDetector
from .feature_tracking import FeatureTracker
from .mock_data import MockDataHandler
from .survey import SurveyRegion
from ... import getManager

logger = get_logger(__name__)
UiTemplate = Qt.importTemplate(".window")


class _ObservableList(list):
    """A ``list`` that calls ``on_change`` after any in-place mutation.

    The autopatch workflow tracks cell state purely by which list a cell lives in
    (waiting / in-progress / patched), and those lists are mutated from many
    places (detection, the demo loop, re-queueing) and from worker threads. Making
    the lists observable lets the UI stay in sync no matter how or where they
    change, rather than relying on every call site to remember to notify.
    """

    def __init__(self, iterable=(), on_change=None):
        self._on_change = None  # suppress notification while populating
        super().__init__(iterable)
        self._on_change = on_change

    def _changed(self):
        if self._on_change is not None:
            self._on_change()

    def append(self, item):
        super().append(item)
        self._changed()

    def extend(self, iterable):
        super().extend(iterable)
        self._changed()

    def insert(self, index, item):
        super().insert(index, item)
        self._changed()

    def remove(self, item):
        super().remove(item)
        self._changed()

    def pop(self, index=-1):
        item = super().pop(index)
        self._changed()
        return item

    def clear(self):
        super().clear()
        self._changed()

    def sort(self, *args, **kwargs):
        super().sort(*args, **kwargs)
        self._changed()

    def reverse(self):
        super().reverse()
        self._changed()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._changed()

    def __delitem__(self, key):
        super().__delitem__(key)
        self._changed()

    def __iadd__(self, other):
        result = super().__iadd__(other)
        self._changed()
        return result

    def __imul__(self, n):
        result = super().__imul__(n)
        self._changed()
        return result


class AutomationDebugWindow(Qt.QWidget):
    sigWorking = Qt.Signal(
        object
    )  # a btn that is busy or False to signify no longer working
    sigLogMessage = Qt.Signal(str)
    # Emitted whenever the waiting/in-progress/patched cell lists change. Drives
    # the cell table; may be emitted from worker threads, so the connected slot
    # runs in the GUI thread via Qt's queued delivery.
    sigCellsChanged = Qt.Signal()

    def __init__(self, module: "AutomationDebug"):
        super().__init__()
        self._annotation_tool = None
        self._annotation_stack_transform = None
        # Base name shared by a detection session's saved z-stack, cellpose masks,
        # and annotations; set when a detection run starts.
        self.annotation_base_name = None
        self.ui = UiTemplate()
        self.ui.setupUi(self)

        # Add z-stack depth spinboxes to the Cell Detection group box
        _zstack_depth_layout = Qt.QHBoxLayout()
        _zstack_depth_layout.addWidget(Qt.QLabel("Start depth:"))
        self.ui.zStackStartDepthSpin = pg.SpinBox(value=20e-6, suffix='m', siPrefix=True, step=5e-6)
        _zstack_depth_layout.addWidget(self.ui.zStackStartDepthSpin)
        _zstack_depth_layout.addWidget(Qt.QLabel("Stop depth:"))
        self.ui.zStackStopDepthSpin = pg.SpinBox(value=60e-6, suffix='m', siPrefix=True, step=5e-6)
        _zstack_depth_layout.addWidget(self.ui.zStackStopDepthSpin)
        _zstack_depth_layout.addWidget(Qt.QLabel("Min volume:"))
        self.ui.minVolumeSpin = pg.SpinBox(value=0, suffix='m³', siPrefix=True, step=100e-18, bounds=(0, None))
        _zstack_depth_layout.addWidget(self.ui.minVolumeSpin)
        _zstack_depth_layout.addStretch()
        self.ui.groupBox.layout().addLayout(_zstack_depth_layout, 5, 0, 1, 4)

        # Survey region controls: a rectangle on the camera view that the autopatch
        # demo tiles across, taking one z-stack per unexamined field of view.
        _survey_layout = Qt.QHBoxLayout()
        self.ui.addSurveyRegionBtn = Qt.QPushButton("Add survey region")
        self.ui.clearSurveyRegionBtn = Qt.QPushButton("Clear region")
        _survey_layout.addWidget(self.ui.addSurveyRegionBtn)
        _survey_layout.addWidget(self.ui.clearSurveyRegionBtn)
        _survey_layout.addWidget(Qt.QLabel("Tile overlap:"))
        self.ui.surveyOverlapSpin = pg.SpinBox(value=20e-6, suffix='m', siPrefix=True, step=5e-6, bounds=(0, None))
        _survey_layout.addWidget(self.ui.surveyOverlapSpin)
        _survey_layout.addStretch()
        self.ui.groupBox.layout().addLayout(
            _survey_layout, self.ui.groupBox.layout().rowCount(), 0, 1, 4
        )
        self.ui.surveyStatsLabel = Qt.QLabel("Survey: no region")
        self.ui.groupBox.layout().addWidget(
            self.ui.surveyStatsLabel, self.ui.groupBox.layout().rowCount(), 0, 1, 4
        )

        # A live table of every known cell and its current patch state. Built
        # before the cell lists are initialized so _refreshCellTable can find it.
        self._buildCellTableUi()

        self.sigWorking.connect(self._setWorkingState)
        self.failedCalibrations = []
        self.module = module
        self.setWindowTitle("Automation Debug")
        self._previousBoxWidgets = []
        self._mockDemo = False
        self._cell = None
        self._visualizers = []
        self._unranked_cells = []  # List of global positions of cells
        self._ranked_cells = []
        self._current_detection_stack = None
        self._current_classification_stack = None  # May be None
        self._previousTargets = []  # Used by autoTarget
        self._open_ranking_windows = []  # Keep track of open windows
        self._autopatchRunning = False

        # Now that the cell lists exist, keep the table in sync with any change.
        self.sigCellsChanged.connect(self._refreshCellTable)
        self._refreshCellTable()

        # --- Composed objects ---
        self._detector = CellDetector(self)
        self._mock_handler = MockDataHandler(self)
        self._autopatcher = Autopatcher(self)
        self._feature_tracker = FeatureTracker(self)
        self._surveyRegion = SurveyRegion(self)

        # --- UI wiring ---
        self.ui.clearBtn.clicked.connect(self._detector.clearCells)
        self.ui.addSurveyRegionBtn.clicked.connect(self._surveyRegion.addRegion)
        self.ui.clearSurveyRegionBtn.clicked.connect(self._surveyRegion.clearRegion)
        self.ui.surveyOverlapSpin.sigValueChanged.connect(self._refreshSurveyStats)
        self.ui.showRoisBtn.toggled.connect(self._toggleCellRois)
        self.ui.zStackDetectBtn.setOpts(
            task_producer=self._detector._detectNeuronsZStack, stoppable=True
        )
        self.ui.zStackDetectBtn.sigFinished.connect(self._detector._handleDetectResults)
        self.ui.testUIBtn.setOpts(task_producer=self._detector._testUI, stoppable=True)
        self.ui.testUIBtn.sigFinished.connect(self._detector._handleDetectResults)
        self.ui.addCellFromTargetBtn.setOpts(
            task_producer=self._detector._addCellFromTarget, stoppable=True
        )

        self.ui.motionPlannerSelector.addItems(self._MOTION_PLANNERS.keys())
        self.ui.motionPlannerSelector.currentIndexChanged.connect(
            self._changeMotionPlanner
        )

        self.ui.rankCellsBtn.clicked.connect(self._detector._rankCells)
        self.ui.selectRankDirBtn.clicked.connect(self._detector._selectRankDir)

        self.ui.setTopLeftButton.clicked.connect(self._setTopLeft)
        self.ui.setBottomRightButton.clicked.connect(self._setBottomRight)

        self.ui.mockFilePath.setReadOnly(True)
        self.ui.mockFileButton.clicked.connect(self._mock_handler._selectMockFile)
        self.ui.mockClassificationFilePath.setReadOnly(True)
        self.ui.mockClassificationFileButton.clicked.connect(
            self._mock_handler._selectMockClassificationFile
        )

        self.ui.autoTargetBtn.setOpts(task_producer=self._autoTarget, stoppable=True)
        self.ui.autoTargetBtn.sigFinished.connect(self._handleAutoFinish)

        # These are InterfaceCombo widgets (promoted in window.ui); they populate
        # themselves from the manager's interface directory and stay in sync as
        # devices come and go.
        self.ui.pipetteSelector.setTypes(['pipette'])
        self.ui.cameraSelector.setTypes(['camera'])

        self.ui.trackFeaturesBtn.setOpts(
            task_producer=self._feature_tracker.doFeatureTracking,
            processing="Stop tracking",
            stoppable=True,
        )
        self.ui.trackFeaturesBtn.sigFinished.connect(
            self._feature_tracker._handleFeatureTrackingFinish
        )
        self.ui.visualizeTrackingBtn.clicked.connect(
            self._feature_tracker._visualizeTracking
        )
        self.ui.visualizeTrackingBtn.setEnabled(True)

        self.ui.testPipetteBtn.setOpts(
            task_producer=self._feature_tracker.doPipetteCalibrationTest,
            stoppable=True,
            processing="Interrupt pipette\ncalibration test",
        )
        self.ui.testPipetteBtn.setToolTip(
            "Start with the pipette calibrated and in the field of view"
        )
        self.ui.testPipetteBtn.sigFinished.connect(
            self._feature_tracker._handleCalibrationFinish
        )

        self._testing_pipette = False
        self.ui.pipetteLog.setReadOnly(True)
        self.sigLogMessage.connect(self.ui.pipetteLog.append)

        self.ui.autopatchDemoBtn.setToolTip("Patch a cell! Repeat! REPEAT!")
        self.ui.autopatchDemoBtn.setOpts(
            task_producer=self._autopatcher._autopatchDemo, stoppable=True
        )
        self.ui.autopatchDemoBtn.sigFinished.connect(
            self._autopatcher._handleAutopatchDemoFinish
        )
        self.ui.reuseLastCellBtn.clicked.connect(self._reuseAllCells)

        self.show()
        current_planner = type(self.module.manager.motionPlanner).__name__
        with pg.SignalBlock(self.ui.motionPlannerSelector.currentIndexChanged, self._changeMotionPlanner):
            self.ui.motionPlannerSelector.setCurrentText(current_planner)
        # Set default ranking dir
        default_rank_dir = (
            Path(self.module.manager.getBaseDir().name()) / "ranked_cells"
        )
        self.ui.rankingSaveDirEdit.setText(str(default_rank_dir))
        self._populatePresetCombos()
        # Connect checkboxes to state update method
        self.ui.multiChannelEnableCheck.toggled.connect(
            self._updateMultiChannelAndMockStates
        )
        self.ui.mockCheckBox.toggled.connect(self._updateMultiChannelAndMockStates)
        self._updateMultiChannelAndMockStates()  # Set initial states

        self.loadConfig()

    # ------------------------------------------------------------------
    # Cell state tracking
    #
    # A cell's patch state is defined by which container it lives in:
    #   _unranked_cells -> "Waiting" (queued, not yet worked on)
    #   _cell           -> "In progress" (currently being patched)
    #   _ranked_cells   -> "Patched" (already worked on; the in-progress cell is
    #                       also appended here, so it is checked first below)
    # These are exposed as properties backed by _ObservableList so that any
    # mutation or reassignment emits sigCellsChanged and refreshes the table.
    # ------------------------------------------------------------------

    # Semi-transparent tints (read on both light and dark themes), keyed by the
    # colour category a row falls into rather than its free-text label.
    _CELL_STATE_COLORS = {
        "waiting": Qt.QColor(128, 128, 128, 60),
        "progress": Qt.QColor(240, 180, 40, 100),
        "ok": Qt.QColor(60, 180, 75, 90),
        "bad": Qt.QColor(200, 70, 70, 80),
    }

    @property
    def _autopatchRunning(self) -> bool:
        """Whether the autopatch demo is actively working a cell.

        Gates the "In progress" label so a cell stops reading as in-progress once
        the demo has finished or been stopped.
        """
        return self._autopatchRunningState

    @_autopatchRunning.setter
    def _autopatchRunning(self, value):
        self._autopatchRunningState = bool(value)
        self._onCellListsChanged()

    def setCellStatus(self, cell, status: str, category: str | None = None):
        """Record a short outcome description for ``cell`` and refresh the table.

        ``category`` is one of "ok"/"bad"/None and only drives the row colour.
        Safe to call from worker threads (updates go through sigCellsChanged).
        """
        if cell is None:
            return
        cell._debugStatus = status
        cell._debugStatusCategory = category
        self._onCellListsChanged()

    @property
    def _cell(self):
        return self._current_cell

    @_cell.setter
    def _cell(self, value):
        self._current_cell = value
        self._onCellListsChanged()

    @property
    def _unranked_cells(self):
        return self._unranked_cells_store

    @_unranked_cells.setter
    def _unranked_cells(self, value):
        self._unranked_cells_store = _ObservableList(value, self._onCellListsChanged)
        self._onCellListsChanged()

    @property
    def _ranked_cells(self):
        return self._ranked_cells_store

    @_ranked_cells.setter
    def _ranked_cells(self, value):
        self._ranked_cells_store = _ObservableList(value, self._onCellListsChanged)
        self._onCellListsChanged()

    def _onCellListsChanged(self):
        """Notify listeners (the cell table) that the cell lists changed.

        Emitting a signal rather than touching widgets directly keeps this safe to
        call from worker threads: the connected slot runs in the GUI thread.
        """
        self.sigCellsChanged.emit()

    def _buildCellTableUi(self):
        """Create the "Cells" group box.

        Left: a table of every cell and its state, plus cell action buttons.
        Right: a pg.ImageView showing the selected cell's initial 3D stack.
        """
        self._cellTableRows = []  # cells in the same order as table rows
        self._selectedCell = None

        group = Qt.QGroupBox("Cells")
        outer = Qt.QVBoxLayout(group)

        self.ui.cellSummaryLabel = Qt.QLabel("No cells")
        outer.addWidget(self.ui.cellSummaryLabel)

        split = Qt.QHBoxLayout()
        outer.addLayout(split)

        # --- Left column: table + action buttons ---
        left = Qt.QVBoxLayout()
        split.addLayout(left, 1)

        table = Qt.QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["State", "Position (µm)", "Score"])
        table.setEditTriggers(Qt.QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(Qt.QAbstractItemView.SelectRows)
        table.setSelectionMode(Qt.QAbstractItemView.SingleSelection)
        table.verticalHeader().setVisible(False)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, Qt.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, Qt.QHeaderView.Stretch)
        header.setSectionResizeMode(2, Qt.QHeaderView.ResizeToContents)
        table.setMinimumHeight(160)
        table.itemSelectionChanged.connect(self._onCellSelectionChanged)
        self.ui.cellTable = table
        left.addWidget(table)

        btnRow = Qt.QHBoxLayout()
        left.addLayout(btnRow)
        # Reuse-all button, relocated here from the Autopatch Demo group. Adding it
        # to this layout reparents it out of that group automatically.
        btnRow.addWidget(self.ui.reuseLastCellBtn)
        self.ui.setTargetFromCellBtn = Qt.QPushButton("Set target from cell")
        self.ui.setTargetFromCellBtn.setToolTip(
            "Set the pipette target to the selected cell's position"
        )
        self.ui.setTargetFromCellBtn.setEnabled(False)
        self.ui.setTargetFromCellBtn.clicked.connect(self._setTargetFromSelectedCell)
        btnRow.addWidget(self.ui.setTargetFromCellBtn)
        self.ui.removeCellBtn = Qt.QPushButton("Remove cell")
        self.ui.removeCellBtn.setToolTip(
            "Remove the selected cell from the waiting/in-progress/patched lists"
        )
        self.ui.removeCellBtn.setEnabled(False)
        self.ui.removeCellBtn.clicked.connect(self._removeSelectedCell)
        btnRow.addWidget(self.ui.removeCellBtn)
        btnRow.addStretch()

        # --- Right column: initial 3D stack of the selected cell ---
        self.ui.cellImageView = pg.ImageView()
        self.ui.cellImageView.setMinimumWidth(260)
        split.addWidget(self.ui.cellImageView, 1)

        self.layout().addWidget(group)

    def _refreshCellTable(self):
        """Rebuild the cell table from the current cell lists.

        Rows are ordered finished -> in progress -> waiting and de-duplicated by
        identity (the in-progress cell also lives in the ranked list). The state
        column shows each cell's recorded outcome rather than a blanket "patched".
        """
        table = getattr(self.ui, "cellTable", None)
        if table is None:
            return

        current = self._cell
        running = self._autopatchRunning
        rows = []  # (cell, label, colour_category)
        seen = set()

        def add(cell, label, category):
            if id(cell) in seen:
                return
            seen.add(id(cell))
            rows.append((cell, label, category))

        for cell in list(self._ranked_cells):
            if cell is current:
                continue
            label, category = self._cellRowInfo(cell, is_current=False, running=running)
            add(cell, label, category)
        if current is not None:
            label, category = self._cellRowInfo(current, is_current=True, running=running)
            add(current, label, category)
        for cell in list(self._unranked_cells):
            add(cell, "Waiting", "waiting")

        counts = {"waiting": 0, "progress": 0, "finished": 0}
        # Suppress selection signals while rebuilding; we restore the selection
        # (by cell identity) and refresh the dependent UI explicitly afterward.
        table.blockSignals(True)
        table.setRowCount(len(rows))
        for row, (cell, label, category) in enumerate(rows):
            if category == "waiting":
                counts["waiting"] += 1
            elif category == "progress":
                counts["progress"] += 1
            else:
                counts["finished"] += 1
            color = self._CELL_STATE_COLORS.get(category)
            values = (label, self._formatCellPosition(cell), self._formatCellScore(cell))
            for col, text in enumerate(values):
                item = Qt.QTableWidgetItem(text)
                if color is not None:
                    item.setBackground(Qt.QBrush(color))
                table.setItem(row, col, item)
        self._cellTableRows = [r[0] for r in rows]

        target_row = next(
            (i for i, cell in enumerate(self._cellTableRows) if cell is self._selectedCell),
            -1,
        )
        if target_row >= 0:
            table.selectRow(target_row)
        else:
            table.clearSelection()
        table.blockSignals(False)
        self._syncCellSelectionUi()

        self.ui.cellSummaryLabel.setText(
            f"{len(rows)} cell(s) — "
            f"{counts['waiting']} waiting, "
            f"{counts['progress']} in progress, "
            f"{counts['finished']} finished"
        )

    @staticmethod
    def _cellRowInfo(cell, is_current: bool, running: bool):
        """Return (label, colour_category) for a worked/in-progress cell.

        A cell only reads as "In progress" while the demo is actively running;
        otherwise it shows the outcome recorded via setCellStatus, falling back to
        "stopped" for a cell that was interrupted before any outcome was recorded.
        """
        if is_current and running:
            return "In progress", "progress"
        status = getattr(cell, "_debugStatus", None)
        if status is None:
            return "stopped", "bad"
        category = getattr(cell, "_debugStatusCategory", None)
        return status, category if category in ("ok", "bad") else None

    def _onCellSelectionChanged(self):
        self._syncCellSelectionUi()

    def _syncCellSelectionUi(self):
        """Reconcile the selected cell with the image view and target button."""
        table = getattr(self.ui, "cellTable", None)
        if table is None:
            return
        selected = table.selectionModel().selectedRows()
        rows = self._cellTableRows
        if selected and 0 <= selected[0].row() < len(rows):
            cell = rows[selected[0].row()]
        else:
            cell = None
        self._selectedCell = cell
        self.ui.setTargetFromCellBtn.setEnabled(cell is not None)
        self.ui.removeCellBtn.setEnabled(cell is not None)
        self._updateCellImage()

    def _updateCellImage(self):
        iv = getattr(self.ui, "cellImageView", None)
        if iv is None:
            return
        stack = self._cellInitialStack(self._selectedCell)
        if stack is None:
            iv.clear()
            return
        # Transpose rows/cols (swap the last two axes) so the stack displays in
        # the same orientation as the camera module, leaving the z axis first.
        if stack.ndim >= 2:
            stack = np.swapaxes(stack, -2, -1)
        iv.setImage(stack, autoRange=True, autoLevels=True)

    @staticmethod
    def _cellInitialStack(cell):
        """The 3D image stack captured when the cell's tracker was initialized.

        Returns None if the cell has not been initialized for tracking yet (e.g. a
        freshly detected cell still waiting in the queue), so callers can clear the
        view instead of showing stale data.
        """
        if cell is None:
            return None
        tracker = getattr(cell, "_tracker", None)
        if tracker is None:
            return None
        try:
            stack = tracker.motion_estimator.original_object_stack.data
        except Exception:
            return None
        if stack is None:
            return None
        return np.asarray(stack)

    def _setTargetFromSelectedCell(self):
        cell = self._selectedCell
        if cell is None:
            return
        try:
            target = np.asarray(cell.position.coordinates, dtype=float)
        except Exception:
            logger.exception("Selected cell has no usable position")
            return
        try:
            self.pipetteDevice.setTarget(target)
        except Exception:
            logger.exception("Failed to set pipette target from selected cell")
            return
        logger.info(f"Set pipette target from selected cell to {target}")

    def _removeSelectedCell(self):
        """Remove the selected cell from whichever list(s) it lives in."""
        cell = self._selectedCell
        if cell is None:
            return
        # Drop the selection first so the table rebuild triggered by the removals
        # below doesn't try to re-select the cell we're deleting.
        self._selectedCell = None
        if self._cell is cell:
            self._cell = None
        if cell in self._unranked_cells:
            self._unranked_cells.remove(cell)
        if cell in self._ranked_cells:
            self._ranked_cells.remove(cell)
        logger.info("Removed selected cell from the cell lists")

    @staticmethod
    def _formatCellPosition(cell) -> str:
        try:
            x, y, z = np.asarray(cell.position.coordinates, dtype=float) * 1e6
            return f"({x:.1f}, {y:.1f}, {z:.1f})"
        except Exception:
            return "?"

    @staticmethod
    def _formatCellScore(cell) -> str:
        score = getattr(cell, "score", None)
        if score is None:
            return ""
        try:
            return f"{score:.0%}"
        except (ValueError, TypeError):
            return str(score)

    def _updateMultiChannelAndMockStates(self):
        multi_channel_enabled = self.ui.multiChannelEnableCheck.isChecked()
        mock_mode_active = self.ui.mockCheckBox.isChecked()

        self.ui.detectionPresetCombo.setEnabled(multi_channel_enabled)
        self.ui.classificationPresetCombo.setEnabled(multi_channel_enabled)

        mock_classification_widgets_enabled = multi_channel_enabled and mock_mode_active
        self.ui.mockClassificationFileLabel.setEnabled(
            mock_classification_widgets_enabled
        )
        self.ui.mockClassificationFileButton.setEnabled(
            mock_classification_widgets_enabled
        )
        self.ui.mockClassificationFilePath.setEnabled(
            mock_classification_widgets_enabled
        )

    def _populatePresetCombos(self):
        presets = self.scopeDevice.presets.keys()
        self.ui.detectionPresetCombo.clear()
        self.ui.classificationPresetCombo.clear()
        self.ui.detectionPresetCombo.addItems(presets)
        self.ui.classificationPresetCombo.addItems(presets)

    def _refreshSurveyStats(self, *args):
        """Update the survey stats readout from the current region and progress.

        Connected to ROI changes and the overlap spinbox, and called by
        SurveyRegion when a region is added/cleared/reset or a tile is imaged.
        """
        stats = self._surveyRegion.stats()
        if stats is None:
            self.ui.surveyStatsLabel.setText("Survey: no region")
            return
        area, total, covered, percent = stats
        self.ui.surveyStatsLabel.setText(
            f"Survey: {area * 1e6:.3g} mm² area | {total} tiles | "
            f"{percent:.0f}% surveyed ({covered}/{total})"
        )

    def _toggleCellRois(self, visible: bool):
        for box in self._previousBoxWidgets:
            box.setVisible(visible)

    def _setWorkingState(self, working: bool | Qt.QPushButton):
        if working:
            self.module.manager.getModule(
                "Camera"
            ).window()  # make sure camera window is open
        self.ui.zStackDetectBtn.setEnabled(
            working == self.ui.zStackDetectBtn or not working
        )
        self.ui.testUIBtn.setEnabled(working == self.ui.testUIBtn or not working)
        self.ui.autoTargetBtn.setEnabled(
            working == self.ui.autoTargetBtn or not working
        )
        self.ui.testPipetteBtn.setEnabled(
            working == self.ui.testPipetteBtn or not working
        )
        self.ui.trackFeaturesBtn.setEnabled(
            working == self.ui.trackFeaturesBtn or not working
        )
        self.ui.rankCellsBtn.setEnabled(len(self._unranked_cells) > 0)
        # self.ui.autopatchDemoBtn.setEnabled(working == self.ui.autopatchDemoBtn or not working)

    @property
    def annotation_save_dir(self) -> Path | None:
        """Directory in which to save cell annotations (and the detection z-stack and
        cellpose masks) from the detection workflow.

        Uses the configured ``misc/cellAnnotationDir`` if set, otherwise a
        ``cell_annotations`` subdirectory of the data storage directory. None when
        neither is available, in which case the annotation tool falls back to the
        working directory.
        """
        manager = self.module.manager
        configured = manager.config.get("misc", {}).get("cellAnnotationDir", None)
        if configured:
            return Path(configured)
        base = manager.getBaseDir()
        if base is not None:
            return Path(base.name()) / "cell_annotations"
        return None

    @property
    def cameraDevice(self) -> Camera:
        return self.module.manager.getDevice(self.ui.cameraSelector.currentText())

    @property
    def scopeDevice(self) -> Microscope:
        return self.cameraDevice.scopeDev  # TODO

    @property
    def pipetteDevice(self) -> Pipette:
        return self.module.manager.getDevice(self.ui.pipetteSelector.currentText())

    @property
    def patchPipetteDevice(self) -> PatchPipette | None:
        pip = self.pipetteDevice
        man = self.module.manager
        for pp in man.listDevices():
            pp = man.getDevice(pp)
            if isinstance(pp, PatchPipette) and pp.pipetteDevice == pip:
                return pp
        return None

    def _setTopLeft(self):
        cam = self.cameraDevice
        region = cam.getParam("region")
        bound = cam.globalTransform().map((region[0], region[1], 0))
        self._xLeftSpin.setValue(bound[0])
        self._yTopSpin.setValue(bound[1])

    def _setBottomRight(self):
        cam = self.cameraDevice
        region = cam.getParam("region")
        bound = cam.globalTransform().map((region[0] + region[2], region[1] + region[3], 0))
        self._xRightSpin.setValue(bound[0])
        self._yBottomSpin.setValue(bound[1])

    @asynch_with_qt_signals
    def _autoTarget(self):
        self.sigWorking.emit(self.ui.autoTargetBtn)
        # If _unranked_cells is populated, use it. Otherwise, run detection.
        if not self._unranked_cells:
            logger.info("Need new potential cells; running detection")
            x, y = self._randomLocation()
            self.scopeDevice.setGlobalPosition(
                (x, y), name="random move to find cells"
            ).wait()
            # TODO don't know why this hangs when using waitFor, but it does
            depth = self.scopeDevice.findSurfaceDepth(
                self.cameraDevice,
                searchDistance=50 * µm,
                searchStep=15 * µm,
            )
            # Target below surface
            depth = depth - 50 * µm
            check_stop()
            self.cameraDevice.setFocusDepth(depth, name=f"{self.cameraDevice.name()} focus below surface for autoTarget")  # Set focus depth

            self._detector._detectNeuronsZStack().wait(
                timeout=600
            )  # Side-effect: populates _unranked_cells
        if not self._unranked_cells:
            raise RuntimeError(
                "Neuron detection ran, but no cells found for autoTarget."
            )

        neurons = self._unranked_cells

        # --- Calculate target ---
        centers = [cell.position.coordinates for cell in neurons]
        # TODO is this important to check? does the detection algorithm already guarantee this?
        target = next(
            (
                c
                for c in centers
                if all(
                    np.linalg.norm(c - prev) > 35 * µm for prev in self._previousTargets
                )
            ),
            None,
        )

        if target is None:
            raise RuntimeError("No suitable new target found among detected cells.")
        self._previousTargets.append(target)
        self.pipetteDevice.setTarget(target)  # TODO setCellTarget
        logger.info(f"Setting pipette target to {target}")

    def _reuseAllCells(self):
        cells_to_requeue = list(self._ranked_cells)
        if self._cell is not None and self._cell not in cells_to_requeue:
            cells_to_requeue.append(self._cell)
        if not cells_to_requeue:
            return
        self._ranked_cells.clear()
        self._cell = None
        self._unranked_cells[:0] = cells_to_requeue
        self.ui.reuseLastCellBtn.setEnabled(False)
        logger.info(f"Re-queued {len(cells_to_requeue)} completed cell(s) to front of unranked list")

    def _handleAutoFinish(self, fut: Task):
        self.sigWorking.emit(False)

    def _randomLocation(self):
        return self.cameraDevice.globalCenterPosition()[:2]
        # TODO get the spinners back
        # x = random.uniform(self._xLeftSpin.value(), self._xRightSpin.value())
        # y = random.uniform(self._yBottomSpin.value(), self._yTopSpin.value())
        # return x, y

    _MOTION_PLANNERS = {
        "DefaultMotionPlanner": DefaultMotionPlanner,
        "GeometryAwareMotionPlanner": GeometryAwareMotionPlanner,
        "MinirigV1MotionPlanner": MinirigV1MotionPlanner,
    }

    def _changeMotionPlanner(self, idx):
        name = self.ui.motionPlannerSelector.currentText()
        cls = self._MOTION_PLANNERS[name]
        self.module.manager.motionPlanner = cls()

    def quit(self):
        self.close()

    def saveConfig(self):
        geom = self.geometry()
        config = {
            'geometry': [geom.x(), geom.y(), geom.width(), geom.height()],
        }
        getManager().writeConfigFile(config, self._configFileName())

    def loadConfig(self):
        config = getManager().readConfigFile(self._configFileName())
        if 'geometry' in config:
            geom = Qt.QRect(*config['geometry'])
            self.setGeometry(geom)

    def _configFileName(self):
        return os.path.join('modules', f'{self.module.name}.cfg')


class AutomationDebug(Module):
    moduleDisplayName = "Automation Debug"
    moduleCategory = "Utilities"
    _instance = None

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        if AutomationDebug._instance is not None:
            AutomationDebug._instance.ui.raise_()
            AutomationDebug._instance.ui.activateWindow()
            Qt.QTimer.singleShot(0, self.quit)
            return
        AutomationDebug._instance = self
        self.ui = AutomationDebugWindow(self)
        manager.declareInterface(name, ["automationDebugModule"], self)
        this_dir = os.path.dirname(__file__)
        self.ui.setWindowIcon(Qt.QIcon(os.path.join(this_dir, "Manager", "icon.png")))

    def quit(self, fromUi=False):
        if AutomationDebug._instance is self:
            AutomationDebug._instance = None
        if hasattr(self, 'ui'):
            self.ui.saveConfig()
            if not fromUi:
                self.ui.quit()
        super().quit()
