import psutil
import pyqtgraph as pg
import time
import queue
import threading
from ..util import Qt


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
        self.metricsLabel = Qt.QLabel("CPU: ---%\nMemory: ---%\nQt activity: ---%\nQt latency: --- ms")
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

        # Initialize CPU monitoring (first call returns 0.0, subsequent calls are accurate)
        try:
            psutil.cpu_percent(interval=None)
        except Exception:
            pass

        # Start the thread
        self.monitorThread = threading.Thread(target=self._monitorThreadLoop, daemon=True)
        self.monitorThread.start()

    def _monitorThreadLoop(self):
        """Background thread loop that monitors resources once per second."""
        while self.threadRunning:
            data = {}

            # Measure CPU
            try:
                data['cpu'] = psutil.cpu_percent(interval=None)
            except Exception:
                data['cpu'] = None

            # Measure memory
            try:
                memory = psutil.virtual_memory()
                data['memory'] = memory.percent
            except Exception:
                data['memory'] = None

            # Measure Qt activity
            if self.hasQtProfiling:
                try:
                    app = Qt.QApplication.instance()
                    fraction = app.activity_fraction
                    if fraction is None:
                        data['qt_activity'] = None
                    else:
                        data['qt_activity'] = fraction * 100
                except Exception:
                    data['qt_activity'] = None
            else:
                data['qt_activity'] = None

            # Measure Qt latency
            latency_start = time.perf_counter()
            self.requestLatencyTimestamp.emit()

            # Wait for the GUI thread to respond
            try:
                gui_timestamp = self.latencyQueue.get(timeout=2.0)
                latency_ms = (gui_timestamp - latency_start) * 1000
                data['latency'] = latency_ms
            except queue.Empty:
                data['latency'] = None

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
            latency_value=data.get('latency')
        )
    
    def _updateMultilineDisplay(self, cpu_value=None, memory_value=None, qt_activity_value=None, latency_value=None):
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
            lines.append(f'<span style="color: {color};">Qt latency: {latency_value:.1f} ms</span>')

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