from __future__ import annotations

import json

from acq4.devices.Device import Device
from acq4.util import Qt
from acq4.util.future import Future, FutureButton


class Sonicator(Device):
    """Base class for any sonicator device.
    Config
    ------
    protocols : dict
        Dictionary of predefined sonication protocols. Subclasses define the format of these protocols.

    """

    sigSonicationChanged = Qt.pyqtSignal(str)

    def __init__(self, deviceManager, config, name):
        super().__init__(deviceManager, config, name)
        self.config = config
        self.protocols = config.get("protocols", {})

    def doProtocol(self, protocol: str | object) -> Future:
        status = "Running"
        if protocol in self.protocols:
            status = protocol
            protocol = self.protocols[protocol]
        self.sigSonicationChanged.emit(status)
        future = self._doProtocol(protocol)
        future.onFinish(self._onProtocolFinished)
        return future

    def _doProtocol(self, protocol: object) -> Future:
        raise NotImplementedError()

    def _onProtocolFinished(self, future):
        self.sigSonicationChanged.emit("Idle")

    def deviceInterface(self, win):
        return SonicatorGUI(win, self)


class SonicatorGUI(Qt.QWidget):
    """GUI interface for controlling a sonicator device.

    Provides controls for:
    - Running predefined protocols (Clean, Quick Cleanse, Expel)
    - Setting custom frequency
    """

    def __init__(self, win, dev):
        Qt.QWidget.__init__(self)
        self.win = win
        self.dev = dev
        self.dev.sigSonicationChanged.connect(self.onSonicationChanged)

        self.setupUI()

    def setupUI(self):
        """Create and arrange all UI elements"""
        self.layout = Qt.QVBoxLayout()
        self.setLayout(self.layout)

        # Protocol controls
        protocolGroup = Qt.QGroupBox("Protocols")
        protocolLayout = Qt.QHBoxLayout()
        protocolGroup.setLayout(protocolLayout)

        self._protocolButtons = {}
        for name in self.dev.protocols:
            btn = FutureButton(self.runProtocol, stoppable=True)
            btn.setText(name)
            btn.setObjectName(name)
            btn.setToolTip(json.dumps(self.dev.protocols[name], indent=2))
            btn.sigFinished.connect(self.onProtocolFinished)
            protocolLayout.addWidget(btn)
            self._protocolButtons[name] = btn

        statusGroup = Qt.QGroupBox("Status")
        statusLayout = Qt.QFormLayout()
        statusGroup.setLayout(statusLayout)

        self.currentStatusLabel = Qt.QLabel("Idle")
        statusLayout.addRow("Current Action:", self.currentStatusLabel)

        # self.freqSpinBox = pg.SpinBox(value=150000, siPrefix=True, suffix="Hz", bounds=[40000, 170000], dec=True)
        # statusLayout.addRow("Frequency:", self.freqSpinBox)
        #
        # self.durationSpinBox = pg.SpinBox(value=1.0, siPrefix=True, suffix="s", bounds=[1e-6, 10.0], dec=True)
        # statusLayout.addRow("Duration:", self.durationSpinBox)
        #
        # self.sonicateBtn = FutureButton(self.runManualSonication, "Sonicate")
        # self.sonicateBtn.sigFinished.connect(self.onProtocolFinished)
        # statusLayout.addRow("", self.sonicateBtn)

        # Add all groups to main layout
        self.layout.addWidget(protocolGroup)
        self.layout.addWidget(statusGroup)

    def runProtocol(self) -> Future:
        """Run the specified protocol and update UI accordingly"""
        protocol = self.sender().objectName()
        self.updateButtonStates(True, protocol)
        return self.dev.doProtocol(protocol)

    def onProtocolFinished(self):
        """Called when a protocol completes"""
        self.updateButtonStates(False)

    def updateButtonStates(self, running, activeProtocol=None):
        """Enable/disable buttons based on current state"""
        for name, button in self._protocolButtons.items():
            button.setEnabled(not running or activeProtocol == name)
        # self.sonicateBtn.setEnabled(not running or activeProtocol == "manual")

    # def runManualSonication(self):
    #     """Handle manual sonication button click"""
    #     frequency = self.freqSpinBox.value()
    #     duration = self.durationSpinBox.value()
    #
    #     self.updateButtonStates(True, "manual")
    #
    #     return self.dev.sonicate(frequency, duration)

    def onSonicationChanged(self, status):
        """Called when the sonication changes"""
        self.currentStatusLabel.setText(status)
