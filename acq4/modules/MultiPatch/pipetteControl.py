# coding: utf8
import re
import acq4.pyqtgraph as pg
from acq4.util import Qt
from acq4.devices.PatchPipette import PatchPipette

Ui_PipetteControl = Qt.importTemplate('.pipetteTemplate')


class PipetteControl(Qt.QWidget):

    sigMoveStarted = Qt.Signal(object)
    sigMoveFinished = Qt.Signal(object)
    sigSelectChanged = Qt.Signal(object, object)
    sigLockChanged = Qt.Signal(object, object)

    def __init__(self, pipette, parent=None):
        Qt.QWidget.__init__(self, parent)
        self.pip = pipette
        self.moving = False
        self.pip.pipetteDevice.sigGlobalTransformChanged.connect(self.positionChanged)
        if isinstance(pipette, PatchPipette):
            self.pip.sigStateChanged.connect(self.patchStateChanged)
            self.pip.sigActiveChanged.connect(self.pipActiveChanged)
            self.pip.sigTestPulseFinished.connect(self.updatePlots)
        self.moveTimer = Qt.QTimer()
        self.moveTimer.timeout.connect(self.positionChangeFinished)

        self.ui = Ui_PipetteControl()
        self.ui.setupUi(self)

        n = re.sub(r'[^\d]+', '', pipette.name())
        self.ui.activeBtn.setText(n)

        self.ui.activeBtn.clicked.connect(self.activeClicked)
        self.ui.selectBtn.clicked.connect(self.selectClicked)
        self.ui.lockBtn.clicked.connect(self.lockClicked)
        self.ui.tipBtn.clicked.connect(self.focusTipBtnClicked)
        self.ui.targetBtn.clicked.connect(self.focusTargetBtnClicked)

        self.stateMenu = Qt.QMenu()
        for state in pipette.listStates():
            self.stateMenu.addAction(state)
        #self.ui.stateCombo.activated.connect(self.stateComboChanged)

        self._pc1 = MousePressCatch(self.ui.stateText, self.stateTextClicked)
        self._pc2 = MousePressCatch(self.ui.modeText, self.modeTextClicked)
        self.pip.clampDevice.sigStateChanged.connect(self.clampStateChanged)
        self.pip.clampDevice.sigHoldingChanged.connect(self.clampHoldingChanged)

        self.gv = pg.GraphicsLayoutWidget()
        self.leftPlot = self.gv.addPlot()
        self.leftPlot.enableAutoRange(True, True)
        self.rightPlot = self.gv.addPlot()
        self.rightPlot.setLogMode(y=True, x=False)
        self.rightPlot.setYRange(6, 10)
        self.rightPlot.setLabels(left=('Rss', u'Ω'))
        self.ui.plotLayout.addWidget(self.gv)

        self.tpLabel = Qt.QGraphicsTextItem()
        self.tpLabel.setParentItem(self.leftPlot.vb)
        self.tpLabel.setDefaultTextColor(pg.mkColor('w'))

        self.patchStateChanged(pipette)
        self.pipActiveChanged()
        self.clampStateChanged(self.pip.clampDevice.getState())
        self.clampHoldingChanged(self.pip.clampDevice, self.pip.clampDevice.getMode())

    def active(self):
        return self.ui.activeBtn.isChecked()

    def activeClicked(self, b):
        self.pip.setActive(b)

    def pipActiveChanged(self):
        self.ui.activeBtn.setChecked(self.pip.active)

    def selected(self):
        return self.ui.selectBtn.isChecked()

    def selectClicked(self):
        self.sigSelectChanged.emit(self, self.selected())

    def setSelected(self, sel):
        self.ui.selectBtn.setChecked(sel)

    def locked(self):
        return self.ui.lockBtn.isChecked()
    
    def lockClicked(self):
        self.sigLockChanged.emit(self, self.locked())

    def setLocked(self, lock):
        self.ui.lockBtn.setChecked(lock)

    def updatePlots(self):
        """Update the pipette data plots."""
        tp = self.pip.lastTestPulse()
        data = tp.data
        pri = data['Channel': 'primary']
        units = pri._info[-1]['ClampState']['primaryUnits'] 
        self.leftPlot.plot(pri.xvals('Time'), pri.asarray(), clear=True)
        self.leftPlot.setLabels(left=('', units))
        tph = self.pip.testPulseHistory()
        self.rightPlot.plot(tph['time'] - tph['time'][0], tph['steadyStateResistance'], clear=True)

        tpa = tp.analysis()
        self.tpLabel.setPlainText(pg.siFormat(tpa['steadyStateResistance'], suffix=u'Ω'))

    def patchStateChanged(self, pipette):
        """Pipette's state changed, reflect that in the UI"""
        state = pipette.getState()
        self.ui.stateText.setText(state)

    def clampStateChanged(self, state):
        self.ui.modeText.setText(state['mode'])

    def clampHoldingChanged(self, clamp, mode):
        hval = clamp.getHolding(mode)
        if mode.lower() == 'vc':
            self.ui.holdingSpin.setValue(hval*1e3)
            self.ui.holdingSpin.setSingleStep(5)
        else:
            self.ui.holdingSpin.setValue(hval*1e12)
            self.ui.holdingSpin.setSingleStep(50)

    def stateTextClicked(self, sender, event):
        self.stateMenu.popup(sender.mapToGlobal(event.pos()))

    def modeTextClicked(self, sender, event):
        if str(self.ui.modeText.text()).lower() == 'vc':
            self.pip.clampDevice.setMode('ic')
        else:
            self.pip.clampDevice.setMode('vc')

    def positionChanged(self):
        self.moveTimer.start(500)
        if self.moving is False:
            self.moving = True
            self.sigMoveStarted.emit(self)

    def positionChangeFinished(self):
        self.moveTimer.stop()
        self.moving = False
        self.sigMoveFinished.emit(self)

    def focusTipBtnClicked(self, state):
        speed = self.selectedSpeed(default='slow')
        self.focusTip(speed)

    def focusTargetBtnClicked(self, state):
        speed = self.selectedSpeed(default='slow')
        self.focusTarget(speed)


class MousePressCatch(Qt.QObject):
    sigMousePress = Qt.Signal(object, object)  # receiver, event
    def __init__(self, receiver, callback):
        Qt.QObject.__init__(self)
        self.receiver = receiver
        receiver.installEventFilter(self)
        self.sigMousePress.connect(callback)

    def eventFilter(self, obj, event):
        if event.type() == event.MouseButtonPress:
            self.sigMousePress.emit(self.receiver, event)
        return False
