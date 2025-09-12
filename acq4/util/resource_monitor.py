import psutil
import pyqtgraph as pg
from ..util import Qt


class ResourceMonitorWidget(Qt.QWidget):
    """Widget for displaying Qt activity percentage and system memory usage.
    
    This widget provides real-time monitoring of:
    - Qt application activity percentage (if ProfiledQApplication is active)
    - System memory usage
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setupColormaps()
        self._setupUI()
        self._setupTimer()
        
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
    
    def _setupTimer(self):
        """Setup timers for updating resource displays and measuring Qt latency."""
        # Main update timer
        self.updateTimer = Qt.QTimer()
        self.updateTimer.timeout.connect(self._updateDisplays)
        self.updateTimer.start(1000)  # Update every second
        
        # Latency measurement timer (0ms single shot)
        self.latencyTimer = Qt.QTimer()
        self.latencyTimer.setSingleShot(True)
        self.latencyTimer.timeout.connect(self._latencyTimerFired)
        
        # Latency measurement variables
        self.latencyStartTime = None
        self.currentLatency = None
        
        # Initialize CPU monitoring (first call returns 0.0, subsequent calls are accurate)
        try:
            psutil.cpu_percent(interval=None)
        except Exception:
            pass
        
        # Initialize metric values for multiline display
        self.cpuValue = None
        self.memoryValue = None
        self.qtActivityValue = None
        self.latencyValue = None
    
    def _updateDisplays(self):
        """Update CPU, memory, Qt profiling, and latency displays."""
        # Start latency measurement
        self._startLatencyMeasurement()
        
        # Update CPU value
        try:
            self.cpuValue = psutil.cpu_percent(interval=None)  # Non-blocking call
        except Exception:
            self.cpuValue = None
        
        # Update memory value
        try:
            memory = psutil.virtual_memory()
            self.memoryValue = memory.percent
        except Exception:
            self.memoryValue = None
        
        # Update Qt activity value
        if self.hasQtProfiling:
            app = Qt.QApplication.instance()
            try:
                fraction = app.activity_fraction
                if fraction is None:
                    self.qtActivityValue = None
                else:
                    self.qtActivityValue = fraction * 100
            except Exception:
                self.qtActivityValue = None
        else:
            self.qtActivityValue = None
        
        # Update latency value (will be set by _latencyTimerFired)
        # No action needed here, latency is updated asynchronously
        
        # Update the multiline display
        self._updateMultilineDisplay()
    
    
    def _startLatencyMeasurement(self):
        """Start a latency measurement by recording current time and starting 0ms timer."""
        import time
        self.latencyStartTime = time.perf_counter()
        self.latencyTimer.start(0)  # Start 0ms timer
    
    def _latencyTimerFired(self):
        """Handle latency timer timeout - measure elapsed time."""
        if self.latencyStartTime is not None:
            import time
            elapsed = time.perf_counter() - self.latencyStartTime
            self.currentLatency = elapsed * 1000  # Convert to milliseconds
            self.latencyValue = self.currentLatency
            # Update display with new latency value
            self._updateMultilineDisplay()
    
    def _updateMultilineDisplay(self):
        """Update the multiline label with all metric values and colors."""
        lines = []
        
        # CPU line with color
        if self.cpuValue is None:
            lines.append('<span style="color: #888888;">CPU: ---%</span>')
        else:
            color = self._getColorFromValue(self.cpuValue, self.cpuColormap, 100.0)
            lines.append(f'<span style="color: {color};">CPU: {self.cpuValue:.1f}%</span>')
        
        # Memory line with color
        if self.memoryValue is None:
            lines.append('<span style="color: #888888;">Memory: ---%</span>')
        else:
            color = self._getColorFromValue(self.memoryValue, self.memoryColormap, 100.0)
            lines.append(f'<span style="color: {color};">Memory: {self.memoryValue:.1f}%</span>')
        
        # Qt Activity line (only if profiling is available)
        if self.hasQtProfiling:
            if self.qtActivityValue is None:
                lines.append('<span style="color: #888888;">Qt Activity: ---%</span>')
            else:
                color = self._getColorFromValue(self.qtActivityValue, self.qtColormap, 100.0)
                lines.append(f'<span style="color: {color};">Qt Activity: {self.qtActivityValue:.1f}%</span>')
        
        # Qt Latency line with color
        if self.latencyValue is None:
            lines.append('<span style="color: #888888;">Qt latency: --- ms</span>')
        else:
            color = self._getColorFromValue(self.latencyValue, self.latencyColormap, 500.0)
            lines.append(f'<span style="color: {color};">Qt latency: {self.latencyValue:.1f} ms</span>')
        
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
        """Stop the timers and clean up resources."""
        if hasattr(self, 'updateTimer'):
            self.updateTimer.stop()
        if hasattr(self, 'latencyTimer'):
            self.latencyTimer.stop()