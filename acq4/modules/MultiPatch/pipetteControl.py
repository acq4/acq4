# coding: utf8
import re
import acq4.pyqtgraph as pg
from acq4.util import Qt
from acq4.devices.PatchPipette import PatchPipette

Ui_PipetteControl = Qt.importTemplate('.pipetteTemplate')


class PipetteControl(Qt.QWidget):

    sigSelectChanged = Qt.Signal(object, object)
    sigLockChanged = Qt.Signal(object, object)

    def __init__(self, pipette, parent=None):
        Qt.QWidget.__init__(self, parent)
        self.pip = pipette
        if isinstance(pipette, PatchPipette):
            self.pip.sigStateChanged.connect(self.patchStateChanged)
            self.pip.sigActiveChanged.connect(self.pipActiveChanged)
            self.pip.sigTestPulseFinished.connect(self.updatePlots)
            self.pip.sigAutoBiasChanged.connect(self.autoBiasChanged)
            self.pip.sigPressureChanged.connect(self.pressureChanged)

        self.ui = Ui_PipetteControl()
        self.ui.setupUi(self)
        self.ui.holdingSpin.setOpts(bounds=[None, None], decimals=0, suffix='V', siPrefix=True, step=5e-3, format='{scaledValue:.3g} {siPrefix:s}{suffix:s}')
        self.ui.pressureSpin.setOpts(bounds=[None, None], decimals=0, suffix='Pa', siPrefix=True, step=1e3, format='{scaledValue:.3g} {siPrefix:s}{suffix:s}')

        self.displayWidgets = [
            self.ui.stateText,
            self.ui.modeText,
            self.ui.holdingSpin,
            self.ui.pressureSpin,
        ]
        for w in self.displayWidgets:
            w.setFixedHeight(20)

        n = re.sub(r'[^\d]+', '', pipette.name())
        self.ui.activeBtn.setText(n)

        self.ui.activeBtn.clicked.connect(self.activeClicked)
        self.ui.selectBtn.clicked.connect(self.selectClicked)
        self.ui.lockBtn.clicked.connect(self.lockClicked)
        self.ui.tipBtn.clicked.connect(self.focusTipBtnClicked)
        self.ui.targetBtn.clicked.connect(self.focusTargetBtnClicked)
        self.ui.autoBiasBtn.clicked.connect(self.autoBiasClicked)
        self.ui.regulatorPressureBtn.clicked.connect(self.regulatorPressureClicked)
        self.ui.userPressureBtn.clicked.connect(self.userPressureClicked)
        self.ui.atmospherePressureBtn.clicked.connect(self.atmospherePressureClicked)
        self.ui.pressureSpin.valueChanged.connect(self.pressureSpinChanged)
        self.ui.holdingSpin.valueChanged.connect(self.holdingSpinChanged)

        self.stateMenu = Qt.QMenu()
        for state in pipette.listStates():
            act = self.stateMenu.addAction(state, self.stateActionClicked)

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
        self.updateHoldingInfo(mode=state['mode'])

    def clampHoldingChanged(self, clamp, mode):
        self.updateHoldingInfo()

    def autoBiasChanged(self, pip, enabled, target):
        self.updateHoldingInfo()

    def holdingSpinChanged(self):
        val = self.ui.holdingSpin.value()
        mode = self.pip.clampDevice.getMode()
        if mode == 'VC' or (mode == 'IC' and self.pip.autoBiasEnabled()):
            self.pip.setAutoBiasTarget(val)        
        if not (mode == 'IC' and self.pip.autoBiasEnabled()):
            self.pip.clampDevice.setHolding(mode, val)

    def updateHoldingInfo(self, mode=None):
        clamp = self.pip.clampDevice
        if mode is None:
            mode = clamp.getMode()
        hval = clamp.getHolding(mode)

        if self.pip.autoBiasEnabled():
            if mode == 'VC':
                spinVal = hval
                units = 'V'
                self.ui.autoBiasBtn.setText('bias: vc')
            else:
                biasTarget = self.pip.autoBiasTarget()
                spinVal = biasTarget
                units = 'V'
                self.ui.autoBiasBtn.setText('bias: %dpA' % int(hval*1e12))
            self.ui.autoBiasBtn.setChecked(True)
        else:
            if mode == 'VC':
                spinVal = hval
                units = 'V'
            else:
                spinVal = hval
                units = 'A'
            self.ui.autoBiasBtn.setChecked(False)
            self.ui.autoBiasBtn.setText('bias: off')

        with pg.SignalBlock(self.ui.holdingSpin.valueChanged, self.holdingSpinChanged):
            self.ui.holdingSpin.setValue(spinVal)
            step = 5e-3 if units == 'V' else 50e-12
            self.ui.holdingSpin.setOpts(suffix=units, step=step)

    def stateActionClicked(self):
        state = str(self.sender().text())
        self.pip.setState(state)

    def stateTextClicked(self, sender, event):
        self.stateMenu.popup(sender.mapToGlobal(event.pos()))

    def modeTextClicked(self, sender, event):
        if str(self.ui.modeText.text()).lower() == 'vc':
            self.pip.clampDevice.setMode('IC')
        else:
            self.pip.clampDevice.setMode('VC')

    def focusTipBtnClicked(self, state):
        speed = self.selectedSpeed(default='slow')
        self.focusTip(speed)

    def focusTargetBtnClicked(self, state):
        speed = self.selectedSpeed(default='slow')
        self.focusTarget(speed)

    def hideHeader(self):
        for col in range(self.ui.gridLayout.columnCount()):
            item = self.ui.gridLayout.itemAtPosition(0, col)
            if item is not None:
                item.widget().hide()

    def autoBiasClicked(self):
        self.pip.enableAutoBias(self.ui.autoBiasBtn.isChecked())
        self.updateHoldingInfo()

    def regulatorPressureClicked(self):
        self.pip.pressureDevice.setPressure(source='regulator')

    def userPressureClicked(self):
        self.pip.pressureDevice.setPressure(source='user')

    def atmospherePressureClicked(self):
        self.pip.pressureDevice.setPressure(source='atmosphere')

    def pressureSpinChanged(self):
        self.pip.pressureDevice.setPressure(pressure=self.ui.pressureSpin.value())

    def pressureChanged(self, pip, source, pressure):
        with pg.SignalBlock(self.ui.pressureSpin.valueChanged, self.pressureSpinChanged):
            self.ui.pressureSpin.setValue(pressure)
        self.ui.atmospherePressureBtn.setChecked(source=='atmosphere')
        self.ui.userPressureBtn.setChecked(source=='user')
        self.ui.regulatorPressureBtn.setChecked(source=='regulator')

        style = {
            'regulator': 'background-color: #FCC; color: #000', 
            'user': 'background-color: #CCF; color: #AAA', 
            'atmosphere': 'color: #AAA', 
        }.get(source, '')
        self.ui.pressureSpin.setStyleSheet(style)            


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
