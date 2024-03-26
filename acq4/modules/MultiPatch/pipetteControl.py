import re

import pyqtgraph as pg
from six.moves import range
from six.moves import zip

from acq4.devices.PatchPipette import PatchPipette
from acq4.util import Qt

Ui_PipetteControl = Qt.importTemplate('.pipetteTemplate')

_vc_mode_opts = dict(
    suffix='V',
    step=5e-3,
    dec=False,
    minStep=1e-3,
    scaleAtZero=1e-3,
)
_ic_mode_opts = dict(
    suffix='A',
    step=0.5,
    dec=True,
    minStep=1e-12,
    scaleAtZero=1e-12,
)


class PipetteControl(Qt.QWidget):

    sigSelectChanged = Qt.Signal(object, object)
    sigLockChanged = Qt.Signal(object, object)
    sigPlotModesChanged = Qt.Signal(object)  # mode list

    def __init__(self, pipette: PatchPipette, mainWin, parent=None):
        Qt.QWidget.__init__(self, parent)
        self.pip = pipette
        self.mainWin = mainWin
        self.ui = Ui_PipetteControl()
        self.ui.setupUi(self)
        if isinstance(pipette, PatchPipette):
            self.pip.sigStateChanged.connect(self.patchStateChanged)
            self.pip.sigActiveChanged.connect(self.pipActiveChanged)
            self.pip.sigTestPulseFinished.connect(self.updatePlots)
            self.pip.sigAutoBiasChanged.connect(self.autoBiasChanged)
            if self.pip.pressureDevice is not None:
                self.ui.pressureWidget.connectPressureDevice(self.pip.pressureDevice)
            self.pip.sigNewPipetteRequested.connect(self.newPipetteRequested)
            self.pip.sigTipCleanChanged.connect(self.tipCleanChanged)
            self.pip.sigTipBrokenChanged.connect(self.tipBrokenChanged)

        self.ui.vcHoldingSpin.setOpts(
            bounds=[None, None],
            decimals=0,
            siPrefix=True,
            format='{scaledValue:.3g} {siPrefix:s}{suffix:s}',
            **_vc_mode_opts,
        )
        self.ui.icHoldingSpin.setOpts(
            bounds=[None, None],
            decimals=0,
            siPrefix=True,
            format='{scaledValue:.3g} {siPrefix:s}{suffix:s}',
            **_ic_mode_opts,
        )
        self.ui.autoOffsetBtn.clicked.connect(self.autoOffsetRequested)
        self.ui.autoPipCapBtn.clicked.connect(self.autoPipCapRequested)
        self.ui.autoBridgeBalanceBtn.clicked.connect(self.autoBridgeBalanceRequested)

        n = re.sub(r'[^\d]+', '', pipette.name())
        self.ui.activeBtn.setText(n)

        self.ui.activeBtn.clicked.connect(self.activeClicked)
        self.ui.selectBtn.clicked.connect(self.selectClicked)
        self.ui.lockBtn.clicked.connect(self.lockClicked)
        self.ui.tipBtn.clicked.connect(self.focusTipBtnClicked)
        self.ui.targetBtn.clicked.connect(self.focusTargetBtnClicked)

        self.modeGroup = Qt.QButtonGroup()
        self.modeGroup.addButton(self.ui.vcBtn, 0)
        self.modeGroup.addButton(self.ui.icBtn, 1)
        self.modeGroup.addButton(self.ui.i0Btn, 2)
        self.modeGroup.idClicked.connect(self.modeBtnClicked)

        self.ui.autoBiasBtn.clicked.connect(self.autoBiasClicked)
        self.ui.vcHoldingSpin.valueChanged.connect(self.vcHoldingSpinChanged)
        self.ui.icHoldingSpin.valueChanged.connect(self.icHoldingSpinChanged)
        self.ui.autoBiasTargetSpin.valueChanged.connect(self.autoBiasSpinChanged)

        self.ui.newPipetteBtn.clicked.connect(self.newPipetteClicked)
        self.ui.fouledCheck.stateChanged.connect(self.fouledCheckChanged)
        self.ui.brokenCheck.stateChanged.connect(self.brokenCheckChanged)

        self.stateMenu = Qt.QMenu()
        if isinstance(pipette, PatchPipette):
            for state in pipette.listStates():
                self.stateMenu.addAction(state, self.stateActionClicked)

        self._pc1 = MousePressCatch(self.ui.stateText, self.stateTextClicked)

        self.plots = [
            PlotWidget(mode='test pulse'), 
            PlotWidget(mode='ss resistance')
        ]
        for plt in self.plots:
            self.ui.plotLayout.addWidget(plt)
            plt.sigModeChanged.connect(self.plotModeChanged)

        if isinstance(self.pip, PatchPipette):
            self.patchStateChanged(pipette)
            self.pipActiveChanged()
        
        if isinstance(self.pip, PatchPipette) and self.pip.clampDevice is not None:
            self.pip.clampDevice.sigStateChanged.connect(self.clampStateChanged)
            self.pip.clampDevice.sigHoldingChanged.connect(self.clampHoldingChanged)
            self.clampStateChanged(self.pip.clampDevice.getState())
            self.clampHoldingChanged(self.pip.clampDevice, self.pip.clampDevice.getMode())
            self.autoBiasChanged(self.pip, self.pip.autoBiasEnabled(), self.pip.autoBiasTarget())

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

    def plotModeChanged(self, plot, mode):
        self.sigPlotModesChanged.emit([plt.mode for plt in self.plots])

    def setPlotModes(self, modes):
        for mode,plt in zip(modes, self.plots):
            plt.setMode(mode)

    def getPlotModes(self):
        return [plt.mode for plt in self.plots]

    def updatePlots(self):
        """Update the pipette data plots."""
        tp = self.pip.lastTestPulse()
        tph = self.pip.testPulseHistory()
        for plt in self.plots:
            plt.newTestPulse(tp, tph)

    def patchStateChanged(self, pipette):
        """Pipette's state changed, reflect that in the UI"""
        state = pipette.getState()
        self.ui.stateText.setText(state.stateName)

    def clampHoldingChanged(self, mode, val):
        self._setHoldingSpin(mode, val)

    def autoBiasChanged(self, pip, enabled, target):
        self.updateAutoBiasSpin()
        with pg.SignalBlock(self.ui.autoBiasBtn.clicked, self.autoBiasClicked):
            self.ui.autoBiasBtn.setChecked(enabled)

    def updateAutoBiasSpin(self):
        if self.pip.autoBiasEnabled() and self.selectedClampMode() == 'IC':
            biasTarget = self.pip.autoBiasTarget()
            self._setHoldingSpin(biasTarget, 'V')

    def vcHoldingSpinChanged(self, value):
        # NOTE: The spin emits a delayed signal when the user changes its value. 
        # That means if we are not careful, some other signal could reset the value
        # of the spin before it has even emitted the change signal, causing the user's
        # requested change to be cancelled.
        self.pip.clampDevice.setHolding('VC', value)

    def icHoldingSpinChanged(self, value):
        self.pip.clampDevice.setHolding('IC', value)

    def autoBiasSpinChanged(self, value):
        self.pip.setAutoBiasTarget(value)
        
    def selectedClampMode(self):
        """Return the currently displayed clamp mode (not necessarily the same as the device clamp mode)
        """
        return [None, 'VC', 'IC', 'I=0'][self.modeGroup.checkedId() + 1]

    def modeBtnClicked(self, btnId):
        mode = self.selectedClampMode()
        self.pip.clampDevice.setMode(mode)

    def clampStateChanged(self, state):
        mode = self.selectedClampMode()
        if mode != state['mode']:
            btnId = {'VC': 0, 'IC': 1, 'I=0': 2}[state['mode']]
            with pg.SignalBlock(self.modeGroup.idClicked, self.modeBtnClicked):
                self.modeGroup.button(btnId).setChecked(True)
            # self.pip.setTestPulseParameters(clampMode=state['mode'])
            # self.updateHoldingInfo(mode=state['mode'])

    # def updateHoldingInfo(self, mode=None):
    #     clamp = self.pip.clampDevice
    #     if mode is None:
    #         mode = clamp.getMode()
    #     hval = clamp.getHolding(mode)

    #     if self.pip.autoBiasEnabled():
    #         if mode == 'VC':
    #             spinVal = hval
    #             self.ui.autoBiasBtn.setText('bias: vc')
    #         else:
    #             biasTarget = self.pip.autoBiasTarget()
    #             spinVal = biasTarget
    #             self.ui.autoBiasBtn.setText(f'bias: {int(hval * 1e12):d}pA')
    #         units = 'V'
    #         self.ui.autoBiasBtn.setChecked(True)
    #     else:
    #         if mode == 'VC':
    #             units = 'V'
    #         else:
    #             units = 'A'
    #         spinVal = hval
    #         self.ui.autoBiasBtn.setChecked(False)
    #         self.ui.autoBiasBtn.setText('bias: off')

    #     self._setHoldingSpin(spinVal, units)

    def _setHoldingSpin(self, mode, value):
        if mode == 'VC':
            with pg.SignalBlock(self.ui.vcHoldingSpin.valueChanged, self.vcHoldingSpinChanged):
                self.ui.vcHoldingSpin.setValue(value)
        elif mode == 'IC':
            with pg.SignalBlock(self.ui.icHoldingSpin.valueChanged, self.icHoldingSpinChanged):
                self.ui.icHoldingSpin.setValue(value)

    def stateActionClicked(self):
        state = str(self.sender().text())
        try:
            self.pip.setState(state)
        except:
            self.patchStateChanged(self.pip)
            raise

    def stateTextClicked(self, sender, event):
        self.stateMenu.popup(sender.mapToGlobal(event.pos()))

    def focusTipBtnClicked(self, state):
        speed = self.mainWin.selectedSpeed(default='fast')
        self.pip.focusOnTip(speed, raiseErrors=True)

    def focusTargetBtnClicked(self, state):
        speed = self.mainWin.selectedSpeed(default='fast')
        self.pip.focusOnTarget(speed, raiseErrors=True)

    def hideHeader(self):
        for col in range(self.ui.gridLayout.columnCount()):
            item = self.ui.gridLayout.itemAtPosition(0, col)
            if item is not None and isinstance(item.widget(), Qt.QLabel):
                item.widget().hide()
        for plt in self.plots:
            plt.hideHeader()

    def autoBiasClicked(self):
        self.pip.enableAutoBias(self.ui.autoBiasBtn.isChecked())
        self.updateHoldingInfo()

    def newPipetteRequested(self):
        self.ui.newPipetteBtn.setStyleSheet("QPushButton {border: 2px solid #F00;}")

    def newPipetteClicked(self):
        self.ui.newPipetteBtn.setStyleSheet("")
        self.pip.newPipette()

    def tipCleanChanged(self, pip, clean):
        with pg.SignalBlock(self.ui.fouledCheck.stateChanged, self.fouledCheckChanged):
            self.ui.fouledCheck.setChecked(not clean)
        self.ui.fouledCheck.setStyleSheet("" if clean else "QCheckBox {border: 2px solid #F00;}")

    def fouledCheckChanged(self, checked):
        self.pip.setTipClean(not self.ui.fouledCheck.isChecked())

    def tipBrokenChanged(self, pip, broken):
        with pg.SignalBlock(self.ui.brokenCheck.stateChanged, self.brokenCheckChanged):
            self.ui.brokenCheck.setChecked(broken)
        self.ui.brokenCheck.setStyleSheet("" if not broken else "QCheckBox {border: 2px solid #F00;}")

    def autoOffsetRequested(self):
        self.pip.clampDevice.autoPipetteOffset()

    def autoPipCapRequested(self):
        self.pip.clampDevice.autoCapComp()

    def autoBridgeBalanceRequested(self):
        self.pip.clampDevice.autoBridgeBalance()

    def brokenCheckChanged(self, checked):
        self.pip.setTipBroken(self.ui.brokenCheck.isChecked())


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


class PlotWidget(Qt.QWidget):
    sigCloseClicked = Qt.Signal(object)  # self
    sigModeChanged = Qt.Signal(object, object)  # self, mode

    def __init__(self, mode):
        Qt.QWidget.__init__(self)
        self.mode = None
        self.layout = Qt.QGridLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.setLayout(self.layout)

        self.modeCombo = pg.ComboBox()
        self.modeCombo.addItems(['test pulse', 'tp analysis', 'ss resistance', 'peak resistance', 'holding current', 'holding potential', 'time constant', 'capacitance'])
        self.layout.addWidget(self.modeCombo, 0, 0)
        self.modeCombo.currentIndexChanged.connect(self.modeComboChanged)

        # self.closeBtn = Qt.QPushButton('X')
        # self.closeBtn.setMaximumWidth(15)
        # self.layout.addWidget(self.closeBtn, 0, 1)
        # self.closeBtn.clicked.connect(self.closeClicked)

        self.plot = pg.PlotWidget()
        self.layout.addWidget(self.plot, 1, 0, 1, 2)

        self.tpLabel = Qt.QGraphicsTextItem()
        self.tpLabel.setParentItem(self.plot.plotItem.vb)
        self.tpLabel.setDefaultTextColor(pg.mkColor('w'))

        self.setMode(mode)

    def hideHeader(self):
        self.modeCombo.hide()
        # self.closeBtn.hide()

    def newTestPulse(self, tp, history):
        if self.mode in ['test pulse', 'tp analysis']:
            data = tp.data
            pri = data['Channel': 'primary']
            units = pri._info[-1]['ClampState']['primaryUnits'] 
            self.plot.plot(pri.xvals('Time'), pri.asarray(), clear=True)
            self.plot.setLabels(left=('', units))

            if self.mode == 'tp analysis':
                t,y = tp.getFitData()
                self.plot.plot(t, y, pen='b')

        elif self.mode in ['ss resistance', 'peak resistance', 'holding current', 'holding potential', 'time constant', 'capacitance']:
            key, units = {
                'ss resistance': ('steadyStateResistance', u'Ω'),
                'peak resistance': ('peakResistance', u'Ω'),
                'holding current': ('baselineCurrent', 'A'),
                'holding potential': ('baselinePotential', 'V'),
                'time constant': ('fitExpTau', 's'),
                'capacitance': ('capacitance', 'F'),
            }[self.mode]
            self.plot.plot(history['time'] - history['time'][0], history[key], clear=True)
            tpa = tp.analysis()
            self.tpLabel.setPlainText(pg.siFormat(tpa[key], suffix=units))

        elif self.mode in ['ss resistance', 'peak resistance']:
            key = {'ss resistance': 'steadyStateResistance', 'peak resistance': 'peakResistance'}[self.mode]
            self.plot.plot(history['time'] - history['time'][0], history[key], clear=True)
            tpa = tp.analysis()
            self.tpLabel.setPlainText(pg.siFormat(tpa[key], suffix=u'Ω'))

    def setMode(self, mode):
        if self.mode == mode:
            return
        self.mode = mode
        with pg.SignalBlock(self.modeCombo.currentIndexChanged, self.modeComboChanged):
            self.modeCombo.setText(mode)
        if mode in ['test pulse', 'tp analysis']:
            self.plot.setLogMode(y=False, x=False)
            self.plot.enableAutoRange(True, True)
            self.tpLabel.setVisible(False)
        elif mode in ['ss resistance', 'peak resistance']:
            self.plot.setLogMode(y=True, x=False)
            self.plot.enableAutoRange(True, False)
            self.plot.setYRange(6, 10)
            self.plot.setLabels(left=('Rss', u'Ω'))
            self.tpLabel.setVisible(True)
        elif mode == 'holding current':
            self.plot.setLogMode(y=False, x=False)
            self.plot.enableAutoRange(True, True)
            self.plot.setLabels(left=('Ihold', u'A'))
            self.tpLabel.setVisible(True)
        elif mode == 'holding potential':
            self.plot.setLogMode(y=False, x=False)
            self.plot.enableAutoRange(True, True)
            self.plot.setLabels(left=('Vhold', u'V'))
            self.tpLabel.setVisible(True)
        elif mode == 'time constant':
            self.plot.setLogMode(y=True, x=False)
            self.plot.enableAutoRange(False, True)
            self.plot.setYRange(-5, -2)
            self.plot.setLabels(left=('Tau', u's'))
            self.tpLabel.setVisible(True)
        elif mode == 'capacitance':
            self.plot.setLogMode(y=False, x=False)
            self.plot.enableAutoRange(False, True)
            self.plot.setYRange(0, 100e-12)
            self.plot.setLabels(left=('Capacitance', u'F'))
            self.tpLabel.setVisible(True)

    def modeComboChanged(self):
        mode = self.modeCombo.currentText()
        self.setMode(mode)
        self.sigModeChanged.emit(self, mode)

    def closeClicked(self):
        self.sigCloseClicked.emit(self)
