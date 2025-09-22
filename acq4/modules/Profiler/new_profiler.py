"""
Fast Function Profiler UI Module

This module provides a comprehensive UI for the new fast profiler (acq4.util.profiler).
It implements a complete profiling workflow with hierarchical visualization and detailed analysis.

ARCHITECTURE:
The profiler UI follows a multi-panel layout designed for comprehensive profile analysis:

1. Control Panel (Top):
   - Start/Stop profiling toggle button with visual feedback (red when active)
   - Session naming for organizing multiple profiling runs
   - Maximum duration setting for automatic profiling termination (seconds, 0=unlimited)
   - Clear All button to remove all stored profiling sessions

2. Results List (Left Panel):
   - Displays completed profiling sessions with metadata
   - Shows session name, timestamp, duration, thread count, and total function calls
   - Click to select and view detailed results
   - Auto-selects newly completed sessions

3. Main Call Tree (Right Panel, Top):
   - Hierarchical display of profiling data organized by threads and function calls
   - Lazy loading for performance with large profiles
   - Five-column display: Function/Thread, Duration (ms), Start Time (ms), % of Parent, Location
   - Numerical sorting on all columns with proper data type handling
   - Expandable tree structure: Threads → Root Calls → Child Calls → Nested Calls

4. Function Detail Analysis (Right Panel, Bottom):
   - Detailed breakdown of selected function performance
   - Shows aggregated statistics across all invocations
   - Includes caller analysis and subcall breakdown
   - Displays timing distributions (min/max/avg)

## Call Tree Panel

Displays hierarchical view of function call structure with lazy loading:

### Thread Items (Root Level)
Columns calculated from thread_info in hierarchical data:
- Function Call: "{thread_name} ({thread_id})" from thread_info['name']
- Duration (ms): thread_info['total_time'] * 1000 (total execution time for thread)
- Start Time (ms): thread_info['start_time'] * 1000 (thread start time)
- Percentage (%): Always "100.0" (threads are 100% of themselves)
- Location: "{call_count} calls" from thread_info['call_count']

### Function Call Items (Nested Under Threads)
Columns calculated from CallRecord data in hierarchical structure:
- Function Call: func_qualified_name from record[5]
- Duration (ms): (end_time - start_time) * 1000 from record[3] and record[4]
- Start Time (ms): start_time * 1000 from record[3] (relative to profiling start)
- Percentage (%): (call_duration / parent_duration) * 100 where parent_duration is:
  * For root calls: thread total time (thread_info['total_time'])
  * For nested calls: parent function's duration
- Location: "{short_filename}:{line_no}" from record[6] and record[7]

Tree structure built from hierarchical_data['children'] relationships.
Lazy loading loads children on expansion using thread_data['children'][call_id].

## Analysis Panel

Detailed function analysis built from Profile.analyze_function() results:

### Totals Section
Root item "Totals" with aggregate statistics:
- Name: "Totals"
- Calls: Sum of n_calls across all threads
- Percentage (%): Empty for root totals item
- Total (ms): Sum of total_duration across all threads * 1000
- Avg (ms): total_duration / total_calls * 1000
- Min (ms): min(all_durations) * 1000 across all threads
- Max (ms): max(all_durations) * 1000 across all threads

Per-thread children under Totals:
- Name: "{thread_name} ({thread_id})" from stats['thread_name']
- Calls: stats['n_calls'] (number of calls in this thread)
- Percentage (%): stats['percentage'] (percentage of total function time)
- Total (ms): stats['total_duration'] * 1000
- Avg (ms): stats['avg_duration'] * 1000
- Min (ms): stats['min_duration'] * 1000
- Max (ms): stats['max_duration'] * 1000

### Callers Section
Root item "Callers" listing functions that call the selected function:
Each caller child shows:
- Name: caller_func (qualified function name that calls selected function)
- Calls: stats['n_calls'] (times this caller invoked selected function)
- Percentage (%): stats['percentage'] (time in selected function / total time of caller invocations that called selected function)
- Total (ms): stats['total_duration'] * 1000 (total time spent in selected function when called by this caller)
- Avg (ms): stats['avg_duration'] * 1000 (average time per call)
- Min (ms): stats['min_duration'] * 1000 (minimum call duration)
- Max (ms): stats['max_duration'] * 1000 (maximum call duration)

### Subcalls Section
Root item "Subcalls" listing functions called by the selected function:
Each subcall child shows:
- Name: child_func (qualified function name called by selected function)
- Calls: stats['n_calls'] (times selected function called this child)
- Percentage (%): stats['percentage'] (percentage of selected function's total time spent in this child)
- Total (ms): stats['total_duration'] * 1000 (total time spent in this child function when it was called directly by selected function)
- Avg (ms): stats['avg_duration'] * 1000 (average time per call)
- Min (ms): stats['min_duration'] * 1000 (minimum call duration)
- Max (ms): stats['max_duration'] * 1000 (maximum call duration)

UI INTERACTION FEATURES:

**Lazy Loading System**: ✅ IMPLEMENTED
- Tree items load children only when expanded for performance
- Handles large profiles without UI freezing
- Dummy "Loading..." children replaced with actual data on expansion

**Thread-Safe Operations**: ✅ IMPLEMENTED
- Automatic profiler stop notification via Qt signals with queued connections
- Handles profiler finishing from timer thread safely
- UI updates only occur on main thread

**Session Management**: ✅ IMPLEMENTED
- Multiple profiling sessions stored and accessible
- Auto-incrementing session names with user customization
- Session metadata display (duration, thread count, call count)
- Clear all functionality

**Data Display**: ✅ IMPLEMENTED
- Duration: Shows actual milliseconds for completed calls, "—" for ongoing/incomplete calls
- Start Time: Relative to profile start (begins at 0.000ms)
- Percentage: Simple calculation (100 * call_duration / parent_duration)
- Thread Duration: Uses total profiling time (profiler.stop_time - profiler.start_time)
- Location: Filename:line_number for function location

**Numerical Sorting**: ✅ IMPLEMENTED
- Custom QTreeWidgetItem subclass for proper numerical sorting
- UserRole data storage for accurate numerical comparisons
- Fallback to text sorting when numerical data unavailable

PROFILER INTEGRATION:
- Uses acq4.util.profiler.Profile backend (not acq4.util.function_profiler)
- Requires Python 3.12+ for threading.setprofile_all_threads() support
- Graceful degradation with error message for unsupported Python versions
- Automatic callback integration for profiler completion notification

DATA STRUCTURES:
- ProfileResult: Container for completed sessions with events data and timing metadata
- LazyThreadItem: Thread-level tree items with total duration calculations
- LazyCallItem: Function call tree items with parent-relative percentage calculations
- NumericalTreeWidgetItem: Base class ensuring proper numerical sorting

FEATURES IMPLEMENTED: ✅
- Function highlighting system (highlight all instances of selected function)
- Function detail analysis panel with totals/callers/subcalls breakdown
- Function information label showing selected function details
- Call tree selection handling with detail view updates
- Thread-safe UI operations with Qt signals
- Lazy loading for performance with large profiles
- Numerical sorting on all columns
- Session management with auto-incrementing names

FEATURES NOT YET IMPLEMENTED:
- Double-click navigation between related function calls
- Advanced analysis features (timing distributions, call patterns)
- Column width persistence and customization
- Percentage calculations for callers/subcalls sections (currently simplified)

DIFFERENCES FROM CUSTOM FUNCTION PROFILER:
- No stack depth limit (removed max_depth control)
- Uses new profiler backend for better performance
- Simplified data model using CallRecord objects
- Cleaner percentage calculation logic
- Better thread duration handling (wall-clock time vs summed function time)

PERFORMANCE CHARACTERISTICS:
- Lazy loading prevents UI freezing with large profiles
- Efficient data structures for minimal memory overhead
- Fast profiler backend with minimal profiling overhead
- Optimized for real-time profiling during application development
"""

import sys
from datetime import datetime
from acq4.util import Qt
import pyqtgraph as pg
from pyqtgraph.console import ConsoleWidget
from acq4.util.profiler import Profile, CallRecord


class ProfileResult:
    """Container for a single profiling session result"""

    def __init__(self, name, start_time, events_data, profile_start_time, profile_stop_time):
        self.name = name
        self.start_time = start_time
        self.end_time = datetime.now()
        self.events_data = events_data  # Result from profile.get_events()
        self.profile_start_time = profile_start_time  # perf_counter() time when profiling started
        self.profile_stop_time = profile_stop_time  # perf_counter() time when profiling stopped
        self.profile_duration = profile_stop_time - profile_start_time  # Actual profiling duration
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

    def _findParentAttribute(self, attribute_name, default_value=None):
        """Walk up parent hierarchy to find an attribute

        Args:
            attribute_name: Name of attribute to find
            default_value: Value to return if not found

        Returns:
            The attribute value or default_value
        """
        current = self.parent()
        while current is not None:
            if hasattr(current, attribute_name):
                return getattr(current, attribute_name)
            current = current.parent()
        return default_value

    def _scroll_to_keep_visible(self, expanded_child):
        """Implement intelligent scrolling after auto-expansion

        Ensures newly expanded items are visible while keeping the original
        expanded item in view.

        Args:
            expanded_child: The child item that was just expanded
        """
        tree_widget = self.treeWidget()
        if not tree_widget:
            return

        # Find the deepest expanded item by recursively following single children
        deepest_item = expanded_child
        while (hasattr(deepest_item, 'children_loaded') and
               deepest_item.children_loaded and
               deepest_item.childCount() == 1):
            deepest_item = deepest_item.child(0)

        # Get the visual rectangles for both items
        expanded_rect = tree_widget.visualItemRect(self)
        deepest_rect = tree_widget.visualItemRect(deepest_item)

        if expanded_rect.isNull() or deepest_rect.isNull():
            return

        # Get viewport geometry
        viewport = tree_widget.viewport()
        viewport_height = viewport.height()

        # Calculate current scroll position
        current_scroll = tree_widget.verticalScrollBar().value()

        # Calculate scroll values needed
        # top_scroll_value: scroll needed to place expanded item at top of view
        top_scroll_value = current_scroll + expanded_rect.top()

        # bottom_scroll_value: scroll needed to place deepest item at bottom of view
        bottom_scroll_value = current_scroll + deepest_rect.bottom() - viewport_height

        # Use the minimum to avoid scrolling too far
        new_scroll_value = min(bottom_scroll_value, top_scroll_value)

        # Only scroll if we need to move down (larger scroll values)
        if new_scroll_value > current_scroll:
            tree_widget.verticalScrollBar().setValue(int(new_scroll_value))

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

    def __init__(self, parent, call_record, profile_start_time, profiler=None):
        super().__init__(parent)
        self.call_record: CallRecord = call_record
        self.profiler = profiler
        self.children_loaded = False

        actual_duration = call_record.duration

        # Calculate percentage: 100 * call_duration / parent_duration
        percentage = 0.0
        percentage_text = "—"
        if hasattr(parent, 'call_record') and parent.call_record.duration is not None:
            # Parent is a function call
            percentage = 100 * actual_duration / parent.call_record.duration
            percentage_text = f"{percentage:.1f}"
        elif hasattr(parent, 'total_duration') and parent.total_duration > 0:
            # Parent is a thread item
            percentage = 100 * actual_duration / parent.total_duration
            percentage_text = f"{percentage:.1f}"

        # Format duration and calculate values
        duration_ms = actual_duration * 1000
        duration_text = self._formatDuration(actual_duration)
        relative_time_ms = (call_record.timestamp - profile_start_time) * 1000

        # Set text and numerical data using shared method
        self._setNumericalData({
            NewProfiler.CallTreeColumns.DURATION: (duration_text, duration_ms),
            NewProfiler.CallTreeColumns.START_TIME: (f"{relative_time_ms:.3f}", relative_time_ms),
            NewProfiler.CallTreeColumns.PERCENT_OF_PARENT: (percentage_text, percentage)
        })

        self.setText(NewProfiler.CallTreeColumns.FUNCTION_THREAD, self.call_record.display_name)
        self.setText(NewProfiler.CallTreeColumns.MODULE, call_record.module)

        # Use calling_location to show where this function was called from
        calling_location = call_record.calling_location
        if calling_location:
            filename, lineno = calling_location
            self.setText(NewProfiler.CallTreeColumns.LOCATION, f"{filename}:{lineno}")
        else:
            # Top-level function - show function definition location as fallback
            self.setText(NewProfiler.CallTreeColumns.LOCATION, f"{call_record.filename}:{call_record.frame.f_code.co_firstlineno}")

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

        # Add child calls - need to get profile_start_time from parent hierarchy
        profile_start_time = self._findParentAttribute('profile_start_time', 0)
        for child_call in self.call_record.children:
            LazyCallItem(self, child_call, profile_start_time, self.profiler)

        self.children_loaded = True

        # Auto-expand if there's only one child
        if len(self.call_record.children) == 1:
            child_item = self.child(0)
            if hasattr(child_item, 'load_children') and hasattr(child_item, 'children_loaded'):
                if not child_item.children_loaded:
                    self.setExpanded(True)
                    child_item.load_children()
                    # Implement intelligent scrolling after expansion
                    self._scroll_to_keep_visible(child_item)



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

        # Thread duration is the total profiling time (same for all threads)
        total_duration = profile_duration
        call_count = len(root_calls)

        # Store total duration for percentage calculations by children
        self.total_duration = total_duration

        # Get earliest start time from root calls, relative to profile start
        if root_calls:
            earliest_time = min(call.timestamp for call in root_calls)
            earliest_time_relative = earliest_time - profile_start_time
        else:
            earliest_time_relative = 0

        # Set thread display data
        total_duration_ms = total_duration * 1000
        earliest_time_ms = earliest_time_relative * 1000
        duration_text = self._formatDuration(total_duration)

        self.setText(NewProfiler.CallTreeColumns.FUNCTION_THREAD, f"{thread_name} ({thread_id})")
        self.setText(NewProfiler.CallTreeColumns.MODULE, "—")  # Threads don't have a specific module
        self.setText(NewProfiler.CallTreeColumns.LOCATION, f"{call_count} calls")

        # Set numerical data using shared method
        self._setNumericalData({
            NewProfiler.CallTreeColumns.DURATION: (duration_text, total_duration_ms),
            NewProfiler.CallTreeColumns.START_TIME: (f"{earliest_time_ms:.3f}", earliest_time_ms),
            NewProfiler.CallTreeColumns.PERCENT_OF_PARENT: ("—", 0.0)  # Threads have no parent, so no percentage
        })

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

        # Auto-expand if there's only one root call
        if len(self.root_calls) == 1:
            child_item = self.child(0)
            if hasattr(child_item, 'load_children') and hasattr(child_item, 'children_loaded'):
                if not child_item.children_loaded:
                    self.setExpanded(True)
                    child_item.load_children()
                    # Implement intelligent scrolling after expansion
                    self._scroll_to_keep_visible(child_item)


class NewProfiler(Qt.QObject):
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

            # Main splitter for results list and profile display
            main_splitter = Qt.QSplitter(Qt.Qt.Horizontal)
            layout.addWidget(main_splitter)

            # Left side: Profile results list
            self.results_list = Qt.QListWidget()
            self.results_list.itemSelectionChanged.connect(self._onResultSelected)
            main_splitter.addWidget(self.results_list)

            # Right side: Vertical splitter for call tree and detail view
            right_splitter = Qt.QSplitter(Qt.Qt.Vertical)
            main_splitter.addWidget(right_splitter)

            # Top right: Call tree display
            self.profile_display = Qt.QTreeWidget()
            self.profile_display.setHeaderLabels([
                "Function/Thread", "Duration (ms)", "Start Time (ms)", "% of Parent", "Module", "Called from"
            ])
            self.profile_display.setSortingEnabled(True)
            self.profile_display.sortByColumn(NewProfiler.CallTreeColumns.DURATION, Qt.Qt.DescendingOrder)
            self.profile_display.setExpandsOnDoubleClick(False)
            self.profile_display.itemExpanded.connect(lambda item: item.load_children() if hasattr(item, 'load_children') else None)
            self.profile_display.itemSelectionChanged.connect(self._onCallTreeSelectionChanged)
            self.profile_display.setColumnWidth(NewProfiler.CallTreeColumns.FUNCTION_THREAD, 250)  # Set first column width
            right_splitter.addWidget(self.profile_display)

            # Bottom right container: Function detail view with info label
            bottom_container = Qt.QWidget()
            bottom_layout = Qt.QVBoxLayout(bottom_container)
            bottom_layout.setContentsMargins(0, 0, 0, 0)
            bottom_layout.setSpacing(2)

            # Function info label
            self.function_info_label = Qt.QLabel("Select a function to see details")
            self.function_info_label.setStyleSheet("font-weight: bold; padding: 4px; background-color: #f0f0f0; border: 1px solid #ccc;")
            self.function_info_label.setWordWrap(True)
            bottom_layout.addWidget(self.function_info_label)

            # Function detail view
            self.detail_tree = Qt.QTreeWidget()
            self.detail_tree.setHeaderLabels(['Name', 'Module', 'Calls', 'Percentage (%)', 'Total (ms)', 'Avg (ms)', 'Min (ms)', 'Max (ms)'])
            self.detail_tree.setSortingEnabled(True)
            self.detail_tree.setColumnWidth(NewProfiler.DetailTreeColumns.NAME, 250)  # Set first column width
            bottom_layout.addWidget(self.detail_tree)

            right_splitter.addWidget(bottom_container)

            # Add console
            self.console = ConsoleWidget(namespace={'profiler': self})
            right_splitter.addWidget(self.console)

            # Set splitter proportions
            main_splitter.setSizes([200, 800])
            right_splitter.setSizes([300, 200, 200])  # call tree, detail tree, console

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
        result = ProfileResult(session_name, self.current_session_start, events_data,
                             self.current_profiler.start_time, self.current_profiler.stop_time)
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

    def _updateFunctionInfoLabel(self, call_record):
        """Update the function info label with selected function details"""
        func_name = call_record.display_name
        filename = call_record.filename
        line_no = call_record.lineno
        short_filename = filename.split('/')[-1] if '/' in filename else filename
        self.function_info_label.setText(f"Function: {func_name} | File: {filename} | Line: {line_no}")

    def _highlightFunction(self, call_record):
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

    def _displayFunctionDetails(self, call_record, result):
        """Display detailed analysis of the selected function"""
        self.detail_tree.clear()

        # Analyze the function across all threads
        analysis = self._analyzeFunctionInResult(call_record, result)

        if not analysis:
            placeholder_item = NumericalTreeWidgetItem(self.detail_tree)
            placeholder_item.setText(0, "No analysis data available")
            return

        # Create the three main sections
        self._createStatisticsTreeItem(self.detail_tree, "Totals", analysis['totals'], analysis['totals']['percentage'])
        self._addCallersSection(analysis['callers'])
        self._addSubcallsSection(analysis['subcalls'])

        # Auto-resize columns (skip first column which has fixed width)
        for i in range(NewProfiler.DetailTreeColumns.MODULE, self.detail_tree.columnCount()):
            self.detail_tree.resizeColumnToContents(i)

        # Auto-expand all sections
        self.detail_tree.expandAll()

    def _buildFunctionLookup(self, result):
        """Build a lookup dictionary mapping function keys to call records

        Returns:
            dict: {function_key: {'calls': [CallRecord, ...], 'callers': {caller_key: [calls]}, 'subcalls': {child_key: [calls]}}}
        """
        function_lookup = {}

        def add_call_to_lookup(call, parent_call=None):
            function_key = call.function_key

            # Initialize function entry if not exists
            if function_key not in function_lookup:
                function_lookup[function_key] = {
                    'calls': [],
                    'callers': {},
                    'subcalls': {}
                }

            # Add this call
            function_lookup[function_key]['calls'].append(call)

            # Track caller relationship
            if parent_call:
                caller_key = parent_call.function_key
                if caller_key not in function_lookup[function_key]['callers']:
                    function_lookup[function_key]['callers'][caller_key] = {'calls': [], 'parent_calls': []}
                function_lookup[function_key]['callers'][caller_key]['calls'].append(call)
                function_lookup[function_key]['callers'][caller_key]['parent_calls'].append(parent_call)

            # Track subcall relationships
            for child_call in call.children:
                child_key = child_call.function_key
                if child_key not in function_lookup[function_key]['subcalls']:
                    function_lookup[function_key]['subcalls'][child_key] = []
                function_lookup[function_key]['subcalls'][child_key].append(child_call)

                # Recursively process children
                add_call_to_lookup(child_call, call)

        # Process all threads
        for thread_id, root_calls in result.events_data.items():
            for root_call in root_calls:
                add_call_to_lookup(root_call)

        return function_lookup

    def _analyzeFunctionInResult(self, call_record, result):
        """Analyze all invocations of a specific function in the profile result"""
        # Build function lookup once for this result
        if not hasattr(result, '_function_lookup'):
            result._function_lookup = self._buildFunctionLookup(result)

        function_key = call_record.function_key
        function_data = result._function_lookup.get(function_key)
        if not function_data:
            return None

        function_calls = function_data['calls']
        callers = function_data['callers']
        subcalls = function_data['subcalls']

        # Calculate totals
        total_calls = len(function_calls)
        total_duration = sum(call.duration for call in function_calls if call.duration is not None)
        durations = [call.duration for call in function_calls if call.duration is not None]

        if durations:
            avg_duration = total_duration / len(durations)
            min_duration = min(durations)
            max_duration = max(durations)
        else:
            avg_duration = min_duration = max_duration = 0

        # Calculate percentages relative to total profiling time
        profile_duration = result.profile_duration
        profile_percentage = (total_duration / profile_duration * 100) if profile_duration > 0 else 0

        return {
            'totals': {
                'n_calls': total_calls,
                'total_duration': total_duration,
                'avg_duration': avg_duration,
                'min_duration': min_duration,
                'max_duration': max_duration,
                'percentage': profile_percentage
            },
            'callers': callers,
            'subcalls': subcalls
        }


    def _calculateDurationStatistics(self, calls):
        """Calculate duration statistics for a list of calls

        Args:
            calls: List of call records with duration attribute

        Returns:
            dict with n_calls, total_duration, avg_duration, min_duration, max_duration
        """
        durations = [call.duration for call in calls if call.duration is not None]
        if not durations:
            return None

        n_calls = len(durations)
        total_duration = sum(durations)
        avg_duration = total_duration / n_calls
        min_duration = min(durations)
        max_duration = max(durations)

        return {
            'n_calls': n_calls,
            'total_duration': total_duration,
            'avg_duration': avg_duration,
            'min_duration': min_duration,
            'max_duration': max_duration
        }

    def _createStatisticsTreeItem(self, parent, name, stats, percentage=None):
        """Create a tree item with standard statistics formatting

        Args:
            parent: Parent tree item
            name: Name for the item (can be function_key tuple or string)
            stats: Statistics dictionary from _calculateDurationStatistics
            percentage: Optional percentage value

        Returns:
            Created NumericalTreeWidgetItem
        """
        item = NumericalTreeWidgetItem(parent)

        # Extract display name from function_key tuple if needed
        if isinstance(name, tuple) and len(name) >= 3:
            if name[0] == 'c_call':
                # For C calls: ('c_call', id, function_name)
                display_name = f"C:{name[2]}"
            else:
                # For Python calls: (filename, lineno, function_name)
                display_name = name[2]  # function_name is the third element
        else:
            display_name = str(name)

        # Extract module from function_key tuple if available
        if isinstance(name, tuple) and len(name) >= 3:
            if name[0] == 'c_call':
                # For C calls: ('c_call', qualname, module)
                module_name = name[2] if len(name) > 2 else "—"
            else:
                # For Python calls: (filename, lineno, function_name)
                # Extract module using the module_from_file function
                from ...util.profiler import module_from_file
                module_name = module_from_file(name[0])
        else:
            module_name = "—"

        # Set column data using shared method
        percentage_text = f"{percentage:.1f}" if percentage is not None else "—"
        item._setNumericalData({
            NewProfiler.DetailTreeColumns.CALLS: (str(stats['n_calls']), stats['n_calls']),
            NewProfiler.DetailTreeColumns.PERCENTAGE: (percentage_text, percentage if percentage is not None else 0.0),
            NewProfiler.DetailTreeColumns.TOTAL: (f"{stats['total_duration'] * 1000:.3f}", stats['total_duration'] * 1000),
            NewProfiler.DetailTreeColumns.AVG: (f"{stats['avg_duration'] * 1000:.3f}", stats['avg_duration'] * 1000),
            NewProfiler.DetailTreeColumns.MIN: (f"{stats['min_duration'] * 1000:.3f}", stats['min_duration'] * 1000),
            NewProfiler.DetailTreeColumns.MAX: (f"{stats['max_duration'] * 1000:.3f}", stats['max_duration'] * 1000)
        })

        item.setText(NewProfiler.DetailTreeColumns.NAME, display_name)
        item.setText(NewProfiler.DetailTreeColumns.MODULE, module_name)
        return item


    def _addCallersSection(self, callers):
        """Add callers section to detail tree"""
        if not callers:
            return

        callers_item = NumericalTreeWidgetItem(self.detail_tree)
        callers_item.setText(0, "Callers")

        for caller_func, caller_data in callers.items():
            calls = caller_data['calls']
            parent_calls = caller_data['parent_calls']

            # Calculate statistics for this caller
            stats = self._calculateDurationStatistics(calls)
            if not stats:
                continue

            # Calculate percentage: time in selected function / total time of caller invocations that called selected function
            # Get unique parent calls (same parent may call selected function multiple times)
            unique_parent_calls = {}
            for parent in parent_calls:
                if parent.duration is not None:
                    # Use call ID or timestamp as unique identifier
                    call_id = id(parent)  # Use object identity as unique key
                    unique_parent_calls[call_id] = parent

            if unique_parent_calls:
                total_caller_time = sum(parent.duration for parent in unique_parent_calls.values())
                percentage = (stats['total_duration'] / total_caller_time * 100) if total_caller_time > 0 else 0.0
            else:
                percentage = 0.0

            self._createStatisticsTreeItem(callers_item, caller_func, stats, percentage)

    def _addSubcallsSection(self, subcalls):
        """Add subcalls section to detail tree"""
        if not subcalls:
            return

        subcalls_item = NumericalTreeWidgetItem(self.detail_tree)
        subcalls_item.setText(0, "Subcalls")

        # Get the total duration of the parent function for percentage calculation
        # We need to find the total duration from the totals section
        parent_total_duration = 0.0
        for i in range(self.detail_tree.topLevelItemCount()):
            item = self.detail_tree.topLevelItem(i)
            if item.text(0) == "Totals":
                parent_total_duration = getattr(item, '_numerical_data', {}).get(3, 0) / 1000  # Convert back to seconds
                break

        for child_func, calls in subcalls.items():
            # Calculate statistics for this subcall
            stats = self._calculateDurationStatistics(calls)
            if not stats:
                continue

            # Calculate percentage based on parent function total time
            percentage = (stats['total_duration'] / parent_total_duration * 100) if parent_total_duration > 0 else 0.0

            self._createStatisticsTreeItem(subcalls_item, child_func, stats, percentage)

    def _clearProfiles(self):
        """Clear all profile results"""
        self.profile_results.clear()
        self.results_list.clear()
        self.profile_display.clear()
        self.detail_tree.clear()
        self.function_to_items.clear()
        self.currently_highlighted_function = None
        self.function_info_label.setText("Select a function to see details")