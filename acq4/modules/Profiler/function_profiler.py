import sys
from datetime import datetime
from typing import Optional
from acq4.util import Qt
import pyqtgraph as pg
from pyqtgraph.console import ConsoleWidget
from acq4.util.profiler import Profile, CallRecord, ProfileAnalyzer, TreeDisplayData, ThreadDisplayData, FunctionAnalysis


class ProfileResult:
    """Container for a single profiling session result"""

    def __init__(self, name, start_time, profile):
        self.name = name
        self.start_time = start_time
        self.end_time = datetime.now()
        self.profile = profile  # The actual Profile instance
        self.events_data = profile.get_events()  # Result from profile.get_events()
        self.profile_start_time = profile.start_time  # perf_counter() time when profiling started
        self.profile_stop_time = profile.stop_time  # perf_counter() time when profiling stopped
        self.profile_duration = profile.stop_time - profile.start_time  # Actual profiling duration
        self.duration = (self.end_time - self.start_time).total_seconds()


class NumericalTreeWidgetItem(Qt.QTreeWidgetItem):
    """QTreeWidgetItem that sorts numerically instead of alphabetically"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._numerical_data = {}  # Store numerical values by column for sorting

    def __lt__(self, other):
        column = self.treeWidget().sortColumn()
        try:
            # Try to get numerical data from our attribute first
            my_data = self._numerical_data.get(column)
            other_data = getattr(other, '_numerical_data', {}).get(column)

            if my_data is not None and other_data is not None:
                return float(my_data) < float(other_data)

            # Fallback to text comparison
            return float(self.text(column)) < float(other.text(column))
        except (ValueError, TypeError):
            # Fallback to string comparison
            return self.text(column) < other.text(column)

    def _setNumericalData(self, column_values):
        """Set both text and numerical data for multiple columns

        Args:
            column_values: dict mapping column index to (text_value, numerical_value) tuples
        """
        for column, (text_val, num_val) in column_values.items():
            self.setText(column, text_val)
            self._numerical_data[column] = num_val

    def _setFields(self, **kwargs):
        """Set fields using named parameters with automatic formatting and column mapping

        Args:
            function_thread: Function/thread name (string)
            module: Module name (string)
            location: Location string
            duration: Duration in seconds (float) - automatically formatted to ms
            start_time: Start time in seconds (float) - automatically formatted to ms
            percent_of_parent: Percentage (float) - automatically formatted with % or "—"
        """
        # Handle text fields
        for name in ['function_thread', 'module', 'location']:
            if name in kwargs:
                column = getattr(FunctionProfiler.CallTreeColumns, name.upper())
                self.setText(column, kwargs[name])

        # Handle numerical fields with scaling and formatting
        numerical_fields = [
            ('duration', '{0:.3f}', 1000),
            ('start_time', '{0:.3f}', 1000),
            ('percent_of_parent', '{0:.1f}', 1),
        ]

        for name, format_str, scale in numerical_fields:
            if name in kwargs:
                value = kwargs[name]
                column = getattr(FunctionProfiler.CallTreeColumns, name.upper())
                self.setText(column, "—" if value is None else format_str.format(value * scale))
                self._numerical_data[column] = value or 0.0

    @staticmethod
    def _formatDuration(duration_seconds):
        """Format duration in seconds to milliseconds text

        Args:
            duration_seconds: Duration in seconds or None

        Returns:
            Formatted string (e.g., "123.456" or "—")
        """
        if duration_seconds is not None and duration_seconds > 0:
            return f"{duration_seconds * 1000:.3f}"
        else:
            return "—"


class LazyCallItem(NumericalTreeWidgetItem):
    """Tree item that lazy-loads child calls"""

    def __init__(self, parent, call_record: CallRecord, profile_start_time: float, profiler=None):
        super().__init__(parent)
        self.call_record: CallRecord = call_record
        self.profile_start_time = profile_start_time  # Store for child items
        self.profiler = profiler
        self.children_loaded = False

        # Use TreeDisplayData for all calculations
        display_data = TreeDisplayData(call_record, profile_start_time)

        # Use simple field-based approach (no more column number mapping!)
        self._setFields(
            function_thread=display_data.function_name,
            module=display_data.module,
            location=display_data.location,
            duration=display_data.duration_seconds,  # Raw seconds, _setFields formats to ms
            start_time=display_data.start_time_relative_seconds,  # Raw seconds, _setFields formats to ms
            percent_of_parent=display_data.parent_percentage
        )

        # Register this item for function highlighting
        self._register_for_highlighting()

        # Add dummy child if there are children to load
        if call_record.children:
            self._dummy_child = Qt.QTreeWidgetItem(self)
            self._dummy_child.setText(0, "Loading...")

    def _register_for_highlighting(self):
        """Register this item for function highlighting"""
        if not self.profiler:
            return

        function_key = self.call_record.function_key
        if function_key not in self.profiler.function_to_items:
            self.profiler.function_to_items[function_key] = []
        self.profiler.function_to_items[function_key].append(self)

    def load_children(self):
        """Load child calls for this item"""
        if self.children_loaded:
            return

        # Remove dummy child
        if hasattr(self, '_dummy_child'):
            self.removeChild(self._dummy_child)

        # Add child calls using stored profile_start_time
        for child_call in self.call_record.children:
            LazyCallItem(self, child_call, self.profile_start_time, self.profiler)

        self.children_loaded = True


class LazyThreadItem(NumericalTreeWidgetItem):
    """Tree item that lazy-loads thread root calls"""

    def __init__(self, parent, thread_id, thread_name, root_calls, profile_start_time, profile_duration, profiler=None):
        super().__init__(parent)
        self.thread_id = thread_id
        self.thread_name = thread_name
        self.root_calls = root_calls
        self.profile_start_time = profile_start_time  # Store for child items
        self.profiler = profiler
        self.children_loaded = False

        # Use ThreadDisplayData for all thread calculations
        thread_display_data = ThreadDisplayData(
            thread_id=thread_id,
            thread_name=thread_name,
            root_calls=root_calls,
            profile_duration=profile_duration,
            profile_start_time=profile_start_time
        )

        # Store total duration for percentage calculations by children
        self.total_duration = thread_display_data.total_duration_seconds

        # Use simple field-based approach (no more column number mapping!)
        self._setFields(
            function_thread=thread_display_data.display_name,
            module="—",  # Threads don't have a specific module
            location=f"{len(root_calls)} calls",
            duration=thread_display_data.total_duration_seconds,  # Raw seconds, _setFields formats to ms
            start_time=thread_display_data.start_time_relative_seconds,  # Raw seconds, _setFields formats to ms
            percent_of_parent=thread_display_data.parent_percentage  # None, _setFields will show "—"
        )

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

        # Add root calls
        for root_call in self.root_calls:
            LazyCallItem(self, root_call, self.profile_start_time, self.profiler)

        self.children_loaded = True


class FunctionProfiler(Qt.QObject):
    """Handles profiling using the new acq4.util.profiler with hierarchical display"""

    # Column indices for call tree (profile_display)
    class CallTreeColumns:
        FUNCTION_THREAD = 0
        DURATION = 1
        START_TIME = 2
        PERCENT_OF_PARENT = 3
        MODULE = 4
        LOCATION = 5

    # Column indices for detail tree
    class DetailTreeColumns:
        NAME = 0
        MODULE = 1
        CALLS = 2
        PERCENTAGE = 3
        TOTAL = 4
        AVG = 5
        MIN = 6
        MAX = 7

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
        self.function_to_items = {}  # {function_key: [list of tree items]}
        self.currently_highlighted_function = None

        # Check Python version requirement
        self.python_version_ok = sys.version_info >= (3, 12)

        # Connect signal to handler
        self.profilerFinished.connect(self._handleProfilerFinished, Qt.Qt.QueuedConnection)

        # Create UI
        self.widget = self._createUI()

    def _createUI(self):
        """Create the new profiler UI"""
        widget = Qt.QWidget()
        layout = Qt.QVBoxLayout(widget)

        # Main content area
        if not self.python_version_ok:
            # Show error message if Python version too low
            error_label = Qt.QLabel(
                f"New profiler requires Python 3.12+ for threading.setprofile_all_threads() support.\n"
                f"Current version: {sys.version_info.major}.{sys.version_info.minor}"
            )
            error_label.setStyleSheet("color: red; font-weight: bold; padding: 20px;")
            error_label.setAlignment(Qt.Qt.AlignCenter)
            layout.addWidget(error_label)
        else:
            # Control panel
            control_panel = self._createControlPanel()
            layout.addWidget(control_panel, 0)

            # Main horizontal splitter for results list and main content
            main_splitter = Qt.QSplitter(Qt.Qt.Horizontal)
            layout.addWidget(main_splitter)

            # Left side: Profile results list
            self.results_list = Qt.QListWidget()
            self.results_list.itemSelectionChanged.connect(self._onResultSelected)
            main_splitter.addWidget(self.results_list)

            # Right side: Vertical splitter for call tree (top) and tab widget (bottom)
            right_splitter = Qt.QSplitter(Qt.Qt.Vertical)
            main_splitter.addWidget(right_splitter)

            # Top: Call tree display
            self.profile_display = Qt.QTreeWidget()
            self.profile_display.setHeaderLabels([
                "Function/Thread", "Duration (ms)", "Start Time (ms)", "% of Parent", "Module", "Called from"
            ])
            self.profile_display.setSortingEnabled(True)
            self.profile_display.sortByColumn(FunctionProfiler.CallTreeColumns.DURATION, Qt.Qt.DescendingOrder)
            self.profile_display.setExpandsOnDoubleClick(False)
            self.profile_display.itemExpanded.connect(self._onItemExpanded)
            self.profile_display.itemSelectionChanged.connect(self._onCallTreeSelectionChanged)
            self.profile_display.setColumnWidth(FunctionProfiler.CallTreeColumns.FUNCTION_THREAD, 250)  # Set first column width
            right_splitter.addWidget(self.profile_display)

            # Bottom: Container for function info label and analysis tabs
            bottom_container = Qt.QWidget()
            bottom_layout = Qt.QVBoxLayout(bottom_container)
            bottom_layout.setContentsMargins(0, 0, 0, 0)
            bottom_layout.setSpacing(0)

            # Function info label (now inside bottom container)
            self.function_info_label = Qt.QLabel("Select a function to see details")
            self.function_info_label.setStyleSheet("font-weight: bold; padding: 4px; background-color: #f0f0f0; border: 1px solid #ccc;")
            self.function_info_label.setWordWrap(True)
            bottom_layout.addWidget(self.function_info_label)

            # Tab widget with Analysis and Console tabs
            self.bottom_tabs = Qt.QTabWidget()
            bottom_layout.addWidget(self.bottom_tabs)

            right_splitter.addWidget(bottom_container)

            # Analysis tab container
            analysis_container = Qt.QWidget()
            analysis_layout = Qt.QVBoxLayout(analysis_container)
            analysis_layout.setContentsMargins(0, 0, 0, 0)
            analysis_layout.setSpacing(2)

            # Function detail view
            self.detail_tree = Qt.QTreeWidget()
            self.detail_tree.setHeaderLabels(['Name', 'Module', 'Calls', 'Percentage (%)', 'Total (ms)', 'Avg (ms)', 'Min (ms)', 'Max (ms)'])
            self.detail_tree.setSortingEnabled(True)
            self.detail_tree.setColumnWidth(FunctionProfiler.DetailTreeColumns.NAME, 250)  # Set first column width
            analysis_layout.addWidget(self.detail_tree)

            # Console tab
            self.console = ConsoleWidget(namespace={'profiler': self})

            # Add tabs
            self.bottom_tabs.addTab(analysis_container, "Analysis")
            self.bottom_tabs.addTab(self.console, "Console")

            # Set splitter proportions
            main_splitter.setSizes([200, 800])
            right_splitter.setSizes([400, 325])  # call tree (top), bottom container (label + tabs)

        return widget

    def _createControlPanel(self):
        """Create the control panel with start/stop and view controls"""
        panel = Qt.QGroupBox("New Profiler Controls")
        panel.setSizePolicy(Qt.QSizePolicy.Preferred, Qt.QSizePolicy.Fixed)
        layout = Qt.QHBoxLayout(panel)

        # Start/Stop button
        self.start_stop_btn = Qt.QPushButton("Start Profiling")
        self.start_stop_btn.clicked.connect(self._toggleProfiling)
        layout.addWidget(self.start_stop_btn)

        # Session name input
        layout.addWidget(Qt.QLabel("Session Name:"))
        self.session_name_edit = Qt.QLineEdit()
        self.session_name_edit.setText(f"NewProfile_{len(self.profile_results) + 1}")
        layout.addWidget(self.session_name_edit)

        # Max duration input
        layout.addWidget(Qt.QLabel("Max Duration (s):"))
        self.max_duration_edit = Qt.QLineEdit()
        self.max_duration_edit.setText("0")
        self.max_duration_edit.setToolTip("Maximum profiling duration in seconds (0 = no limit)")
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
        """Begin a new profiling session"""
        # Parse max duration
        max_duration_text = self.max_duration_edit.text().strip()
        max_duration = float(max_duration_text) if max_duration_text else 0

        # Create and start profiler with callback for auto-stop notification
        self.current_profiler = Profile(
            max_duration=max_duration if max_duration > 0 else None,
            finish_callback=lambda profile: self.profilerFinished.emit()
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

        # Stop profiler and get events data
        self.current_profiler.stop()
        events_data = self.current_profiler.get_events()

        # Create result object
        session_name = self.session_name_edit.text() or f"NewProfile_{len(self.profile_results) + 1}"
        result = ProfileResult(session_name, self.current_session_start, self.current_profiler)
        self.profile_results.append(result)

        # Update UI
        self._addResultToList(result)
        self.is_profiling = False
        self.current_session_start = None
        self.current_profiler = None

        self.start_stop_btn.setText("Start Profiling")
        self.start_stop_btn.setStyleSheet("")

        # Update session name for next run
        self.session_name_edit.setText(f"NewProfile_{len(self.profile_results) + 1}")


    def _handleProfilerFinished(self):
        """Handle profiler auto-stop in the main thread"""
        if self.is_profiling and self.current_profiler is not None:
            # Call the normal stop method to handle UI updates
            self._stopProfiling()

    def _addResultToList(self, result):
        """Add a profile result to the results list"""
        thread_count = len(result.events_data)
        total_calls = sum(len(calls) for calls in result.events_data.values())

        item_text = f"{result.name} ({result.start_time.strftime('%H:%M:%S')}) - {result.duration:.2f}s, {thread_count} threads, {total_calls} calls"
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
        self.function_to_items.clear()

        # Get thread names from the profiler
        thread_names = {}
        if self.current_profiler:
            thread_names = self.current_profiler._thread_names

        # Display threads and their root calls
        for thread_id, root_calls in result.events_data.items():
            thread_name = thread_names.get(thread_id, f"Thread-{thread_id}")
            thread_item = LazyThreadItem(
                self.profile_display, thread_id, thread_name, root_calls,
                result.profile_start_time, result.profile_duration, self
            )

        # Auto-resize columns to fit content
        for i in range(self.profile_display.columnCount()):
            self.profile_display.resizeColumnToContents(i)

    def _onItemExpanded(self, item):
        root_item = item
        try:
            self.profile_display.itemExpanded.disconnect(self._onItemExpanded)

            while True:
                if hasattr(item, 'load_children'):
                    item.load_children()

                # if item has only one child, auto-expand that child as well
                if item.childCount() == 1:
                    child_item = item.child(0)
                    child_item.setExpanded(True)
                    item = child_item
                else:
                    break
        finally:
            self.profile_display.itemExpanded.connect(self._onItemExpanded)

        # scroll towards bottom-most expanded item while keeping root item visible
        if item.childCount() > 0:
            scroll_item = item.child(item.childCount() - 1)
        else:
            scroll_item = item
        self.profile_display.scrollToItem(scroll_item)
        self.profile_display.scrollToItem(root_item)

    def _onCallTreeSelectionChanged(self):
        """Handle selection change in call tree to update detail view and console stack"""
        selected_items = self.profile_display.selectedItems()
        if not selected_items:
            self.detail_tree.clear()
            self.function_info_label.setText("Select a function to see details")
            self._clearHighlighting()
            # Clear console stack
            if self.console:
                self.console.setStack(None)
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
            # Extract function info from the call record
            call_record = selected_item.call_record

            # Update function info label
            self._updateFunctionInfoLabel(call_record)

            # Highlight all instances of this function
            self._highlightFunction(call_record)

            # Display function details
            self._displayFunctionDetails(call_record, result)

            # Update console stack with the selected function's frame
            if self.console:
                self.console.setStack(call_record.frame)
        elif isinstance(selected_item, LazyThreadItem):
            # Thread selected - clear detail view
            self.detail_tree.clear()
            self.function_info_label.setText("Select a function to see details")
            self._clearHighlighting()
            # Clear console stack
            if self.console:
                self.console.setStack(None)

    def _updateFunctionInfoLabel(self, call_record: CallRecord):
        """Update the function info label with selected function details"""
        func_name = call_record.display_name
        module_name = call_record.module

        # Get calling location info
        calling_location = call_record.calling_location
        if calling_location:
            calling_file, calling_line = calling_location
            calling_file_short = calling_file.split('/')[-1] if '/' in calling_file else calling_file
            called_from = f"{calling_file_short}:{calling_line}"
        else:
            called_from = "N/A"

        self.function_info_label.setText(f"Selected function: {module_name}.{func_name}  Called from: {called_from}")

    def _highlightFunction(self, call_record: CallRecord):
        """Highlight all instances of the specified function in the call tree"""
        # Clear previous highlighting
        self._clearHighlighting()

        function_key = call_record.function_key
        # Store original backgrounds and highlight all instances of this function
        if function_key in self.function_to_items:
            for item in self.function_to_items[function_key]:
                # Store original background before changing it
                if not hasattr(item, '_original_background'):
                    item._original_background = item.background(0)

                # Apply highlight
                item.setBackground(0, Qt.QColor(255, 255, 0, 100))  # Light yellow highlight

        self.currently_highlighted_function = function_key

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

    def _displayFunctionDetails(self, call_record: CallRecord, result):
        """Display detailed analysis of the selected function"""
        self.detail_tree.clear()

        # Use ProfileAnalyzer (no more UI analysis!)
        analyzer = ProfileAnalyzer(result.profile)
        analysis = analyzer.analyze_function(call_record)

        if not analysis:
            placeholder_item = NumericalTreeWidgetItem(self.detail_tree)
            placeholder_item.setText(0, "No analysis data available")
            return

        # Get the selected function name for tooltips
        selected_func_name = call_record.display_name

        # Create totals section using ProfileAnalyzer data
        totals_stats = {
            'n_calls': analysis.total_calls,
            'total_duration': analysis.total_duration,
            'avg_duration': analysis.avg_duration,
            'min_duration': analysis.min_duration,
            'max_duration': analysis.max_duration
        }
        totals_tooltip_context = {
            'type': 'totals',
            'selected_func': selected_func_name,
            'other_func': None
        }
        self._createStatisticsTreeItem(self.detail_tree, "Totals", "—", totals_stats, analysis.profile_percentage, totals_tooltip_context)
        self._addCallersSection(analysis, selected_func_name)
        self._addSubcallsSection(analysis, selected_func_name)

        # Auto-resize columns (skip first column which has fixed width)
        for i in range(FunctionProfiler.DetailTreeColumns.MODULE, self.detail_tree.columnCount()):
            self.detail_tree.resizeColumnToContents(i)

        # Auto-expand all sections
        self.detail_tree.expandAll()

    def _createStatisticsTreeItem(self, parent, display_name, module_name, stats, percentage=None, tooltip_context=None):
        """Create a tree item with statistics using display name and module directly

        Args:
            parent: Parent tree item
            display_name: Already-formatted display name
            module_name: Module name
            stats: Statistics dictionary
            percentage: Optional percentage value
            tooltip_context: Dict with 'type' ('caller' or 'subcall'), 'selected_func', 'other_func'

        Returns:
            Created NumericalTreeWidgetItem
        """
        item = NumericalTreeWidgetItem(parent)

        # Set column data using shared method
        percentage_text = f"{percentage:.1f}" if percentage is not None else "—"
        item._setNumericalData({
            FunctionProfiler.DetailTreeColumns.CALLS: (str(stats['n_calls']), stats['n_calls']),
            FunctionProfiler.DetailTreeColumns.PERCENTAGE: (percentage_text, percentage if percentage is not None else 0.0),
            FunctionProfiler.DetailTreeColumns.TOTAL: (f"{stats['total_duration']*1000:.3f}", stats['total_duration']*1000),
            FunctionProfiler.DetailTreeColumns.AVG: (f"{stats['avg_duration']*1000:.3f}", stats['avg_duration']*1000),
            FunctionProfiler.DetailTreeColumns.MIN: (f"{stats['min_duration']*1000:.3f}", stats['min_duration']*1000),
            FunctionProfiler.DetailTreeColumns.MAX: (f"{stats['max_duration']*1000:.3f}", stats['max_duration']*1000),
        })

        # Set text columns
        item.setText(FunctionProfiler.DetailTreeColumns.NAME, display_name)
        item.setText(FunctionProfiler.DetailTreeColumns.MODULE, module_name)

        # Add tooltip for percentage column if context is provided
        if tooltip_context and percentage is not None:
            if tooltip_context['type'] == 'caller':
                tooltip = (f"Percent of {tooltip_context['other_func']} time spent inside {tooltip_context['selected_func']}\n"
                          f"(Ignoring invocations of {tooltip_context['other_func']} that do not call {tooltip_context['selected_func']})")
            elif tooltip_context['type'] == 'subcall':
                tooltip = (f"Percent of {tooltip_context['selected_func']} time spent inside {tooltip_context['other_func']}\n"
                          f"(Ignoring invocations of {tooltip_context['selected_func']} that do not call {tooltip_context['other_func']})")
            elif tooltip_context['type'] == 'totals':
                tooltip = (f"Percent of total profile time spent in {tooltip_context['selected_func']}\n"
                          f"(Sum of all invocations of {tooltip_context['selected_func']} relative to entire profile duration)")
            else:
                tooltip = None

            if tooltip:
                item.setToolTip(FunctionProfiler.DetailTreeColumns.PERCENTAGE, tooltip)

        return item


    def _addCallersSection(self, analysis: FunctionAnalysis, selected_func_name: str):
        """Add callers section to detail tree using FunctionAnalysis"""
        callers_data = analysis.get_callers_with_percentages()
        if not callers_data:
            return

        callers_item = NumericalTreeWidgetItem(self.detail_tree)
        callers_item.setText(0, "Callers")

        # Get actual CallRecord objects for caller functions using ProfileAnalyzer
        for caller_key, stats in callers_data.items():
            # Use ProfileAnalyzer to find CallRecord instances for this caller function
            caller_records = analysis.analyzer.get_call_records(caller_key) if analysis.analyzer else []
            if caller_records:
                # Use the first record for display (they all represent the same function)
                caller_record = caller_records[0]
                display_name = caller_record.display_name
                module_name = caller_record.module
            else:
                display_name = str(caller_key)
                module_name = "—"

            tooltip_context = {
                'type': 'caller',
                'selected_func': selected_func_name,
                'other_func': display_name
            }
            self._createStatisticsTreeItem(callers_item, display_name, module_name, stats, stats['percentage'], tooltip_context)

    def _addSubcallsSection(self, analysis: FunctionAnalysis, selected_func_name: str):
        """Add subcalls section to detail tree using FunctionAnalysis"""
        subcalls_data = analysis.get_subcalls_with_percentages()
        if not subcalls_data:
            return

        subcalls_item = NumericalTreeWidgetItem(self.detail_tree)
        subcalls_item.setText(0, "Subcalls")

        # Get actual CallRecord objects for subcall functions using ProfileAnalyzer
        for subcall_key, stats in subcalls_data.items():
            # Use ProfileAnalyzer to find CallRecord instances for this subcall function
            subcall_records = analysis.analyzer.get_call_records(subcall_key) if analysis.analyzer else []
            if subcall_records:
                # Use the first record for display (they all represent the same function)
                subcall_record = subcall_records[0]
                display_name = subcall_record.display_name
                module_name = subcall_record.module
            else:
                display_name = str(subcall_key)
                module_name = "—"

            tooltip_context = {
                'type': 'subcall',
                'selected_func': selected_func_name,
                'other_func': display_name
            }
            self._createStatisticsTreeItem(subcalls_item, display_name, module_name, stats, stats['percentage'], tooltip_context)

    def _clearProfiles(self):
        """Clear all profile results"""
        self.profile_results.clear()
        self.results_list.clear()
        self.profile_display.clear()
        self.detail_tree.clear()
        self.function_to_items.clear()
        self.currently_highlighted_function = None
        self.function_info_label.setText("Select a function to see details")