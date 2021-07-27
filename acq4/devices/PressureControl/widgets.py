import pyqtgraph as pg

from acq4.util import Qt

Ui_DatabaseTemplate = Qt.importTemplate('.PressureControlWidget')


class PressureControlWidget(Qt.QWidget):
    """Presents a compact interface for controlling a pressure-control device."""
    styles = {
        'regulator': 'background-color: #FCC; color: #000',
        'user': 'background-color: #CCF; color: #AAA',
        'atmosphere': 'color: #AAA',
    }

    def __init__(self, parent=None, dev=None):
        Qt.QWidget.__init__(self, parent)
        self.dev = None
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
        if dev is not None:
            self.connectPressureDevice(dev)

    def connectPressureDevice(self, dev):
        """
        Parameters
        ----------
        dev : PressureControl
        """
        self.dev = dev
        self.pressureChanged(dev, dev.getSource(), dev.getPressure())
        self.ui.pressureSpin.setMaximum(dev.maximum)
        self.ui.pressureSpin.setMinimum(dev.minimum)
        dev.sigPressureChanged.connect(self.pressureChanged)
        self.ui.regulatorPressureBtn.clicked.connect(self.regulatorPressureClicked)
        self.ui.userPressureBtn.clicked.connect(self.userPressureClicked)
        self._userButtonCanBeUsed = ("user" in dev.sources)
        self.ui.atmospherePressureBtn.clicked.connect(self.atmospherePressureClicked)
        self.ui.pressureSpin.valueChanged.connect(self.pressureSpinChanged)
        self._busyChanged(dev, dev.getBusyStatus())
        dev.sigBusyChanged.connect(self._busyChanged)

    def regulatorPressureClicked(self):
        # TODO this sleeps for 0.3s in the UI thread
        self.dev.setPressure(source='regulator')
        self.ui.pressureSpin.setEnabled(True)

    def userPressureClicked(self):
        self.dev.setPressure(source='user')
        self.ui.pressureSpin.setEnabled(False)

    def atmospherePressureClicked(self):
        self.dev.setPressure(source='atmosphere')
        self.ui.pressureSpin.setEnabled(False)

    def pressureSpinChanged(self):
        self.dev.setPressure(pressure=self.ui.pressureSpin.value())

    def pressureChanged(self, dev, source, pressure):
        with pg.SignalBlock(self.ui.pressureSpin.valueChanged, self.pressureSpinChanged):
            self.ui.pressureSpin.setValue(pressure)
        self.ui.atmospherePressureBtn.setChecked(source == 'atmosphere')
        self.ui.userPressureBtn.setChecked(source == 'user')
        self.ui.regulatorPressureBtn.setChecked(source == 'regulator')
        self.setStyle(source)

    def _busyChanged(self, dev, isBusy):
        self.ui.pressureSpin.setEnabled(not isBusy)
        self.ui.atmospherePressureBtn.setEnabled(not isBusy)
        self.ui.userPressureBtn.setEnabled(self._userButtonCanBeUsed and not isBusy)
        self.ui.regulatorPressureBtn.setEnabled(not isBusy)

    def setStyle(self, source=None):
        style = self.styles.get(source, self.styles.get(self.dev.source, ''))
        self.ui.pressureSpin.setStyleSheet(style)

    @property
    def pressureSpin(self):
        return self.ui.pressureSpin
