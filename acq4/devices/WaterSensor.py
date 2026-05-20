# -*- coding: utf-8 -*-
from __future__ import print_function

import threading
import time
import pyqtgraph as pg
from acq4.devices.Device import Device
from acq4.devices.DAQGeneric import DAQGeneric
from acq4.util import Qt
from acq4.util.Mutex import Mutex
from acq4.util import ptime
from collections import deque


class WaterSensor(Device):
    """
    A device that detects the presence of water by monitoring an analog input channel on a DAQ.

    Water is detected by reading the voltage on the configured analog input channel.
    If the voltage is below a configured threshold, then water is considered detected.

    Configuration options:

    * **channel** (dict): The AI channel configuration
        - **device** (str): Name of underlying DAQ device (e.g., 'NiDAQ')
        - **channel** (str): AI channel path (e.g., '/Dev1/ai0')
        - **type** (str): Must be 'ai'
        - **mode** (str, optional): Input mode (e.g., 'nrse', 'rse', 'diff')

    * **interval** (float): Polling interval in seconds (default: 5.0)

    * **threshold** (float): Voltage threshold for water detection in volts (default: 2.5)
        Water is detected when measured voltage is below this threshold.

    Emits sigWaterDetectionChanged(device, waterDetected) when water detection state changes.

    Example configuration::

        WaterSensor:
            driver: 'WaterSensor'
            channel:
                device: 'NiDAQ'
                channel: '/Dev1/ai0'
                type: 'ai'
                mode: 'nrse'
            interval: 5.0
            threshold: 2.5
    """

    sigWaterDetectionChanged = Qt.Signal(object, object)  # self, waterDetected (bool)

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.lock = Mutex()

        # Create internal DAQGeneric device to manage the AI channel
        daq_conf = {
            "channels": {
                "sensor": config['channel'],
            }
        }
        self._daq = DAQGeneric(
            dm,
            config=daq_conf,
            name=f"__{name}DAQ",
        )

        self.interval = config.get('interval', 5.0)
        self.threshold = config.get('threshold', 2.5)

        # State tracking
        self._waterDetected = None  # None means not yet checked

        # Perform initial detection
        self._detect()

        self._run_poller = True
        self.pollThread = threading.Thread(target=self._pollSensor, daemon=True)
        self.pollThread.start()

    def _detect(self):
        """
        Read sensor voltage and return True if water is detected, False otherwise.
        Updates internal state and emits signal if state changed.

        Returns
        -------
        dict
            Dictionary containing:
            - 'detected': bool, whether water was detected
            - 'voltage': float, the measured sensor voltage in volts
        """
        voltage = self._daq.getChannelValue("sensor")
        detected = voltage < self.threshold

        # Check if state changed
        with self.lock:
            previousState = self._waterDetected
            self._waterDetected = detected

        # Emit signal if state changed
        if previousState != detected:
            self.sigWaterDetectionChanged.emit(self, detected)

        return detected

    def _pollSensor(self):
        """Background thread method to periodically check sensor state"""
        while self._run_poller:
            try:
                self._detect()
            except Exception as e:
                self.logger.warning(f"Error during water detection check: {e}", exc_info=True)
            time.sleep(self.interval)

    def waterDetected(self, refresh=False):
        """
        Return whether water was detected.

        Parameters
        ----------
        refresh : bool
            If True, immediately run detection again before returning result.
            If False, return the most recent detection result.

        Returns
        -------
        bool or None
            True if water is detected, False if not detected, None if never checked.
        """
        if refresh:
            return self._detect()
        else:
            return self._waterDetected

    def deviceInterface(self, win):
        """Return a widget with a UI to put in the device rack"""
        return DevGui(self)

    def quit(self):
        """Clean up resources when device is removed"""
        self._run_poller = False
        self._daq.quit()


class DevGui(Qt.QWidget):
    """Device interface widget for WaterSensor"""

    def __init__(self, dev):
        Qt.QWidget.__init__(self)
        self.dev = dev
        self.liveWindow = None

        # Set up layout
        self.layout = Qt.QVBoxLayout()
        self.setLayout(self.layout)

        # Status label
        self.statusLabel = Qt.QLabel()
        self.layout.addWidget(self.statusLabel)

        # Live monitoring button
        self.liveBtn = Qt.QPushButton("Live")
        self.liveBtn.setCheckable(True)
        self.liveBtn.toggled.connect(self.liveToggled)
        self.layout.addWidget(self.liveBtn)

        # Connect to device signal to update status
        self.dev.sigWaterDetectionChanged.connect(self.updateStatus)

        # Set initial status
        self.updateStatus(self.dev, self.dev.waterDetected())

    def updateStatus(self, dev, detected):
        """Update the status label based on water detection state"""
        if detected is None:
            self.statusLabel.setText("Water: Unknown")
        elif detected:
            self.statusLabel.setText("Water: Detected")
        else:
            self.statusLabel.setText("Water: Not Detected")

    def liveToggled(self, checked):
        """Handle Live button toggle"""
        if checked:
            # Open live window
            self.liveWindow = LiveWindow(self.dev)
            self.liveWindow.show()
            self.liveWindow.closed.connect(lambda: self.liveBtn.setChecked(False))
        else:
            # Close live window
            if self.liveWindow is not None:
                self.liveWindow.close()
                self.liveWindow = None


class LiveWindow(Qt.QWidget):
    """Live monitoring window with voltage history plot"""

    closed = Qt.Signal()

    def __init__(self, dev):
        Qt.QWidget.__init__(self)
        self.dev = dev
        self.setWindowTitle(f"{self.dev.name()} - Live Monitoring")
        self.resize(800, 600)

        # Set up layout
        layout = Qt.QVBoxLayout()
        self.setLayout(layout)

        # Create graphics layout widget with one plot
        self.glw = pg.GraphicsLayoutWidget()
        layout.addWidget(self.glw)

        # Voltage over time
        self.voltagePlot = self.glw.addPlot(row=0, col=0, title="Sensor Voltage")
        self.voltagePlot.setLabel('left', 'Voltage', units='V')
        self.voltagePlot.setLabel('bottom', 'Time', units='s')
        self.voltageCurve = self.voltagePlot.plot(pen='y')

        # Add threshold line to voltage plot
        self.thresholdLine = pg.InfiniteLine(
            pos=self.dev.threshold,
            angle=0,
            pen=pg.mkPen('r', width=2, style=Qt.Qt.DashLine),
            label='Threshold'
        )
        self.voltagePlot.addItem(self.thresholdLine)

        # Scrolling data buffer for voltage plot
        self.maxDataPoints = 100
        self.voltageHistory = deque(maxlen=self.maxDataPoints)
        self.timeHistory = deque(maxlen=self.maxDataPoints)
        self.startTime = None

        # Create background thread for continuous detection
        self.running = True
        self.thread = DetectionThread(self.dev)
        self.thread.newData.connect(self.updatePlots)
        self.thread.start()

    def updatePlots(self, result):
        """Update voltage history plot with new detection result"""
        if self.startTime is None:
            self.startTime = ptime.time()

        currentTime = ptime.time() - self.startTime
        self.timeHistory.append(currentTime)
        self.voltageHistory.append(result['voltage'])

        # Update voltage plot
        self.voltageCurve.setData(list(self.timeHistory), list(self.voltageHistory))

    def closeEvent(self, event):
        """Clean up when window is closed"""
        self.running = False
        self.thread.stop()
        self.thread.wait()
        self.closed.emit()
        event.accept()


class DetectionThread(Qt.QThread):
    """Background thread that continuously runs detection"""

    newData = Qt.Signal(object)  # Emits detection result dict

    def __init__(self, dev):
        Qt.QThread.__init__(self)
        self.dev = dev
        self.running = True

    def run(self):
        """Continuously run detection and emit results"""
        while self.running:
            try:
                result = self.dev._detect()
                self.newData.emit(result)
            except Exception as e:
                self.dev.logger.error(f"Error in live detection thread: {e}")
                # Continue running even if there's an error
            time.sleep(0.1)

    def stop(self):
        """Stop the thread"""
        self.running = False
