from threading import RLock

from acq4.devices.Device import Device
from acq4.util import Qt
from acq4.util.future import future_wrap, Future


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
                _future.waitFor(self.sonicate(frequency, duration))
            elif mode == "quick cleanse":
                start = kwargs.get("start", 140e3)
                stop = kwargs.get("stop", 154e3)
                step = kwargs.get("step", 1e3)
                step_duration = kwargs.get("stepDuration", 100e-3)
                frequency = start
                while frequency < stop:
                    _future.waitFor(self.sonicate(frequency, step_duration))
                    frequency += step
                frequency -= step
                while frequency > start:
                    _future.waitFor(self.sonicate(frequency, step_duration))
                    frequency -= step
            else:
                raise ValueError(f"Unrecognized sonication protocol '{mode}'")

    def isBusy(self) -> bool:
        available = self.actionLock.acquire(blocking=False)
        if available:
            self.actionLock.release()
        return not available

    def sonicate(self, frequency: float, duration: float) -> Future:
        raise NotImplementedError()

    def deviceInterface(self, win):
        return SonicatorGUI(win, self)


class SonicatorGUI(Qt.QWidget):
    """GUI interface for controlling a sonicator device.
    
    Provides controls for:
    - Running predefined protocols (Clean, Quick Cleanse, Expel)
    - Setting custom frequency
    - Visualizing the current sonication waveform
    """
    
    def __init__(self, win, dev):
        Qt.QWidget.__init__(self)
        self.win = win
        self.dev = dev
        self.dev.sigSonicationChanged.connect(self.onSonicationChanged)
        
        self.currentFrequency = 0.0
        self.activeProtocol = None
        
        self.setupUI()
        
    def setupUI(self):
        """Create and arrange all UI elements"""
        self.layout = Qt.QVBoxLayout()
        self.setLayout(self.layout)
        
        # Protocol controls
        protocolGroup = Qt.QGroupBox("Protocols")
        protocolLayout = Qt.QHBoxLayout()
        protocolGroup.setLayout(protocolLayout)
        
        self.cleanBtn = Qt.QPushButton("Clean")
        self.quickCleanseBtn = Qt.QPushButton("Quick Cleanse")
        self.expelBtn = Qt.QPushButton("Expel")
        
        self.cleanBtn.clicked.connect(lambda: self.runProtocol("clean"))
        self.quickCleanseBtn.clicked.connect(lambda: self.runProtocol("quick cleanse"))
        self.expelBtn.clicked.connect(lambda: self.runProtocol("expel"))
        
        protocolLayout.addWidget(self.cleanBtn)
        protocolLayout.addWidget(self.quickCleanseBtn)
        protocolLayout.addWidget(self.expelBtn)
        
        # Frequency control
        freqGroup = Qt.QGroupBox("Frequency Control")
        freqLayout = Qt.QFormLayout()
        freqGroup.setLayout(freqLayout)
        
        self.freqSpinBox = Qt.QSpinBox()
        self.freqSpinBox.setRange(40000, 170000)  # 40kHz to 170kHz
        self.freqSpinBox.setSingleStep(1000)  # 1kHz steps
        self.freqSpinBox.setValue(150000)  # Default to 150kHz
        self.freqSpinBox.setSuffix(" Hz")
        
        self.sonicateBtn = Qt.QPushButton("Sonicate")
        self.sonicateBtn.clicked.connect(self.onSonicateClicked)
        
        self.durationSpinBox = Qt.QDoubleSpinBox()
        self.durationSpinBox.setRange(0.1, 10.0)  # 0.1 to 10 seconds
        self.durationSpinBox.setSingleStep(0.1)
        self.durationSpinBox.setValue(1.0)
        self.durationSpinBox.setSuffix(" s")
        
        freqLayout.addRow("Frequency:", self.freqSpinBox)
        freqLayout.addRow("Duration:", self.durationSpinBox)
        freqLayout.addRow("", self.sonicateBtn)
        
        # Status display
        statusGroup = Qt.QGroupBox("Status")
        statusLayout = Qt.QFormLayout()
        statusGroup.setLayout(statusLayout)
        
        self.statusLabel = Qt.QLabel("Idle")
        self.currentFreqLabel = Qt.QLabel("0 Hz")
        
        statusLayout.addRow("Status:", self.statusLabel)
        statusLayout.addRow("Current Frequency:", self.currentFreqLabel)
        
        # Waveform visualization
        waveformGroup = Qt.QGroupBox("Waveform")
        waveformLayout = Qt.QVBoxLayout()
        waveformGroup.setLayout(waveformLayout)
        
        import pyqtgraph as pg
        self.waveformPlot = pg.PlotWidget()
        self.waveformPlot.setMinimumHeight(100)
        self.waveformPlot.setLabel('left', 'Amplitude')
        self.waveformPlot.setLabel('bottom', 'Time', 's')
        self.waveformCurve = self.waveformPlot.plot(pen='y')
        
        # Initialize with flat line
        self.updateWaveform(0)
        
        waveformLayout.addWidget(self.waveformPlot)
        
        # Add all groups to main layout
        self.layout.addWidget(protocolGroup)
        self.layout.addWidget(freqGroup)
        self.layout.addWidget(statusGroup)
        self.layout.addWidget(waveformGroup)
        
    def runProtocol(self, protocol):
        """Run the specified protocol and update UI accordingly"""
        self.activeProtocol = protocol
        self.updateButtonStates(True, protocol)
        self.statusLabel.setText(f"Running: {protocol}")
        
        # Start the protocol and connect to its completion
        future = self.dev.doProtocol(protocol)
        future.addCallback(self.onProtocolFinished)
        
    def onProtocolFinished(self):
        """Called when a protocol completes"""
        self.activeProtocol = None
        self.updateButtonStates(False)
        self.statusLabel.setText("Idle")
        
    def updateButtonStates(self, running, activeProtocol=None):
        """Enable/disable buttons based on current state"""
        self.cleanBtn.setEnabled(not running or activeProtocol == "clean")
        self.quickCleanseBtn.setEnabled(not running or activeProtocol == "quick cleanse")
        self.expelBtn.setEnabled(not running or activeProtocol == "expel")
        self.sonicateBtn.setEnabled(not running)
        self.freqSpinBox.setEnabled(not running)
        self.durationSpinBox.setEnabled(not running)
        
    def onSonicateClicked(self):
        """Handle manual sonication button click"""
        frequency = self.freqSpinBox.value()
        duration = self.durationSpinBox.value()
        
        self.updateButtonStates(True)
        self.statusLabel.setText(f"Sonicating at {frequency} Hz")
        
        future = self.dev.sonicate(frequency, duration)
        future.addCallback(self.onSonicationFinished)
        
    def onSonicationFinished(self):
        """Called when manual sonication completes"""
        self.updateButtonStates(False)
        self.statusLabel.setText("Idle")
        
    def onSonicationChanged(self, frequency):
        """Called when the sonication frequency changes"""
        self.currentFrequency = frequency
        
        # Update frequency display with formatted value
        if frequency > 0:
            from pyqtgraph import siFormat
            self.currentFreqLabel.setText(siFormat(frequency, suffix='Hz'))
        else:
            self.currentFreqLabel.setText("0 Hz")
            
        # Update waveform visualization
        self.updateWaveform(frequency)
        
    def updateWaveform(self, frequency):
        """Update the waveform visualization based on current frequency"""
        import numpy as np
        
        if frequency <= 0:
            # Flat line when not sonicating
            x = np.linspace(0, 0.1, 1000)
            y = np.zeros_like(x)
        else:
            # Simple sine wave visualization
            period = 1.0 / frequency
            x = np.linspace(0, min(5 * period, 0.0001), 1000)  # Show 5 cycles or max 0.1ms
            y = np.sin(2 * np.pi * frequency * x)
            
        self.waveformCurve.setData(x, y)
