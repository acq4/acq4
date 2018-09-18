from __future__ import print_function
import os, re
import numpy as np
import json
from acq4.util import Qt

from acq4.modules.Module import Module
from acq4 import getManager
from acq4.devices.PatchPipette import PatchPipette
import acq4.pyqtgraph as pg

from .multipatchTemplate import Ui_MultiPatch
from .pipetteTemplate import Ui_PipetteControl


class MultiPatch(Module):
    moduleDisplayName = "MultiPatch"
    moduleCategory = "Acquisition"

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config) 
        
        self.win = MultiPatchWindow(self)
        self.win.show()


class PipetteControl(Qt.QWidget):

    sigMoveStarted = Qt.Signal(object)
    sigMoveFinished = Qt.Signal(object)

    def __init__(self, pipette, parent=None):
        Qt.QWidget.__init__(self, parent)
        self.pip = pipette
        self.moving = False
        self.pip.sigGlobalTransformChanged.connect(self.positionChanged)
        self.pip.sigDataChanged.connect(self.updatePlots)
        if isinstance(pipette, PatchPipette):
            self.pip.sigStateChanged.connect(self.stateChanged)
        self.moveTimer = Qt.QTimer()
        self.moveTimer.timeout.connect(self.positionChangeFinished)

        self.ui = Ui_PipetteControl()
        self.ui.setupUi(self)
        self.ui.stateCombo.activated.connect(self.changeState)

        n = re.sub(r'[^\d]+', '', pipette.name())
        self.ui.selectBtn.setText(n)

        for ch in self.children():
            ch.pipette = pipette
            ch.pipCtrl = self

        self.gv = pg.GraphicsLayoutWidget()
        self.leftPlot = self.gv.addPlot()
        self.rightPlot = self.gv.addPlot()
        self.rightPlot.setXLink(self.leftPlot.getViewBox())
        self.ui.plotLayout.addWidget(self.gv)

    def solo(self):
        return self.ui.soloBtn.isChecked()

    def selected(self):
        return self.ui.selectBtn.isChecked()

    def locked(self):
        return self.ui.lockBtn.isChecked()

    def updatePlots(self):
        """Update the pipette data plots."""
        # TODO: Make the information plotted selectable for future
        #       case where we have more than just Rss and Rpeak
        t = self.pip.TPData["time"]
        rss = self.pip.TPData["Rss"]
        peak = self.pip.TPData["Rpeak"]
        self.leftPlot.plot(t, rss, clear=True)
        self.rightPlot.plot(t, peak, clear=True)

    def stateChanged(self, pipette):
        """Pipette's state changed, reflect that in the UI"""
        state = pipette.getState()
        index = self.ui.stateCombo.findText(state)
        self.ui.stateCombo.setCurrentIndex(index)

    def changeState(self, stateIndex):
        if isinstance(self.pip, PatchPipette):
            state = str(self.ui.stateCombo.itemText(stateIndex))
            self.pip.setState(state)

    def positionChanged(self):
        self.moveTimer.start(500)
        if self.moving is False:
            self.moving = True
            self.sigMoveStarted.emit(self)

    def positionChangeFinished(self):
        self.moveTimer.stop()
        self.moving = False
        self.sigMoveFinished.emit(self)


class MultiPatchWindow(Qt.QWidget):
    def __init__(self, module):
        self.storageFile = None

        self._calibratePips = []
        self._calibrateStagePositions = []
        self._setTargetPips = []

        Qt.QWidget.__init__(self)
        self.module = module

        self.ui = Ui_MultiPatch()
        self.ui.setupUi(self)

        self.setWindowTitle('Multipatch')
        self.setWindowIcon(Qt.QIcon(os.path.join(os.path.dirname(__file__), 'icon.png')))

        man = getManager()
        pipNames = man.listInterfaces('pipette')
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
            pip.sigTargetChanged.connect(self.pipetteTargetChanged)
            if isinstance(pip, PatchPipette):
                pip.sigStateChanged.connect(self.pipetteStateChanged)
            ctrl = PipetteControl(pip)
            ctrl.sigMoveStarted.connect(self.pipetteMoveStarted)
            ctrl.sigMoveFinished.connect(self.pipetteMoveFinished)

            self.ui.matrixLayout.addWidget(ctrl, i, 0)

            ctrl.ui.selectBtn.clicked.connect(self.selectBtnClicked)
            ctrl.ui.soloBtn.clicked.connect(self.soloBtnClicked)
            ctrl.ui.lockBtn.clicked.connect(self.lockBtnClicked)
            ctrl.ui.tipBtn.clicked.connect(self.focusTipBtnClicked)
            ctrl.ui.targetBtn.clicked.connect(self.focusTargetBtnClicked)

            self.pipCtrls.append(ctrl)
            ctrl.leftPlot.setXLink(self.pipCtrls[0].leftPlot.getViewBox())

        self.ui.stepSizeSpin.setOpts(value=10e-6, suffix='m', siPrefix=True, bounds=[5e-6, None], step=5e-6)
        self.ui.calibrateBtn.toggled.connect(self.calibrateToggled)
        self.ui.setTargetBtn.toggled.connect(self.setTargetToggled)

        self.ui.moveInBtn.clicked.connect(self.moveIn)
        self.ui.stepInBtn.clicked.connect(self.stepIn)
        self.ui.stepOutBtn.clicked.connect(self.stepOut)
        self.ui.aboveTargetBtn.clicked.connect(self.moveAboveTarget)
        self.ui.approachBtn.clicked.connect(self.moveApproach)
        self.ui.toTargetBtn.clicked.connect(self.moveToTarget)
        self.ui.homeBtn.clicked.connect(self.moveHome)
        self.ui.idleBtn.clicked.connect(self.moveIdle)
        self.ui.coarseSearchBtn.clicked.connect(self.coarseSearch)
        self.ui.fineSearchBtn.clicked.connect(self.fineSearch)
        self.ui.hideMarkersBtn.toggled.connect(self.hideBtnToggled)
        self.ui.sealBtn.clicked.connect(self.sealClicked)
        self.ui.recordBtn.toggled.connect(self.recordToggled)
        self.ui.resetBtn.clicked.connect(self.resetHistory)
        self.ui.reSealBtn.clicked.connect(self.reSeal)

        self.ui.fastBtn.clicked.connect(lambda: self.ui.slowBtn.setChecked(False))
        self.ui.slowBtn.clicked.connect(lambda: self.ui.fastBtn.setChecked(False))

        xkdevname = module.config.get('xkeysDevice', None)
        if xkdevname is not None:
            self.xkdev = getManager().getDevice(xkdevname)
            self.xkdev.sigStateChanged.connect(self.xkeysStateChanged)
            self.xkdev.dev.setIntensity(255, 255)
        else:
            self.xkdev = None

        self.resetHistory()

        for i, pip in enumerate(self.pips):
            if isinstance(pip, PatchPipette):
                self.pipetteStateChanged(pip)

        if self.microscope:
            d = self.microscope.getSurfaceDepth()
            if d is not None:
                self.surfaceDepthChanged(d)

    def moveIn(self):
        for pip in self.selectedPipettes():
            pip.startAdvancing(10e-6)

    def stepIn(self):
        speed = self.selectedSpeed(default='slow')
        for pip in self.selectedPipettes():
            pip.advanceTowardTarget(self.ui.stepSizeSpin.value(), speed)

    def stepOut(self):
        speed = self.selectedSpeed(default='slow')
        for pip in self.selectedPipettes():
            pip.retract(self.ui.stepSizeSpin.value(), speed)

    def reSeal(self):
        speed = self.module.config.get('reSealSpeed', 1e-6)
        distance = self.module.config.get('reSealDistance', 150e-6)
        for pip in self.selectedPipettes():
            pip.retract(distance, speed)
        
    def moveAboveTarget(self):
        speed = self.selectedSpeed(default='fast')
        pips = self.selectedPipettes()
        if len(pips) == 1:
            pips[0].goAboveTarget(speed=speed)
            return

        fut = []
        wp = []
        for pip in pips:
            w1, w2 = pip.aboveTargetPath()
            wp.append(w2)
            fut.append(pip._moveToGlobal(w1, speed))
        for f in fut:
            f.wait(updates=True)
        for pip, waypoint in zip(pips, wp):
            pip._moveToGlobal(waypoint, 'slow')

        self.calibrateWithStage(pips, wp)

    def moveApproach(self):
        speed = self.selectedSpeed(default='slow')
        for pip in self.selectedPipettes():
            pip.goApproach(speed)
            pip.setState('approach')
            if isinstance(pip, PatchPipette):
                pip.autoPipetteOffset()

    def moveToTarget(self):
        speed = self.selectedSpeed(default='slow')
        for pip in self.selectedPipettes():
            pip.goTarget(speed)

    def moveHome(self):
        speed = self.selectedSpeed(default='fast')
        for pip in self.selectedPipettes():
            pip.goHome(speed)
            if isinstance(pip, PatchPipette):
                pip.setState('out')

    def moveIdle(self):
        speed = self.selectedSpeed(default='fast')
        for pip in self.selectedPipettes():
            pip.goIdle(speed)

    def selectedPipettes(self):
        sel = []
        for ctrl in self.pipCtrls:
            if ctrl.solo():
                # solo mode
                if ctrl.locked():
                    return []
                return [ctrl.pip]
            if ctrl.selected() and not ctrl.locked():
                sel.append(ctrl.pip)
        return sel

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
            pip.goSearch(speed, distance=distance)

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
        pos = self._cammod.window().getView().mapSceneToView(ev.scenePos())
        spos = pip.scopeDevice().globalPosition()
        pos = [pos.x(), pos.y(), spos.z()]
        pip.setGlobalPosition(pos)

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
        pos = self._cammod.window().getView().mapSceneToView(ev.scenePos())
        spos = pip.scopeDevice().globalPosition()
        pos = [pos.x(), pos.y(), spos.z()]
        pip.setTarget(pos)

        if len(self._setTargetPips) == 0:
            self.ui.setTargetBtn.setChecked(False)
            self.updateXKeysBacklight()

    def hideBtnToggled(self, hide):
        for pip in self.pips:
            pip.hideMarkers(hide)

    def soloBtnClicked(self, state):
        pip = self.sender().pipette
        if state is True:
            # uncheck all other solo buttons
            for ctrl in self.pipCtrls:
                if ctrl.pip is pip:
                    continue
                ctrl.ui.soloBtn.setChecked(False)

        self.selectionChanged()

        if state is True and isinstance(pip, PatchPipette):
            pip.setSelected()

    def lockBtnClicked(self, state):
        pip = self.sender().pipette
        # lock manipulator movement, pressure
        self.selectionChanged()

    def focusTipBtnClicked(self, state):
        pip = self.sender().pipette
        speed = self.selectedSpeed(default='slow')
        pip.focusTip(speed)

    def focusTargetBtnClicked(self, state):
        pip = self.sender().pipette
        speed = self.selectedSpeed(default='slow')
        pip.focusTarget(speed)

    def selectBtnClicked(self, b):
        pip = self.sender().pipette
        if isinstance(pip, PatchPipette):
            pip.setActive(b)
        self.selectionChanged()

    def selectionChanged(self):
        pips = self.selectedPipettes()
        solo = len(pips) == 1
        none = len(pips) == 0

        if none:
            self.ui.calibrateBtn.setChecked(False)
            self.ui.setTargetBtn.setChecked(False)

        self.updateXKeysBacklight()

    def updateXKeysBacklight(self):
        if self.xkdev is None:
            return
        sel = self.selectedPipettes()
        # bl = np.zeros(self.xkdev.keyshape + (2,), dtype='ubyte')
        bl = self.xkdev.getBacklights()
        for i, ctrl in enumerate(self.pipCtrls):
            pip = ctrl.pip
            bl[0, i+4, 0] = 1 if ctrl.selected() else 0
            bl[0, i+4, 1] = 2 if ctrl.moving else 0
            bl[1, i+4, 1] = 1 if pip in sel else 0
            bl[1, i+4, 0] = 1 if ctrl.locked() else 0
            bl[2, i+4, 1] = 1 if pip in sel else 0
            bl[2, i+4, 0] = 1 if ctrl.solo() else 0

        bl[1, 2] = 1 if self.ui.hideMarkersBtn.isChecked() else 0
        bl[0, 2] = 1 if self.ui.setTargetBtn.isChecked() else 0
        bl[2, 2] = 1 if self.ui.calibrateBtn.isChecked() else 0
        bl[4, 1] = 1 if self.ui.slowBtn.isChecked() else 0
        bl[4, 2] = 1 if self.ui.fastBtn.isChecked() else 0
        bl[7, 2] = 1 if self.ui.recordBtn.isChecked() else 0
        
        self.xkdev.setBacklights(bl, axis=1)

    def xkeysStateChanged(self, dev, changes):
        for k,v in changes.items():
            if k == 'keys':
                for key, state in v:
                    if state is True:
                        if key[1] > 3:
                            row = key[0]
                            col = key[1] - 4
                            actions = {0:'selectBtn', 1:'lockBtn', 2:'soloBtn', 3:'tipBtn', 4:'targetBtn'}
                            if row in actions:
                                btnName = actions[row]
                                btn = getattr(self.pipCtrls[col].ui, btnName)
                                btn.click()
                        else:
                            self.xkeysAction(key)

    def xkeysAction(self, key):
        actions = {
            (0, 0): self.ui.sealBtn,
            (1, 2): self.ui.hideMarkersBtn,
            (0, 2): self.ui.setTargetBtn,
            (2, 0): self.ui.coarseSearchBtn,
            (2, 1): self.ui.fineSearchBtn,
            (2, 2): self.ui.calibrateBtn,
            (3, 1): self.ui.aboveTargetBtn,
            (3, 2): self.ui.approachBtn,
            (4, 1): self.ui.slowBtn,
            (4, 2): self.ui.fastBtn,
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

    def pipetteMoveStarted(self, pip):
        self.updateXKeysBacklight()
        event = {"device": str(pip.pip.name()),
                 "event": "move_start"}
        self.recordEvent(**event)

    def pipetteMoveFinished(self, pip):
        self.updateXKeysBacklight()
        pos = pip.pip.globalPosition()
        event = {"device": str(pip.pip.name()),
                 "event": "move_stop",
                 "position": (pos[0], pos[1], pos[2])}
        self.recordEvent(**event)

    def pipetteTargetChanged(self, pipette, target):
        event = {"device": str(pipette.name()),
                 "event": "target_changed",
                 "target_position": (target[0], target[1], target[2])}
        self.recordEvent(**event)

    def pipetteStateChanged(self, pipette):
        event = {"device": str(pipette.name()),
                 "event": "state_changed",
                 "state": str(pipette.getState())}
        self.recordEvent(**event)

    def surfaceDepthChanged(self, depth):
        event = {"device": str(self.microscope.name()),
                 "event": "surface_depth_changed",
                 "surface_depth": depth}
        self.recordEvent(**event)

    def recordToggled(self, rec):
        if self.storageFile is not None:
            self.storageFile.close()
            self.storageFile = None
            self.resetHistory()
        if rec is True:
            man = getManager()
            sdir = man.getCurrentDir()
            self.storageFile = open(sdir.createFile('MultiPatch.log', autoIncrement=True).name(), 'ab')
            self.writeRecords(self.eventHistory)

    def recordEvent(self, **kwds):
        kwds["event_time"] = pg.ptime.time()
        self.eventHistory.append(kwds)
        self.writeRecords([kwds])

    def resetHistory(self):
        self.eventHistory = []
        for pc in self.pipCtrls:
            pip = pc.pip

    def writeRecords(self, recs):
        if self.storageFile is None:
            return
        for rec in recs:
            self.storageFile.write(json.dumps(rec) + ",\n")
        self.storageFile.flush()

