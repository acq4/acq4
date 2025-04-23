import json
import os
import re
from collections import OrderedDict
from typing import List

import h5py

import pyqtgraph as pg
from acq4 import getManager
from acq4.devices.PatchPipette import PatchPipette
from acq4.modules.Module import Module
from acq4.util import Qt, ptime
from neuroanalysis.test_pulse_stack import H5BackedTestPulseStack
from .mockPatch import MockPatch
from .pipetteControl import PipetteControl
from ...devices.PatchPipette.statemanager import PatchPipetteStateManager
from ...util.future import MultiFuture, future_wrap
from ...util.json_encoder import ACQ4JSONEncoder

Ui_MultiPatch = Qt.importTemplate('.multipatchTemplate')


class MultiPatch(Module):
    """
    Config
    ----------

    enableMockPatch : bool
        Whether or not to allow mock patching.

    """
    moduleDisplayName = "MultiPatch"
    moduleCategory = "Acquisition"

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)

        self.win = MultiPatchWindow(self)
        self.win.show()

    def quit(self):
        self.win.saveConfig()
        return Module.quit(self)


class MultiPatchWindow(Qt.QWidget):
    def __init__(self, module):
        self._eventStorageFile = None
        self._testPulseStacks = {}

        self._calibratePips = []
        self._calibrateStagePositions = []
        self._setTargetPips = []
        self._profileEditor = None

        Qt.QWidget.__init__(self)
        self.module = module

        self.ui = Ui_MultiPatch()
        self.ui.setupUi(self)

        self.setWindowTitle('Multipatch')
        self.setWindowIcon(Qt.QIcon(os.path.join(os.path.dirname(__file__), 'icon.png')))

        man = getManager()
        pipNames = man.listInterfaces('patchpipette')
        self.pips = [man.getDevice(name) for name in pipNames]
        self.pips.sort(key=lambda p: int(re.sub(r'[^\d]+', '', p.name())))

        microscopeNames = man.listInterfaces('microscope')
        if len(microscopeNames) == 1:
            self.microscope = man.getDevice(microscopeNames[0])
            self.microscope.sigSurfaceDepthChanged.connect(self.surfaceDepthChanged)
        elif len(microscopeNames) == 0:
            # flying blind?
            self.microscope = None
        else:
            raise AssertionError("Currently only 1 microscope is supported")

        self.pipCtrls = []
        for i, pip in enumerate(self.pips):
            pip.sigMoveStarted.connect(self.pipetteMoveStarted)
            pip.sigMoveFinished.connect(self.pipetteMoveFinished)
            if isinstance(pip, PatchPipette):
                pip.sigNewEvent.connect(self.pipetteEvent)
                if pip.clampDevice is not None:
                    pip.clampDevice.sigTestPulseEnabled.connect(self.pipetteTestPulseEnabled)
            ctrl = PipetteControl(pip, self)
            if i > 0:
                ctrl.hideHeader()

            # insert mock patching ui if requested
            self.ui.matrixLayout.addWidget(ctrl, i, 0)
            if module.config.get('enableMockPatch', False):
                pip.mockpatch = MockPatch(pip)
                self.ui.matrixLayout.addWidget(pip.mockpatch.widget, i, 1)

            pip.sigActiveChanged.connect(self.pipetteActiveChanged)
            ctrl.sigSelectChanged.connect(self.pipetteSelectChanged)
            ctrl.sigLockChanged.connect(self.pipetteLockChanged)
            ctrl.sigPlotModesChanged.connect(self.setPlotModes)

            self.pipCtrls.append(ctrl)

        # load profile configurations from old location
        for name, profile in module.config.get('patchProfiles', {}).items():
            PatchPipetteStateManager.addProfile(name, profile, overwrite=True)

        # set up patch profile menu
        profiles = PatchPipetteStateManager.listProfiles()
        if 'default' not in profiles:
            profiles.insert(0, 'default')
        for profile in profiles:
            self.ui.profileCombo.addItem(profile)

        common_opts = dict(stoppable=True, failure="FAILED!", showStatus=False)

        self.ui.homeBtn.setOpts(future_producer=self._moveHome, **common_opts)
        self.ui.nucleusHomeBtn.setOpts(future_producer=self._nucleusHome, raiseOnError=False, **common_opts)
        self.ui.coarseSearchBtn.setOpts(future_producer=self._coarseSearch, **common_opts)
        self.ui.fineSearchBtn.setOpts(future_producer=self._fineSearch, **common_opts)
        self.ui.aboveTargetBtn.setOpts(future_producer=self._aboveTarget, **common_opts)
        self.ui.autoCalibrateBtn.setOpts(future_producer=self._autoCalibrate, **common_opts)
        self.ui.cellDetectBtn.setOpts(future_producer=self._cellDetect, raiseOnError=False, **common_opts)
        self.ui.breakInBtn.setOpts(future_producer=self._breakIn, raiseOnError=False, **common_opts)
        self.ui.toTargetBtn.setOpts(future_producer=self._toTarget, **common_opts)
        self.ui.sealBtn.setOpts(future_producer=self._seal, raiseOnError=False, **common_opts)
        self.ui.reSealBtn.setOpts(future_producer=self._reSeal, raiseOnError=False, **common_opts)
        self.ui.approachBtn.setOpts(future_producer=self._approach, **common_opts)
        self.ui.cleanBtn.setOpts(future_producer=self._clean, raiseOnError=False, **common_opts)
        self.ui.collectBtn.setOpts(future_producer=self._collect, raiseOnError=False, **common_opts)

        self.ui.profileCombo.currentIndexChanged.connect(self.profileComboChanged)
        self.ui.editProfileBtn.clicked.connect(self.openProfileEditor)
        self.ui.calibrateBtn.toggled.connect(self.calibrateToggled)
        self.ui.setTargetBtn.toggled.connect(self.setTargetToggled)

        self.ui.hideMarkersBtn.toggled.connect(self.hideBtnToggled)
        self.ui.recordTestPulsesBtn.toggled.connect(self.recordTestPulsesToggled)
        self.ui.recordBtn.toggled.connect(self.recordToggled)
        self.ui.resetBtn.clicked.connect(self.resetHistory)

        self.ui.fastBtn.clicked.connect(self._turnOffSlowBtn)
        self.ui.slowBtn.clicked.connect(self._turnOffFastBtn)

        xkdevname = module.config.get('xkeysDevice', None)
        if xkdevname is not None:
            self.xkdev = getManager().getDevice(xkdevname)
            self.xkdev.sigStateChanged.connect(self.xkeysStateChanged)
            self.xkdev.setIntensity(255, 255)
        else:
            self.xkdev = None

        self.eventHistory = []
        self.resetHistory()

        if self.microscope:
            d = self.microscope.getSurfaceDepth()
            if d is not None:
                self.surfaceDepthChanged(d)

        self.loadConfig()

    @property
    def _shouldSaveCalibrationImages(self):
        return self.ui.saveCalibrationsBtn.isChecked()

    @_shouldSaveCalibrationImages.setter
    def _shouldSaveCalibrationImages(self, value):
        self.ui.saveCalibrationsBtn.setChecked(True)

    def _turnOffSlowBtn(self, checked):
        self.ui.slowBtn.setChecked(False)

    def _turnOffFastBtn(self, checked):
        self.ui.fastBtn.setChecked(False)

    def saveConfig(self):
        geom = self.geometry()
        config = {
            'geometry': [geom.x(), geom.y(), geom.width(), geom.height()],
            'plotModes': self.pipCtrls[0].getPlotModes(),
            "plots": {
                (ctrl.pip.name(), plot.mode): plot.plot.saveState()
                for ctrl in self.pipCtrls for plot in ctrl.plots
            },
            "should save calibration images": self._shouldSaveCalibrationImages,
        }
        getManager().writeConfigFile(config, self._configFileName())

    def loadConfig(self):
        config = getManager().readConfigFile(self._configFileName())
        if 'geometry' in config:
            geom = Qt.QRect(*config['geometry'])
            self.setGeometry(geom)
        if 'plotModes' in config:
            self.setPlotModes(config['plotModes'])
        if "plots" in config:
            for pipette, plotname in config["plots"]:
                ctrl = next((ctrl for ctrl in self.pipCtrls if ctrl.pip.name() == pipette), None)
                if ctrl is not None:
                    plot = next((plot for plot in ctrl.plots if plot.mode == plotname), None)
                    if plot is not None:
                        plot.plot.restoreState(config["plots"][(pipette, plotname)])
        self._shouldSaveCalibrationImages = config.get("should save calibration images", True)

    def _configFileName(self):
        return os.path.join('modules', f'{self.module.name}.cfg')

    def profileComboChanged(self):
        profile = self.ui.profileCombo.currentText()
        for pip in self.pips:
            pip.stateManager().setProfile(profile)

    def openProfileEditor(self):
        if self._profileEditor is None or not self._profileEditor.isVisible():
            from .patchProfileEditor import ProfileEditor
            self._profileEditor = ProfileEditor()
            self._profileEditor.sigProfileChanged.connect(self.patchProfilesChanged)
            self._profileEditor.show()
        else:
            self._profileEditor.setTopLevelWindow()

    def patchProfilesChanged(self, profiles):
        self.recordEvent({
            "event_time": ptime.time(),
            "device": None,
            "event": "global patch profiles changed",
            "profile": json.dumps(profiles, cls=ACQ4JSONEncoder),
        })

    def setPlotModes(self, modes):
        for ctrl in self.pipCtrls:
            ctrl.setPlotModes(modes)
        self.saveConfig()

    def _setAllSelectedPipettesToState(self, state):
        return MultiFuture([
            pip.setState(state)
            for pip in self.selectedPipettes()
            if isinstance(pip, PatchPipette)
        ])

    def _moveHome(self):
        futures = []
        for pip in self.selectedPipettes():
            speed = self.selectedSpeed(default='fast')
            if isinstance(pip, PatchPipette):
                pip.setState('out')
                pip = pip.pipetteDevice
            futures.append(pip.goHome(speed))
        return MultiFuture(futures)

    def _nucleusHome(self):
        return self._setAllSelectedPipettesToState('home with nucleus')

    def _coarseSearch(self):
        return self.moveSearch(self.module.config.get('coarseSearchDistance', 400e-6))

    def _fineSearch(self):
        if len(self.selectedPipettes()) == 1:
            distance = 0
        else:
            distance = self.module.config.get('fineSearchDistance', 50e-6)
        return self.moveSearch(distance)

    def _aboveTarget(self):
        futures = []
        speed = self.selectedSpeed(default='fast')
        for pip in self.selectedPipettes():
            pip.setState('bath')
            futures.append(pip.pipetteDevice.goAboveTarget(speed))
        return MultiFuture(futures)

    @future_wrap
    def _autoCalibrate(self, _future):
        work_to_do = self.selectedPipettes()
        while work_to_do:
            patchpip = work_to_do.pop(0)
            pip = patchpip.pipetteDevice if isinstance(patchpip, PatchPipette) else patchpip
            pos = pip.tracker.findTipInFrame()
            success = _future.waitFor(pip.setTipOffsetIfAcceptable(pos), timeout=None).getResult()
            if not success:
                work_to_do.insert(0, patchpip)
                continue

            _future.checkStop()

    def _cellDetect(self):
        return self._setAllSelectedPipettesToState('cell detect')

    def _breakIn(self):
        return self._setAllSelectedPipettesToState('break in')

    def _toTarget(self):
        speed = self.selectedSpeed(default='fast')
        return MultiFuture([
            (
                pip.pipetteDevice if isinstance(pip, PatchPipette) else pip
            ).goTarget(speed)
            for pip in self.selectedPipettes()
        ])

    def _seal(self):
        return self._setAllSelectedPipettesToState('seal')

    def _reSeal(self):
        return self._setAllSelectedPipettesToState('reseal')

    def _approach(self):
        speed = self.selectedSpeed(default='fast')
        futures = []
        for pip in self.selectedPipettes():
            if isinstance(pip, PatchPipette):
                pip.setState('bath')
                futures.append(pip.pipetteDevice.goApproach(speed))
                if pip.clampDevice is not None:
                    pip.clampDevice.autoPipetteOffset()
            else:
                futures.append(pip.goApproach(speed))
        return MultiFuture(futures)

    def _clean(self):
        return self._setAllSelectedPipettesToState('clean')

    def _collect(self):
        return self._setAllSelectedPipettesToState('collect')

    def _setTarget(self):
        pass

    def _handle_setTarget_finish(self, results):
        pass

    def _calibrate(self):
        pass

    def _handle_calibrate_finish(self, results):
        pass

    def selectedSpeed(self, default):
        if self.ui.fastBtn.isChecked():
            self.ui.fastBtn.setChecked(False)
            self.updateXKeysBacklight()
            return 'fast'
        if self.ui.slowBtn.isChecked():
            self.ui.slowBtn.setChecked(False)
            self.updateXKeysBacklight()
            return 'slow'
        return default

    def moveSearch(self, distance):
        speed = self.selectedSpeed(default='fast')
        futures = []
        for pip in self.selectedPipettes():
            if isinstance(pip, PatchPipette):
                pip.setState('bath')
                pip = pip.pipetteDevice
            futures.append(pip.goSearch(speed, distance=distance))
        return MultiFuture(futures)

    # def calibrateWithStage(self, pipettes, positions):
    #     """Begin calibration of selected pipettes and move the stage to a selected position for each pipette.
    #     """
    #     self.ui.calibrateBtn.setChecked(False)
    #     self.ui.calibrateBtn.setChecked(True)
    #     pipettes[0].scopeDevice().setGlobalPosition(positions.pop(0))
    #     self._calibratePips = pipettes
    #     self._calibrateStagePositions = positions

    def calibrateToggled(self, b):
        cammod = getManager().getModule('Camera')
        self._cammod = cammod
        pips = self.selectedPipettes()
        if b is True:
            self.ui.setTargetBtn.setChecked(False)
            if len(pips) == 0:
                self.ui.calibrateBtn.setChecked(False)
                return
            # start calibration of selected pipettes
            cammod.window().getView().scene().sigMouseClicked.connect(self.cameraModuleClicked_calibrate)
            self._calibratePips = pips
        else:
            # stop calibration
            pg.disconnect(cammod.window().getView().scene().sigMouseClicked, self.cameraModuleClicked_calibrate)
            self._calibratePips = []
            self._calibrateStagePositions = []

    def setTargetToggled(self, b):
        cammod = getManager().getModule('Camera')
        self._cammod = cammod
        pips = self.selectedPipettes()
        if b is True:
            self.ui.calibrateBtn.setChecked(False)
            if len(pips) == 0:
                self.ui.setTargetBtn.setChecked(False)
                return
            # start calibration of selected pipettes
            cammod.window().getView().scene().sigMouseClicked.connect(self.cameraModuleClicked_setTarget)
            self._setTargetPips = pips
        else:
            # stop calibration
            pg.disconnect(cammod.window().getView().scene().sigMouseClicked, self.cameraModuleClicked_setTarget)
            self._setTargetPips = []

    def cameraModuleClicked_calibrate(self, ev):
        if ev.button() != Qt.Qt.LeftButton:
            return

        # Set next pipette position from mouse click
        pip = self._calibratePips.pop(0)
        if isinstance(pip, PatchPipette):
            pip = pip.pipetteDevice
        pos = self._cammod.window().getView().mapSceneToView(ev.scenePos())
        spos = pip.scopeDevice().globalPosition()
        pos = [pos.x(), pos.y(), spos.z()]
        tip_future = pip.setTipOffsetIfAcceptable(pos)
        tip_future.onFinish(self._handleManualSetTip, pip)

    def _handleManualSetTip(self, future, pip):
        success = future.getResult()
        if not success:
            self._calibratePips.insert(0, pip)
            return

        if self._shouldSaveCalibrationImages:
            pip.saveManualCalibration().raiseErrors("Failed to save calibration images")

        # if calibration stage positions were requested, then move the stage now
        if len(self._calibrateStagePositions) > 0:
            stagepos = self._calibrateStagePositions.pop(0)
            pip.scopeDevice().setGlobalPosition(stagepos, speed='slow')

        if len(self._calibratePips) == 0:
            self.ui.calibrateBtn.setChecked(False)
            self.updateXKeysBacklight()

    def cameraModuleClicked_setTarget(self, ev):
        if ev.button() != Qt.Qt.LeftButton:
            return

        # Set next pipette position from mouse click
        pip = self._setTargetPips.pop(0)
        if isinstance(pip, PatchPipette):
            pip = pip.pipetteDevice
        pos = self._cammod.window().getView().mapSceneToView(ev.scenePos())
        spos = pip.scopeDevice().globalPosition()
        pos = [pos.x(), pos.y(), spos.z()]
        pip.setTarget(pos)

        if len(self._setTargetPips) == 0:
            self.ui.setTargetBtn.setChecked(False)
            self.updateXKeysBacklight()

    def hideBtnToggled(self, hide):
        for pip in self.pips:
            if isinstance(pip, PatchPipette):
                pip = pip.pipetteDevice
            pip.hideMarkers(hide)

    def pipetteTestPulseEnabled(self, clamp, enabled):
        self.updateSelectedPipControls()

    # def testPulseClicked(self):
    #     for pip in self.selectedPipettes():
    #         pip.clampDevice.enableTestPulse(self.ui.testPulseBtn.isChecked())

    def pipetteActiveChanged(self, active):
        self.selectionChanged()

    def pipetteSelectChanged(self, pipctrl, sel):
        if sel:
            # unselect all other pipettes
            for ctrl in self.pipCtrls:
                if ctrl is pipctrl:
                    continue
                ctrl.setSelected(False)

        self.selectionChanged()

    def pipetteLockChanged(self, state):
        self.selectionChanged()

    def selectionChanged(self):
        pips = self.selectedPipettes()
        solo = len(pips) == 1
        none = len(pips) == 0

        if none:
            self.ui.calibrateBtn.setChecked(False)
            self.ui.setTargetBtn.setChecked(False)
            self.ui.selectedGroupBox.setTitle("Selected:")
            self.ui.selectedGroupBox.setEnabled(False)
        else:
            if solo:
                self.ui.selectedGroupBox.setTitle(f"Selected: {pips[0].name()}")
            elif len(pips) > 1:
                self.ui.selectedGroupBox.setTitle("Selected: multiple")
            self.ui.selectedGroupBox.setEnabled(True)
            self.updateSelectedPipControls()

        self.updateXKeysBacklight()

    def updateSelectedPipControls(self):
        pips = self.selectedPipettes()
        # tp = any([pip.testPulseEnabled() for pip in pips])
        # self.ui.testPulseBtn.setChecked(tp)

    def selectedPipettes(self) -> List[PatchPipette]:
        sel = []
        for ctrl in self.pipCtrls:
            if ctrl.selected():
                # solo mode
                if ctrl.locked():
                    return []
                return [ctrl.pip]
            if ctrl.active() and not ctrl.locked():
                sel.append(ctrl.pip)
        return sel

    def updateXKeysBacklight(self):
        if self.xkdev is None:
            return
        sel = self.selectedPipettes()
        # bl = np.zeros(self.xkdev.keyshape + (2,), dtype='ubyte')
        bl = self.xkdev.getBacklights()
        for i, ctrl in enumerate(self.pipCtrls):
            pip = ctrl.pip
            bl[0, i + 4, 0] = 1 if ctrl.active() else 0
            bl[0, i + 4, 1] = 2 if ctrl.pip.pipetteDevice.moving else 0
            bl[1, i + 4, 1] = 1 if pip in sel else 0
            bl[1, i + 4, 0] = 1 if ctrl.locked() else 0
            bl[2, i + 4, 1] = 1 if pip in sel else 0
            bl[2, i + 4, 0] = 1 if ctrl.selected() else 0

        bl[1, 2] = 1 if self.ui.hideMarkersBtn.isChecked() else 0
        bl[0, 2] = 1 if self.ui.setTargetBtn.isChecked() else 0
        bl[2, 2] = 1 if self.ui.calibrateBtn.isChecked() else 0
        bl[4, 1] = 1 if self.ui.slowBtn.isChecked() else 0
        bl[4, 2] = 1 if self.ui.fastBtn.isChecked() else 0
        bl[7, 2] = 1 if self.ui.recordBtn.isChecked() else 0

        self.xkdev.setBacklights(bl, axis=1)

    def xkeysStateChanged(self, dev, changes):
        actions = {0: 'activeBtn', 1: 'lockBtn', 2: 'selectBtn', 3: 'tipBtn', 4: 'targetBtn'}
        for k, v in changes.items():
            if k == 'keys':
                for key, state in v:
                    if state:
                        if key[1] > 3:
                            col = key[1] - 4
                            if col >= len(self.pips):
                                continue
                            row = key[0]
                            if row in actions:
                                btnName = actions[row]
                                btn = getattr(self.pipCtrls[col].ui, btnName)
                                btn.click()
                        else:
                            self.xkeysAction(key)

    def xkeysAction(self, key):
        actions = {
            (0, 0): self.ui.sealBtn,
            (1, 0): self.ui.cellDetectBtn,
            (1, 2): self.ui.hideMarkersBtn,
            (0, 2): self.ui.setTargetBtn,
            (2, 0): self.ui.coarseSearchBtn,
            (2, 1): self.ui.fineSearchBtn,
            (2, 2): self.ui.calibrateBtn,
            (3, 1): self.ui.aboveTargetBtn,
            (3, 2): self.ui.approachBtn,
            (4, 1): self.ui.slowBtn,
            (4, 2): self.ui.fastBtn,
            (5, 2): self.ui.cleanBtn,
            (6, 2): self.ui.homeBtn,
            (5, 0): self.ui.reSealBtn,
            (7, 2): self.ui.recordBtn,
        }
        action = actions.get(key, None)
        if action is None:
            return
        action.click()
        self.updateXKeysBacklight()

    def pipetteMoveStarted(self, pip):
        self.updateXKeysBacklight()

    def pipetteMoveFinished(self, pip):
        self.updateXKeysBacklight()

    def pipetteEvent(self, pip, ev):
        self.recordEvent(ev)

    def surfaceDepthChanged(self, depth):
        event = OrderedDict([
            ("device", str(self.microscope.name())),
            ("event_time", ptime.time()),
            ("event", "surface_depth_changed"),
            ("surface_depth", depth),
        ])
        self.recordEvent(event)

    def recordToggled(self, rec):
        if self._eventStorageFile is not None:
            self._eventStorageFile.close()
            self._eventStorageFile = None
            self.resetHistory()
        if rec is True:
            man = getManager()
            sdir = man.getCurrentDir()
            self._eventStorageFile = open(sdir.createFile('MultiPatch.log', autoIncrement=True).name(), 'ab')
            self.writeRecords(self.eventHistory)
            profile_data = PatchPipetteStateManager.buildPatchProfilesParameters().getValues()
            self.patchProfilesChanged(profile_data)

    def recordTestPulsesToggled(self, rec):
        files = set()
        for stack in self._testPulseStacks.values():
            files.update(stack.files)
        self._testPulseStacks = {}
        for f in files:
            f.close()
        if rec is True:
            man = getManager()
            sdir = man.getCurrentDir()
            name = sdir.createFile('TestPulses.hdf5', autoIncrement=True).name()
            container = h5py.File(name, 'a')
            group = container.create_group('test_pulses')
            for dev in self.pips:
                dev_gr = group.create_group(dev.name())
                dev_gr.attrs['device'] = dev.name()
                self._testPulseStacks[dev.name()] = H5BackedTestPulseStack(dev_gr)
        for pip in self.selectedPipettes():
            pip.emitFullTestPulseData(rec)

    def recordEvent(self, event):
        if not self.eventHistory:
            self.resetHistory()
        self.writeRecords([event])
        event = {k: v for k, v in event.items() if k != 'full_test_pulse'}
        self.eventHistory.append(event)

    def resetHistory(self):
        self.eventHistory = []
        for pip in self.selectedPipettes():
            if pip.clampDevice is not None:
                pip.clampDevice.resetTestPulseHistory()

    def writeRecords(self, recs):
        for rec in recs:
            if 'full_test_pulse' in rec:
                if self._testPulseStacks.get(rec['device'], None) is not None:
                    filename, path = self._testPulseStacks[rec['device']].append(rec['full_test_pulse'])
                    if self._eventStorageFile:
                        filename = os.path.relpath(filename, os.path.dirname(self._eventStorageFile.name))
                    rec = {k: v for k, v in rec.items() if k != 'full_test_pulse'}
                    rec['full_test_pulse'] = f"{filename}:{path}"
                else:
                    rec = {k: v for k, v in rec.items() if k != 'full_test_pulse'}
            if self._eventStorageFile:
                self._eventStorageFile.write(json.dumps(rec, cls=ACQ4JSONEncoder).encode("utf8") + b",\n")
        if self._eventStorageFile:
            self._eventStorageFile.flush()
        for stack in self._testPulseStacks.values():
            stack.flush()
