import os, re
import numpy as np
from PyQt4 import QtGui, QtCore

from acq4.modules.Module import Module
from acq4 import getManager
from acq4.devices.PatchPipette import PatchPipette
import acq4.pyqtgraph as pg

from .multipatchTemplate import Ui_MultiPatch
from .pipetteTemplate import Ui_PipetteControl


class MultiPatch(Module):
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config) 
        
        self.win = MultiPatchWindow(self)
        self.win.show()


class PipetteControl(QtGui.QWidget):

    sigMoveStarted = QtCore.Signal(object)
    sigMoveFinished = QtCore.Signal(object)

    def __init__(self, pipette, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.pip = pipette
        self.moving = False
        self.pip.sigGlobalTransformChanged.connect(self.positionChanged)
        self.moveTimer = QtCore.QTimer()
        self.moveTimer.timeout.connect(self.positionChangeFinished)

        self.ui = Ui_PipetteControl()
        self.ui.setupUi(self)

        n = re.sub(r'[^\d]+', '', pipette.name())
        self.ui.selectBtn.setText(n)

        for ch in self.children():
            ch.pipette = pipette
            ch.pipCtrl = self

        self.gv = pg.GraphicsLayoutWidget()
        self.tpPlot = self.gv.addPlot()
        self.rPlot = self.gv.addPlot()
        self.ui.plotLayout.addWidget(self.gv)

    def solo(self):
        return self.ui.soloBtn.isChecked()

    def selected(self):
        return self.ui.selectBtn.isChecked()

    def locked(self):
        return self.ui.lockBtn.isChecked()

    def positionChanged(self):
        self.moveTimer.start(500)
        if self.moving is False:
            self.moving = True
            self.sigMoveStarted.emit(self)

    def positionChangeFinished(self):
        self.moveTimer.stop()
        self.moving = False
        self.sigMoveFinished.emit(self)


class MultiPatchWindow(QtGui.QWidget):
    def __init__(self, module):
        self._calibratePips = []
        self._calibrateStagePositions = []
        self._setTargetPips = []

        QtGui.QWidget.__init__(self)
        self.module = module

        self.ui = Ui_MultiPatch()
        self.ui.setupUi(self)

        self.setWindowTitle('Multipatch')
        self.setWindowIcon(QtGui.QIcon(os.path.join(os.path.dirname(__file__), 'icon.png')))

        # self.layout = QtGui.QGridLayout()
        # self.setLayout(self.layout)

        # self.matrix = QtGui.QWidget()
        # self.matrixLayout = QtGui.QGridLayout()
        # self.matrix.setLayout(self.matrixLayout)
        # self.layout.addWidget(self.matrix, 0, 0)

        man = getManager()
        pipNames = man.listInterfaces('pipette')
        self.pips = [man.getDevice(name) for name in pipNames]
        self.pips.sort(key=lambda p: int(re.sub(r'[^\d]+', '', p.name())))

        self.pipCtrls = []
        for i, pip in enumerate(self.pips):
            ctrl = PipetteControl(pip)
            ctrl.sigMoveStarted.connect(self.pipetteMoveStarted)
            ctrl.sigMoveFinished.connect(self.pipetteMoveFinished)

            # nbtn = QtGui.QPushButton(re.sub(r'[^\d]+', '', pip.name()))
            # nbtn.setCheckable(True)
            # lockBtn = QtGui.QPushButton('Lock')
            # lockBtn.setCheckable(True)
            # soloBtn = QtGui.QPushButton('Solo')
            # soloBtn.setCheckable(True)
            # focusTipBtn = QtGui.QPushButton('Tip')
            # focusTargetBtn = QtGui.QPushButton('Target')

            # self.matrixLayout.addWidget(nbtn, 0, i)
            # self.matrixLayout.addWidget(lockBtn, 1, i)
            # self.matrixLayout.addWidget(soloBtn, 2, i)
            # self.matrixLayout.addWidget(focusTipBtn, 3, i)
            # self.matrixLayout.addWidget(focusTargetBtn, 4, i)
            self.ui.matrixLayout.addWidget(ctrl, i, 0)

            ctrl.ui.selectBtn.clicked.connect(self.selectBtnClicked)
            ctrl.ui.soloBtn.clicked.connect(self.soloBtnClicked)
            ctrl.ui.lockBtn.clicked.connect(self.lockBtnClicked)
            ctrl.ui.tipBtn.clicked.connect(self.focusTipBtnClicked)
            ctrl.ui.targetBtn.clicked.connect(self.focusTargetBtnClicked)

            self.pipCtrls.append(ctrl)


        # self.movementWidget = QtGui.QWidget()
        # self.layout.addWidget(self.movementWidget)

        # self.movementLayout = QtGui.QGridLayout()
        # self.movementWidget.setLayout(self.movementLayout)

        # self.stepInBtn = QtGui.QPushButton("Step in")
        # self.stepTargetOutBtn = QtGui.QPushButton("Step to target")
        # self.stepOutBtn = QtGui.QPushButton("Step out")
        # self.moveInBtn = QtGui.QPushButton("Move in")
        # self.moveAboveTargetBtn = QtGui.QPushButton("Above target")
        # self.moveApproachBtn = QtGui.QPushButton("Approach")
        # self.moveToTargetBtn = QtGui.QPushButton("To target")
        # self.moveHomeBtn = QtGui.QPushButton("Home")
        # self.coarseSearchBtn = QtGui.QPushButton("Coarse search")
        # self.fineSearchBtn = QtGui.QPushButton("Fine search")
        # self.moveIdleBtn = QtGui.QPushButton("Idle")
        # self.hideBtn = QtGui.QPushButton('Hide markers')
        # self.hideBtn.setCheckable(True)
        # self.sealBtn = QtGui.QPushButton('Seal')

        # self.movementLayout.addWidget(self.moveInBtn, 0, 0)
        # self.movementLayout.addWidget(self.stepInBtn, 0, 1)
        # self.movementLayout.addWidget(self.stepOutBtn, 0, 2)
        # self.movementLayout.addWidget(self.moveAboveTargetBtn, 0, 3)
        # self.movementLayout.addWidget(self.moveApproachBtn, 0, 4)
        # self.movementLayout.addWidget(self.moveToTargetBtn, 0, 5)
        # self.movementLayout.addWidget(self.moveHomeBtn, 0, 6)
        # self.movementLayout.addWidget(self.coarseSearchBtn, 0, 7)
        # self.movementLayout.addWidget(self.fineSearchBtn, 1, 7)
        # self.movementLayout.addWidget(self.moveIdleBtn, 0, 8)
        # self.movementLayout.addWidget(self.hideBtn, 1, 8)

        # self.stepSizeSpin = pg.SpinBox(value=10e-6, suffix='m', siPrefix=True, limits=[5e-6, None], step=5e-6)
        self.ui.stepSizeSpin.setOpts(value=10e-6, suffix='m', siPrefix=True, limits=[5e-6, None], step=5e-6)
        # self.stepSizeLabel = QtGui.QLabel('Step size')
        # self.fastBtn = QtGui.QPushButton('Fast')
        # self.fastBtn.setCheckable(True)
        # self.slowBtn = QtGui.QPushButton('Slow')
        # self.slowBtn.setCheckable(True)

        # self.movementLayout.addWidget(self.stepSizeLabel, 1, 0)
        # self.movementLayout.addWidget(self.stepSizeSpin, 1, 1)
        # self.movementLayout.addWidget(self.slowBtn, 1, 2)
        # self.movementLayout.addWidget(self.fastBtn, 1, 3)

        # self.calibrateBtn = QtGui.QPushButton('Calibrate')
        # self.calibrateBtn.setCheckable(True)
        self.ui.calibrateBtn.toggled.connect(self.calibrateToggled)
        # self.movementLayout.addWidget(self.calibrateBtn, 1, 4)

        # self.setTargetBtn = QtGui.QPushButton('Set target')
        # self.setTargetBtn.setCheckable(True)
        self.ui.setTargetBtn.toggled.connect(self.setTargetToggled)
        # self.movementLayout.addWidget(self.setTargetBtn, 1, 5)

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

        self.ui.fastBtn.clicked.connect(lambda: self.ui.slowBtn.setChecked(False))
        self.ui.slowBtn.clicked.connect(lambda: self.ui.fastBtn.setChecked(False))

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
            pip.advanceTowardTarget(self.ui.stepSizeSpin.value(), speed)

    def stepOut(self):
        speed = self.selectedSpeed(default='slow')
        for pip in self.selectedPipettes():
            pip.retract(self.ui.stepSizeSpin.value(), speed)

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
        for ctrl in self.pipCtrls:
            if ctrl.solo():
                # solo mode
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
            self.ui.calibrateBtn.setChecked(False)
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
        bl = np.zeros(self.xkdev.keyshape + (2,), dtype='ubyte')
        for i, ctrl in enumerate(self.pipCtrls):
            pip = ctrl.pip
            bl[0, i+4, 0] = 1 if ctrl.selected() else 0
            bl[0, i+4, 1] = 2 if ctrl.moving else 0
            bl[1, i+4, 1] = 1 if pip in sel else 0
            bl[1, i+4, 0] = 1 if ctrl.locked() else 0
            bl[2, i+4, 1] = 1 if pip in sel else 0
            bl[2, i+4, 0] = 1 if ctrl.solo() else 0

        bl[0, 1] = 1 if self.ui.hideMarkersBtn.isChecked() else 0
        bl[0, 2] = 1 if self.ui.setTargetBtn.isChecked() else 0
        bl[2, 2] = 1 if self.ui.calibrateBtn.isChecked() else 0
        bl[4, 0] = 1 if self.ui.slowBtn.isChecked() else 0
        bl[4, 2] = 1 if self.ui.fastBtn.isChecked() else 0
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
            (0, 1): self.ui.hideMarkersBtn,
            (0, 2): self.ui.setTargetBtn,
            (2, 0): self.ui.coarseSearchBtn,
            (2, 1): self.ui.fineSearchBtn,
            (2, 2): self.ui.calibrateBtn,
            (3, 0): self.ui.idleBtn,
            (3, 1): self.ui.aboveTargetBtn,
            (3, 2): self.ui.approachBtn,
            (4, 0): self.ui.slowBtn,
            (4, 2): self.ui.fastBtn,
            (6, 1): self.ui.toTargetBtn,
            (6, 2): self.ui.homeBtn,
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

    def pipetteMoveStarted(self):
        self.updateXKeysBacklight()

    def pipetteMoveFinished(self):
        self.updateXKeysBacklight()

