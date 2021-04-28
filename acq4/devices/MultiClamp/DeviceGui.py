# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.util import Qt
import pyqtgraph as pg

Ui_Form = Qt.importTemplate('.RackTemplate')


class MCDeviceGui(Qt.QWidget):
    def __init__(self, dev, win):
        Qt.QWidget.__init__(self)
        self.dev = dev
        self.win = win
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.ui.channelLabel.setText(dev.config['channelID'])
        self.ui.vcHoldingSpin.setOpts(suffix='V', siPrefix=True, step=5e-3)
        self.ui.icHoldingSpin.setOpts(suffix='A', siPrefix=True, step=10e-12)

        self.state = pg.WidgetGroup(self)

        self.state.sigChanged.connect(self.uiStateChanged)
        self.dev.sigStateChanged.connect(self.devStateChanged)
        self.dev.sigHoldingChanged.connect(self.devHoldingChanged)
        self.devStateChanged()

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
                hold = self.dev.getParam('HoldingEnable')
                if hold:
                    hval = self.dev.getParam('Holding')
                    sign = '+' if hval > 0 else '-'
                    hval = abs(hval)
                else:
                    hval = 0
                    sign = '+'

                if state['mode'] == 'IC':
                    self.ui.icRadio.setChecked(True)
                    self.ui.vcHoldingLabel.setText('')
                    self.ui.icHoldingLabel.setText('%s %0.0f pA' % (sign, hval*1e12))
                else:
                    self.ui.vcRadio.setChecked(True)
                    self.ui.icHoldingLabel.setText('')
                    self.ui.vcHoldingLabel.setText('%s %0.0f mV' % (sign, hval*1e3))

            istate = self.dev.getLastState('IC')
            vstate = self.dev.getLastState('VC')
            if istate is not None:
                self.ui.icHoldingSpin.setValue(istate['holding'])
            if vstate is not None:
                self.ui.vcHoldingSpin.setValue(vstate['holding'])

        finally:
            self.state.sigChanged.connect(self.uiStateChanged)

    def devHoldingChanged(self, dev, mode):
        with pg.SignalBlock(self.state.sigChanged, self.uiStateChanged):
            state = self.dev.getLastState(mode)
            if mode == 'VC':
                self.ui.vcHoldingSpin.setValue(state['holding'])
            elif mode == 'IC':
                self.ui.icHoldingSpin.setValue(state['holding'])

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
