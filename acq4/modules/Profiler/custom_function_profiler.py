# ABOUTME: Custom function profiling using acq4.util.function_profiler with hierarchical call tree display
# ABOUTME: Provides call structure visualization with lazy loading for large profiles
import sys
import threading
from datetime import datetime
from acq4.util import Qt
from acq4.util.function_profiler import Profile


class NumericalTreeWidgetItem(Qt.QTreeWidgetItem):
    """Tree widget item that sorts numerical columns properly"""

    def __lt__(self, other):
        """Custom comparison for proper numerical sorting"""
        if not isinstance(other, Qt.QTreeWidgetItem):
            return super().__lt__(other)

        tree = self.treeWidget()
        if not tree:
            return super().__lt__(other)

        column = tree.sortColumn()

        # Get UserRole data for numerical comparison
        self_data = self.data(column, Qt.Qt.UserRole)
        other_data = other.data(column, Qt.Qt.UserRole)

        # If both have numerical data, use it for comparison
        if self_data is not None and other_data is not None:
            try:
                return float(self_data) < float(other_data)
            except (ValueError, TypeError):
                pass

        # Fall back to text comparison
        return self.text(column) < other.text(column)


class ProfileResult:
    """Container for a single custom function profiling session result"""

    def __init__(self, name, start_time, hierarchical_data):
        self.name = name
        self.start_time = start_time
        self.end_time = datetime.now()
        self.hierarchical_data = hierarchical_data
        self.duration = (self.end_time - self.start_time).total_seconds()


class LazyCallItem(NumericalTreeWidgetItem):
    """Tree item that lazy-loads function call children"""

    def __init__(self, parent, call_id, record, hierarchical_data, thread_id, parent_duration=None, profiler=None):
        super().__init__(parent)
        self.call_id = call_id
        self.record = record
        self.hierarchical_data = hierarchical_data
        self.thread_id = thread_id
        self.parent_duration = parent_duration
        self.profiler = profiler
        self.children_loaded = False

        # Set item data
        self._populate_item_data()

        # Register this item for function highlighting
        self._register_for_highlighting()

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

        # Calculate percentage of parent duration
        percentage_value = 0.0
        percentage_text = ""
        if self.parent_duration and self.parent_duration > 0:
            percentage_value = (duration / self.parent_duration) * 100
            percentage_text = f"{percentage_value:.1f}"

        # Format display text
        short_filename = filename.split('/')[-1] if '/' in filename else filename
        duration_ms = duration * 1000
        start_time_ms = start_time * 1000

        self.setText(0, func_name)
        self.setText(1, f"{duration_ms:.3f}")
        self.setText(2, f"{start_time_ms:.3f}")
        self.setText(3, percentage_text)
        self.setText(4, f"{short_filename}:{line_no}")

        # Store numeric values for sorting using Qt.UserRole (in ms for consistency)
        self.setData(1, Qt.Qt.UserRole, duration_ms)
        self.setData(2, Qt.Qt.UserRole, start_time_ms)
        self.setData(3, Qt.Qt.UserRole, percentage_value)

    def _register_for_highlighting(self):
        """Register this item for function highlighting"""
        if not self.profiler:
            return

        func_name = self.record[5]  # func_qualified_name
        if func_name not in self.profiler.function_to_items:
            self.profiler.function_to_items[func_name] = []
        self.profiler.function_to_items[func_name].append(self)

    def load_children(self):
        """Load child function calls"""
        if self.children_loaded:
            return

        # Remove dummy child
        if hasattr(self, '_dummy_child'):
            self.removeChild(self._dummy_child)

        thread_data = self.hierarchical_data[self.thread_id]
        child_call_ids = thread_data['children'].get(self.call_id, [])

        # Get this call's duration to pass as parent duration to children
        call_id, parent_id, thread_id, start_time, end_time, func_name, filename, line_no = self.record
        my_duration = (end_time - start_time) if end_time else 0

        for child_call_id in child_call_ids:
            child_record = thread_data['records'][child_call_id]
            LazyCallItem(self, child_call_id, child_record, self.hierarchical_data, self.thread_id, my_duration, self.profiler)

        self.children_loaded = True


class LazyThreadItem(NumericalTreeWidgetItem):
    """Tree item that lazy-loads thread root calls"""

    def __init__(self, parent, thread_id, thread_info, hierarchical_data, profiler=None):
        super().__init__(parent)
        self.thread_id = thread_id
        self.thread_info = thread_info
        self.hierarchical_data = hierarchical_data
        self.profiler = profiler
        self.children_loaded = False

        # Get thread start time from thread_info
        thread_start_time = thread_info['start_time']
        thread_duration_ms = thread_info['total_time'] * 1000
        thread_start_time_ms = thread_start_time * 1000

        # Set thread display data
        self.setText(0, f"{thread_info['name']} ({thread_id})")
        self.setText(1, f"{thread_duration_ms:.3f}")
        self.setText(2, f"{thread_start_time_ms:.3f}")
        self.setText(3, "100.0")  # Threads are always 100% of themselves
        self.setText(4, f"{thread_info['call_count']} calls")

        # Store numeric values for sorting using Qt.UserRole (in ms for consistency)
        self.setData(1, Qt.Qt.UserRole, thread_duration_ms)
        self.setData(2, Qt.Qt.UserRole, thread_start_time_ms)
        self.setData(3, Qt.Qt.UserRole, 100.0)

        # Add dummy child
        self._dummy_child = Qt.QTreeWidgetItem(self)
        self._dummy_child.setText(0, "Loading...")

    def load_children(self):
        """Load root function calls for this thread"""
        if self.children_loaded:
            return

        # Remove dummy child
        if hasattr(self, '_dummy_child'):
            self.removeChild(self._dummy_child)

        thread_data = self.hierarchical_data[self.thread_id]
        thread_total_time = self.thread_info['total_time']

        for call_id in thread_data['root_calls']:
            record = thread_data['records'][call_id]
            LazyCallItem(self, call_id, record, self.hierarchical_data, self.thread_id, thread_total_time, self.profiler)

        self.children_loaded = True


class CustomFunctionProfiler(Qt.QObject):
    """Handles custom function profiling using acq4.util.function_profiler with hierarchical display"""

    # Signal emitted when profiler finishes automatically
    profilerFinished = Qt.Signal()

    def __init__(self, parent_widget):
        super().__init__()
        self.parent = parent_widget
        self.is_profiling = False
        self.current_profiler = None
        self.current_session_start = None
        self.profile_results = []

        # Function highlighting system
        self.function_to_items = {}  # {function_name: [list of tree items]}
        self.currently_highlighted_function = None

        # Check Python version requirement
        self.python_version_ok = sys.version_info >= (3, 12)

        # Connect signal to handler with queued connection for thread safety
        self.profilerFinished.connect(self._handleProfilerFinished, Qt.Qt.QueuedConnection)

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
            main_splitter = Qt.QSplitter(Qt.Qt.Horizontal)
            layout.addWidget(main_splitter)

            # Left side: Profile results list
            self.results_list = Qt.QListWidget()
            self.results_list.itemSelectionChanged.connect(self._onResultSelected)
            main_splitter.addWidget(self.results_list)

            # Right side: Vertical splitter for call tree and detail view
            right_splitter = Qt.QSplitter(Qt.Qt.Vertical)
            main_splitter.addWidget(right_splitter)

            # Top right container: Call tree with function info label
            top_container = Qt.QWidget()
            top_layout = Qt.QVBoxLayout(top_container)
            top_layout.setContentsMargins(0, 0, 0, 0)
            top_layout.setSpacing(2)

            # Function info label
            self.function_info_label = Qt.QLabel("Select a function to see details")
            self.function_info_label.setStyleSheet("font-weight: bold; padding: 4px; background-color: #f0f0f0; border: 1px solid #ccc;")
            self.function_info_label.setWordWrap(True)
            top_layout.addWidget(self.function_info_label)

            # Call tree display
            self.call_tree = Qt.QTreeWidget()
            self.call_tree.setHeaderLabels(['Function Call', 'Duration (ms)', 'Start Time (ms)', 'Percentage (%)', 'Location'])
            self.call_tree.setSortingEnabled(True)
            self.call_tree.sortByColumn(1, Qt.Qt.DescendingOrder)  # Default sort by duration
            self.call_tree.itemExpanded.connect(self._onItemExpanded)
            self.call_tree.itemSelectionChanged.connect(self._onCallTreeSelectionChanged)
            self.call_tree.setColumnWidth(0, 250)  # Set first column width
            top_layout.addWidget(self.call_tree)

            right_splitter.addWidget(top_container)

            # Bottom right: Function detail view
            self.detail_tree = Qt.QTreeWidget()
            self.detail_tree.setHeaderLabels(['Name', 'Calls', 'Percentage (%)', 'Total (ms)', 'Avg (ms)', 'Min (ms)', 'Max (ms)'])
            self.detail_tree.setSortingEnabled(True)
            self.detail_tree.setColumnWidth(0, 250)  # Set first column width
            right_splitter.addWidget(self.detail_tree)

            # Set splitter proportions
            main_splitter.setSizes([200, 800])
            right_splitter.setSizes([400, 300])

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

        # Max duration input
        layout.addWidget(Qt.QLabel("Max Duration (s):"))
        self.max_duration_edit = Qt.QLineEdit()
        self.max_duration_edit.setText("0")
        self.max_duration_edit.setToolTip("Maximum profiling duration in seconds (0 for no limit)")
        layout.addWidget(self.max_duration_edit)

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
        # Parse max depth
        max_depth_text = self.max_depth_edit.text().strip()
        max_depth = int(max_depth_text) if max_depth_text else None

        # Parse max duration
        max_duration_text = self.max_duration_edit.text().strip()
        max_duration = float(max_duration_text) if max_duration_text else 0

        # Create and start profiler with callback for auto-stop notification
        self.current_profiler = Profile(
            max_depth=max_depth,
            max_duration=max_duration,
            on_finished=self._onProfilerFinished
        )
        self.current_profiler.start()

        self.is_profiling = True
        self.current_session_start = datetime.now()

        self.start_stop_btn.setText("Stop Profiling")
        self.start_stop_btn.setStyleSheet("background-color: #ff4444;")

    def _stopProfiling(self):
        """End current profiling session and store results"""
        if not self.is_profiling or self.current_profiler is None:
            return

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

    def _onProfilerFinished(self):
        """Callback invoked when profiler finishes automatically"""
        # Emit signal to safely update UI from another thread
        self.profilerFinished.emit()

    def _handleProfilerFinished(self):
        """Handle profiler auto-stop in the main thread"""
        if self.is_profiling and self.current_profiler is not None:
            # Call the normal stop method to handle UI updates
            self._stopProfiling()

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

        # Clear function highlighting mapping
        self.function_to_items.clear()
        self.currently_highlighted_function = None

        # Create thread items
        for thread_id, thread_data in result.hierarchical_data.items():
            thread_info = thread_data['thread_info']
            LazyThreadItem(self.call_tree, thread_id, thread_info, result.hierarchical_data, self)

        # Auto-resize columns to fit content
        for i in range(self.call_tree.columnCount()):
            self.call_tree.resizeColumnToContents(i)

    def _onItemExpanded(self, item):
        """Handle tree item expansion for lazy loading"""
        if isinstance(item, LazyThreadItem):
            item.load_children()
        elif isinstance(item, LazyCallItem):
            item.load_children()

    def _onCallTreeSelectionChanged(self):
        """Handle selection change in call tree to update detail view"""
        selected_items = self.call_tree.selectedItems()
        if not selected_items:
            self.detail_tree.clear()
            self.function_info_label.setText("Select a function to see details")
            self._clearHighlighting()
            return

        # Get the current profile result
        current_result_item = self.results_list.currentItem()
        if not current_result_item:
            return

        result = current_result_item.data(Qt.Qt.UserRole)
        if not result:
            return

        # Get the selected function name
        selected_item = selected_items[0]
        if isinstance(selected_item, LazyCallItem):
            # Extract function info from the record
            func_name = selected_item.record[5]  # func_qualified_name
            filename = selected_item.record[6]  # filename
            line_no = selected_item.record[7]  # line_no

            # Update function info label
            self._updateFunctionInfoLabel(func_name, filename, line_no)

            # Highlight all instances of this function
            self._highlightFunction(func_name)

            # Display function details
            self._displayFunctionDetails(func_name, result)
        elif isinstance(selected_item, LazyThreadItem):
            # Thread selected - clear detail view
            self.detail_tree.clear()
            self.function_info_label.setText("Select a function to see details")
            self._clearHighlighting()

    def _updateFunctionInfoLabel(self, func_name, filename, line_no):
        """Update the function info label with selected function details"""
        short_filename = filename.split('/')[-1] if '/' in filename else filename
        self.function_info_label.setText(f"Function: {func_name} | File: {filename} | Line: {line_no}")

    def _highlightFunction(self, func_name):
        """Highlight all instances of the specified function in the call tree"""
        # Clear previous highlighting
        self._clearHighlighting()

        # Store original backgrounds and highlight all instances of this function
        if func_name in self.function_to_items:
            for item in self.function_to_items[func_name]:
                # Store original background before changing it
                if not hasattr(item, '_original_background'):
                    item._original_background = item.background(0)

                # Apply highlight
                item.setBackground(0, Qt.QColor(255, 255, 0, 100))  # Light yellow highlight

        self.currently_highlighted_function = func_name

    def _clearHighlighting(self):
        """Clear all function highlighting by restoring original backgrounds"""
        if self.currently_highlighted_function and self.currently_highlighted_function in self.function_to_items:
            for item in self.function_to_items[self.currently_highlighted_function]:
                # Restore original background if we stored it
                if hasattr(item, '_original_background'):
                    item.setBackground(0, item._original_background)
                else:
                    # Fall back to clearing the background data entirely
                    item.setData(0, Qt.Qt.BackgroundRole, None)

        self.currently_highlighted_function = None

    def _displayFunctionDetails(self, func_name, result):
        """Display detailed analysis of the selected function"""
        self.detail_tree.clear()

        # Get profile data to analyze
        profile_data = self._getProfileDataFromResult(result)
        if not profile_data:
            return

        # Analyze the function
        analysis = profile_data.analyze_function(func_name)

        # Create the three main sections
        self._addTotalsSection(analysis['totals_by_thread'])
        self._addCallersSection(analysis['callers'])
        self._addSubcallsSection(analysis['subcalls'])

        # Auto-resize columns (skip first column which has fixed width)
        for i in range(1, self.detail_tree.columnCount()):
            self.detail_tree.resizeColumnToContents(i)

        # Auto-expand all sections
        self.detail_tree.expandAll()

    def _getProfileDataFromResult(self, result):
        """Extract Profile object from ProfileResult to access analyze_function method"""
        # We need to reconstruct or access the original Profile object
        # For now, let's create a temporary Profile with the data
        # This is a bit of a hack - ideally we'd store the Profile object in ProfileResult
        from acq4.util.function_profiler import Profile

        # Create a new Profile instance and populate it with the hierarchical data
        temp_profile = Profile()
        temp_profile._profile_start_time = 0  # Relative times already
        temp_profile._profile_end_time = max(
            data['thread_info']['total_time']
            for data in result.hierarchical_data.values()
        )

        # Reconstruct records from hierarchical data
        temp_profile._records = {}
        for thread_id, thread_data in result.hierarchical_data.items():
            for call_id, record in thread_data['records'].items():
                temp_profile._records[call_id] = record

        return temp_profile

    def _addTotalsSection(self, totals_by_thread):
        """Add totals section to detail tree"""
        if not totals_by_thread:
            return

        totals_item = NumericalTreeWidgetItem(self.detail_tree)
        totals_item.setText(0, "Totals")

        # Calculate overall totals
        total_calls = sum(stats['n_calls'] for stats in totals_by_thread.values())
        total_duration = sum(stats['total_duration'] for stats in totals_by_thread.values())

        # Calculate overall avg, min, max across all threads
        all_durations = []
        for stats in totals_by_thread.values():
            all_durations.extend(stats['durations'])

        if all_durations:
            avg_duration = total_duration / total_calls
            min_duration = min(all_durations)
            max_duration = max(all_durations)
        else:
            avg_duration = min_duration = max_duration = 0

        totals_item.setText(1, str(total_calls))
        totals_item.setText(3, f"{total_duration * 1000:.3f}")
        totals_item.setText(4, f"{avg_duration * 1000:.3f}")
        totals_item.setText(5, f"{min_duration * 1000:.3f}")
        totals_item.setText(6, f"{max_duration * 1000:.3f}")

        # Store numerical data for sorting
        totals_item.setData(1, Qt.Qt.UserRole, total_calls)
        totals_item.setData(3, Qt.Qt.UserRole, total_duration * 1000)
        totals_item.setData(4, Qt.Qt.UserRole, avg_duration * 1000)
        totals_item.setData(5, Qt.Qt.UserRole, min_duration * 1000)
        totals_item.setData(6, Qt.Qt.UserRole, max_duration * 1000)

        # Add per-thread breakdown
        for thread_id, stats in totals_by_thread.items():
            thread_item = NumericalTreeWidgetItem(totals_item)
            thread_item.setText(0, f"{stats['thread_name']} ({thread_id})")
            thread_item.setText(1, str(stats['n_calls']))
            thread_item.setText(2, f"{stats['percentage']:.1f}")
            thread_item.setText(3, f"{stats['total_duration'] * 1000:.3f}")
            thread_item.setText(4, f"{stats['avg_duration'] * 1000:.3f}")
            thread_item.setText(5, f"{stats['min_duration'] * 1000:.3f}")
            thread_item.setText(6, f"{stats['max_duration'] * 1000:.3f}")

            # Store numerical data for sorting
            thread_item.setData(1, Qt.Qt.UserRole, stats['n_calls'])
            thread_item.setData(2, Qt.Qt.UserRole, stats['percentage'])
            thread_item.setData(3, Qt.Qt.UserRole, stats['total_duration'] * 1000)
            thread_item.setData(4, Qt.Qt.UserRole, stats['avg_duration'] * 1000)
            thread_item.setData(5, Qt.Qt.UserRole, stats['min_duration'] * 1000)
            thread_item.setData(6, Qt.Qt.UserRole, stats['max_duration'] * 1000)

    def _addCallersSection(self, callers):
        """Add callers section to detail tree"""
        if not callers:
            return

        callers_item = NumericalTreeWidgetItem(self.detail_tree)
        callers_item.setText(0, "Callers")

        for caller_func, stats in callers.items():
            caller_item = NumericalTreeWidgetItem(callers_item)
            caller_item.setText(0, caller_func)
            caller_item.setText(1, str(stats['n_calls']))
            caller_item.setText(2, f"{stats['percentage']:.1f}")
            caller_item.setText(3, f"{stats['total_duration'] * 1000:.3f}")
            caller_item.setText(4, f"{stats['avg_duration'] * 1000:.3f}")
            caller_item.setText(5, f"{stats['min_duration'] * 1000:.3f}")
            caller_item.setText(6, f"{stats['max_duration'] * 1000:.3f}")

            # Store numerical data for sorting
            caller_item.setData(1, Qt.Qt.UserRole, stats['n_calls'])
            caller_item.setData(2, Qt.Qt.UserRole, stats['percentage'])
            caller_item.setData(3, Qt.Qt.UserRole, stats['total_duration'] * 1000)
            caller_item.setData(4, Qt.Qt.UserRole, stats['avg_duration'] * 1000)
            caller_item.setData(5, Qt.Qt.UserRole, stats['min_duration'] * 1000)
            caller_item.setData(6, Qt.Qt.UserRole, stats['max_duration'] * 1000)

    def _addSubcallsSection(self, subcalls):
        """Add subcalls section to detail tree"""
        if not subcalls:
            return

        subcalls_item = NumericalTreeWidgetItem(self.detail_tree)
        subcalls_item.setText(0, "Subcalls")

        for child_func, stats in subcalls.items():
            child_item = NumericalTreeWidgetItem(subcalls_item)
            child_item.setText(0, child_func)
            child_item.setText(1, str(stats['n_calls']))
            child_item.setText(2, f"{stats['percentage']:.1f}")
            child_item.setText(3, f"{stats['total_duration'] * 1000:.3f}")
            child_item.setText(4, f"{stats['avg_duration'] * 1000:.3f}")
            child_item.setText(5, f"{stats['min_duration'] * 1000:.3f}")
            child_item.setText(6, f"{stats['max_duration'] * 1000:.3f}")

            # Store numerical data for sorting
            child_item.setData(1, Qt.Qt.UserRole, stats['n_calls'])
            child_item.setData(2, Qt.Qt.UserRole, stats['percentage'])
            child_item.setData(3, Qt.Qt.UserRole, stats['total_duration'] * 1000)
            child_item.setData(4, Qt.Qt.UserRole, stats['avg_duration'] * 1000)
            child_item.setData(5, Qt.Qt.UserRole, stats['min_duration'] * 1000)
            child_item.setData(6, Qt.Qt.UserRole, stats['max_duration'] * 1000)

    def _clearProfiles(self):
        """Clear all custom function profile results"""
        self.profile_results.clear()
        self.results_list.clear()
        self.call_tree.clear()
        self.detail_tree.clear()
        self.function_to_items.clear()
        self.currently_highlighted_function = None
        self.function_info_label.setText("Select a function to see details")