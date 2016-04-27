import os, re
import numpy as np
from PyQt4 import QtGui, QtCore

from acq4.modules.Module import Module
from acq4 import getManager
from acq4.devices.PatchPipette import PatchPipette
import acq4.pyqtgraph as pg


class MultiPatch(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config) 
        
        self.win = MultiPatchWindow(self)
        self.win.show()


class MultiPatchWindow(QtGui.QWidget):
    def __init__(self, module):
        self._calibratePips = []
        self._calibrateStagePositions = []
        self._setTargetPips = []

        QtGui.QWidget.__init__(self)
        self.setWindowTitle('Multipatch')
        self.setWindowIcon(QtGui.QIcon(os.path.join(os.path.dirname(__file__), 'icon.png')))
        self.module = module

        self.layout = QtGui.QGridLayout()
        self.setLayout(self.layout)

        self.matrix = QtGui.QWidget()
        self.matrixLayout = QtGui.QGridLayout()
        self.matrix.setLayout(self.matrixLayout)
        self.layout.addWidget(self.matrix, 0, 0)

        man = getManager()
        pipNames = man.listInterfaces('pipette')
        self.pips = [man.getDevice(name) for name in pipNames]
        self.columns = []
        self.pips.sort(key=lambda p: int(re.sub(r'[^\d]+', '', p.name())))

        for i, pip in enumerate(self.pips):
            nbtn = QtGui.QPushButton(re.sub(r'[^\d]+', '', pip.name()))
            nbtn.setCheckable(True)
            lockBtn = QtGui.QPushButton('Lock')
            lockBtn.setCheckable(True)
            soloBtn = QtGui.QPushButton('Solo')
            soloBtn.setCheckable(True)
            focusTipBtn = QtGui.QPushButton('Tip')
            focusTargetBtn = QtGui.QPushButton('Target')

            self.matrixLayout.addWidget(nbtn, 0, i)
            self.matrixLayout.addWidget(lockBtn, 1, i)
            self.matrixLayout.addWidget(soloBtn, 2, i)
            self.matrixLayout.addWidget(focusTipBtn, 3, i)
            self.matrixLayout.addWidget(focusTargetBtn, 4, i)

            nbtn.clicked.connect(self.selectBtnClicked)
            soloBtn.clicked.connect(self.soloBtnClicked)
            lockBtn.clicked.connect(self.lockBtnClicked)
            focusTipBtn.clicked.connect(self.focusTipBtnClicked)
            focusTargetBtn.clicked.connect(self.focusTargetBtnClicked)

            btns = {'sel':nbtn, 'lock':lockBtn, 'solo':soloBtn, 'tip':focusTipBtn, 'target':focusTargetBtn}
            self.columns.append(btns)
            for b in btns.values():
                b.pipette = pip
            btns['pipette'] = pip


        self.movementWidget = QtGui.QWidget()
        self.layout.addWidget(self.movementWidget)

        self.movementLayout = QtGui.QGridLayout()
        self.movementWidget.setLayout(self.movementLayout)

        self.stepInBtn = QtGui.QPushButton("Step in")
        self.stepTargetOutBtn = QtGui.QPushButton("Step to target")
        self.stepOutBtn = QtGui.QPushButton("Step out")
        self.moveInBtn = QtGui.QPushButton("Move in")
        self.moveAboveTargetBtn = QtGui.QPushButton("Above target")
        self.moveApproachBtn = QtGui.QPushButton("Approach")
        self.moveToTargetBtn = QtGui.QPushButton("To target")
        self.moveHomeBtn = QtGui.QPushButton("Home")
        self.coarseSearchBtn = QtGui.QPushButton("Coarse search")
        self.fineSearchBtn = QtGui.QPushButton("Fine search")
        self.moveIdleBtn = QtGui.QPushButton("Idle")
        self.hideBtn = QtGui.QPushButton('Hide markers')
        self.hideBtn.setCheckable(True)
        self.sealBtn = QtGui.QPushButton('Seal')

        self.movementLayout.addWidget(self.moveInBtn, 0, 0)
        self.movementLayout.addWidget(self.stepInBtn, 0, 1)
        self.movementLayout.addWidget(self.stepOutBtn, 0, 2)
        self.movementLayout.addWidget(self.moveAboveTargetBtn, 0, 3)
        self.movementLayout.addWidget(self.moveApproachBtn, 0, 4)
        self.movementLayout.addWidget(self.moveToTargetBtn, 0, 5)
        self.movementLayout.addWidget(self.moveHomeBtn, 0, 6)
        self.movementLayout.addWidget(self.coarseSearchBtn, 0, 7)
        self.movementLayout.addWidget(self.fineSearchBtn, 1, 7)
        self.movementLayout.addWidget(self.moveIdleBtn, 0, 8)
        self.movementLayout.addWidget(self.hideBtn, 1, 8)

        self.stepSizeSpin = pg.SpinBox(value=10e-6, suffix='m', siPrefix=True, limits=[5e-6, None], step=5e-6)
        self.stepSizeLabel = QtGui.QLabel('Step size')
        self.fastBtn = QtGui.QPushButton('Fast')
        self.fastBtn.setCheckable(True)
        self.slowBtn = QtGui.QPushButton('Slow')
        self.slowBtn.setCheckable(True)

        self.movementLayout.addWidget(self.stepSizeLabel, 1, 0)
        self.movementLayout.addWidget(self.stepSizeSpin, 1, 1)
        self.movementLayout.addWidget(self.slowBtn, 1, 2)
        self.movementLayout.addWidget(self.fastBtn, 1, 3)

        self.calibrateBtn = QtGui.QPushButton('Calibrate')
        self.calibrateBtn.setCheckable(True)
        self.calibrateBtn.toggled.connect(self.calibrateToggled)
        self.movementLayout.addWidget(self.calibrateBtn, 1, 4)

        self.setTargetBtn = QtGui.QPushButton('Set target')
        self.setTargetBtn.setCheckable(True)
        self.setTargetBtn.toggled.connect(self.setTargetToggled)
        self.movementLayout.addWidget(self.setTargetBtn, 1, 5)

        self.moveInBtn.clicked.connect(self.moveIn)
        self.stepInBtn.clicked.connect(self.stepIn)
        self.stepOutBtn.clicked.connect(self.stepOut)
        self.moveAboveTargetBtn.clicked.connect(self.moveAboveTarget)
        self.moveApproachBtn.clicked.connect(self.moveApproach)
        self.moveToTargetBtn.clicked.connect(self.moveToTarget)
        self.moveHomeBtn.clicked.connect(self.moveHome)
        self.moveIdleBtn.clicked.connect(self.moveIdle)
        self.coarseSearchBtn.clicked.connect(self.coarseSearch)
        self.fineSearchBtn.clicked.connect(self.fineSearch)
        self.hideBtn.toggled.connect(self.hideBtnToggled)
        self.sealBtn.clicked.connect(self.sealClicked)

        self.fastBtn.clicked.connect(lambda: self.slowBtn.setChecked(False))
        self.slowBtn.clicked.connect(lambda: self.fastBtn.setChecked(False))


        xkdevname = module.config.get('xkeysDevice', None)
        if xkdevname is not None:
            self.xkdev = getManager().getDevice(xkdevname)
            self.xkdev.sigStateChanged.connect(self.xkeysStateChanged)
        else:
            self.xkdev = None

    def moveIn(self):
        for pip in self.selectedPipettes():
            pip.startAdvancing(10e-6)

    def stepIn(self):
        speed = self.selectedSpeed(default='slow')
        for pip in self.selectedPipettes():
            pip.advanceTowardTarget(self.stepSizeSpin.value(), speed)

    def stepOut(self):
        speed = self.selectedSpeed(default='slow')
        for pip in self.selectedPipettes():
            pip.retract(self.stepSizeSpin.value(), speed)

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
        for col in self.columns:
            if col['solo'].isChecked():
                # solo mode
                return [col['pipette']]
            if col['sel'].isChecked() and not col['lock'].isChecked():
                sel.append(col['pipette'])
        return sel

    def selectedSpeed(self, default):
        if self.fastBtn.isChecked():
            self.fastBtn.setChecked(False)
            return 'fast'
        if self.slowBtn.isChecked():
            self.slowBtn.setChecked(False)
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
        self.calibrateBtn.setChecked(False)
        self.calibrateBtn.setChecked(True)
        pipettes[0].scopeDevice().setGlobalPosition(positions.pop(0))
        self._calibratePips = pipettes
        self._calibrateStagePositions = positions

    def calibrateToggled(self, b):
        cammod = getManager().getModule('Camera')
        self._cammod = cammod
        pips = self.selectedPipettes()
        if b is True:
            self.setTargetBtn.setChecked(False)
            if len(pips) == 0:
                self.calibrateBtn.setChecked(False)
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
            self.calibrateBtn.setChecked(False)
            if len(pips) == 0:
                self.setTargetBtn.setChecked(False)
                return
            # start calibration of selected pipettes
            cammod.window().getView().scene().sigMouseClicked.connect(self.cameraModuleClicked_setTarget)
            self._setTargetPips = pips
        else:
            # stop calibration
            pg.disconnect(cammod.window().getView().scene().sigMouseClicked, self.cameraModuleClicked_setTarget)
            self._setTargetPips = []

    def cameraModuleClicked_calibrate(self, ev):
        if ev.button() != QtCore.Qt.LeftButton:
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
            self.calibrateBtn.setChecked(False)
            self.updateXKeysBacklight()


    def cameraModuleClicked_setTarget(self, ev):
        if ev.button() != QtCore.Qt.LeftButton:
            return

        # Set next pipette position from mouse click
        pip = self._setTargetPips.pop(0)
        pos = self._cammod.window().getView().mapSceneToView(ev.scenePos())
        spos = pip.scopeDevice().globalPosition()
        pos = [pos.x(), pos.y(), spos.z()]
        pip.setTarget(pos)

        if len(self._setTargetPips) == 0:
            self.setTargetBtn.setChecked(False)
            self.updateXKeysBacklight()

    def hideBtnToggled(self, hide):
        for pip in self.pips:
            pip.hideMarkers(hide)

    def soloBtnClicked(self, state):
        pip = self.sender().pipette
        if state is True:
            # uncheck all other solo buttons
            for btns in self.columns:
                if btns['solo'].pipette is pip:
                    continue
                btns['solo'].setChecked(False)

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
            self.calibrateBtn.setChecked(False)
            self.setTargetBtn.setChecked(False)

        self.updateXKeysBacklight()

    def updateXKeysBacklight(self):
        if self.xkdev is None:
            return
        sel = self.selectedPipettes()
        bl = np.zeros(self.xkdev.keyshape + (2,), dtype='ubyte')
        for i, col in enumerate(self.columns):
            pip = col['pipette']
            bl[0, i+4, 0] = 1 if col['sel'].isChecked() else 0
            bl[1, i+4, 1] = 1 if pip in sel else 0
            bl[1, i+4, 0] = 1 if col['lock'].isChecked() else 0
            bl[2, i+4, 1] = 1 if pip in sel else 0
            bl[2, i+4, 0] = 1 if col['solo'].isChecked() else 0

        bl[0, 1] = 1 if self.hideBtn.isChecked() else 0
        bl[0, 2] = 1 if self.setTargetBtn.isChecked() else 0
        bl[2, 2] = 1 if self.calibrateBtn.isChecked() else 0
        bl[4, 0] = 1 if self.slowBtn.isChecked() else 0
        bl[4, 2] = 1 if self.fastBtn.isChecked() else 0
        self.xkdev.setBacklights(bl, axis=1)

    def xkeysStateChanged(self, dev, changes):
        for k,v in changes.items():
            if k == 'keys':
                for key, state in v:
                    if state is True:
                        if key[1] > 3:
                            row = key[0]
                            col = key[1] - 4
                            actions = {0:'sel', 1:'lock', 2:'solo', 3:'tip'}
                            if row in actions:
                                self.columns[col][actions[row]].click()
                        else:
                            self.xkeysAction(key)

    def xkeysAction(self, key):
        actions = {
            (0, 0): self.sealBtn,
            (0, 1): self.hideBtn,
            (0, 2): self.setTargetBtn,
            (2, 0): self.coarseSearchBtn,
            (2, 1): self.fineSearchBtn,
            (2, 2): self.calibrateBtn,
            (3, 0): self.moveIdleBtn,
            (3, 1): self.moveAboveTargetBtn,
            (3, 2): self.moveApproachBtn,
            (4, 0): self.slowBtn,
            (4, 2): self.fastBtn,
            (6, 2): self.moveHomeBtn,
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



