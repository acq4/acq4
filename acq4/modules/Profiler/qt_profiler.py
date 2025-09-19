# ABOUTME: Qt event loop profiling using ProfiledQApplication with UI for control and display
# ABOUTME: Provides Qt event profiling with event type breakdown and receiver analysis
import weakref
from acq4.util import Qt
import pyqtgraph as pg


class QtEventProfiler:
    """Handles Qt event loop profiling using ProfiledQApplication and provides UI for control and display"""

    def __init__(self, parent_widget):
        self.parent = parent_widget
        self.is_profiling = False
        self.current_profile = None
        self.profile_results = []

        # Check if Qt profiling is available
        self.qt_profiling_available = self._checkQtProfilingAvailability()

        # Create UI
        self.widget = self._createUI()

    def _checkQtProfilingAvailability(self):
        """Check if Qt event profiling is available"""
        app = Qt.QApplication.instance()
        if app is None:
            return False
        return hasattr(app, 'start_profile')

    def _createUI(self):
        """Create the Qt event profiling UI"""
        widget = Qt.QWidget()
        layout = Qt.QVBoxLayout(widget)

        # Main content area
        if not self.qt_profiling_available:
            # Show error message if Qt profiling not available
            error_label = Qt.QLabel("Qt profiling not available. Start acq4 with --qt-profile flag.")
            error_label.setStyleSheet("color: red; font-weight: bold; padding: 20px;")
            error_label.setAlignment(Qt.Qt.AlignCenter)
            layout.addWidget(error_label)
        else:
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

            # Bottom pane: Event breakdown by type and receiver
            self.type_receiver_display = Qt.QTreeWidget()
            type_receiver_headers = ['Event Type → Receiver', 'Count', 'Total Time (s)', 'Avg Time (ms)', 'Percentage']
            self.type_receiver_display.setHeaderLabels(type_receiver_headers)
            self.type_receiver_display.setSortingEnabled(True)
            self.type_receiver_display.sortByColumn(2, Qt.Qt.DescendingOrder)
            self.type_receiver_display.itemDoubleClicked.connect(self._onTypeReceiverDoubleClicked)
            right_splitter.addWidget(self.type_receiver_display)

            # Set right splitter proportions (33% top, 67% bottom)
            right_splitter.setSizes([240, 480])

            splitter.addWidget(right_splitter)

            # Set main splitter proportions (keep left panel same size, expand right panel)
            splitter.setSizes([200, 900])

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

        layout.addStretch()

        return panel

    def _toggleProfiling(self):
        """Start or stop Qt profiling session"""
        if not self.qt_profiling_available:
            return

        if self.is_profiling:
            self._stopProfiling()
        else:
            self._startProfiling()

    def _startProfiling(self):
        """Start a new Qt event profiling session"""
        # Get the QApplication instance (we know it's valid from availability check)
        app = Qt.QApplication.instance()

        # Start profiling session
        session_name = self.session_name_edit.text() or f"Qt_Profile_{len(self.profile_results) + 1}"

        self.current_profile = app.start_profile(session_name)

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
        wall_time = profile.end_time - profile.start_time
        total_events = len(profile._events)

        item_text = f"{profile.name} ({total_events:,} events, {wall_time:.1f}s)"
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
        self.type_receiver_display.clear()

        # Top pane: Event breakdown by type with uniform column format
        type_stats = profile.get_statistics(group_by='type')
        for row_data in type_stats:
            item = Qt.QTreeWidgetItem(self.profile_display)
            item.setText(0, row_data['description'])
            item.setText(1, f"{row_data['count']:,}")
            item.setText(2, f"{row_data['total_time']:.6f}")
            item.setText(3, f"{row_data['avg_time']*1000:.2f}")
            item.setText(4, f"{row_data['percentage']:.1f}%")

        # Bottom pane: Event breakdown by type and receiver
        type_receiver_stats = profile.get_statistics(group_by='type_receiver')
        for row_data in type_receiver_stats:
            item = Qt.QTreeWidgetItem(self.type_receiver_display)
            item.setText(0, row_data['description'])
            item.setText(1, f"{row_data['count']:,}")
            item.setText(2, f"{row_data['total_time']:.6f}")
            item.setText(3, f"{row_data['avg_time']*1000:.2f}")
            item.setText(4, f"{row_data['percentage']:.1f}%")
            # Store receiver object for double-click inspection using weak reference
            if 'receiver' in row_data and not isinstance(row_data['receiver'], str):
                item.receiver_ref = weakref.ref(row_data['receiver'])

        # Auto-resize columns for both displays
        for i in range(self.profile_display.columnCount()):
            self.profile_display.resizeColumnToContents(i)
        for i in range(self.type_receiver_display.columnCount()):
            self.type_receiver_display.resizeColumnToContents(i)

    def _onTypeReceiverDoubleClicked(self, item, column):
        """Handle double-click on type-receiver items to show detailed object info"""
        receiver_ref = getattr(item, 'receiver_ref', None)
        if receiver_ref is None:
            return

        receiver = receiver_ref()
        if receiver is None:
            print("Receiver object has been garbage collected.")
            return

        # prints to console
        print("Receiver object QObject parent chain:")
        obj = receiver
        while obj is not None:
            name = obj.objectName()
            print(f" - Name: {name:<30}   Type: {type(obj)}")
            obj = obj.parent()

        print("Receiver object references:")
        pg.debug.describeObj(receiver)