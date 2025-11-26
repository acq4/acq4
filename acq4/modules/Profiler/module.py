from acq4.modules.Module import Module
from acq4.util import Qt
from rtprofile.profiler_tabs import ProfilerTabs


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

        # Use the ProfilerTabs widget from rtprofile
        self.profiler_tabs = ProfilerTabs()
        self.win.setCentralWidget(self.profiler_tabs)

        self.win.show()

    def quit(self):
        """Stop all Qt profiles when the profiler module quits."""
        # The ProfilerTabs widget handles cleanup in its closeEvent
        # Call parent quit method
        super().quit()