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

        self.ui.profileCombo.currentIndexChanged.connect(self.profileComboChanged)
        self.ui.editProfileBtn.clicked.connect(self.openProfileEditor)
        # self.ui.stepSizeSpin.setOpts(value=10e-6, suffix='m', siPrefix=True, bounds=[5e-6, None], step=5e-6)
        self.ui.calibrateBtn.toggled.connect(self.calibrateToggled)
        self.ui.setTargetBtn.toggled.connect(self.setTargetToggled)

        # self.ui.moveInBtn.clicked.connect(self.moveIn)
        # self.ui.stepInBtn.clicked.connect(self.stepIn)
        # self.ui.stepOutBtn.clicked.connect(self.stepOut)
        self.ui.aboveTargetBtn.clicked.connect(self.moveAboveTarget)
        self.ui.approachBtn.clicked.connect(self.moveApproach)
        self.ui.toTargetBtn.clicked.connect(self.moveToTarget)
        self.ui.homeBtn.clicked.connect(self.moveHome)
        # self.ui.idleBtn.clicked.connect(self.moveIdle)
        self.ui.coarseSearchBtn.clicked.connect(self.coarseSearch)
        self.ui.fineSearchBtn.clicked.connect(self.fineSearch)
        self.ui.hideMarkersBtn.toggled.connect(self.hideBtnToggled)
        self.ui.cellDetectBtn.clicked.connect(self.cellDetectClicked)
        self.ui.sealBtn.clicked.connect(self.sealClicked)   
        self.ui.collectBtn.clicked.connect(self.collectClicked)
        self.ui.nucleusHomeBtn.clicked.connect(self.nucleusHomeClicked)
        self.ui.breakInBtn.clicked.connect(self.breakInClicked)
        self.ui.reSealBtn.clicked.connect(self.reSealClicked)
        self.ui.cleanBtn.clicked.connect(self.cleanClicked)
        self.ui.recordTestPulsesBtn.toggled.connect(self.recordTestPulsesToggled)
        self.ui.recordBtn.toggled.connect(self.recordToggled)
        self.ui.resetBtn.clicked.connect(self.resetHistory)
        # self.ui.testPulseBtn.clicked.connect(self.testPulseClicked)

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

    def _turnOffSlowBtn(self, checked):
        self.ui.slowBtn.setChecked(False)

    def _turnOffFastBtn(self, checked):
        self.ui.FastBtn.setChecked(False)

    def saveConfig(self):
        geom = self.geometry()
        config = {
            'geometry': [geom.x(), geom.y(), geom.width(), geom.height()],
            'plotModes': self.pipCtrls[0].getPlotModes(),
            "plots": {
                (ctrl.pip.name(), plot.mode): plot.plot.saveState()
                for ctrl in self.pipCtrls for plot in ctrl.plots
            },
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
            self._profileEditor.show()
        else:
            self._profileEditor.setTopLevelWindow()

    def setPlotModes(self, modes):
        for ctrl in self.pipCtrls:
            ctrl.setPlotModes(modes)
        self.saveConfig()

    def moveAboveTarget(self):
        speed = self.selectedSpeed(default='fast')
        for pip in self.selectedPipettes():
            pip.pipetteDevice.goAboveTarget(speed, raiseErrors=True)
            pip.setState('bath')

    def moveApproach(self):
        speed = self.selectedSpeed(default='fast')
        for pip in self.selectedPipettes():
            if isinstance(pip, PatchPipette):
                pip.pipetteDevice.goApproach(speed, raiseErrors=True)
                pip.setState('bath')
                pip.clampDevice.autoPipetteOffset()
            else:
                pip.goApproach(speed, raiseErrors=True)

    def moveToTarget(self):
        speed = self.selectedSpeed(default='fast')
        for pip in self.selectedPipettes():
            if isinstance(pip, PatchPipette):
                pip = pip.pipetteDevice
            pip.goTarget(speed, raiseErrors=True)

    def moveHome(self):
        speed = self.selectedSpeed(default='fast')
        for pip in self.selectedPipettes():
            if isinstance(pip, PatchPipette):
                pip.setState('out')
                pip = pip.pipetteDevice
            pip.goHome(speed, raiseErrors=True)

    # def moveIdle(self):
    #     speed = self.selectedSpeed(default='fast')
    #     for pip in self.selectedPipettes():
    #         if isinstance(pip, PatchPipette):
    #             pip = pip.pipetteDevice
    #         pip.goIdle(speed, raiseErrors=True)

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

    def coarseSearch(self):
        self.moveSearch(self.module.config.get('coarseSearchDistance', 400e-6))

    def fineSearch(self):
        pips = self.selectedPipettes()
        if len(pips) == 1:
            distance = 0
        else:
            distance = self.module.config.get('fineSearchDistance', 50e-6)
        self.moveSearch(distance)

    def moveSearch(self, distance):
        speed = self.selectedSpeed(default='fast')
        pips = self.selectedPipettes()
        for pip in pips:
            if isinstance(pip, PatchPipette):
                pip.setState('bath')
                pip = pip.pipetteDevice
            pip.goSearch(speed, distance=distance, raiseErrors=True)

    def calibrateWithStage(self, pipettes, positions):
        """Begin calibration of selected pipettes and move the stage to a selected position for each pipette.
        """
        self.ui.calibrateBtn.setChecked(False)
        self.ui.calibrateBtn.setChecked(True)
        pipettes[0].scopeDevice().setGlobalPosition(positions.pop(0))
        self._calibratePips = pipettes
        self._calibrateStagePositions = positions

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
        pip.resetGlobalPosition(pos)

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
            bl[0, i+4, 0] = 1 if ctrl.active() else 0
            bl[0, i+4, 1] = 2 if ctrl.pip.pipetteDevice.moving else 0
            bl[1, i+4, 1] = 1 if pip in sel else 0
            bl[1, i+4, 0] = 1 if ctrl.locked() else 0
            bl[2, i+4, 1] = 1 if pip in sel else 0
            bl[2, i+4, 0] = 1 if ctrl.selected() else 0

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

    def sealClicked(self):
        pips = self.selectedPipettes()
        for pip in pips:
            if isinstance(pip, PatchPipette):
                pip.setState('seal')

    def collectClicked(self):
        pips = self.selectedPipettes()
        for pip in pips:
            if isinstance(pip, PatchPipette):
                pip.setState('collect')

    def nucleusHomeClicked(self):
        pips = self.selectedPipettes()
        for pip in pips:
            if isinstance(pip, PatchPipette):
                pip.setState('home with nucleus')

    def breakInClicked(self):
        pips = self.selectedPipettes()
        for pip in pips:
            if isinstance(pip, PatchPipette):
                pip.setState('break in')

    def cellDetectClicked(self):
        pips = self.selectedPipettes()
        for pip in pips:
            if isinstance(pip, PatchPipette):
                pip.setState('cell detect')

    def reSealClicked(self):
        pips = self.selectedPipettes()
        for pip in pips:
            if isinstance(pip, PatchPipette):
                pip.setState('reseal')
        
    def cleanClicked(self):
        pips = self.selectedPipettes()
        for pip in pips:
            if isinstance(pip, PatchPipette):
                pip.setState('clean')
        
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
