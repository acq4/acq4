from acq4.modules.Module import Module
from acq4.util import Qt
from .qt_profiler import QtEventProfiler
from .memory_profiler import MemoryProfiler
from .new_profiler import NewProfiler


class Profiler(Module):
    """Performance profiling module for acq4

    Provides separate function profiling (yappi), Qt event profiling (ProfiledQApplication),
    and memory profiling (guppy/heapy) with clean separation of concerns.
    """
    moduleDisplayName = "Profiler"
    moduleCategory = "Utilities"

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.manager = manager

        self._setupUI()

    def _setupUI(self):
        """Initialize the user interface with tabbed profilers"""
        self.win = Qt.QMainWindow()
        self.win.setWindowTitle('Profiler')
        self.win.resize(1300, 800)

        # Central widget with tabs
        central_widget = Qt.QWidget()
        self.win.setCentralWidget(central_widget)
        layout = Qt.QVBoxLayout(central_widget)

        # Tab widget for different profiling views
        self.tab_widget = Qt.QTabWidget()
        layout.addWidget(self.tab_widget)

        # Create profiler instances
        self.qt_profiler = QtEventProfiler(self.win)
        self.memory_profiler = MemoryProfiler(self.win)
        self.function_profiler = NewProfiler(self.win)

        # Add tabs
        self.tab_widget.addTab(self.function_profiler.widget, "Function Profiler")
        self.tab_widget.addTab(self.qt_profiler.widget, "Qt Event Profile")
        self.tab_widget.addTab(self.memory_profiler.widget, "Memory Profile")

        self.win.show()

    def quit(self):
        """Stop all Qt profiles when the profiler module quits."""
        # Stop all active Qt profiles
        app = Qt.QApplication.instance()
        if hasattr(app, 'stop_all_profiles'):
            app.stop_all_profiles()

        # Call parent quit method
        super().quit()