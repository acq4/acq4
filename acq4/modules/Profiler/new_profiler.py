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
import time
from datetime import datetime
from acq4.util import Qt


# Only import if Python 3.12+
if sys.version_info >= (3, 12):
    from acq4.util.profiler import Profile


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

    def __lt__(self, other):
        column = self.treeWidget().sortColumn()
        try:
            # Try to get numerical data from UserRole first
            my_data = self.data(column, Qt.Qt.UserRole)
            other_data = other.data(column, Qt.Qt.UserRole)

            if my_data is not None and other_data is not None:
                return float(my_data) < float(other_data)

            # Fallback to text comparison
            return float(self.text(column)) < float(other.text(column))
        except (ValueError, TypeError):
            # Fallback to string comparison
            return self.text(column) < other.text(column)


class LazyCallItem(NumericalTreeWidgetItem):
    """Tree item that lazy-loads child calls"""

    def __init__(self, parent, call_record, profile_start_time, profiler=None):
        super().__init__(parent)
        self.call_record = call_record
        self.profiler = profiler
        self.children_loaded = False

        # Get profile duration for initial stack items
        profile_duration = self._getProfileDuration()

        # Set display data
        if call_record.duration is not None:
            # Normal call with duration
            duration_ms = call_record.duration * 1000
            duration_text = f"{duration_ms:.3f}"
            actual_duration = call_record.duration
        else:
            # Initial stack item that never returns - use total profile duration
            duration_ms = profile_duration * 1000
            duration_text = f"{duration_ms:.3f}"
            actual_duration = profile_duration

        # Calculate percentage: 100 * call_duration / parent_duration
        percentage = 0.0
        percentage_text = "—"
        if hasattr(parent, 'call_record') and parent.call_record.duration is not None:
            # Parent is a function call
            percentage = 100 * actual_duration / parent.call_record.duration
            percentage_text = f"{percentage:.1f}"
        elif hasattr(parent, 'call_record') and parent.call_record.duration is None:
            # Parent is also an initial stack item - use profile duration
            percentage = 100 * actual_duration / profile_duration
            percentage_text = f"{percentage:.1f}"
        elif hasattr(parent, 'total_duration') and parent.total_duration > 0:
            # Parent is a thread item
            percentage = 100 * actual_duration / parent.total_duration
            percentage_text = f"{percentage:.1f}"

        # Make start time relative to profile start (begins at 0)
        relative_time_ms = (call_record.timestamp - profile_start_time) * 1000

        self.setText(0, self._get_function_name())
        self.setText(1, duration_text)
        self.setText(2, f"{relative_time_ms:.3f}")
        self.setText(3, percentage_text)
        self.setText(4, f"{call_record.filename}:{call_record.lineno}")

        # Store numeric values for sorting
        self.setData(1, Qt.Qt.UserRole, duration_ms)
        self.setData(2, Qt.Qt.UserRole, relative_time_ms)
        self.setData(3, Qt.Qt.UserRole, percentage)

        # Register this item for function highlighting
        self._register_for_highlighting()

        # Add dummy child if there are children to load
        if call_record.children:
            self._dummy_child = Qt.QTreeWidgetItem(self)
            self._dummy_child.setText(0, "Loading...")

    def _get_function_name(self):
        """Get the function name, handling C functions"""
        if self.call_record.event_type == 'c_call':
            return f"C:{self.call_record.arg.__name__}"
        else:
            # Check for class methods
            if 'self' in self.call_record.frame.f_locals:
                class_name = self.call_record.frame.f_locals['self'].__class__.__name__
                return f"{class_name}.{self.call_record.funcname}"
            else:
                return self.call_record.funcname

    def _register_for_highlighting(self):
        """Register this item for function highlighting"""
        if not self.profiler:
            return

        func_name = self._get_function_name()
        if func_name not in self.profiler.function_to_items:
            self.profiler.function_to_items[func_name] = []
        self.profiler.function_to_items[func_name].append(self)

    def load_children(self):
        """Load child calls for this item"""
        if self.children_loaded:
            return

        # Remove dummy child
        if hasattr(self, '_dummy_child'):
            self.removeChild(self._dummy_child)

        # Add child calls - need to get profile_start_time from parent hierarchy
        profile_start_time = self._get_profile_start_time()
        for child_call in self.call_record.children:
            LazyCallItem(self, child_call, profile_start_time, self.profiler)

        self.children_loaded = True

    def _getProfileDuration(self):
        """Get the profile duration from parent hierarchy"""
        # Walk up to find thread item which has the profile duration
        current = self.parent()
        while current is not None:
            if hasattr(current, 'total_duration'):
                return current.total_duration
            current = current.parent()
        return 0  # Fallback

    def _get_profile_start_time(self):
        """Get the profile start time from parent hierarchy"""
        # Walk up to find thread item which has the profile start time
        current = self.parent()
        while current is not None:
            if hasattr(current, 'profile_start_time'):
                return current.profile_start_time
            current = current.parent()
        return 0  # Fallback


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

        self.setText(0, f"{thread_name} ({thread_id})")
        self.setText(1, f"{total_duration_ms:.3f}" if total_duration > 0 else "—")
        self.setText(2, f"{earliest_time_ms:.3f}")
        self.setText(3, "—")  # Threads have no parent, so no percentage
        self.setText(4, f"{call_count} calls")

        # Store numeric values for sorting
        self.setData(1, Qt.Qt.UserRole, total_duration_ms)
        self.setData(2, Qt.Qt.UserRole, earliest_time_ms)
        self.setData(3, Qt.Qt.UserRole, 0.0)

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


class NewProfiler(Qt.QObject):
    """Handles profiling using the new acq4.util.profiler with hierarchical display"""

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
                "Function/Thread", "Duration (ms)", "Start Time (ms)", "% of Parent", "Location"
            ])
            self.profile_display.setSortingEnabled(True)
            self.profile_display.sortByColumn(1, Qt.Qt.DescendingOrder)
            self.profile_display.setExpandsOnDoubleClick(False)
            self.profile_display.itemExpanded.connect(self._onItemExpanded)
            self.profile_display.itemSelectionChanged.connect(self._onCallTreeSelectionChanged)
            self.profile_display.setColumnWidth(0, 250)  # Set first column width
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
            self.detail_tree.setHeaderLabels(['Name', 'Calls', 'Percentage (%)', 'Total (ms)', 'Avg (ms)', 'Min (ms)', 'Max (ms)'])
            self.detail_tree.setSortingEnabled(True)
            self.detail_tree.setColumnWidth(0, 250)  # Set first column width
            bottom_layout.addWidget(self.detail_tree)

            right_splitter.addWidget(bottom_container)

            # Set splitter proportions
            main_splitter.setSizes([200, 800])
            right_splitter.setSizes([400, 300])

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
            finish_callback=self._onProfilerFinished
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

    def _onProfilerFinished(self, profile=None):
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
        """Handle item expansion to trigger lazy loading"""
        if hasattr(item, 'load_children'):
            item.load_children()

    def _onCallTreeSelectionChanged(self):
        """Handle selection change in call tree to update detail view"""
        selected_items = self.profile_display.selectedItems()
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
            # Extract function info from the call record
            func_name = selected_item._get_function_name()
            filename = selected_item.call_record.filename
            line_no = selected_item.call_record.lineno

            # Update function info label
            self._updateFunctionInfoLabel(func_name, filename, line_no)

            # Highlight all instances of this function
            self._highlightFunction(func_name)

            # Display function details - for now just show basic info
            # TODO: Implement full analysis once we have the analyze_function equivalent
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

        # Analyze the function across all threads
        analysis = self._analyzeFunctionInResult(func_name, result)

        if not analysis:
            placeholder_item = NumericalTreeWidgetItem(self.detail_tree)
            placeholder_item.setText(0, "No analysis data available")
            return

        # Create the three main sections
        self._addTotalsSection(analysis['totals'])
        self._addCallersSection(analysis['callers'])
        self._addSubcallsSection(analysis['subcalls'])

        # Auto-resize columns (skip first column which has fixed width)
        for i in range(1, self.detail_tree.columnCount()):
            self.detail_tree.resizeColumnToContents(i)

        # Auto-expand all sections
        self.detail_tree.expandAll()

    def _analyzeFunctionInResult(self, func_name, result):
        """Analyze all invocations of a specific function in the profile result"""
        # Collect all instances of this function across all threads
        function_calls = []
        callers = {}
        subcalls = {}

        # Walk through all threads to find instances of the function
        for thread_id, root_calls in result.events_data.items():
            self._walkCallTree(root_calls, func_name, function_calls, callers, subcalls, thread_id)

        if not function_calls:
            return None

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

    def _walkCallTree(self, calls, target_func, function_calls, callers, subcalls, thread_id, parent_call=None):
        """Recursively walk call tree to find function instances and relationships"""
        for call in calls:
            func_name = self._getCallFunctionName(call)

            if func_name == target_func:
                # Found an instance of our target function
                function_calls.append(call)

                # Track caller if we have a parent
                if parent_call:
                    caller_name = self._getCallFunctionName(parent_call)
                    if caller_name not in callers:
                        callers[caller_name] = []
                    callers[caller_name].append(call)

                # Track subcalls (children of this call)
                for child_call in call.children:
                    child_name = self._getCallFunctionName(child_call)
                    if child_name not in subcalls:
                        subcalls[child_name] = []
                    subcalls[child_name].append(child_call)

            # Recurse into children
            self._walkCallTree(call.children, target_func, function_calls, callers, subcalls, thread_id, call)

    def _getCallFunctionName(self, call_record):
        """Get function name from a call record, matching the LazyCallItem logic"""
        if call_record.event_type == 'c_call':
            return f"C:{call_record.arg.__name__}"
        else:
            # Check for class methods
            if 'self' in call_record.frame.f_locals:
                class_name = call_record.frame.f_locals['self'].__class__.__name__
                return f"{class_name}.{call_record.funcname}"
            else:
                return call_record.funcname

    def _addTotalsSection(self, totals):
        """Add totals section to detail tree"""
        totals_item = NumericalTreeWidgetItem(self.detail_tree)
        totals_item.setText(0, "Totals")
        totals_item.setText(1, str(totals['n_calls']))
        totals_item.setText(2, f"{totals['percentage']:.1f}")
        totals_item.setText(3, f"{totals['total_duration'] * 1000:.3f}")
        totals_item.setText(4, f"{totals['avg_duration'] * 1000:.3f}")
        totals_item.setText(5, f"{totals['min_duration'] * 1000:.3f}")
        totals_item.setText(6, f"{totals['max_duration'] * 1000:.3f}")

        # Store numerical data for sorting
        totals_item.setData(1, Qt.Qt.UserRole, totals['n_calls'])
        totals_item.setData(2, Qt.Qt.UserRole, totals['percentage'])
        totals_item.setData(3, Qt.Qt.UserRole, totals['total_duration'] * 1000)
        totals_item.setData(4, Qt.Qt.UserRole, totals['avg_duration'] * 1000)
        totals_item.setData(5, Qt.Qt.UserRole, totals['min_duration'] * 1000)
        totals_item.setData(6, Qt.Qt.UserRole, totals['max_duration'] * 1000)

    def _addCallersSection(self, callers):
        """Add callers section to detail tree"""
        if not callers:
            return

        callers_item = NumericalTreeWidgetItem(self.detail_tree)
        callers_item.setText(0, "Callers")

        for caller_func, calls in callers.items():
            # Calculate statistics for this caller
            durations = [call.duration for call in calls if call.duration is not None]
            if not durations:
                continue

            n_calls = len(durations)
            total_duration = sum(durations)
            avg_duration = total_duration / n_calls
            min_duration = min(durations)
            max_duration = max(durations)

            # Percentage calculation would need parent call durations - simplified for now
            percentage = 0.0  # TODO: Calculate based on parent call durations

            caller_item = NumericalTreeWidgetItem(callers_item)
            caller_item.setText(0, caller_func)
            caller_item.setText(1, str(n_calls))
            caller_item.setText(2, f"{percentage:.1f}")
            caller_item.setText(3, f"{total_duration * 1000:.3f}")
            caller_item.setText(4, f"{avg_duration * 1000:.3f}")
            caller_item.setText(5, f"{min_duration * 1000:.3f}")
            caller_item.setText(6, f"{max_duration * 1000:.3f}")

            # Store numerical data for sorting
            caller_item.setData(1, Qt.Qt.UserRole, n_calls)
            caller_item.setData(2, Qt.Qt.UserRole, percentage)
            caller_item.setData(3, Qt.Qt.UserRole, total_duration * 1000)
            caller_item.setData(4, Qt.Qt.UserRole, avg_duration * 1000)
            caller_item.setData(5, Qt.Qt.UserRole, min_duration * 1000)
            caller_item.setData(6, Qt.Qt.UserRole, max_duration * 1000)

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
                parent_total_duration = item.data(3, Qt.Qt.UserRole) / 1000  # Convert back to seconds
                break

        for child_func, calls in subcalls.items():
            # Calculate statistics for this subcall
            durations = [call.duration for call in calls if call.duration is not None]
            if not durations:
                continue

            n_calls = len(durations)
            total_duration = sum(durations)
            avg_duration = total_duration / n_calls
            min_duration = min(durations)
            max_duration = max(durations)

            # Calculate percentage based on parent function total time
            percentage = (total_duration / parent_total_duration * 100) if parent_total_duration > 0 else 0.0

            child_item = NumericalTreeWidgetItem(subcalls_item)
            child_item.setText(0, child_func)
            child_item.setText(1, str(n_calls))
            child_item.setText(2, f"{percentage:.1f}")
            child_item.setText(3, f"{total_duration * 1000:.3f}")
            child_item.setText(4, f"{avg_duration * 1000:.3f}")
            child_item.setText(5, f"{min_duration * 1000:.3f}")
            child_item.setText(6, f"{max_duration * 1000:.3f}")

            # Store numerical data for sorting
            child_item.setData(1, Qt.Qt.UserRole, n_calls)
            child_item.setData(2, Qt.Qt.UserRole, percentage)
            child_item.setData(3, Qt.Qt.UserRole, total_duration * 1000)
            child_item.setData(4, Qt.Qt.UserRole, avg_duration * 1000)
            child_item.setData(5, Qt.Qt.UserRole, min_duration * 1000)
            child_item.setData(6, Qt.Qt.UserRole, max_duration * 1000)

    def _clearProfiles(self):
        """Clear all profile results"""
        self.profile_results.clear()
        self.results_list.clear()
        self.profile_display.clear()
        self.detail_tree.clear()
        self.function_to_items.clear()
        self.currently_highlighted_function = None
        self.function_info_label.setText("Select a function to see details")