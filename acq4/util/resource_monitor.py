import collections
import logging
import pyqtgraph as pg
import statistics
import time
import queue
import threading
from ..util import Qt

logger = logging.getLogger(__name__)

# 1 ms; longer intervals pick up Windows timer granularity, which swamps the
# baseline (median excess 0.5 ms vs 0.02).
GIL_PROBE_INTERVAL = 0.001
GIL_WINDOW = 3.0

_sampler_lock = threading.RLock()
_sampler_proc = None  # teleprox ChildProcess running the sampler
_sampler = None       # proxy to the remote resource_sampler module


def _remote_sampler():
    """Return a proxy to the out-of-process system sampler, starting it if needed."""
    global _sampler_proc, _sampler
    with _sampler_lock:
        if _sampler is not None:
            return _sampler
        import teleprox

        from acq4.logging_config import log_server

        _sampler_proc = teleprox.start_process(
            "resource_sampler",
            log_addr=getattr(log_server, "address", None),
            log_level="INFO",
            daemon=False,
            exit_on_parent_death=True,
        )
        mod = _sampler_proc.client._import("acq4.util.resource_sampler")
        mod.start(1.0, _timeout=30)
        _sampler = mod
        logger.info("Started out-of-process resource sampler (pid %s)",
                    getattr(_sampler_proc.proc, "pid", "?"))
        return _sampler


def shutdown_sampler():
    """Stop the sampler child, if one is running."""
    global _sampler_proc, _sampler
    with _sampler_lock:
        proc, _sampler = _sampler_proc, None
        _sampler_proc = None
        if proc is None:
            return
        try:
            proc.stop()
        except Exception:
            logger.warning("Error stopping the resource sampler process", exc_info=True)
        if proc.poll() is None:
            logger.warning("Resource sampler did not exit on request; killing it")
            proc.kill()


def sample_resources(app=None):
    """Return a one-shot resource sample: CPU %, memory %, and Qt activity %.

    CPU and memory come from the out-of-process sampler. qt_activity is
    app.activity_fraction * 100 when a ProfiledQApplication is active, else None.
    """
    remote = _remote_sampler().latest(_timeout=10, _return_type="value")
    qt_activity = None
    fraction = getattr(app, "activity_fraction", None) if app is not None else None
    if fraction is not None:
        qt_activity = fraction * 100
    return {
        "cpu_percent": remote.get("cpu_percent"),
        "memory_percent": remote.get("memory_percent"),
        "qt_activity": qt_activity,
    }


class GilLatencyProbe:
    """Measure how long a thread waits past a requested sleep, in ms.

    The excess is time the thread was runnable but not scheduled: in CPython,
    usually another thread holding the GIL. Samples from a daemon thread started
    in __init__ and ended by stop().
    """

    def __init__(self, interval=GIL_PROBE_INTERVAL, window=GIL_WINDOW):
        self.interval = interval
        self.window = window
        self._samples = collections.deque(maxlen=int(window / interval * 1.5))
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._loop, name="gil_latency_probe", daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.is_set():
            t0 = time.perf_counter()
            time.sleep(self.interval)
            t1 = time.perf_counter()
            with self._lock:
                self._samples.append((t1, (t1 - t0 - self.interval) * 1000))

    def stats(self):
        """Return (min, median, max) excess in ms over the window, or None."""
        cutoff = time.perf_counter() - self.window
        with self._lock:
            while self._samples and self._samples[0][0] < cutoff:
                self._samples.popleft()
            values = [v for _, v in self._samples]
        if not values:
            return None
        return min(values), statistics.median(values), max(values)

    def stop(self):
        self._stop.set()


class ResourceMonitorWidget(Qt.QWidget):
    """Widget for displaying Qt activity percentage and system memory usage.

    This widget provides real-time monitoring of:
    - Qt application activity percentage (if ProfiledQApplication is active)
    - System memory usage
    """

    # Signal to send resource data from background thread to GUI thread
    resourceDataReady = Qt.Signal(object)  # Will send dict with cpu, memory, qt_activity, latency

    # Signal to request latency measurement timestamp from GUI thread
    requestLatencyTimestamp = Qt.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setupColormaps()
        self._setupUI()
        self._startBackgroundThread()

    def _setupColormaps(self):
        """Setup colormaps for each label."""
        # Create colormap from green to orange to red
        colors = [(0, 128, 0), (0, 128, 0), (128, 100, 0), (180, 0, 0)]  # Green, Orange, Red
        positions = [0.0, 0.5, 0.75, 1.0]

        # Qt activity colormap (0-100%)
        self.qtColormap = pg.ColorMap(positions, colors)

        # Memory usage colormap (0-100%)
        self.memoryColormap = pg.ColorMap(positions, colors)

        # CPU usage colormap (0-100%) - same as Qt activity
        self.cpuColormap = pg.ColorMap(positions, colors)

        # Qt latency colormap (0ms to 500ms+)
        # Green at 1/60s (16.67ms), Red at 500ms
        latency_colors = [(0, 128, 0), (0, 128, 0), (128, 100, 0), (180, 0, 0)]  # Green, Orange, Red
        latency_positions = [0.0, 16.67/500.0, 0.5, 1.0]  # 0ms, 16.67ms (1/60s), 250ms, 500ms+
        self.latencyColormap = pg.ColorMap(latency_positions, latency_colors)

    def _setupUI(self):
        """Setup the user interface."""
        layout = Qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Single multiline label for all metrics
        self.metricsLabel = Qt.QLabel(
            "CPU: ---%\nMemory: ---%\nQt activity: ---%\nQt latency: --- ms\n"
            "GIL latency: --- ms")
        layout.addWidget(self.metricsLabel)

        # Store whether ProfiledQApplication is active for conditional display
        app = Qt.QApplication.instance()
        self.hasQtProfiling = hasattr(app, 'activity_fraction')

        # Connect signals with queued connections for thread safety
        self.resourceDataReady.connect(self._updateDisplays, Qt.Qt.QueuedConnection)
        self.requestLatencyTimestamp.connect(self._handleLatencyTimestampRequest, Qt.Qt.QueuedConnection)

    def _startBackgroundThread(self):
        """Start the background thread for resource monitoring."""
        # Queue for latency timestamp communication
        self.latencyQueue = queue.Queue()

        # Thread control
        self.threadRunning = True

        self.gilProbe = GilLatencyProbe()

        # Start the thread
        self.monitorThread = threading.Thread(target=self._monitorThreadLoop, daemon=True)
        self.monitorThread.start()

    def _monitorThreadLoop(self):
        """Background thread loop that monitors resources once per second."""
        while self.threadRunning:
            data = {}

            # Measure CPU, memory, and Qt activity via the shared sampling helper
            app = Qt.QApplication.instance()
            s = sample_resources(app)
            data['cpu'] = s['cpu_percent']
            data['memory'] = s['memory_percent']
            data['qt_activity'] = s['qt_activity']
            data['gil'] = self.gilProbe.stats()

            # Measure Qt latency
            latency_start = time.perf_counter()
            self.requestLatencyTimestamp.emit()

            # Wait for the GUI thread to respond
            gui_timestamp = self.latencyQueue.get()
            data['latency'] = gui_timestamp - latency_start

            # Send data to GUI thread
            self.resourceDataReady.emit(data)

            # Sleep for 1 second
            time.sleep(1.0)

    def _handleLatencyTimestampRequest(self):
        """Handle latency timestamp request from background thread (runs in GUI thread)."""
        self.latencyQueue.put(time.perf_counter())

    def _updateDisplays(self, data):
        """Update displays with resource data from background thread."""
        # Update the multiline display with the data
        self._updateMultilineDisplay(
            cpu_value=data.get('cpu'),
            memory_value=data.get('memory'),
            qt_activity_value=data.get('qt_activity'),
            latency_value=data.get('latency'),
            gil_value=data.get('gil'),
        )
    
    def _updateMultilineDisplay(self, cpu_value=None, memory_value=None, qt_activity_value=None,
                                latency_value=None, gil_value=None):
        """Update the multiline label with all metric values and colors."""
        lines = []

        # CPU line with color
        if cpu_value is None:
            lines.append('<span style="color: #888888;">CPU: ---%</span>')
        else:
            color = self._getColorFromValue(cpu_value, self.cpuColormap, 100.0)
            lines.append(f'<span style="color: {color};">CPU: {cpu_value:.1f}%</span>')

        # Memory line with color
        if memory_value is None:
            lines.append('<span style="color: #888888;">Memory: ---%</span>')
        else:
            color = self._getColorFromValue(memory_value, self.memoryColormap, 100.0)
            lines.append(f'<span style="color: {color};">Memory: {memory_value:.1f}%</span>')

        # Qt Activity line (only if profiling is available)
        if self.hasQtProfiling:
            if qt_activity_value is None:
                lines.append('<span style="color: #888888;">Qt Activity: ---%</span>')
            else:
                color = self._getColorFromValue(qt_activity_value, self.qtColormap, 100.0)
                lines.append(f'<span style="color: {color};">Qt Activity: {qt_activity_value:.1f}%</span>')

        # Qt Latency line with color
        if latency_value is None:
            lines.append('<span style="color: #888888;">Qt latency: --- ms</span>')
        else:
            color = self._getColorFromValue(latency_value, self.latencyColormap, 500.0)
            lines.append(f'<span style="color: {color};">Qt latency: {latency_value*1000:.1f} ms</span>')

        # GIL latency line, coloured by the worst sample in the window
        if gil_value is None:
            lines.append('<span style="color: #888888;">GIL latency: --- ms</span>')
        else:
            lo, mid, hi = gil_value
            color = self._getColorFromValue(hi, self.latencyColormap, 500.0)
            lines.append(f'<span style="color: {color};">'
                         f'GIL latency: {lo:.1f}/{mid:.1f}/{hi:.1f} ms</span>')

        # Set the multiline text with HTML formatting and apply styling
        self.metricsLabel.setText("<br>".join(lines))
        self._applyMultilineStyle()
    
    def _getColorFromValue(self, value, colormap, max_value):
        """Get hex color from value using the specified colormap."""
        normalized = min(max(value / max_value, 0.0), 1.0)
        rgb = colormap.map(normalized, mode='byte')
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
    
    def _applyMultilineStyle(self):
        """Apply styling to the multiline metrics label."""
        self.metricsLabel.setStyleSheet("""
            QLabel { 
                font-weight: bold; 
                color: #333333;
                background-color: #f0f0f0;
                border: 1px solid #cccccc;
                border-radius: 3px;
                padding: 4px;
                font-family: monospace;
            }
        """)
    
    def cleanup(self):
        self.threadRunning = False
        self.gilProbe.stop()
        shutdown_sampler()