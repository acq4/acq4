from collections import deque

import numpy as np
import pyqtgraph as pg

from acq4.logging_config import get_logger
from acq4.modules.Module import Module
from acq4.util import Qt, ptime
from acq4.util.Thread import Thread

logger = get_logger(__name__)

MAX_LIVE_POINTS = 3000


def amplitudeSpectrum(data, rate):
    """Return (frequencies, amplitudes) of a Hann-windowed, mean-subtracted chunk.

    Amplitudes are in the units of *data* (a sine of amplitude A gives a peak of ~A).
    """
    data = np.asarray(data, dtype=float)
    data = data - data.mean()
    window = np.hanning(len(data))
    amps = np.abs(np.fft.rfft(data * window)) * 2 / window.sum()
    return np.fft.rfftfreq(len(data), 1.0 / rate), amps


class AcquisitionThread(Thread):
    """Repeatedly runs a finite AI task and emits each chunk until asked to stop."""

    sigChunk = Qt.Signal(object, float)  # samples, sample rate
    sigFailed = Qt.Signal()

    def __init__(self, manager, devName, channel, getParams):
        """*getParams* returns (rate, numPts, downsample) and is re-read before every chunk.

        numPts and rate describe the raw DAQ acquisition; the DAQ task averages
        *downsample* samples together, so emitted chunks have numPts // downsample
        samples at rate / downsample.
        """
        super().__init__(name="VibrationMonitor")
        self._manager = manager
        self._devName = devName
        self._channel = channel
        self._getParams = getParams
        self._stopRequested = False

    def requestStop(self):
        self._stopRequested = True

    def run(self):
        dev = self._manager.getDevice(self._devName)
        daqName = dev.getDAQName(self._channel)
        try:
            while not self._stopRequested:
                rate, numPts, downsample = self._getParams()
                cmd = {
                    'protocol': {'duration': numPts / rate},
                    daqName: {'rate': rate, 'numPts': numPts, 'downsample': downsample},
                    self._devName: {self._channel: {'record': True}},
                }
                task = self._manager.createTask(cmd)
                task.execute()
                result = task.getResult()
                data = result[self._devName].view(np.ndarray)[0]
                self.sigChunk.emit(data, rate / downsample)
        except Exception:
            logger.exception("Error in vibration acquisition thread, exiting.")
            self.sigFailed.emit()


class VibrationWindow(Qt.QMainWindow):
    sigWindowClosed = Qt.Signal(object)

    def __init__(self, manager, devName, channel):
        super().__init__()
        self.setWindowTitle("Vibration Monitor")
        self.resize(900, 1000)
        self._manager = manager
        self._devName = devName
        self._channel = channel

        self._thread = None
        self._retiring = []  # stopped threads that are still finishing their last chunk
        self._t0 = ptime.time()
        self._regionInitialized = False
        self._times = deque(maxlen=MAX_LIVE_POINTS)
        self._values = deque(maxlen=MAX_LIVE_POINTS)
        self._recording = False
        self._recTimes = []
        self._recValues = []
        self._recBand = None
        self._samples = []  # dicts: name, values, band

        self._buildUi()
        self._paramsChanged()
        self.runBtn.setChecked(True)

    # ---- UI ----

    def _buildUi(self):
        central = Qt.QWidget()
        self.setCentralWidget(central)
        layout = Qt.QVBoxLayout(central)

        acqRow = Qt.QHBoxLayout()
        self.runBtn = Qt.QPushButton("Run")
        self.runBtn.setCheckable(True)
        self.runBtn.toggled.connect(self._setRunning)
        self.rateSpin = pg.SpinBox(value=10000, bounds=(100, 250000), int=True, dec=True,
                                   minStep=1, suffix='Hz', siPrefix=True)
        self.chunkSpin = pg.SpinBox(value=10000, bounds=(64, 2000000), int=True, dec=True,
                                    minStep=1)
        self.downsampleSpin = pg.SpinBox(value=20, bounds=(1, 10000), int=True, dec=True,
                                         minStep=1)
        self.rateSpin.valueChanged.connect(self._paramsChanged)
        self.chunkSpin.valueChanged.connect(self._paramsChanged)
        self.downsampleSpin.valueChanged.connect(self._paramsChanged)
        self.infoLabel = Qt.QLabel()
        acqRow.addWidget(self.runBtn)
        acqRow.addWidget(Qt.QLabel("Sample rate:"))
        acqRow.addWidget(self.rateSpin)
        acqRow.addWidget(Qt.QLabel("Chunk size (samples):"))
        acqRow.addWidget(self.chunkSpin)
        acqRow.addWidget(Qt.QLabel("Downsample:"))
        acqRow.addWidget(self.downsampleSpin)
        layout.addLayout(acqRow)
        layout.addWidget(self.infoLabel)

        recRow = Qt.QHBoxLayout()
        self.nameEdit = Qt.QLineEdit()
        self.nameEdit.setPlaceholderText("Sample name (e.g. location)")
        self.recBtn = Qt.QPushButton("Start recording")
        self.recBtn.setCheckable(True)
        self.recBtn.toggled.connect(self._recordToggled)
        self.clearBtn = Qt.QPushButton("Clear samples")
        self.clearBtn.clicked.connect(self._clearSamples)
        recRow.addWidget(Qt.QLabel("Sample:"))
        recRow.addWidget(self.nameEdit, stretch=1)
        recRow.addWidget(self.recBtn)
        recRow.addWidget(self.clearBtn)
        layout.addLayout(recRow)

        glw = pg.GraphicsLayoutWidget()
        layout.addWidget(glw, stretch=1)

        self.specPlot = glw.addPlot(row=0, col=0, title="Spectrum (latest chunk)")
        self.specPlot.setLabel('left', 'Amplitude', units='V')
        self.specPlot.setLabel('bottom', 'Frequency', units='Hz')
        self.specPlot.setLogMode(y=True)
        self.specCurve = self.specPlot.plot(pen='y')
        self.region = pg.LinearRegionItem()
        self.specPlot.addItem(self.region)

        self.bandPlot = glw.addPlot(row=1, col=0, title="Summed amplitude in band")
        self.bandPlot.setLabel('left', 'Summed amplitude', units='V')
        self.bandPlot.setLabel('bottom', 'Time', units='s')
        self.liveCurve = self.bandPlot.plot(pen=pg.mkPen((150, 150, 150)))
        self.recCurve = self.bandPlot.plot(pen=pg.mkPen('r', width=2))

        self.samplePlot = glw.addPlot(row=2, col=0, title="Samples: mean ± SD")
        self.samplePlot.setLabel('left', 'Summed amplitude', units='V')
        self.errorBars = pg.ErrorBarItem(beam=0.15, pen=pg.mkPen('w', width=2))
        self.samplePlot.addItem(self.errorBars)
        self.meanPoints = self.samplePlot.plot(pen=None, symbol='o', symbolSize=10,
                                               symbolBrush='r')
        self._updateSamplePlot()

    # ---- acquisition ----

    def _paramsChanged(self, *_):
        rate = int(self.rateSpin.value())
        numPts = int(self.chunkSpin.value())
        downsample = int(self.downsampleSpin.value())
        self._params = (rate, numPts, downsample)
        effRate = rate / downsample
        self.infoLabel.setText(
            f"{numPts / rate:.3g} s/chunk, {numPts // downsample} samples at {effRate:.6g} Hz "
            f"after downsampling (averaged by the DAQ task); "
            f"{rate / numPts:.3g} Hz resolution, {effRate / 2:.6g} Hz Nyquist"
        )

    def _setRunning(self, run):
        if run and self._thread is None:
            thread = AcquisitionThread(self._manager, self._devName, self._channel,
                                       lambda: self._params)
            thread.sigChunk.connect(self._newChunk)
            thread.sigFailed.connect(self._acquisitionFailed)
            self._thread = thread
            self._specKey = None
            thread.start()
            self.recBtn.setEnabled(True)
        elif not run and self._thread is not None:
            if self._recording:
                self.recBtn.setChecked(False)
            self.recBtn.setEnabled(False)
            thread, self._thread = self._thread, None
            thread.requestStop()
            thread.sigChunk.disconnect(self._newChunk)
            thread.sigFailed.disconnect(self._acquisitionFailed)
            self._retiring.append(thread)
            thread.finished.connect(lambda t=thread: self._retiring.remove(t))

    def _acquisitionFailed(self):
        self.runBtn.setChecked(False)

    def _newChunk(self, data, rate):
        freqs, amps = amplitudeSpectrum(data, rate)
        self.specCurve.setData(freqs, amps)
        if self._specKey != (len(data), rate):
            self._specKey = (len(data), rate)
            self.specPlot.setXRange(0, rate / 2, padding=0)
        if not self._regionInitialized:
            self._regionInitialized = True
            nyquist = rate / 2
            self.region.setRegion((50, 100) if nyquist > 200 else (nyquist / 4, nyquist / 2))

        lo, hi = self.region.getRegion()
        value = float(amps[(freqs >= lo) & (freqs <= hi)].sum())
        t = ptime.time() - self._t0
        self._times.append(t)
        self._values.append(value)
        self.liveCurve.setData(np.array(self._times), np.array(self._values))
        if self._recording:
            self._recTimes.append(t)
            self._recValues.append(value)
            self.recCurve.setData(self._recTimes, self._recValues)

    # ---- recording ----

    def _recordToggled(self, recording):
        self._recording = recording
        self.region.setMovable(not recording)
        self.recBtn.setText("Stop recording" if recording else "Start recording")
        if recording:
            self._recTimes = []
            self._recValues = []
            self._recBand = tuple(self.region.getRegion())
            self.recCurve.setData([], [])
        else:
            self.recCurve.setData([], [])
            if self._recValues:
                name = self.nameEdit.text().strip() or f"sample {len(self._samples) + 1}"
                self._samples.append({
                    'name': name,
                    'values': np.array(self._recValues),
                    'band': self._recBand,
                })
                self._updateSamplePlot()

    def _clearSamples(self):
        self._samples = []
        self._updateSamplePlot()

    def _updateSamplePlot(self):
        axis = self.samplePlot.getAxis('bottom')
        n = len(self._samples)
        if n == 0:
            self.meanPoints.setData([], [])
            self.errorBars.setVisible(False)
            axis.setTicks(None)
            return
        x = np.arange(n)
        means = np.array([s['values'].mean() for s in self._samples])
        stds = np.array([s['values'].std(ddof=1) if len(s['values']) > 1 else 0.0
                         for s in self._samples])
        self.meanPoints.setData(x, means)
        self.errorBars.setData(x=x, y=means, height=2 * stds)
        self.errorBars.setVisible(True)
        axis.setTicks([[(i, s['name']) for i, s in enumerate(self._samples)]])
        self.samplePlot.setXRange(-0.5, n - 0.5)

    # ---- shutdown ----

    def quit(self):
        self.runBtn.setChecked(False)
        for thread in list(self._retiring):
            thread.wait(30000)

    def closeEvent(self, ev):
        self.sigWindowClosed.emit(self)
        ev.accept()


class VibrationMonitor(Module):
    """Records vibration from a DAQGeneric AI channel and compares band-limited levels.

    Plots the spectrum of each acquired chunk, the summed amplitude inside a
    user-selected frequency band over time, and mean +/- SD of that sum for each named
    recording.

    Configuration options:

    * **device** (str): DAQGeneric device name (default 'VibrationSensor')
    * **channel** (str): channel name on that device (default 'vibration')
    """
    moduleDisplayName = "Vibration Monitor"
    moduleCategory = "Utilities"

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.ui = VibrationWindow(
            manager,
            config.get('device', 'VibrationSensor'),
            config.get('channel', 'vibration'),
        )
        self.ui.sigWindowClosed.connect(self.quit)
        self.ui.show()

    def window(self):
        return self.ui

    def quit(self):
        self.ui.quit()
        Module.quit(self)
