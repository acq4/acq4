# -*- coding: utf-8 -*-
from __future__ import print_function

import time
import numpy as np
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

    Water is detected by analyzing the signal for 60Hz noise. When the sensor is in contact with
    water (which acts as a ground), the 60Hz noise disappears. When not in contact with water,
    60Hz noise is present on the line.

    Configuration options:

    * **channel** (dict): The AI channel configuration
        - **device** (str): Name of underlying DAQ device (e.g., 'NiDAQ')
        - **channel** (str): AI channel path (e.g., '/Dev1/ai0')
        - **type** (str): Must be 'ai'
        - **mode** (str, optional): Input mode (e.g., 'nrse', 'rse', 'diff')

    * **method** (str): Detection method to use. Currently only '60hz_ground' is supported.

    * **interval** (float): Polling interval in seconds (default: 5.0)

    * **threshold** (float): Z-score threshold for 60Hz detection (default: 2.0)
        The z-score is calculated from 9 FFT bins centered on 60Hz. The signal is the sum
        of the 3 center bins, compared to the standard deviation of the 6 flanking bins.
        A Hann window is applied before FFT to reduce spectral leakage. Water is detected
        when the z-score is below this threshold (indicating no 60Hz peak).

    * **recordDuration** (float): Duration to record for each check in seconds (default: 0.2)

    Emits sigWaterDetectionChanged(device, waterDetected) when water detection state changes.

    Example configuration::

        WaterSensor:
            driver: 'WaterSensor'
            channel:
                device: 'NiDAQ'
                channel: '/Dev1/ai0'
                type: 'ai'
                mode: 'nrse'
            method: '60hz_ground'
            interval: 5.0
            threshold: 2.0
            recordDuration: 0.2
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

        self.method = config.get('method', '60hz_ground')
        self.interval = config.get('interval', 5.0)
        self.threshold = config.get('threshold', 2.0)
        self.recordDuration = config.get('recordDuration', 0.2)

        # State tracking
        self._waterDetected = None  # None means not yet checked

        # Validate method
        if self.method != '60hz_ground':
            raise ValueError(f"Unknown detection method: {self.method}. Only '60hz_ground' is supported.")

        # Perform initial detection
        self._detect()

        # Set up periodic checking with background thread
        self.periodicThread = PeriodicDetectionThread(self, self.interval)
        self.periodicThread.start()

    def _detect(self):
        """
        Run the configured detection method and return True if water is detected, False otherwise.
        Updates internal state and emits signal if state changed.

        Returns
        -------
        dict
            Dictionary containing:
            - 'detected': bool, whether water was detected
            - 'data': ndarray, the raw signal data
            - 'time': ndarray, time values for the signal
            - 'zscore60': float, the measured 60Hz z-score
        """
        if self.method == '60hz_ground':
            result = self._detect60HzGround()
        else:
            raise ValueError(f"Unknown detection method: {self.method}")

        detected = result['detected']

        # Check if state changed
        with self.lock:
            previousState = self._waterDetected
            self._waterDetected = detected

        # Emit signal if state changed
        if previousState is not None and previousState != detected:
            self.sigWaterDetectionChanged.emit(self, detected)

        return result

    def _detect60HzGround(self):
        """
        Detect water by checking for absence of 60Hz noise.

        When the sensor is in contact with water (ground), 60Hz noise disappears.
        When not in contact, 60Hz noise is present above threshold.

        Returns dict with detection results and plotting data.
        """
        # Set up recording parameters
        rate = 10000  # 10kHz sample rate
        numPts = int(self.recordDuration * rate)

        # Get the underlying DAQ device name
        daq_name = self._daq.getDAQName("sensor")

        # Build task command following DAQSonicator pattern
        cmd = {
            'protocol': {
                'duration': self.recordDuration
            },
            daq_name: {
                'rate': rate,
                'numPts': numPts,
            },
            self._daq.name(): {
                'sensor': {
                    'record': True,
                }
            }
        }

        # Create and execute task
        task = self.dm.createTask(cmd)
        try:
            task.execute()

            # Get the recorded data
            result = task.getResult()
            data = result[self._daq.name()]['sensor'].asarray()

            # Create time array
            time = np.arange(len(data)) / rate

            # Apply Hann window to reduce spectral leakage
            window_func = np.hanning(len(data))
            data_windowed = data * window_func

            # Analyze for 60Hz content using FFT
            fft = np.fft.rfft(data_windowed)
            freqs = np.fft.rfftfreq(len(data), 1.0/rate)

            # Find the bin closest to 60Hz
            idx60 = np.argmin(np.abs(freqs - 60.0))

            # Get 9 bins: 3 centered on 60Hz + 3 on each side for baseline
            # Get amplitudes (normalized by number of samples)
            bins = np.abs(fft[idx60-4:idx60+5]) / len(data)

            # Signal: sum of 3 bins centered on 60Hz (idx-1, idx, idx+1)
            signal_bins = bins[3:6]  # [idx-1, idx, idx+1]
            signal_amplitude = np.sum(signal_bins)

            # Baseline: 6 bins flanking the signal (3 on each side)
            baseline_bins = np.concatenate([bins[0:3], bins[6:9]])  # [idx-4, idx-3, idx-2] + [idx+2, idx+3, idx+4]

            # Calculate z-score of signal relative to baseline
            std_baseline = np.std(baseline_bins)
            mean_baseline = np.mean(baseline_bins)

            if std_baseline > 0:
                zscore60 = (signal_amplitude - mean_baseline) / std_baseline
            else:
                # If std is zero, all baseline bins are identical
                # Set zscore based on whether signal differs from mean
                zscore60 = 0 if signal_amplitude == mean_baseline else np.inf

            # Water is detected if z-score is BELOW threshold
            # (water acts as ground and eliminates 60Hz peak, making z-score low)
            waterDetected = zscore60 < self.threshold

            return {
                'detected': waterDetected,
                'data': data,
                'time': time,
                'zscore60': zscore60
            }

        finally:
            # Clean up the task
            task.stop()


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
            return self._detect()['detected']
        else:
            with self.lock:
                return self._waterDetected

    def deviceInterface(self, win):
        """Return a widget with a UI to put in the device rack"""
        return DevGui(self)

    def quit(self):
        """Stop the periodic checking thread."""
        self.periodicThread.stop()
        self.periodicThread.wait()


class PeriodicDetectionThread(Qt.QThread):
    """Background thread that runs detection periodically"""

    def __init__(self, dev, interval):
        Qt.QThread.__init__(self)
        self.dev = dev
        self.interval = interval
        self.running = True

    def run(self):
        """Periodically run detection in background"""
        while self.running:
            try:
                self.dev._detect()
            except Exception as e:
                self.dev.logger.error(f"Error during periodic water detection check: {e}")

            # Sleep in small increments so we can stop quickly
            elapsed = 0
            while self.running and elapsed < self.interval:
                time.sleep(0.1)
                elapsed += 0.1

    def stop(self):
        """Stop the thread"""
        self.running = False


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
    """Live monitoring window with signal and amplitude plots"""

    closed = Qt.Signal()

    def __init__(self, dev):
        Qt.QWidget.__init__(self)
        self.dev = dev
        self.setWindowTitle(f"{self.dev.name()} - Live Monitoring")
        self.resize(800, 600)

        # Set up layout
        layout = Qt.QVBoxLayout()
        self.setLayout(layout)

        # Create graphics layout widget with two plots
        self.glw = pg.GraphicsLayoutWidget()
        layout.addWidget(self.glw)

        # Top plot: Raw signal
        self.signalPlot = self.glw.addPlot(row=0, col=0, title="Raw Signal")
        self.signalPlot.setLabel('left', 'Voltage', units='V')
        self.signalPlot.setLabel('bottom', 'Time', units='s')
        self.signalCurve = self.signalPlot.plot(pen='g')

        # Bottom plot: 60Hz z-score over time
        self.amplitudePlot = self.glw.addPlot(row=1, col=0, title="60Hz Z-Score")
        self.amplitudePlot.setLabel('left', 'Z-Score')
        self.amplitudePlot.setLabel('bottom', 'Time', units='s')
        self.amplitudeCurve = self.amplitudePlot.plot(pen='y')

        # Add threshold line to amplitude plot
        self.thresholdLine = pg.InfiniteLine(
            pos=self.dev.threshold,
            angle=0,
            pen=pg.mkPen('r', width=2, style=Qt.Qt.DashLine),
            label='Threshold'
        )
        self.amplitudePlot.addItem(self.thresholdLine)

        # Scrolling data buffer for amplitude plot
        self.maxDataPoints = 100
        self.amplitudeHistory = deque(maxlen=self.maxDataPoints)
        self.timeHistory = deque(maxlen=self.maxDataPoints)
        self.startTime = None

        # Create background thread for continuous detection
        self.running = True
        self.thread = DetectionThread(self.dev)
        self.thread.newData.connect(self.updatePlots)
        self.thread.start()

    def updatePlots(self, result):
        """Update both plots with new detection result"""
        # Update signal plot (replace data)
        self.signalCurve.setData(result['time'], result['data'])

        # Update z-score history (scrolling)
        if self.startTime is None:
            self.startTime = ptime.time()

        currentTime = ptime.time() - self.startTime
        self.timeHistory.append(currentTime)
        self.amplitudeHistory.append(result['zscore60'])

        # Update z-score plot
        self.amplitudeCurve.setData(list(self.timeHistory), list(self.amplitudeHistory))

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

    def stop(self):
        """Stop the thread"""
        self.running = False
