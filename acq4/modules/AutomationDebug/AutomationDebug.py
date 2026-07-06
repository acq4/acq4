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


class AutomationDebugWindow(Qt.QWidget):
    sigWorking = Qt.Signal(
        object
    )  # a btn that is busy or False to signify no longer working
    sigLogMessage = Qt.Signal(str)

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
