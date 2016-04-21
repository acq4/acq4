import re
import numpy as np
from PyQt4 import QtGui, QtCore

from acq4.modules.Module import Module
from acq4 import getManager
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

        QtGui.QWidget.__init__(self)
        self.setWindowTitle('Multipatch')
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
            soloBtn = QtGui.QPushButton('Solo')
            soloBtn.setCheckable(True)
            lockBtn = QtGui.QPushButton('Lock')
            lockBtn.setCheckable(True)
            focusTipBtn = QtGui.QPushButton('Tip')
            focusTargetBtn = QtGui.QPushButton('Target')

            self.matrixLayout.addWidget(nbtn, 0, i)
            self.matrixLayout.addWidget(soloBtn, 1, i)
            self.matrixLayout.addWidget(lockBtn, 2, i)
            self.matrixLayout.addWidget(focusTipBtn, 3, i)
            self.matrixLayout.addWidget(focusTargetBtn, 4, i)

            btns = [nbtn, soloBtn, lockBtn, focusTipBtn, focusTargetBtn]
            self.columns.append(btns)
            for b in btns:
                b.pipette = pip

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

        self.fastBtn.clicked.connect(lambda: self.slowBtn.setChecked(False))
        self.slowBtn.clicked.connect(lambda: self.fastBtn.setChecked(False))


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

    def moveToTarget(self):
        speed = self.selectedSpeed(default='slow')
        for pip in self.selectedPipettes():
            pip.goTarget(speed)

    def moveHome(self):
        speed = self.selectedSpeed(default='fast')
        for pip in self.selectedPipettes():
            pip.goHome(speed)

    def moveIdle(self):
        speed = self.selectedSpeed(default='fast')
        for pip in self.selectedPipettes():
            pip.goIdle(speed)

    def selectedPipettes(self):
        return [col[0].pipette for col in self.columns if col[0].isChecked()]

    def selectedSpeed(self, default):
        if self.fastBtn.isChecked():
            self.fastBtn.setChecked(False)
            return 'fast'
        if self.slowBtn.isChecked():
            self.slowBtn.setChecked(False)
            return 'slow'
        return default

    def coarseSearch(self):
        self.moveSearch(-self.module.config.get('coarseSearchDistance', 400e-6))

    def fineSearch(self):
        self.moveSearch(-self.module.config.get('fineSearchDistance', 50e-6))

    def moveSearch(self, distance):
        speed = self.selectedSpeed(default='fast')
        pips = self.selectedPipettes()
        if len(pips) == 1:
            pips[0].goSearch(speed)
        else:
            for pip in pips:
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
            if len(pips) == 0:
                self.calibrateBtn.setChecked(False)
                return
            # start calibration of selected pipettes
            cammod.window().getView().scene().sigMouseClicked.connect(self.cameraModuleClicked)
            self._calibratePips = pips
        else:
            # stop calibration
            pg.disconnect(cammod.window().getView().scene().sigMouseClicked, self.cameraModuleClicked)
            self._calibratePips = []
            self._calibrateStagePositions = []

    def cameraModuleClicked(self, ev):
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

    def hideBtnToggled(self, hide):
        for pip in self.pips:
            pip.hideMarkers(hide)
