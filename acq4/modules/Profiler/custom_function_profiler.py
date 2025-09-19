# ABOUTME: Custom function profiling using acq4.util.function_profiler with hierarchical call tree display
# ABOUTME: Provides call structure visualization with lazy loading for large profiles
import sys
import threading
from datetime import datetime
from acq4.util import Qt
from acq4.util.function_profiler import Profile


class ProfileResult:
    """Container for a single custom function profiling session result"""

    def __init__(self, name, start_time, hierarchical_data):
        self.name = name
        self.start_time = start_time
        self.end_time = datetime.now()
        self.hierarchical_data = hierarchical_data
        self.duration = (self.end_time - self.start_time).total_seconds()


class LazyCallItem(Qt.QTreeWidgetItem):
    """Tree item that lazy-loads function call children"""

    def __init__(self, parent, call_id, record, hierarchical_data, thread_id):
        super().__init__(parent)
        self.call_id = call_id
        self.record = record
        self.hierarchical_data = hierarchical_data
        self.thread_id = thread_id
        self.children_loaded = False

        # Set item data
        self._populate_item_data()

        # Add dummy child if this call has children
        thread_data = hierarchical_data[thread_id]
        if call_id in thread_data['children']:
            self._dummy_child = Qt.QTreeWidgetItem(self)
            self._dummy_child.setText(0, "Loading...")

    def _populate_item_data(self):
        """Populate item with function call data"""
        call_id, parent_id, thread_id, start_time, end_time, func_name, filename, line_no = self.record

        # Calculate duration
        duration = (end_time - start_time) if end_time else 0

        # Format display text
        short_filename = filename.split('/')[-1] if '/' in filename else filename
        self.setText(0, func_name)
        self.setText(1, f"{duration:.6f}s")
        self.setText(2, f"{short_filename}:{line_no}")

    def load_children(self):
        """Load child function calls"""
        if self.children_loaded:
            return

        try:
            # Remove dummy child
            if hasattr(self, '_dummy_child'):
                self.removeChild(self._dummy_child)

            thread_data = self.hierarchical_data[self.thread_id]
            child_call_ids = thread_data['children'].get(self.call_id, [])

            for child_call_id in child_call_ids:
                child_record = thread_data['records'][child_call_id]
                LazyCallItem(self, child_call_id, child_record, self.hierarchical_data, self.thread_id)

            self.children_loaded = True

        except Exception as e:
            error_item = Qt.QTreeWidgetItem(self)
            error_item.setText(0, f"Error loading children: {e}")


class LazyThreadItem(Qt.QTreeWidgetItem):
    """Tree item that lazy-loads thread root calls"""

    def __init__(self, parent, thread_id, thread_info, hierarchical_data):
        super().__init__(parent)
        self.thread_id = thread_id
        self.thread_info = thread_info
        self.hierarchical_data = hierarchical_data
        self.children_loaded = False

        # Set thread display data
        self.setText(0, f"Thread {thread_id} ({thread_info['name']})")
        self.setText(1, f"{thread_info['total_time']:.6f}s")
        self.setText(2, f"{thread_info['call_count']} calls")

        # Add dummy child
        self._dummy_child = Qt.QTreeWidgetItem(self)
        self._dummy_child.setText(0, "Loading...")

    def load_children(self):
        """Load root function calls for this thread"""
        if self.children_loaded:
            return

        try:
            # Remove dummy child
            if hasattr(self, '_dummy_child'):
                self.removeChild(self._dummy_child)

            thread_data = self.hierarchical_data[self.thread_id]

            for call_id in thread_data['root_calls']:
                record = thread_data['records'][call_id]
                LazyCallItem(self, call_id, record, self.hierarchical_data, self.thread_id)

            self.children_loaded = True

        except Exception as e:
            error_item = Qt.QTreeWidgetItem(self)
            error_item.setText(0, f"Error loading calls: {e}")


class CustomFunctionProfiler:
    """Handles custom function profiling using acq4.util.function_profiler with hierarchical display"""

    def __init__(self, parent_widget):
        self.parent = parent_widget
        self.is_profiling = False
        self.current_profiler = None
        self.current_session_start = None
        self.profile_results = []

        # Check Python version requirement
        self.python_version_ok = sys.version_info >= (3, 12)

        # Create UI
        self.widget = self._createUI()

    def _createUI(self):
        """Create the custom function profiling UI"""
        widget = Qt.QWidget()
        layout = Qt.QVBoxLayout(widget)

        # Main content area
        if not self.python_version_ok:
            # Show error message if Python version too low
            error_label = Qt.QLabel(
                f"Custom function profiling requires Python 3.12+ for threading.setprofile_all_threads() support.\n"
                f"Current version: {sys.version_info.major}.{sys.version_info.minor}"
            )
            error_label.setStyleSheet("color: red; font-weight: bold; padding: 20px;")
            error_label.setAlignment(Qt.Qt.AlignCenter)
            layout.addWidget(error_label)
        else:
            # Control panel
            control_panel = self._createControlPanel()
            layout.addWidget(control_panel, 0)

            # Main splitter for results list and call tree display
            splitter = Qt.QSplitter(Qt.Qt.Horizontal)
            layout.addWidget(splitter)

            # Left side: Profile results list
            self.results_list = Qt.QListWidget()
            self.results_list.itemSelectionChanged.connect(self._onResultSelected)
            splitter.addWidget(self.results_list)

            # Right side: Call tree display
            self.call_tree = Qt.QTreeWidget()
            self.call_tree.setHeaderLabels(['Function Call', 'Duration', 'Location'])
            self.call_tree.setSortingEnabled(False)  # Keep chronological order
            self.call_tree.itemExpanded.connect(self._onItemExpanded)
            splitter.addWidget(self.call_tree)

            # Set splitter proportions
            splitter.setSizes([200, 600])

        return widget

    def _createControlPanel(self):
        """Create the control panel with start/stop and session naming"""
        panel = Qt.QGroupBox("Custom Function Profile Controls")
        panel.setSizePolicy(Qt.QSizePolicy.Preferred, Qt.QSizePolicy.Fixed)
        layout = Qt.QHBoxLayout(panel)

        # Start/Stop button
        self.start_stop_btn = Qt.QPushButton("Start Profiling")
        self.start_stop_btn.clicked.connect(self._toggleProfiling)
        layout.addWidget(self.start_stop_btn)

        # Session name input
        layout.addWidget(Qt.QLabel("Session Name:"))
        self.session_name_edit = Qt.QLineEdit()
        self.session_name_edit.setText(f"Custom_Profile_{len(self.profile_results) + 1}")
        layout.addWidget(self.session_name_edit)

        # Max depth input
        layout.addWidget(Qt.QLabel("Max Depth:"))
        self.max_depth_edit = Qt.QLineEdit()
        self.max_depth_edit.setText("100")
        self.max_depth_edit.setToolTip("Maximum call stack depth to record (leave empty for unlimited)")
        layout.addWidget(self.max_depth_edit)

        # Clear profiles button
        self.clear_btn = Qt.QPushButton("Clear All")
        self.clear_btn.clicked.connect(self._clearProfiles)
        layout.addWidget(self.clear_btn)

        layout.addStretch()

        return panel

    def _toggleProfiling(self):
        """Start or stop profiling session"""
        if not self.python_version_ok:
            return

        if self.is_profiling:
            self._stopProfiling()
        else:
            self._startProfiling()

    def _startProfiling(self):
        """Begin a new custom function profiling session"""
        try:
            # Parse max depth
            max_depth_text = self.max_depth_edit.text().strip()
            max_depth = int(max_depth_text) if max_depth_text else None

            # Create and start profiler
            self.current_profiler = Profile(max_depth=max_depth)
            self.current_profiler.start()

            self.is_profiling = True
            self.current_session_start = datetime.now()

            self.start_stop_btn.setText("Stop Profiling")
            self.start_stop_btn.setStyleSheet("background-color: #ff4444;")

        except Exception as e:
            Qt.QMessageBox.warning(self.parent, "Profiling Error", f"Failed to start profiling: {e}")

    def _stopProfiling(self):
        """End current profiling session and store results"""
        if not self.is_profiling or self.current_profiler is None:
            return

        try:
            # Stop profiler and get hierarchical data
            self.current_profiler.stop()
            hierarchical_data = self.current_profiler.get_hierarchical_structure()

            # Create result object
            session_name = self.session_name_edit.text() or f"Custom_Profile_{len(self.profile_results) + 1}"
            result = ProfileResult(session_name, self.current_session_start, hierarchical_data)
            self.profile_results.append(result)

            # Update UI
            self._addResultToList(result)
            self.is_profiling = False
            self.current_session_start = None
            self.current_profiler = None

            self.start_stop_btn.setText("Start Profiling")
            self.start_stop_btn.setStyleSheet("")

            # Update session name for next run
            self.session_name_edit.setText(f"Custom_Profile_{len(self.profile_results) + 1}")

        except Exception as e:
            Qt.QMessageBox.warning(self.parent, "Profiling Error", f"Failed to stop profiling: {e}")

    def _addResultToList(self, result):
        """Add a profile result to the results list"""
        thread_count = len(result.hierarchical_data)
        total_calls = sum(data['thread_info']['call_count'] for data in result.hierarchical_data.values())

        item_text = f"{result.name} ({result.start_time.strftime('%H:%M:%S')}) - {result.duration:.2f}s - {total_calls} calls, {thread_count} threads"
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
        """Display profile result in the call tree"""
        self.call_tree.clear()

        # Create thread items
        for thread_id, thread_data in result.hierarchical_data.items():
            thread_info = thread_data['thread_info']
            LazyThreadItem(self.call_tree, thread_id, thread_info, result.hierarchical_data)

        # Auto-resize columns to fit content
        for i in range(self.call_tree.columnCount()):
            self.call_tree.resizeColumnToContents(i)

    def _onItemExpanded(self, item):
        """Handle tree item expansion for lazy loading"""
        if isinstance(item, LazyThreadItem):
            item.load_children()
        elif isinstance(item, LazyCallItem):
            item.load_children()

    def _clearProfiles(self):
        """Clear all custom function profile results"""
        self.profile_results.clear()
        self.results_list.clear()
        self.call_tree.clear()