from acq4.util import Qt

Ui_DatabaseTemplate = Qt.importTemplate('.PressureControlWidget')


class PressureControlWidget(Qt.QWidget):
    """Presents a compact interface for controlling a pressure-control device."""

    def __init__(self, parent=None):
        Qt.QWidget.__init__(self)
        self.ui = Ui_DatabaseTemplate()
        self.ui.setupUi(self)
        self.ui.pressureSpin.setOpts(
            bounds=[None, None],
            decimals=0,
            suffix='Pa',
            siPrefix=True,
            step=1e3,
            format='{scaledValue:.3g} {siPrefix:s}{suffix:s}',
        )

    def pressureChanged(self, source, pressure):
        self.ui.pressureSpin.setValue(pressure)
        self.ui.atmospherePressureBtn.setChecked(source == 'atmosphere')
        self.ui.userPressureBtn.setChecked(source == 'user')
        self.ui.regulatorPressureBtn.setChecked(source == 'regulator')

        style = {
            'regulator': 'background-color: #FCC; color: #000',
            'user': 'background-color: #CCF; color: #AAA',
            'atmosphere': 'color: #AAA',
        }.get(source, '')
        self.ui.pressureSpin.setStyleSheet(style)

    @property
    def pressureSpin(self):
        return self.ui.pressureSpin

    @property
    def regulatorPressureBtn(self):
        return self.ui.regulatorPressureBtn

    @property
    def userPressureBtn(self):
        return self.ui.userPressureBtn

    @property
    def atmospherePressureBtn(self):
        return self.ui.atmospherePressureBtn
