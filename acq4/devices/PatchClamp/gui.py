import pyqtgraph as pg
from acq4.filetypes.MultiPatchLog import TEST_PULSE_PARAMETER_CONFIG
from acq4.util import Qt

Ui_Form = Qt.importTemplate('.DeviceGuiTemplate')


class PatchClampDeviceGui(Qt.QWidget):
    def __init__(self, dev: "PatchClamp", dm):
        super().__init__()
        self.dev = dev
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.ui.channelLabel.setText(dev.description())
        self.ui.vcHoldingSpin.setOpts(suffix='V', siPrefix=True, step=5e-3)
        self.ui.icHoldingSpin.setOpts(suffix='A', siPrefix=True, step=10e-12)

        self.state = pg.WidgetGroup(self)

        self.state.sigChanged.connect(self.uiStateChanged)
        self.dev.sigStateChanged.connect(self.devStateChanged)
        self.dev.sigHoldingChanged.connect(self.devHoldingChanged)
        self.devStateChanged()

        editorSpace = self.ui.mockAnalysisLayout
        self.ui.toggleMockAnalysis.clicked.connect(self._toggleMockAnalysis)
        self.analysisPTree = pg.parametertree.ParameterTree()
        editorSpace.addWidget(self.analysisPTree, 0, 0)

        editable = [c for c in TEST_PULSE_PARAMETER_CONFIG if c['name'] != 'event_time']
        self._mockAnalysisRoot = pg.parametertree.Parameter.create(
            name='Analysis', type='group', children=editable)
        self.analysisPTree.setParameters(self._mockAnalysisRoot, showTop=False)
        self._mockAnalysisRoot.sigTreeStateChanged.connect(self._paramTreeChanged)
        self.analysisPTree.setEnabled(False)
        self.dev.sigTestPulseFinished.connect(self._handleTestPulseFinished)

    def _toggleMockAnalysis(self, enable):
        self.analysisPTree.setEnabled(enable)
        if enable:
            self.dev.mockTestPulseAnalysis(**{k: self._mockAnalysisRoot[k] for k in self._mockAnalysisRoot.keys()})
        else:
            self.dev.disableMockTestPulseAnalysis()

    def _handleTestPulseFinished(self, clamp, tp):
        if not self.ui.toggleMockAnalysis.isChecked():
            for k, v in tp.analysis.items():
                if k == 'event_time':
                    continue
                self._mockAnalysisRoot[k] = v

    def _paramTreeChanged(self, root_param, changes):
        if not self.ui.toggleMockAnalysis.isChecked():
            return
        for param, change, data in changes:
            if change != 'value':
                continue
            param_name = root_param.childPath(param)[0]
            self.dev.mockTestPulseAnalysis(**{param_name: data})

    def devStateChanged(self, state=None):
        if state is None:
            state = self.dev.getState()

        pg.disconnect(self.state.sigChanged, self.uiStateChanged)
        try:
            if state['mode'] == 'I=0':
                self.ui.i0Radio.setChecked(True)
                self.ui.icHoldingLabel.setText('')
                self.ui.vcHoldingLabel.setText('')
            else:
                if self.dev.getParam('HoldingEnable'):
                    hval = self.dev.getHolding()
                    sign = '+' if hval > 0 else '-'
                    hval = abs(hval)
                else:
                    hval = 0
                    sign = '+'

                if state['mode'] == 'IC':
                    self.ui.icRadio.setChecked(True)
                    self.ui.vcHoldingLabel.setText('')
                    self.ui.icHoldingLabel.setText(f'{sign} {hval * 1e12:0.0f} pA')
                else:
                    self.ui.vcRadio.setChecked(True)
                    self.ui.icHoldingLabel.setText('')
                    self.ui.vcHoldingLabel.setText(f'{sign} {hval * 1e3:0.0f} mV')

            istate = self.dev.getLastState('IC')
            vstate = self.dev.getLastState('VC')
            if istate is not None:
                self.ui.icHoldingSpin.setValue(istate['holding'])
            if vstate is not None:
                self.ui.vcHoldingSpin.setValue(vstate['holding'])

        finally:
            self.state.sigChanged.connect(self.uiStateChanged)

    def devHoldingChanged(self, mode, val):
        with pg.SignalBlock(self.state.sigChanged, self.uiStateChanged):
            if mode == 'VC':
                self.ui.vcHoldingSpin.setValue(val)
            else:
                self.ui.icHoldingSpin.setValue(val)

    def uiStateChanged(self, name=None, value=None):
        if name == 'icRadio' and value is True:
            self.dev.setMode('IC')
        elif name == 'i0Radio' and value is True:
            self.dev.setMode('I=0')
        elif name == 'vcRadio' and value is True:
            self.dev.setMode('VC')
        elif name == 'icHoldingSpin':
            self.dev.setHolding('IC', value)
        elif name == 'vcHoldingSpin':
            self.dev.setHolding('VC', value)
