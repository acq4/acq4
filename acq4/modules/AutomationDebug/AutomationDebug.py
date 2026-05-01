from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from acq4.devices.Camera import Camera
from acq4.devices.Microscope import Microscope
from acq4.devices.PatchPipette import PatchPipette
from acq4.devices.Pipette import Pipette
from acq4.devices.Pipette.planners import (
    PipettePathGenerator,
    GeometryAwarePathGenerator,
)
from acq4.logging_config import get_logger
from acq4.modules.Module import Module
from acq4.util import Qt
import pyqtgraph as pg
from acq4.util.future import Future, future_wrap
from acq4.util.imaging import Frame
from acq4.util.imaging.sequencer import acquire_z_stack
from acq4.util.target import TargetBox
from acq4.util.threadrun import futureInGuiThread, runInGuiThread
from acq4_automation.cell_quality_annotation_tool import open_annotation_tool_with_detections
from acq4_automation.feature_tracking.cell import Cell
from coorx import Point, AffineTransform, SRT3DTransform
from pyqtgraph.units import µm, m
from .ranking_window import RankingWindow
from pyqtgraph.units import µm
from .autopatch import Autopatcher
from .detection import CellDetector
from .feature_tracking import FeatureTracker
from .mock_data import MockDataHandler
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
        _zstack_depth_layout.addStretch()
        self.ui.groupBox.layout().addLayout(_zstack_depth_layout, 5, 0, 1, 4)

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

        # --- UI wiring ---
        self.ui.clearBtn.clicked.connect(self._detector.clearCells)
        self.ui.showRoisBtn.toggled.connect(self._toggleCellRois)
        self.ui.zStackDetectBtn.setOpts(
            future_producer=self._detector._detectNeuronsZStack, stoppable=True
        )
        self.ui.zStackDetectBtn.sigFinished.connect(self._detector._handleDetectResults)
        self.ui.testUIBtn.setOpts(future_producer=self._detector._testUI, stoppable=True)
        self.ui.testUIBtn.sigFinished.connect(self._detector._handleDetectResults)
        self.ui.addCellFromTargetBtn.setOpts(
            future_producer=self._detector._addCellFromTarget, stoppable=True
        )

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

        self.ui.autoTargetBtn.setOpts(future_producer=self._autoTarget, stoppable=True)
        self.ui.autoTargetBtn.sigFinished.connect(self._handleAutoFinish)

        self._motionPlanners = {}
        for name, dev in self.module.manager.devices.items():
            if isinstance(dev, Pipette):
                self.ui.pipetteSelector.addItem(name)
                self._motionPlanners[(name, dev.pathGeneratorClass)] = dev.pathGenerator
            elif isinstance(dev, Camera):
                self.ui.cameraSelector.addItem(name)

        self.ui.trackFeaturesBtn.setOpts(
            future_producer=self._feature_tracker.doFeatureTracking,
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
            future_producer=self._feature_tracker.doPipetteCalibrationTest,
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
            future_producer=self._autopatcher._autopatchDemo, stoppable=True
        )
        self.ui.autopatchDemoBtn.sigFinished.connect(
            self._autopatcher._handleAutopatchDemoFinish
        )

        self.show()
        planner = self.module.config.get("motionPlanner", "Objective radius only")
        self.ui.motionPlannerSelector.setCurrentText(planner)
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

    @future_wrap
    def _autoTarget(self, _future):
        self.sigWorking.emit(self.ui.autoTargetBtn)
        # If _unranked_cells is populated, use it. Otherwise, run detection.
        if not self._unranked_cells:
            logger.info("Need new potential cells; running detection")
            x, y = self._randomLocation()
            _future.waitFor(
                self.scopeDevice.setGlobalPosition(
                    (x, y), name="random move to find cells"
                )
            )
            # TODO don't know why this hangs when using waitFor, but it does
            depth_fut = self.scopeDevice.findSurfaceDepth(
                self.cameraDevice,
                searchDistance=50 * µm,
                searchStep=15 * µm,  # , block=True, checkStopThrough=_future
            )
            depth = depth_fut.getResult() - 50 * µm  # Target below surface
            _future.checkStop()
            self.cameraDevice.setFocusDepth(depth)  # Set focus depth

            _future.waitFor(
                self._detector._detectNeuronsZStack(), timeout=600
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

    def _handleAutoFinish(self, fut: Future):
        self.sigWorking.emit(False)

    def _randomLocation(self):
        return self.cameraDevice.globalCenterPosition()[:2]
        # TODO get the spinners back
        # x = random.uniform(self._xLeftSpin.value(), self._xRightSpin.value())
        # y = random.uniform(self._yBottomSpin.value(), self._yTopSpin.value())
        # return x, y

    def _changeMotionPlanner(self, idx):
        name = self.ui.motionPlannerSelector.currentText()
        planner = {
            "Geometry-aware": GeometryAwarePathGenerator,
            "Objective radius only": PipettePathGenerator,
        }[name]
        Pipette.pathGeneratorClass = planner
        for name, dev in self.module.manager.devices.items():
            if isinstance(dev, Pipette):
                cache_key = (dev.name(), planner)
                if cache_key not in self._motionPlanners:
                    self._motionPlanners[cache_key] = planner(dev)
                dev.pathGenerator = self._motionPlanners[cache_key]

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

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.ui = AutomationDebugWindow(self)
        manager.declareInterface(name, ["automationDebugModule"], self)
        this_dir = os.path.dirname(__file__)
        self.ui.setWindowIcon(Qt.QIcon(os.path.join(this_dir, "Manager", "icon.png")))

    def quit(self, fromUi=False):
        self.ui.saveConfig()
        if not fromUi:
            self.ui.quit()
        super().quit()
