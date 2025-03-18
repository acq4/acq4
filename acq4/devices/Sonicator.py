from threading import RLock

import numpy as np

import pyqtgraph as pg
from acq4.devices.Device import Device
from acq4.util import Qt
from acq4.util.future import future_wrap, Future, FutureButton


class Sonicator(Device):
    """Base class for any sonicator device."""

    sigSonicationChanged = Qt.pyqtSignal(float)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.actionLock = RLock()

    @future_wrap
    def doProtocol(self, mode: str, _future: Future = None, **kwargs) -> None:
        with self.actionLock:
            if mode in {"clean", "expel"}:
                duration = kwargs.get("duration", 5 if mode == "clean" else 1)
                frequency = kwargs.get("frequency", 150e3)
                _future.waitFor(self.sonicate(frequency, duration, lock=False))
            elif mode == "quick cleanse":
                start = kwargs.get("start", 140e3)
                stop = kwargs.get("stop", 154e3)
                step = kwargs.get("step", 1e3)
                step_duration = kwargs.get("stepDuration", 100e-3)
                frequency = start
                while frequency < stop:
                    _future.waitFor(self.sonicate(frequency, step_duration, lock=False))
                    frequency += step
                frequency -= step
                while frequency > start:
                    _future.waitFor(self.sonicate(frequency, step_duration, lock=False))
                    frequency -= step
            else:
                raise ValueError(f"Unrecognized sonication protocol '{mode}'")

    def isBusy(self) -> bool:
        available = self.actionLock.acquire(blocking=False)
        if available:
            self.actionLock.release()
        return not available

    def sonicate(self, frequency: float, duration: float, lock: bool = True) -> Future:
        raise NotImplementedError()

    def deviceInterface(self, win):
        return SonicatorGUI(win, self)


class SonicatorGUI(Qt.QWidget):
    """GUI interface for controlling a sonicator device.
    
    Provides controls for:
    - Running predefined protocols (Clean, Quick Cleanse, Expel)
    - Setting custom frequency
    - (disabled) Visualizing the current sonication waveform
    """

    def __init__(self, win, dev):
        Qt.QWidget.__init__(self)
        self.win = win
        self.dev = dev
        self.dev.sigSonicationChanged.connect(self.onSonicationChanged)

        self.currentFrequency = 0.0

        self.setupUI()

    def setupUI(self):
        """Create and arrange all UI elements"""
        self.layout = Qt.QVBoxLayout()
        self.setLayout(self.layout)

        # Protocol controls
        protocolGroup = Qt.QGroupBox("Protocols")
        protocolLayout = Qt.QHBoxLayout()
        protocolGroup.setLayout(protocolLayout)

        self.cleanBtn = FutureButton(self.runCleanProtocol, "Clean", stoppable=True)
        self.cleanBtn.sigFinished.connect(self.onProtocolFinished)
        protocolLayout.addWidget(self.cleanBtn)

        self.quickCleanseBtn = FutureButton(self.runQuickCleanseProtocol, "Quick Cleanse", stoppable=True)
        self.quickCleanseBtn.sigFinished.connect(self.onProtocolFinished)
        protocolLayout.addWidget(self.quickCleanseBtn)

        self.expelBtn = FutureButton(self.runExpelProtocol, "Expel", stoppable=True)
        self.expelBtn.sigFinished.connect(self.onProtocolFinished)
        protocolLayout.addWidget(self.expelBtn)

        # Frequency control
        freqGroup = Qt.QGroupBox("Manual Control")
        freqLayout = Qt.QFormLayout()
        freqGroup.setLayout(freqLayout)

        self.currentFreqLabel = Qt.QLabel("Idle")
        freqLayout.addRow("Current Action:", self.currentFreqLabel)

        # self.waveformPlot = pg.PlotWidget()
        # self.waveformPlot.setMinimumHeight(80)
        # self.waveformPlot.setInteractive(False)
        # self.waveformCurve = self.waveformPlot.plot(pen='y')
        # freqLayout.addRow(self.waveformPlot)
        # self.updateWaveform(0)

        self.freqSpinBox = pg.SpinBox(value=150000, siPrefix=True, suffix="Hz", bounds=[40000, 170000], dec=True)
        freqLayout.addRow("Frequency:", self.freqSpinBox)

        self.durationSpinBox = pg.SpinBox(value=1.0, siPrefix=True, suffix="s", bounds=[1e-6, 10.0], dec=True)
        freqLayout.addRow("Duration:", self.durationSpinBox)

        self.sonicateBtn = FutureButton(self.runManualSonication, "Sonicate")
        self.sonicateBtn.sigFinished.connect(self.onProtocolFinished)
        freqLayout.addRow("", self.sonicateBtn)

        # Add all groups to main layout
        self.layout.addWidget(protocolGroup)
        self.layout.addWidget(freqGroup)

    def runCleanProtocol(self):
        return self.runProtocol("clean")

    def runQuickCleanseProtocol(self):
        return self.runProtocol("quick cleanse")

    def runExpelProtocol(self):
        return self.runProtocol("expel")

    def runProtocol(self, protocol) -> Future:
        """Run the specified protocol and update UI accordingly"""
        self.updateButtonStates(True, protocol)
        return self.dev.doProtocol(protocol)

    def onProtocolFinished(self):
        """Called when a protocol completes"""
        self.updateButtonStates(False)

    def updateButtonStates(self, running, activeProtocol=None):
        """Enable/disable buttons based on current state"""
        self.cleanBtn.setEnabled(not running or activeProtocol == "clean")
        self.quickCleanseBtn.setEnabled(not running or activeProtocol == "quick cleanse")
        self.expelBtn.setEnabled(not running or activeProtocol == "expel")
        self.sonicateBtn.setEnabled(not running or activeProtocol == "manual")

    def runManualSonication(self):
        """Handle manual sonication button click"""
        frequency = self.freqSpinBox.value()
        duration = self.durationSpinBox.value()

        self.updateButtonStates(True, "manual")

        return self.dev.sonicate(frequency, duration)

    def onSonicationChanged(self, frequency):
        """Called when the sonication frequency changes"""
        self.currentFrequency = frequency

        # Update frequency display with formatted value
        if frequency > 0:
            self.currentFreqLabel.setText(pg.siFormat(frequency, suffix='Hz'))
        else:
            self.currentFreqLabel.setText("Idle")

        # Update waveform visualization
        # self.updateWaveform(frequency)

    # def updateWaveform(self, frequency):
    #     """Update the waveform visualization based on current frequency"""
    #     if frequency <= 0:
    #         # Flat line when not sonicating
    #         x = np.linspace(0, 0.1, 1000)
    #         y = np.zeros_like(x)
    #     else:
    #         # Simple sine wave visualization
    #         x = np.linspace(0, 0.0001, 1000)  # Show 0.1ms
    #         y = np.sin(2 * np.pi * frequency * x)
    #
    #     self.waveformCurve.setData(x, y)


if __name__ == "__main__":
    import sys
    from unittest.mock import MagicMock

    from acq4.devices.MockSonicator import MockSonicator


    class TestWindow(Qt.QtWidgets.QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Sonicator Test")
            self.resize(600, 500)

            # Create a mock sonicator device
            mock_manager = MagicMock()
            self.sonicator = MockSonicator(mock_manager, dict(), "test_sonicator")

            # Create and set the GUI as central widget
            self.gui = self.sonicator.deviceInterface(self)
            self.setCentralWidget(self.gui)


    app = Qt.QtWidgets.QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec_())
