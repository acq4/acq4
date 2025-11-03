from __future__ import annotations

import json
from functools import cached_property

from acq4.devices.Device import Device
from acq4.util import Qt
from acq4.util.PromptUser import prompt
from acq4.util.future import Future, FutureButton, future_wrap


class Sonicator(Device):
    """
    Base class for ultrasonic sonicator devices.
    
    Provides common functionality for controlling ultrasonic cleaners and sonicators
    used for pipette cleaning and laboratory equipment maintenance.
    
    Configuration options:
    
    protocols : dict
        Dictionary of predefined sonication protocols
            - Key: Protocol name (str)
            - Value: Protocol definition (format depends on subclass implementation)
    unsafeSonicationBelow : float
        If set, disable sonication when the pipette is below the surface plus this value.

    Subclasses define the specific format and implementation of protocols.
    
    Emits sigSonicationChanged(status) when sonication state changes.
    """

    sigSonicationChanged = Qt.pyqtSignal(str)

    def __init__(self, deviceManager, config, name):
        super().__init__(deviceManager, config, name)
        self.protocols = config.get("protocols", {})

    def safeToSonicate(self, _future: Future = None, askUser=True) -> bool:
        pos = self.patchPipetteDevice.pipetteDevice.globalPosition()
        well = self.patchPipetteDevice.pipetteDevice.getCleaningWell()
        if well and well.containsPoint(pos):
            return True
        lower_bound = self.config.get("unsafeSonicationBelow")
        if lower_bound is not None:
            lower_bound += self.patchPipetteDevice.scopeDevice().getSurfaceDepth()
            if pos[2] > lower_bound:
                return True
        if not askUser:
            return False
        response = _future.waitFor(
            prompt(
                "Sonication Safety Warning",
                "Sonication may be unsafe at the current pipette position. Proceed?",
                ["Yes", "No"],
            )
        ).getResult()
        return response == "Yes"

    @future_wrap
    def doProtocol(self, protocol: str | object, _future):
        if not self.safeToSonicate(_future):
            self.logger.info("Sonication deemed unsafe. Aborting.")
            return
        status = "Running"
        if protocol in self.protocols:
            status = protocol
            protocol = self.protocols[protocol]
        self.sigSonicationChanged.emit(status)
        _future.waitFor(self._doProtocol(protocol))
        self._onProtocolFinished()

    def _doProtocol(self, protocol: object) -> Future:
        raise NotImplementedError()

    def _onProtocolFinished(self):
        self.sigSonicationChanged.emit("Idle")

    def deviceInterface(self, win):
        return SonicatorGUI(win, self)

    @cached_property
    def patchPipetteDevice(self):
        for pp in self.dm.listInterfaces('patchpipette'):
            pp = self.dm.getDevice(pp)
            if pp.sonicatorDevice == self:
                return pp
        return None


class SonicatorGUI(Qt.QWidget):
    """GUI interface for controlling a sonicator device.

    Provides controls for:
    - Running predefined protocols (Clean, Quick Cleanse, Expel)
    - Setting custom frequency
    """

    def __init__(self, win, dev: Sonicator):
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

    def onSonicationChanged(self, status):
        """Called when the sonication changes"""
        self.currentStatusLabel.setText(status)
