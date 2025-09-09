# ABOUTME: Profiling module for monitoring acq4 performance and identifying bottlenecks
# ABOUTME: Provides function profiling via yappi and Qt event loop profiling via ProfiledQApplication
import yappi
import time
import re
from datetime import datetime
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.codeEditor import invokeCodeEditor
from pyqtgraph import TableWidget


class FunctionProfiler:
    """Handles function-level profiling using yappi and provides UI for control and display"""
    
    # Column definitions: (header, attribute, format_func)
    COLUMNS = [
        ('Function/Thread', 'name', str),
        ('Calls', 'ncall', str),
        ('Total Time', 'ttot', lambda x: f"{x:.6f}"),
        ('Sub Time', 'tsub', lambda x: f"{x:.6f}"),
        ('Avg Time', 'tavg', lambda x: f"{x:.6f}"),
        ('Location', 'full_name', str),
    ]
    
    def __init__(self, parent_widget):
        self.parent = parent_widget
        self.is_profiling = False
        self.current_session_start = None
        self.profile_results = []
        
        # Create UI
        self.widget = self._createUI()
    
    def _createUI(self):
        """Create the function profiling UI"""
        widget = Qt.QWidget()
        layout = Qt.QVBoxLayout(widget)
        
        # Control panel
        control_panel = self._createControlPanel()
        layout.addWidget(control_panel, 0)
        
        # Main splitter for results list and profile display
        splitter = Qt.QSplitter(Qt.Qt.Horizontal)
        layout.addWidget(splitter)
        
        # Left side: Profile results list
        self.results_list = Qt.QListWidget()
        self.results_list.itemSelectionChanged.connect(self._onResultSelected)
        splitter.addWidget(self.results_list)
        
        # Right side: Profile data display
        self.profile_display = Qt.QTreeWidget()
        self.profile_display.setHeaderLabels([col[0] for col in self.COLUMNS])
        self.profile_display.setSortingEnabled(True)
        self.profile_display.sortByColumn(2, Qt.Qt.DescendingOrder)
        self.profile_display.setExpandsOnDoubleClick(False)
        self.profile_display.itemDoubleClicked.connect(self._onItemDoubleClicked)
        splitter.addWidget(self.profile_display)
        
        # Set splitter proportions
        splitter.setSizes([200, 600])
        
        return widget
    
    def _createControlPanel(self):
        """Create the control panel with start/stop and view controls"""
        panel = Qt.QGroupBox("Function Profile Controls")
        panel.setSizePolicy(Qt.QSizePolicy.Preferred, Qt.QSizePolicy.Fixed)
        layout = Qt.QHBoxLayout(panel)
        
        # Start/Stop button
        self.start_stop_btn = Qt.QPushButton("Start Profiling")
        self.start_stop_btn.clicked.connect(self._toggleProfiling)
        layout.addWidget(self.start_stop_btn)
        
        # Session name input
        layout.addWidget(Qt.QLabel("Session Name:"))
        self.session_name_edit = Qt.QLineEdit()
        self.session_name_edit.setText(f"Profile_{len(self.profile_results) + 1}")
        layout.addWidget(self.session_name_edit)
        
        # View mode selector
        layout.addWidget(Qt.QLabel("View:"))
        self.view_mode_combo = Qt.QComboBox()
        self.view_mode_combo.addItems(["Grouped by Thread", "Combined Threads"])
        self.view_mode_combo.currentTextChanged.connect(self._onViewModeChanged)
        layout.addWidget(self.view_mode_combo)
        
        # Clock type selector
        layout.addWidget(Qt.QLabel("Clock:"))
        self.clock_type_combo = Qt.QComboBox()
        self.clock_type_combo.addItems(["CPU Time", "Wall Time"])
        layout.addWidget(self.clock_type_combo)
        
        layout.addStretch()
        
        return panel
    
    def _toggleProfiling(self):
        """Start or stop profiling session"""
        if self.is_profiling:
            self._stopProfiling()
        else:
            self._startProfiling()

    def _startProfiling(self):
        """Begin a new profiling session"""
        yappi.clear_stats()
        
        # Set clock type based on user selection
        clock_type = 'cpu' if self.clock_type_combo.currentText() == "CPU Time" else 'wall'
        yappi.set_clock_type(clock_type)
        
        yappi.start()
        
        self.is_profiling = True
        self.current_session_start = datetime.now()
        
        self.start_stop_btn.setText("Stop Profiling")
        self.start_stop_btn.setStyleSheet("background-color: #ff4444;")

    def _stopProfiling(self):
        """End current profiling session and store results"""
        if not self.is_profiling:
            return
            
        yappi.stop()
        
        # Collect profiling data
        func_stats = yappi.get_func_stats()
        thread_stats = yappi.get_thread_stats()
        
        # Create result object
        session_name = self.session_name_edit.text() or f"Profile_{len(self.profile_results) + 1}"
        result = ProfileResult(session_name, self.current_session_start, func_stats, thread_stats)
        self.profile_results.append(result)
        
        # Update UI
        self._addResultToList(result)
        self.is_profiling = False
        self.current_session_start = None
        
        self.start_stop_btn.setText("Start Profiling")
        self.start_stop_btn.setStyleSheet("")
        
        # Update session name for next run
        self.session_name_edit.setText(f"Profile_{len(self.profile_results) + 1}")

    def _addResultToList(self, result):
        """Add a profile result to the results list"""
        item_text = f"{result.name} ({result.start_time.strftime('%H:%M:%S')}) - {result.duration:.2f}s"
        item = Qt.QListWidgetItem(item_text)
        item.setData(Qt.Qt.UserRole, result)
        self.results_list.addItem(item)
        
        # Auto-select the new item
        self.results_list.setCurrentItem(item)

    def _onResultSelected(self):
        """Handle selection change in results list"""
        current_item = self.results_list.currentItem()
        if current_item is None:
            return
            
        result = current_item.data(Qt.Qt.UserRole)
        self._displayProfileResult(result)

    def _displayProfileResult(self, result):
        """Display profile result in the tree widget"""
        self.profile_display.clear()
        
        view_mode = self.view_mode_combo.currentText()
        
        if view_mode == "Grouped by Thread":
            self._displayGroupedByThread(result)
        else:  # Combined Threads
            self._displayCombinedThreads(result)
        
        # Auto-resize columns to fit content
        for i in range(self.profile_display.columnCount()):
            self.profile_display.resizeColumnToContents(i)

    def _onViewModeChanged(self):
        """Handle view mode change"""
        current_item = self.results_list.currentItem()
        if current_item is not None:
            result = current_item.data(Qt.Qt.UserRole)
            self._displayProfileResult(result)

    def _setItemColumns(self, item, data_obj=None, **custom_values):
        """Set item column values using COLUMNS definition"""
        for i, (header, attr, format_func) in enumerate(self.COLUMNS):
            if header in custom_values:
                value = custom_values[header]
            elif data_obj and hasattr(data_obj, attr):
                value = format_func(getattr(data_obj, attr))
            else:
                value = ""
            item.setText(i, value)

    def _displayGroupedByThread(self, result):
        """Display profile data grouped by thread with per-thread function breakdown"""
        # Display thread statistics first
        thread_stats_item = Qt.QTreeWidgetItem(self.profile_display)
        self._setItemColumns(thread_stats_item, **{'Function/Thread': f"Thread Statistics ({len(result.thread_stats)} threads)"})
        
        for thread_stat in result.thread_stats:
            if thread_stat.ttot > 0.000001:  # Skip empty threads
                thread_item = Qt.QTreeWidgetItem(thread_stats_item)
                thread_name = getattr(thread_stat, 'name', f"Thread {thread_stat.id}")
                self._setItemColumns(thread_item, thread_stat, **{'Function/Thread': thread_name})
        
        # Display functions grouped by thread
        for thread_stat in result.thread_stats:
            thread_funcs = [fs for fs in result.func_stats if getattr(fs, 'ctx_id', 0) == thread_stat.id]
            if len(thread_funcs) > 0:
                thread_name = getattr(thread_stat, 'name', f"Thread {thread_stat.id}")
                thread_func_item = Qt.QTreeWidgetItem(self.profile_display)
                self._setItemColumns(thread_func_item, **{'Function/Thread': f"{thread_name} Functions ({len(thread_funcs)})"})
                
                for func_stat in sorted(thread_funcs, key=lambda x: x.ttot, reverse=True):
                    self._addFunctionItem(thread_func_item, func_stat, result.func_stats)

    def _displayCombinedThreads(self, result):
        """Display thread stats and combined function stats separately"""
        # Display thread statistics
        thread_stats_item = Qt.QTreeWidgetItem(self.profile_display)
        self._setItemColumns(thread_stats_item, **{'Function/Thread': f"Thread Statistics ({len(result.thread_stats)} threads)"})
        
        for thread_stat in result.thread_stats:
            if thread_stat.ttot > 0.000001:  # Skip empty threads
                thread_item = Qt.QTreeWidgetItem(thread_stats_item)
                thread_name = getattr(thread_stat, 'name', f"Thread {thread_stat.id}")
                self._setItemColumns(thread_item, thread_stat, **{'Function/Thread': thread_name})
        
        # Display combined function statistics
        func_stats_item = Qt.QTreeWidgetItem(self.profile_display)
        self._setItemColumns(func_stats_item, **{'Function/Thread': f"Function Statistics ({len(result.func_stats)} functions)"})
        
        for func_stat in sorted(result.func_stats, key=lambda x: x.ttot, reverse=True):
            self._addFunctionItem(func_stats_item, func_stat, result.func_stats)

    def _addFunctionItem(self, parent_item, func_stat, all_func_stats):
        """Add a function item with subcalls and callers"""
        # Main function item
        func_item = Qt.QTreeWidgetItem(parent_item)
        self._setItemColumns(func_item, func_stat)
        func_item.func_stat = func_stat
        func_item.item_type = 'function'
        
        # Subcalls (children) section
        if hasattr(func_stat, 'children') and func_stat.children:
            subcalls_item = Qt.QTreeWidgetItem(func_item)
            self._setItemColumns(subcalls_item, **{'Function/Thread': f"Subcalls ({len(func_stat.children)})"})
            
            for child in sorted(func_stat.children, key=lambda x: x.ttot, reverse=True):
                child_item = Qt.QTreeWidgetItem(subcalls_item)
                self._setItemColumns(child_item, child)
                child_item.link_target = child.name
                child_item.item_type = 'link'
        
        # Callers section - find all functions that call this one
        callers = self._findCallers(func_stat.name, all_func_stats)
        if callers:
            callers_item = Qt.QTreeWidgetItem(func_item)
            self._setItemColumns(callers_item, **{'Function/Thread': f"Callers ({len(callers)})"})
            
            for caller_stat, child_stat in callers:
                caller_item = Qt.QTreeWidgetItem(callers_item)
                self._setItemColumns(caller_item, child_stat, **{'Function/Thread': caller_stat.name})
                caller_item.link_target = caller_stat.name
                caller_item.item_type = 'link'

    def _findCallers(self, func_name, all_func_stats):
        """Find all functions that call the specified function"""
        callers = []
        for stat in all_func_stats:
            if hasattr(stat, 'children'):
                for child in stat.children:
                    if child.name == func_name:
                        callers.append((stat, child))
        return callers

    def _onItemDoubleClicked(self, item, column):
        """Handle double-click on tree items to navigate to linked functions or open editor"""
        if hasattr(item, 'item_type'):
            if item.item_type == 'link':
                self._scrollToFunction(item.link_target)
            elif item.item_type == 'function':
                # Double-clicked on a function item - open in editor
                self._openInEditor(item.func_stat)

    def _scrollToFunction(self, func_name):
        """Scroll to and select the specified function in the tree"""
        # Find the function item in the tree
        iterator = Qt.QTreeWidgetItemIterator(self.profile_display)
        while iterator.value():
            item = iterator.value()
            if (hasattr(item, 'item_type') and item.item_type == 'function' and 
                hasattr(item, 'func_stat') and item.func_stat.name == func_name):
                self.profile_display.scrollToItem(item)
                self.profile_display.setCurrentItem(item)
                item.setExpanded(True)
                break
            iterator += 1

    def _openInEditor(self, func_stat):
        """Open function in code editor using module and lineno attributes"""
        if not (hasattr(func_stat, 'module') and hasattr(func_stat, 'lineno')):
            return
        
        file_path = func_stat.module
        line_num = func_stat.lineno
        
        try:
            invokeCodeEditor(file_path, line_num)
        except Exception as e:
            print(f"Failed to open editor for {file_path}:{line_num}: {e}")


class QtEventProfiler:
    """Handles Qt event loop profiling using ProfiledQApplication and provides UI for control and display"""
    
    def __init__(self, parent_widget):
        self.parent = parent_widget
        self.is_profiling = False
        self.current_profile = None
        self.profile_results = []
        
        # Create UI
        self.widget = self._createUI()
    
    def _createUI(self):
        """Create the Qt event profiling UI"""
        widget = Qt.QWidget()
        layout = Qt.QVBoxLayout(widget)
        
        # Control panel
        control_panel = self._createControlPanel()
        layout.addWidget(control_panel, 0)
        
        # Main splitter
        splitter = Qt.QSplitter(Qt.Qt.Horizontal)
        layout.addWidget(splitter)
        
        # Left side: Profile sessions list
        self.results_list = Qt.QListWidget()
        self.results_list.itemSelectionChanged.connect(self._onResultSelected)
        splitter.addWidget(self.results_list)
        
        # Right side: Vertical splitter with two panes
        right_splitter = Qt.QSplitter(Qt.Qt.Vertical)
        
        # Top pane: Event breakdown by type
        self.profile_display = Qt.QTreeWidget()
        headers = ['Event Type', 'Count', 'Total Time (s)', 'Avg Time (ms)', 'Percentage']
        self.profile_display.setHeaderLabels(headers)
        self.profile_display.setSortingEnabled(True)
        self.profile_display.sortByColumn(2, Qt.Qt.DescendingOrder)
        right_splitter.addWidget(self.profile_display)
        
        # Bottom pane: Most expensive individual events
        self.slow_events_display = Qt.QTreeWidget()
        slow_headers = ['Event Type', 'Duration (ms)', 'Receiver', 'Info']
        self.slow_events_display.setHeaderLabels(slow_headers)
        self.slow_events_display.setSortingEnabled(True)
        self.slow_events_display.sortByColumn(1, Qt.Qt.DescendingOrder)
        right_splitter.addWidget(self.slow_events_display)
        
        # Set right splitter proportions (60% top, 40% bottom)
        right_splitter.setSizes([360, 240])
        
        splitter.addWidget(right_splitter)
        
        # Set main splitter proportions
        splitter.setSizes([200, 600])
        
        return widget
    
    def _createControlPanel(self):
        """Create control panel for Qt event profiling"""
        panel = Qt.QGroupBox("Qt Event Profile Controls")
        panel.setSizePolicy(Qt.QSizePolicy.Preferred, Qt.QSizePolicy.Fixed)
        layout = Qt.QHBoxLayout(panel)
        
        # Start/Stop button
        self.start_stop_btn = Qt.QPushButton("Start Qt Profiling")
        self.start_stop_btn.clicked.connect(self._toggleProfiling)
        layout.addWidget(self.start_stop_btn)
        
        # Session name input
        layout.addWidget(Qt.QLabel("Session Name:"))
        self.session_name_edit = Qt.QLineEdit()
        self.session_name_edit.setText(f"Qt_Profile_{len(self.profile_results) + 1}")
        layout.addWidget(self.session_name_edit)
        
        # Slow threshold input
        layout.addWidget(Qt.QLabel("Slow Threshold (ms):"))
        self.slow_threshold_spin = Qt.QDoubleSpinBox()
        self.slow_threshold_spin.setRange(0.1, 1000.0)
        self.slow_threshold_spin.setValue(5.0)
        self.slow_threshold_spin.setSuffix(" ms")
        layout.addWidget(self.slow_threshold_spin)
        
        layout.addStretch()
        
        return panel
    
    def _toggleProfiling(self):
        """Start or stop Qt profiling session"""
        if self.is_profiling:
            self._stopProfiling()
        else:
            self._startProfiling()
    
    def _startProfiling(self):
        """Start a new Qt event profiling session"""
        # Get the QApplication instance
        app = Qt.QApplication.instance()
        if app is None:
            Qt.QMessageBox.warning(self.parent, "Warning", "No QApplication instance found")
            return
        
        # Check if it's a ProfiledQApplication
        if not hasattr(app, 'start_profile'):
            Qt.QMessageBox.warning(self.parent, "Warning", 
                                 "QApplication is not a ProfiledQApplication. Start acq4 with --qt-profile flag.")
            return
        
        # Start profiling session
        session_name = self.session_name_edit.text() or f"Qt_Profile_{len(self.profile_results) + 1}"
        slow_threshold = self.slow_threshold_spin.value()
        
        self.current_profile = app.start_profile(session_name, slow_threshold)
        
        # Update UI
        self.is_profiling = True
        self.start_stop_btn.setText("Stop Qt Profiling")
        self.start_stop_btn.setStyleSheet("background-color: #ff4444;")
        
    def _stopProfiling(self):
        """Stop the current Qt profiling session"""
        if self.current_profile is None:
            return
        
        # Stop the profile
        self.current_profile.stop()
        
        # Add to results list
        self._addResultToList(self.current_profile)
        self.profile_results.append(self.current_profile)
        
        # Reset UI
        self.is_profiling = False
        self.start_stop_btn.setText("Start Qt Profiling")
        self.start_stop_btn.setStyleSheet("")
        
        # Update session name for next run
        self.session_name_edit.setText(f"Qt_Profile_{len(self.profile_results) + 1}")
        
        self.current_profile = None
    
    def _addResultToList(self, profile):
        """Add a Qt profile result to the results list"""
        stats = profile.get_statistics()
        item_text = f"{stats['name']} ({stats['total_events']:,} events, {stats['wall_time']:.1f}s)"
        item = Qt.QListWidgetItem(item_text)
        item.setData(Qt.Qt.UserRole, profile)
        self.results_list.addItem(item)
        
        # Auto-select the new item
        self.results_list.setCurrentItem(item)
    
    def _onResultSelected(self):
        """Handle selection change in Qt results list"""
        current_item = self.results_list.currentItem()
        if current_item is None:
            return
        
        profile = current_item.data(Qt.Qt.UserRole)
        self._displayProfileResult(profile)
    
    def _displayProfileResult(self, profile):
        """Display Qt profile result in both tree widgets"""
        self.profile_display.clear()
        self.slow_events_display.clear()
        
        stats = profile.get_statistics()
        
        # Top pane: Event breakdown by type
        # Create summary item
        summary_item = Qt.QTreeWidgetItem(self.profile_display)
        summary_item.setText(0, f"Session: {stats['name']}")
        summary_item.setText(1, f"{stats['total_events']:,}")
        summary_item.setText(2, f"{stats['active_time']:.3f}")
        summary_item.setText(3, f"{stats['active_fraction']:.1%}")
        summary_item.setText(4, f"Wall: {stats['wall_time']:.1f}s")
        
        # Add event breakdown
        breakdown = profile.get_event_breakdown_by_type()
        for event_name, total_time, count, avg_time, percentage in breakdown:
            if count > 0:  # Only show events that actually occurred
                item = Qt.QTreeWidgetItem(self.profile_display)
                item.setText(0, event_name)
                item.setText(1, f"{count:,}")
                item.setText(2, f"{total_time:.6f}")
                item.setText(3, f"{avg_time*1000:.2f}")
                item.setText(4, f"{percentage:.1f}%")
        
        # Bottom pane: Most expensive individual events
        slow_events = sorted(stats['slow_events'], key=lambda x: x[0], reverse=True)[:50]
        for event_data in slow_events:
            if len(event_data) == 3:
                # Old format (duration, event_name, receiver)
                duration, event_name, receiver = event_data
                info = ""
            else:
                # New format (duration, event_name, receiver, info)
                duration, event_name, receiver, info = event_data
            
            item = Qt.QTreeWidgetItem(self.slow_events_display)
            item.setText(0, event_name)
            item.setText(1, f"{duration*1000:.2f}")
            item.setText(2, receiver)
            item.setText(3, info)
        
        # Auto-resize columns for both displays
        for i in range(self.profile_display.columnCount()):
            self.profile_display.resizeColumnToContents(i)
        for i in range(self.slow_events_display.columnCount()):
            self.slow_events_display.resizeColumnToContents(i)


class ProfileResult:
    """Container for a single function profiling session result"""
    
    def __init__(self, name, start_time, func_stats, thread_stats):
        self.name = name
        self.start_time = start_time
        self.end_time = datetime.now()
        self.func_stats = func_stats
        self.thread_stats = thread_stats
        self.duration = (self.end_time - self.start_time).total_seconds()


class Profiler(Module):
    """Performance profiling module for acq4
    
    Provides separate function profiling (yappi) and Qt event profiling (ProfiledQApplication)
    with clean separation of concerns and parallel UI implementations.
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
        self.win.resize(1000, 800)
        
        # Central widget with tabs
        central_widget = Qt.QWidget()
        self.win.setCentralWidget(central_widget)
        layout = Qt.QVBoxLayout(central_widget)
        
        # Tab widget for different profiling views
        self.tab_widget = Qt.QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Create profiler instances
        self.function_profiler = FunctionProfiler(self.win)
        self.qt_profiler = QtEventProfiler(self.win)
        
        # Add tabs
        self.tab_widget.addTab(self.function_profiler.widget, "Function Profile")
        self.tab_widget.addTab(self.qt_profiler.widget, "Qt Event Profile")
        
        self.win.show()