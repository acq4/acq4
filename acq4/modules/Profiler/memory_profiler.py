# ABOUTME: Memory profiling using guppy/heapy with UI for heap analysis and leak detection
# ABOUTME: Provides snapshot-based memory profiling and object analysis for debugging leaks
from datetime import datetime
from acq4.util import Qt

try:
    from guppy import hpy
    GUPPY_AVAILABLE = True
except ImportError:
    GUPPY_AVAILABLE = False


class NumericTreeWidgetItem(Qt.QTreeWidgetItem):
    """QTreeWidgetItem that sorts numeric columns properly"""

    def __lt__(self, other):
        """Custom comparison for proper numeric sorting"""
        column = self.treeWidget().sortColumn()

        # For numeric columns (1, 2, 3), use stored numeric data
        if column in [1, 2, 3]:
            self_data = self.data(column, Qt.Qt.UserRole)
            other_data = other.data(column, Qt.Qt.UserRole)

            if self_data is not None and other_data is not None:
                return self_data < other_data

        # For text columns, use default string comparison
        return self.text(column) < other.text(column)


class LazyTypeItem(NumericTreeWidgetItem):
    """Tree item that lazy-loads individual objects of a specific type using byid"""

    def __init__(self, parent, type_stat):
        super().__init__(parent)
        self.type_stat = type_stat
        self.objects_loaded = False

        # Add dummy child to make it expandable
        self._dummy_child = Qt.QTreeWidgetItem(self)
        self._dummy_child.setText(0, "Loading...")

    def load_objects(self):
        """Load individual objects of this type using byid"""
        if self.objects_loaded:
            return

        try:
            # Remove dummy child
            self.removeChild(self._dummy_child)

            # Use byid to get individual objects
            byid = self.type_stat.byid
            total_count = len(byid)

            # Show top 100 largest objects by size
            for i in range(min(100, total_count)):
                try:
                    obj_set = byid[i]
                    obj_item = ObjectItem(self, obj_set, i)
                except Exception as e:
                    error_item = Qt.QTreeWidgetItem(self)
                    error_item.setText(0, f"Error loading object {i}: {e}")

            # Add summary if we truncated
            if total_count > 100:
                summary_item = Qt.QTreeWidgetItem(self)
                summary_item.setText(0, f"... and {total_count - 100:,} more objects")

            self.objects_loaded = True

        except Exception as e:
            error_item = Qt.QTreeWidgetItem(self)
            error_item.setText(0, f"Error loading objects: {e}")


class ObjectItem(NumericTreeWidgetItem):
    """Tree item representing an individual object"""

    def __init__(self, parent, obj_set, index):
        super().__init__(parent)
        self.obj_set = obj_set
        self.details_loaded = False

        # Display object info
        try:
            size = obj_set.size
            count = obj_set.count

            if count == 1:
                # Single object - try to get type and preview
                try:
                    actual_obj = obj_set.theone
                    obj_type = type(actual_obj).__name__
                    obj_repr = repr(actual_obj)
                    if len(obj_repr) > 50:
                        obj_repr = obj_repr[:47] + "..."
                    object_desc = f"{obj_type}: {obj_repr}"
                except Exception:
                    object_desc = f"Object {index}"
            else:
                object_desc = f"ObjectSet {index} ({count} objects)"

            self.setText(0, object_desc)
            self.setText(1, str(count))
            self.setText(2, f"{size:,}")
            self.setText(3, "")  # No percentage at object level

            # Store numeric values for sorting
            self.setData(1, Qt.Qt.UserRole, count)
            self.setData(2, Qt.Qt.UserRole, size)
            self.setData(3, Qt.Qt.UserRole, 0)

            # Add dummy child for details if single object
            if count == 1:
                self._dummy_child = Qt.QTreeWidgetItem(self)
                self._dummy_child.setText(0, "Loading details...")

        except Exception as e:
            self.setText(0, f"Error: {e}")

    def load_details(self):
        """Load object details (shortest path, referrers, etc.)"""
        if self.details_loaded or self.obj_set.count != 1:
            return

        try:
            # Remove dummy child
            if hasattr(self, '_dummy_child'):
                self.removeChild(self._dummy_child)

            # Get shortest path to object
            try:
                sp = self.obj_set.sp
                if sp and str(sp).strip():
                    sp_item = Qt.QTreeWidgetItem(self)
                    sp_item.setText(0, f"Shortest Path: {sp}")
                else:
                    sp_item = Qt.QTreeWidgetItem(self)
                    sp_item.setText(0, "Shortest Path: <object deleted - no longer reachable>")
            except Exception as e:
                sp_item = Qt.QTreeWidgetItem(self)
                error_msg = str(e).lower()
                if "deleted" in error_msg or "collected" in error_msg or "invalid" in error_msg:
                    sp_item.setText(0, "Shortest Path: <object deleted - garbage collected>")
                elif "unreachable" in error_msg or "not found" in error_msg:
                    sp_item.setText(0, "Shortest Path: <object no longer reachable from root>")
                else:
                    sp_item.setText(0, f"Shortest Path: Error - {e}")

            # Try to get object value details
            try:
                actual_obj = self.obj_set.theone

                # Show object type and size info
                type_item = Qt.QTreeWidgetItem(self)
                type_item.setText(0, f"Type: {type(actual_obj).__name__}")
                type_item.setText(2, f"{self.obj_set.size:,}")

                # Show object attributes if reasonable
                if hasattr(actual_obj, '__dict__') and len(str(actual_obj.__dict__)) < 200:
                    attrs_item = Qt.QTreeWidgetItem(self)
                    attrs_item.setText(0, f"Attributes: {actual_obj.__dict__}")

            except Exception as e:
                error_item = Qt.QTreeWidgetItem(self)
                error_msg = str(e).lower()
                if "deleted" in error_msg or "collected" in error_msg or "invalid" in error_msg:
                    error_item.setText(0, "Object Details: <object deleted - garbage collected>")
                elif "theone requires a singleton set" in error_msg:
                    error_item.setText(0, f"Object Details: Multiple objects in set ({self.obj_set.count})")
                else:
                    error_item.setText(0, f"Object Details: Error - {e}")

            self.details_loaded = True

        except Exception as e:
            error_item = Qt.QTreeWidgetItem(self)
            error_item.setText(0, f"Error loading details: {e}")




class MemorySnapshot:
    """Container for a single memory snapshot"""

    def __init__(self, name, timestamp, heap_stats=None, error_message=None):
        self.name = name
        self.timestamp = timestamp
        self.heap_stats = heap_stats
        self.error_message = error_message

    @property
    def is_valid(self):
        return self.heap_stats is not None and self.error_message is None


class MemoryProfiler:
    """Handles memory profiling using guppy/heapy and provides UI for snapshot management and analysis"""

    def __init__(self, parent_widget):
        self.parent = parent_widget
        self.snapshots = []
        self.baseline_snapshot = None

        # Initialize guppy if available
        if GUPPY_AVAILABLE:
            self.hpy = hpy()
        else:
            self.hpy = None

        # Create UI
        self.widget = self._createUI()

    def _createUI(self):
        """Create the memory profiling UI"""
        widget = Qt.QWidget()
        layout = Qt.QVBoxLayout(widget)

        # Main content area
        if not GUPPY_AVAILABLE:
            # Show error message if guppy not available
            error_label = Qt.QLabel("Guppy3 not available. Install with: pip install guppy3")
            error_label.setStyleSheet("color: red; font-weight: bold; padding: 20px;")
            error_label.setAlignment(Qt.Qt.AlignCenter)
            layout.addWidget(error_label)
        else:
            # Control panel
            control_panel = self._createControlPanel()
            layout.addWidget(control_panel, 0)

            # Main splitter for snapshots list and analysis display
            splitter = Qt.QSplitter(Qt.Qt.Horizontal)
            layout.addWidget(splitter)

            # Left side: Snapshots list
            self.snapshots_list = Qt.QListWidget()
            self.snapshots_list.setSelectionMode(Qt.QAbstractItemView.ExtendedSelection)
            self.snapshots_list.itemSelectionChanged.connect(self._onSnapshotSelected)
            splitter.addWidget(self.snapshots_list)

            # Right side: Memory analysis display
            self.analysis_display = Qt.QTreeWidget()
            headers = ['Description', 'Count', 'Size (bytes)', 'Percentage']
            self.analysis_display.setHeaderLabels(headers)
            self.analysis_display.setSortingEnabled(True)
            self.analysis_display.sortByColumn(2, Qt.Qt.DescendingOrder)
            self.analysis_display.itemExpanded.connect(self._onItemExpanded)
            splitter.addWidget(self.analysis_display)

            # Set splitter proportions
            splitter.setSizes([300, 700])

        return widget

    def _createControlPanel(self):
        """Create the control panel with snapshot and analysis controls"""
        panel = Qt.QGroupBox("Memory Profile Controls")
        panel.setSizePolicy(Qt.QSizePolicy.Preferred, Qt.QSizePolicy.Fixed)
        layout = Qt.QHBoxLayout(panel)

        # Take snapshot button
        self.snapshot_btn = Qt.QPushButton("Take Snapshot")
        self.snapshot_btn.clicked.connect(self._takeSnapshot)
        layout.addWidget(self.snapshot_btn)

        # Snapshot name input
        layout.addWidget(Qt.QLabel("Name:"))
        self.snapshot_name_edit = Qt.QLineEdit()
        self.snapshot_name_edit.setText(f"Snapshot_{len(self.snapshots) + 1}")
        layout.addWidget(self.snapshot_name_edit)

        # Set baseline button
        self.baseline_btn = Qt.QPushButton("Set as Baseline")
        self.baseline_btn.clicked.connect(self._setBaseline)
        self.baseline_btn.setEnabled(False)
        layout.addWidget(self.baseline_btn)

        # Clear snapshots button
        self.clear_btn = Qt.QPushButton("Clear All")
        self.clear_btn.clicked.connect(self._clearSnapshots)
        layout.addWidget(self.clear_btn)

        layout.addStretch()

        return panel

    def _takeSnapshot(self):
        """Take a memory snapshot using guppy"""
        if not GUPPY_AVAILABLE:
            return

        snapshot_name = self.snapshot_name_edit.text() or f"Snapshot_{len(self.snapshots) + 1}"
        timestamp = datetime.now()

        try:
            # Get heap statistics
            heap_stats = self.hpy.heap()
            snapshot = MemorySnapshot(snapshot_name, timestamp, heap_stats)
        except Exception as e:
            snapshot = MemorySnapshot(snapshot_name, timestamp, error_message=str(e))

        self.snapshots.append(snapshot)
        self._addSnapshotToList(snapshot)

        # Update snapshot name for next run
        self.snapshot_name_edit.setText(f"Snapshot_{len(self.snapshots) + 1}")

    def _addSnapshotToList(self, snapshot):
        """Add a snapshot to the snapshots list"""
        if snapshot.is_valid:
            total_size = snapshot.heap_stats.size
            baseline_prefix = "[BASELINE] " if snapshot == self.baseline_snapshot else ""
            item_text = f"{baseline_prefix}{snapshot.name} ({snapshot.timestamp.strftime('%H:%M:%S')}) - {total_size:,} bytes"
        else:
            item_text = f"{snapshot.name} ({snapshot.timestamp.strftime('%H:%M:%S')}) - ERROR: {snapshot.error_message}"

        item = Qt.QListWidgetItem(item_text)
        item.setData(Qt.Qt.UserRole, snapshot)

        # Color code based on validity
        if not snapshot.is_valid:
            item.setForeground(Qt.QColor("red"))
        elif snapshot == self.baseline_snapshot:
            item.setForeground(Qt.QColor("blue"))

        self.snapshots_list.addItem(item)

        # Auto-select all snapshots since the last baseline
        self._selectSnapshotsSinceBaseline()

    def _selectSnapshotsSinceBaseline(self):
        """Select all snapshots since the last baseline"""
        if self.baseline_snapshot is None:
            # No baseline set - select all snapshots
            self.snapshots_list.selectAll()
            return

        # Find the baseline index in the snapshots list
        baseline_index = -1
        try:
            baseline_index = self.snapshots.index(self.baseline_snapshot)
        except ValueError:
            # Baseline not found in snapshots list - select all
            self.snapshots_list.selectAll()
            return

        # Clear current selection
        self.snapshots_list.clearSelection()

        # Select all snapshots after the baseline
        for i in range(baseline_index + 1, self.snapshots_list.count()):
            item = self.snapshots_list.item(i)
            item.setSelected(True)

    def _onSnapshotSelected(self):
        """Handle selection change in snapshots list"""
        selected_items = self.snapshots_list.selectedItems()
        if not selected_items:
            self.baseline_btn.setEnabled(False)
            self.analysis_display.clear()
            return

        # Enable baseline button only if single valid snapshot selected
        if len(selected_items) == 1:
            snapshot = selected_items[0].data(Qt.Qt.UserRole)
            self.baseline_btn.setEnabled(snapshot.is_valid)
        else:
            self.baseline_btn.setEnabled(False)

        # Get valid selected snapshots
        selected_snapshots = []
        for item in selected_items:
            snapshot = item.data(Qt.Qt.UserRole)
            if snapshot.is_valid:
                selected_snapshots.append(snapshot)

        if selected_snapshots:
            self._displayAnalysis(selected_snapshots)

    def _displayAnalysis(self, snapshots):
        """Display analysis of snapshots with optional baseline subtraction"""
        self.analysis_display.clear()

        if not snapshots:
            return

        try:
            # Determine what to analyze
            if len(snapshots) == 1:
                # Single snapshot
                analysis_data = snapshots[0].heap_stats
                description = snapshots[0].name
            else:
                # Multiple snapshots - intersection
                analysis_data = snapshots[0].heap_stats
                for snapshot in snapshots[1:]:
                    analysis_data = analysis_data & snapshot.heap_stats
                description = f"Intersection of: {', '.join([s.name for s in snapshots])}"

            # Apply baseline subtraction if baseline exists
            baseline_note = ""
            if self.baseline_snapshot and self.baseline_snapshot.is_valid:
                analysis_data = analysis_data - self.baseline_snapshot.heap_stats
                baseline_note = f" (excluding baseline: {self.baseline_snapshot.name})"

            # Get breakdown by type
            by_type = analysis_data.bytype
            total_size = analysis_data.size

            # Display header if filtered or multiple snapshots
            if len(snapshots) > 1 or baseline_note:
                header_item = NumericTreeWidgetItem(self.analysis_display)
                header_item.setText(0, f"{description}{baseline_note}")
                header_item.setText(2, f"Total: {total_size:,} bytes")

            for i in range(min(20, len(by_type))):  # Show top 20 types
                type_stat = by_type[i]
                item = LazyTypeItem(self.analysis_display, type_stat)

                # Extract type information from guppy stat object
                type_name = str(type_stat.kind)
                count = type_stat.count
                size = type_stat.size
                percentage = (size / total_size * 100) if total_size > 0 else 0

                item.setText(0, type_name)
                item.setText(1, f"{count:,}")
                item.setText(2, f"{size:,}")
                item.setText(3, f"{percentage:.1f}%")

                # Store actual numeric values for proper sorting
                item.setData(1, Qt.Qt.UserRole, count)
                item.setData(2, Qt.Qt.UserRole, size)
                item.setData(3, Qt.Qt.UserRole, percentage)

        except Exception as e:
            error_item = NumericTreeWidgetItem(self.analysis_display)
            error_item.setText(0, f"Error analyzing snapshots: {e}")

        # Auto-resize columns to fit content
        for i in range(self.analysis_display.columnCount()):
            self.analysis_display.resizeColumnToContents(i)

    def _setBaseline(self):
        """Set the selected snapshot as baseline"""
        selected_items = self.snapshots_list.selectedItems()
        if len(selected_items) != 1:
            return

        snapshot = selected_items[0].data(Qt.Qt.UserRole)
        if not snapshot.is_valid:
            return

        # Set new baseline
        self.baseline_snapshot = snapshot

        # Refresh all list items to update baseline display
        self._refreshSnapshotsList()

    def _refreshSnapshotsList(self):
        """Refresh all snapshot list items to update baseline display"""
        for i in range(self.snapshots_list.count()):
            item = self.snapshots_list.item(i)
            snapshot = item.data(Qt.Qt.UserRole)

            if snapshot.is_valid:
                total_size = snapshot.heap_stats.size
                baseline_prefix = "[BASELINE] " if snapshot == self.baseline_snapshot else ""
                item_text = f"{baseline_prefix}{snapshot.name} ({snapshot.timestamp.strftime('%H:%M:%S')}) - {total_size:,} bytes"
            else:
                item_text = f"{snapshot.name} ({snapshot.timestamp.strftime('%H:%M:%S')}) - ERROR: {snapshot.error_message}"

            item.setText(item_text)

            # Update colors
            if not snapshot.is_valid:
                item.setForeground(Qt.QColor("red"))
            elif snapshot == self.baseline_snapshot:
                item.setForeground(Qt.QColor("blue"))
            else:
                item.setForeground(Qt.QColor("black"))

    def _onItemExpanded(self, item):
        """Handle tree item expansion for lazy loading"""
        if isinstance(item, LazyTypeItem):
            item.load_objects()
        elif isinstance(item, ObjectItem):
            item.load_details()

    def _clearSnapshots(self):
        """Clear all snapshots"""
        reply = Qt.QMessageBox.question(self.parent, "Clear Snapshots",
                                        "Are you sure you want to clear all snapshots?",
                                        Qt.QMessageBox.Yes | Qt.QMessageBox.No,
                                        Qt.QMessageBox.No)

        if reply == Qt.QMessageBox.Yes:
            self.snapshots.clear()
            self.baseline_snapshot = None
            self.snapshots_list.clear()
            self.analysis_display.clear()
            self.snapshot_name_edit.setText("Snapshot_1")