from pyqtgraph.functions import siFormat

from acq4.devices.Laser.LaserDevGui import LaserDevGui
from acq4.drivers.MaiTai import PUMP_CURRENT, PUMP_GREEN_POWER, PUMP_IR_POWER
from acq4.util import Qt

Ui_MaiTaiStatusWidget = Qt.importTemplate('.maiTaiTemplate')


class MaiTaiDevGui(LaserDevGui):
    def __init__(self, dev):
        LaserDevGui.__init__(self, dev)

        # the Mai Tai widget provides its own wavelength control; the base group's GDD controls do not apply
        self.ui.wavelengthGroup.hide()
        self.ui.qSwitchBtn.hide()

        self.mtui = Ui_MaiTaiStatusWidget()
        self.mtWidget = Qt.QWidget()
        self.mtui.setupUi(self.mtWidget)
        self.ui.gridLayout.addWidget(self.mtWidget, self.ui.gridLayout.rowCount(), 0, 1, 3)
        if not self.dev.hasExternalSwitch:
            self.mtui.linkLaserExtSwitchCheckBox.setChecked(False)
            self.mtui.linkLaserExtSwitchCheckBox.hide()
            self.mtui.externalSwitchBtn.hide()
        self.pumpModeButtons = {
            PUMP_CURRENT: self.mtui.currentBtn,
            PUMP_GREEN_POWER: self.mtui.greenPowerBtn,
            PUMP_IR_POWER: self.mtui.irPowerBtn,
        }

        self.mtui.pumpCurrentSpin.setOpts(suffix='%', siPrefix=False, dec=False, step=0.1)
        self.mtui.greenPowerSpin.setOpts(suffix='W', siPrefix=True, dec=False, step=0.1)
        self.mtui.wavelengthSpin_2.setOpts(suffix='m', siPrefix=True, dec=False, step=5e-9,
                                           bounds=self.dev.getWavelengthRange())
        startWl = self.dev.getWavelength()
        self.mtui.wavelengthSpin_2.setValue(startWl)
        self.mtui.currentWaveLengthLabel.setText(siFormat(startWl, suffix='m'))

        self.updatePumpModeControls(self.dev.getPumpMode())

        laserOn = self.dev.isLaserOn()
        self.mtui.turnOnOffBtn.setChecked(laserOn)
        self.updateLaserOnControls(laserOn)
        if laserOn and self.dev.getInternalShutter():
            self.mtui.InternalShutterBtn.setChecked(True)
            self.updateInternalShutterControls(True)

        self.mtui.wavelengthSpin_2.valueChanged.connect(self.dev.setWavelength)
        self.mtui.powerButtonGroup.buttonClicked.connect(self.pumpModeClicked)
        self.mtui.pumpCurrentSpin.valueChanged.connect(self.pumpCurrentSpinChanged)
        self.mtui.greenPowerSpin.valueChanged.connect(self.greenPowerSpinChanged)
        self.mtui.turnOnOffBtn.toggled.connect(self.onOffToggled)
        self.mtui.InternalShutterBtn.toggled.connect(self.internalShutterToggled)
        self.mtui.externalSwitchBtn.toggled.connect(self.externalSwitchToggled)
        self.mtui.linkLaserExtSwitchCheckBox.toggled.connect(self.linkLaserExtSwitchToggled)
        self.mtui.alignmentModeBtn.toggled.connect(self.alignmentModeToggled)

        self.dev.sigStatusChanged.connect(self.statusChanged)

    def updateLaserOnControls(self, on):
        self.mtui.turnOnOffBtn.setText('Turn Off Laser' if on else 'Turn On Laser')
        self.mtui.EmissionLabel.setText('Emission ON' if on else 'Emission Off')
        self.mtui.EmissionLabel.setStyleSheet("QLabel {color: #C00}" if on else "")
        self.mtui.InternalShutterBtn.setEnabled(on)

    def updateInternalShutterControls(self, opened):
        self.mtui.InternalShutterBtn.setText('Close Laser Shutter' if opened else 'Open Laser Shutter')
        self.mtui.InternalShutterLabel.setText('Laser Shutter Open' if opened else 'Laser Shutter Closed')
        self.mtui.InternalShutterLabel.setStyleSheet("QLabel {color: #0A0}" if opened else "")

    def updatePumpModeControls(self, mode):
        self.pumpModeButtons[mode].setChecked(True)
        self.mtui.pumpCurrentSpin.setEnabled(mode == PUMP_CURRENT)
        self.mtui.greenPowerSpin.setEnabled(mode == PUMP_GREEN_POWER)
        self.currentPumpMode = mode

    def onOffToggled(self, on):
        if on:
            self.dev.switchLaserOn()
        else:
            self.mtui.InternalShutterBtn.setChecked(False)
            self.ui.shutterBtn.setChecked(False)
            self.dev.switchLaserOff()
        self.updateLaserOnControls(on)

    def internalShutterToggled(self, opened):
        linked = self.mtui.linkLaserExtSwitchCheckBox.isChecked()
        if opened:
            if linked:
                self.mtui.externalSwitchBtn.setChecked(False)
            self.dev.openInternalShutter()
        else:
            self.dev.closeInternalShutter()
            if linked:
                self.mtui.externalSwitchBtn.setChecked(True)
        self.updateInternalShutterControls(opened)

    def externalSwitchToggled(self, on):
        self.dev.setExternalSwitch(on)
        self.mtui.externalSwitchBtn.setText('External Switch ON' if on else 'External Switch OFF')

    def linkLaserExtSwitchToggled(self, linked):
        self.mtui.externalSwitchBtn.setEnabled(not linked)

    def alignmentModeToggled(self, enable):
        self.dev.setPumpAlignmentMode(enable)
        self.mtui.alignmentModeBtn.setText('Alignment Mode ON' if enable else 'Alignment Mode OFF')

    def pumpModeClicked(self, button):
        mode = next(m for m, b in self.pumpModeButtons.items() if b is button)
        self.dev.setPumpMode(mode)
        self.updatePumpModeControls(mode)

    def pumpCurrentSpinChanged(self, value):
        if self.currentPumpMode == PUMP_CURRENT:
            self.dev.setPumpCurrent(value)

    def greenPowerSpinChanged(self, value):
        if self.currentPumpMode == PUMP_GREEN_POWER:
            self.dev.setPumpPower(value)

    def statusChanged(self, status):
        self.mtui.currentWaveLengthLabel.setText(siFormat(status['wavelength'], suffix='m'))
        self.mtui.relHumidityLabel.setText(f"{status['humidity']:.1f} %")
        self.mtui.pumpPowerLabel.setText(siFormat(status['pumpPower'], suffix='W'))
        self.mtui.irPowerLabel.setText(siFormat(status['commandedPower'], suffix='W'))
        self.mtui.pumpModeLabel.setText(status['pumpMode'])
        self.mtui.P2OptimizationLabel.setText('ON' if status['p2Optimization'] else 'OFF')
        self.mtui.systemStatusLabel.setText(status['status'])
        self.mtui.pumpLaserSystemStatusLabel.setText(status['pumpLaserStatus'])

        pulsing = status['isPulsing']
        self.mtui.PulsingLabel.setText('Pulsing' if pulsing else 'Not Pulsing')
        self.mtui.PulsingLabel.setStyleSheet("QLabel {color: #EA0}" if pulsing else "")

        # keep inactive setpoint controls showing the laser's current values
        if self.currentPumpMode != PUMP_GREEN_POWER:
            self.mtui.greenPowerSpin.blockSignals(True)
            self.mtui.greenPowerSpin.setValue(status['pumpPower'])
            self.mtui.greenPowerSpin.blockSignals(False)
        if self.currentPumpMode != PUMP_CURRENT:
            self.mtui.pumpCurrentSpin.blockSignals(True)
            self.mtui.pumpCurrentSpin.setValue(status['pumpCurrent'])
            self.mtui.pumpCurrentSpin.blockSignals(False)
