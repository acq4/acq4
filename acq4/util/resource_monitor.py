# ABOUTME: Resource monitor widget for displaying Qt activity and system memory usage
# ABOUTME: Provides a unified widget for monitoring system resources in ACQ4 applications

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
        
        # Qt profiling label
        self.qtProfileLabel = Qt.QLabel("Qt Activity: ---%")
        layout.addWidget(self.qtProfileLabel)
        
        # Memory usage label
        self.memoryLabel = Qt.QLabel("Memory: ---%")
        layout.addWidget(self.memoryLabel)
        
        # Qt latency label
        self.latencyLabel = Qt.QLabel("Qt latency: --- ms")
        layout.addWidget(self.latencyLabel)
        
        # Check if ProfiledQApplication is active
        app = Qt.QApplication.instance()
        if not hasattr(app, 'activity_fraction'):
            self.qtProfileLabel.setVisible(False)
    
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
    
    def _updateDisplays(self):
        """Update Qt profiling, memory usage, and latency displays."""
        # Start latency measurement
        self._startLatencyMeasurement()
        
        # Update Qt activity display
        app = Qt.QApplication.instance()
        if hasattr(app, 'activity_fraction'):
            try:
                fraction = app.activity_fraction
                if fraction is None:
                    self._updateLabel(self.qtProfileLabel, "Qt Activity", None, self.qtColormap)
                    return
                percentage = fraction * 100
                self._updateLabel(self.qtProfileLabel, "Qt Activity", percentage, self.qtColormap)
            except Exception:
                self._updateLabel(self.qtProfileLabel, "Qt Activity", None, self.qtColormap)
        
        # Update memory display
        try:
            memory = psutil.virtual_memory()
            percentage = memory.percent
            self._updateLabel(self.memoryLabel, "Memory", percentage, self.memoryColormap)
        except Exception:
            self._updateLabel(self.memoryLabel, "Memory", None, self.memoryColormap)
        
        # Update latency display with most recent measurement
        self._updateLatencyDisplay()
    
    def _updateLabel(self, label, prefix, percentage, colormap):
        """Update a label with percentage and colormap-based styling."""
        if percentage is None:
            label.setText(f"{prefix}: ---%")
            color = "#888888"  # Gray for error/unavailable
        else:
            label.setText(f"{prefix}: {percentage:.1f}%")
            # Map percentage (0-100) to colormap (0.0-1.0)
            normalized = min(max(percentage / 100.0, 0.0), 1.0)
            rgb = colormap.map(normalized, mode='byte')
            color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        
        self._setLabelStyle(label, color)
    
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
    
    def _updateLatencyDisplay(self):
        """Update the Qt latency display."""
        if self.currentLatency is None:
            self.latencyLabel.setText("Qt latency: --- ms")
            self._setLabelStyle(self.latencyLabel, "#888888")  # Gray
        else:
            # Map latency (0-500ms+) to colormap
            latency_ms = min(self.currentLatency, 500.0)  # Cap at 500ms for color mapping
            normalized = latency_ms / 500.0  # Normalize to 0.0-1.0 range
            rgb = self.latencyColormap.map(normalized, mode='byte')
            color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
            
            self.latencyLabel.setText(f"Qt latency: {self.currentLatency:.1f} ms")
            self._setLabelStyle(self.latencyLabel, color)
    
    def _setLabelStyle(self, label, color):
        """Set styling for a label with the given color."""
        label.setStyleSheet(f"""
            QLabel {{ 
                font-weight: bold; 
                color: {color};
                background-color: #f0f0f0;
                border: 1px solid #cccccc;
                border-radius: 3px;
                padding: 2px;
            }}
        """)
    
    def cleanup(self):
        """Stop the timers and clean up resources."""
        if hasattr(self, 'updateTimer'):
            self.updateTimer.stop()
        if hasattr(self, 'latencyTimer'):
            self.latencyTimer.stop()