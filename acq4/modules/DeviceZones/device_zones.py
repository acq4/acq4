from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from pyqtgraph import opengl as gl

from acq4.logging_config import get_logger
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.InterfaceCombo import InterfaceCombo

logger = get_logger(__name__)

_UserRole = Qt.Qt.ItemDataRole.UserRole
_COLLINEAR_TOL = 5e-6  # perpendicular distance — middle point is dropped when below this


def _points_collinear(a, b, c):
    """Return True if b lies within _COLLINEAR_TOL of the line from a to c."""
    ac = c - a
    ac_len = np.linalg.norm(ac)
    if ac_len < 1e-10:
        return True
    dist = np.linalg.norm(np.cross(b - a, ac)) / ac_len
    return dist < _COLLINEAR_TOL
_ItemIsEditable = Qt.Qt.ItemFlag.ItemIsEditable
_ItemIsDragEnabled = Qt.Qt.ItemFlag.ItemIsDragEnabled
_Key_Delete = Qt.Qt.Key.Key_Delete

# Zone-tree columns
_COL_NAME = 0
_COL_IN_ZONE = 1
_IN_ZONE_INTERVAL = 1000  # ms between zone-membership polls


class DeviceZonesModule(Module):
    moduleDisplayName = "Device Zones"
    moduleCategory = "Utilities"

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self._3d_adapter = None
        self.ui = DeviceZonesWidget(manager, self)
        manager.declareInterface(name, ['3D Visualizable', 'deviceZonesModule'], self)

    def visualize3DAdapter(self, win):
        self._3d_adapter = DeviceZonesVisualizerAdapter(self.ui, win)
        return self._3d_adapter

    def window(self):
        return self.ui

    def quit(self, fromUi=False):
        if not fromUi:
            self.ui.quit()
        Module.quit(self)


# ---------------------------------------------------------------------------
# 3D Visualizable adapter
# ---------------------------------------------------------------------------

class DeviceZonesVisualizerAdapter(Qt.QObject):
    """Manages scatter + mesh GL items for the selected zone in the 3D viewer."""

    def __init__(self, widget, win):
        super().__init__()
        self._widget = widget
        self.win = win
        self._scatter = None
        self._mesh = None
        self._relative_device = None

    def _connect_device(self, dev):
        if self._relative_device is dev:
            return
        if self._relative_device is not None:
            self._relative_device.sigGlobalTransformChanged.disconnect(self._on_transform_changed)
        self._relative_device = dev
        if dev is not None:
            dev.sigGlobalTransformChanged.connect(self._on_transform_changed)

    def _on_transform_changed(self, sender, changed_device):
        tr = self._relative_device.globalTransform().as_pyqtgraph()
        if self._scatter is not None:
            self._scatter.setTransform(tr)
        if self._mesh is not None:
            self._mesh.setTransform(tr)

    def update_scatter(self, zone, selected_indices: set) -> None:
        pts = np.asarray(zone.hull_points)
        if pts.ndim != 2 or pts.shape[1] != 3 or len(pts) == 0:
            if self._scatter is not None:
                self.win.remove3DItem(self._scatter)
                self._scatter = None
            self._connect_device(None)
            return
        colors = np.array(
            [[1.0, 1.0, 1.0, 1.0] if i in selected_indices else [0.3, 0.3, 0.3, 1.0]
             for i in range(len(pts))],
            dtype=float,
        )
        sizes = np.array([5 if i in selected_indices else 3 for i in range(len(pts))], dtype=float)
        if self._scatter is None:
            self._scatter = gl.GLScatterPlotItem(pos=pts, color=colors, size=sizes)
            self.win.add3DItem(self._scatter)
        else:
            self._scatter.setData(pos=pts, color=colors, size=sizes)
        rel = zone.relative_to
        self._connect_device(rel)
        tr = rel.globalTransform().as_pyqtgraph() if rel is not None else pg.Transform3D()
        self._scatter.setTransform(tr)

    def update_mesh(self, zone) -> None:
        rel = zone.relative_to if zone is not None else None
        mesh_data = zone.mesh() if zone is not None else None
        if mesh_data is None:
            if self._mesh is not None:
                self.win.remove3DItem(self._mesh)
                self._mesh = None
            return
        verts, faces = mesh_data
        md = gl.MeshData(vertexes=verts, faces=faces)
        if self._mesh is None:
            self._mesh = gl.GLMeshItem(
                meshdata=md, smooth=True,
                color=(0.4, 0.7, 1.0, 0.12), shader='balloon', glOptions='additive',
            )
            self.win.add3DItem(self._mesh)
        else:
            self._mesh.setMeshData(meshdata=md)
        tr = rel.globalTransform().as_pyqtgraph() if rel is not None else pg.Transform3D()
        self._mesh.setTransform(tr)

    def clear_items(self) -> None:
        self._connect_device(None)
        if self._scatter is not None:
            self.win.remove3DItem(self._scatter)
            self._scatter = None
        if self._mesh is not None:
            self.win.remove3DItem(self._mesh)
            self._mesh = None

    def clear(self) -> None:
        """Called by Visualize3D when this adapter is removed."""
        self.clear_items()
        if self._widget.module._3d_adapter is self:
            self._widget.module._3d_adapter = None


# ---------------------------------------------------------------------------
# Drag-reorder-aware tree widget
# ---------------------------------------------------------------------------

class _ReadOnlyColumnDelegate(Qt.QStyledItemDelegate):
    """Suppresses the editor for columns that only display computed values."""

    def createEditor(self, parent, option, index):
        return None


class ZoneTreeWidget(Qt.QTreeWidget):
    """QTreeWidget that restricts drag-drop to within the same device parent."""

    def dropEvent(self, event):
        target = self.itemAt(event.pos())
        dragged = self.currentItem()
        if dragged is None:
            event.ignore()
            return

        # Device items have no parent; only zone items may be dragged.
        if dragged.parent() is None:
            event.ignore()
            return

        if target is None:
            event.ignore()
            return
        target_parent = target if target.parent() is None else target.parent()

        if target_parent is not dragged.parent():
            event.ignore()
            return

        super().dropEvent(event)

        # Read back the new child order and persist it.
        device_item = dragged.parent()
        if device_item is None:
            return
        device = device_item.data(0, _UserRole)
        new_order = [
            device_item.child(i).text(_COL_NAME)
            for i in range(device_item.childCount())
        ]
        widget = self._owner
        if widget is not None and device is not None:
            widget.manager.deviceZones.reorder_zones(device, new_order, save=True)


# ---------------------------------------------------------------------------
# Hull-points table
# ---------------------------------------------------------------------------

class HullPointsTree(Qt.QTreeWidget):
    """Editable hull-point table; Delete key removes selected rows."""

    pointsChanged = Qt.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(4)
        self.setHeaderLabels(["#", "X (m)", "Y (m)", "Z (m)"])
        self.setSelectionMode(Qt.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(Qt.QAbstractItemView.EditTrigger.DoubleClicked)
        self._zone = None
        self._device = None
        self._manager = None
        self.itemChanged.connect(self._on_item_changed)
        self._updating = False

    def setContext(self, manager, device, zone):
        self._manager = manager
        self._device = device
        self._zone = zone

    def populate(self, zone, selected_indices=None):
        self._updating = True
        try:
            self.clear()
            if zone is None:
                return
            pts = np.asarray(zone.hull_points)
            selected_indices = set(selected_indices or [])
            for i, pt in enumerate(pts):
                item = Qt.QTreeWidgetItem([
                    str(i),
                    f"{pt[0]:.6g}",
                    f"{pt[1]:.6g}",
                    f"{pt[2]:.6g}",
                ])
                for col in range(1, 4):
                    item.setFlags(item.flags() | _ItemIsEditable)
                self.addTopLevelItem(item)
                if i in selected_indices:
                    item.setSelected(True)
        finally:
            self._updating = False

    def selectedIndices(self):
        indices = []
        for item in self.selectedItems():
            idx = self.indexOfTopLevelItem(item)
            if idx >= 0:
                indices.append(idx)
        return sorted(indices)

    def keyPressEvent(self, event):
        if event.key() == _Key_Delete:
            indices = self.selectedIndices()
            if indices and self._zone is not None:
                self._zone.remove_points(indices)
                self.populate(self._zone)
                self.pointsChanged.emit()
                if self._manager is not None and self._device is not None:
                    self._manager.deviceZones.save_device_zones(self._device)
            return
        super().keyPressEvent(event)

    def _on_item_changed(self, item, column):
        if self._updating or self._zone is None or column == 0:
            return
        idx = self.indexOfTopLevelItem(item)
        if idx < 0:
            return
        pts = np.asarray(self._zone.hull_points)
        try:
            x = float(self.topLevelItem(idx).text(1))
            y = float(self.topLevelItem(idx).text(2))
            z = float(self.topLevelItem(idx).text(3))
        except ValueError:
            # Restore previous value on bad float input.
            self._updating = True
            try:
                if idx < len(pts):
                    item.setText(column, f"{pts[idx][column - 1]:.6g}")
            finally:
                self._updating = False
            return
        self._zone.set_point(idx, [x, y, z])
        if self._manager is not None and self._device is not None:
            self._manager.deviceZones.save_device_zones(self._device)
        self.pointsChanged.emit()


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class DeviceZonesWidget(Qt.QWidget):

    def __init__(self, manager, module):
        super().__init__()
        self.manager = manager
        self.module = module
        self.setWindowTitle("Device Zones")
        self.resize(900, 600)

        self._current_device = None
        self._current_zone = None
        self._recording = False
        self._last_record_pt = None
        self._quitting = False
        self._in_zone_errors = set()

        self._build_ui()
        self._populate_tree()
        self._update_in_zone_column()
        self.show()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root_layout = Qt.QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        splitter = Qt.QSplitter(Qt.Qt.Orientation.Horizontal)
        root_layout.addWidget(splitter)

        # ---- Left pane ------------------------------------------------
        left = Qt.QWidget()
        left_layout = Qt.QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)

        self.zone_tree = ZoneTreeWidget()
        self.zone_tree._owner = self
        self.zone_tree.setColumnCount(2)
        self.zone_tree.setHeaderLabels(["Device / Zone", "In Zone"])
        self.zone_tree.setItemDelegateForColumn(_COL_IN_ZONE, _ReadOnlyColumnDelegate(self.zone_tree))
        self.zone_tree.header().setStretchLastSection(False)
        self.zone_tree.header().setSectionResizeMode(_COL_NAME, Qt.QHeaderView.ResizeMode.Stretch)
        self.zone_tree.header().setSectionResizeMode(
            _COL_IN_ZONE, Qt.QHeaderView.ResizeMode.ResizeToContents
        )
        self.zone_tree.setDragDropMode(Qt.QAbstractItemView.DragDropMode.InternalMove)
        self.zone_tree.setSelectionMode(Qt.QAbstractItemView.SelectionMode.SingleSelection)
        self.zone_tree.itemSelectionChanged.connect(self._on_zone_selection_changed)
        self.zone_tree.itemChanged.connect(self._on_zone_item_renamed)
        left_layout.addWidget(self.zone_tree)

        btn_grid = Qt.QGridLayout()
        self.btn_add = Qt.QPushButton("Add Zone")
        self.btn_remove = Qt.QPushButton("Remove Zone")
        self.btn_record = Qt.QPushButton("Record")
        self.btn_record.setCheckable(True)
        self.btn_record_point = Qt.QPushButton("Record Point")
        self.btn_clear = Qt.QPushButton("Clear")

        btn_grid.addWidget(self.btn_add, 0, 0)
        btn_grid.addWidget(self.btn_remove, 0, 1)
        btn_grid.addWidget(self.btn_record, 1, 0)
        btn_grid.addWidget(self.btn_record_point, 1, 1)
        btn_grid.addWidget(self.btn_clear, 2, 0)

        self.btn_add.clicked.connect(self._on_add_zone)
        self.btn_remove.clicked.connect(self._on_remove_zone)
        self.btn_record.toggled.connect(self._on_record_toggled)
        self.btn_record_point.clicked.connect(self._on_record_point)
        self.btn_clear.clicked.connect(self._on_clear_points)

        left_layout.addLayout(btn_grid)
        splitter.addWidget(left)

        # ---- Right pane -----------------------------------------------
        right = Qt.QWidget()
        right_layout = Qt.QVBoxLayout(right)
        right_layout.setContentsMargins(4, 4, 4, 4)

        rel_row = Qt.QHBoxLayout()
        self.chk_relative = Qt.QCheckBox("Relative to:")
        self.combo_relative = InterfaceCombo(types=['OptomechDevice'])
        self.combo_relative.setEnabled(False)
        rel_row.addWidget(self.chk_relative)
        rel_row.addWidget(self.combo_relative)
        rel_row.addStretch()
        right_layout.addLayout(rel_row)

        self.hull_tree = HullPointsTree()
        right_layout.addWidget(self.hull_tree)

        self.chk_relative.toggled.connect(self._on_relative_toggled)
        self.combo_relative.currentIndexChanged.connect(self._on_relative_combo_changed)
        self.hull_tree.pointsChanged.connect(self._on_hull_points_changed)
        self.hull_tree.itemSelectionChanged.connect(self._update_3d_scatter)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        # Recording timer
        self._record_timer = Qt.QTimer(self)
        self._record_timer.setInterval(333)
        self._record_timer.timeout.connect(self._record_tick)

        # Zone-membership poll timer
        self._in_zone_timer = Qt.QTimer(self)
        self._in_zone_timer.setInterval(_IN_ZONE_INTERVAL)
        self._in_zone_timer.timeout.connect(self._update_in_zone_column)
        self._in_zone_timer.start()

    # ------------------------------------------------------------------
    # Tree population
    # ------------------------------------------------------------------

    def _populate_tree(self):
        self.zone_tree.blockSignals(True)
        try:
            self.zone_tree.clear()
            device_names = self.manager.listInterfaces('OptomechDevice')
            for dev_name in device_names:
                dev = self.manager.getInterface('OptomechDevice', dev_name)
                dev_item = Qt.QTreeWidgetItem([dev_name])
                dev_item.setData(0, _UserRole, dev)
                dev_item.setFlags(
                    dev_item.flags()
                    & ~_ItemIsEditable
                    & ~_ItemIsDragEnabled
                )
                self.zone_tree.addTopLevelItem(dev_item)
                zones = self.manager.deviceZones.list_zones(dev)
                for zone in zones:
                    zone_item = self._make_zone_item(zone)
                    dev_item.addChild(zone_item)
                dev_item.setExpanded(True)
        finally:
            self.zone_tree.blockSignals(False)

    def _make_zone_item(self, zone):
        item = Qt.QTreeWidgetItem([zone.name])
        item.setData(0, _UserRole, zone)
        item.setFlags(item.flags() | _ItemIsEditable | _ItemIsDragEnabled)
        return item

    def _device_item_for(self, device):
        for i in range(self.zone_tree.topLevelItemCount()):
            item = self.zone_tree.topLevelItem(i)
            if item.data(0, _UserRole) is device:
                return item
        return None

    # ------------------------------------------------------------------
    # Zone membership column
    # ------------------------------------------------------------------

    def _update_in_zone_column(self):
        """Poll every device's zones and report whether the device is inside each."""
        tree = self.zone_tree
        zone_service = self.manager.deviceZones
        tree.blockSignals(True)
        try:
            for i in range(tree.topLevelItemCount()):
                dev_item = tree.topLevelItem(i)
                if dev_item.childCount() == 0:
                    continue
                device = dev_item.data(0, _UserRole)
                try:
                    inside = {id(z) for z in zone_service.find_zones(device)}
                except Exception:
                    # Devices without a position (or with a comms failure) can't be
                    # tested; report unknown and log once per device.
                    inside = None
                    if device not in self._in_zone_errors:
                        self._in_zone_errors.add(device)
                        logger.warning(
                            "Cannot determine zone membership for %s", dev_item.text(_COL_NAME),
                            exc_info=True,
                        )
                else:
                    self._in_zone_errors.discard(device)
                for j in range(dev_item.childCount()):
                    zone_item = dev_item.child(j)
                    zone = zone_item.data(0, _UserRole)
                    if inside is None:
                        text = "?"
                    else:
                        text = "yes" if id(zone) in inside else "no"
                    if zone_item.text(_COL_IN_ZONE) != text:
                        zone_item.setText(_COL_IN_ZONE, text)
        finally:
            tree.blockSignals(False)

    # ------------------------------------------------------------------
    # Selection / detail pane
    # ------------------------------------------------------------------

    def _on_zone_selection_changed(self):
        item = self._selected_zone_item()
        if item is None:
            self._current_device = None
            self._current_zone = None
            self._refresh_detail()
            return
        zone = item.data(0, _UserRole)
        dev_item = item.parent()
        device = dev_item.data(0, _UserRole) if dev_item else None
        self._current_zone = zone
        self._current_device = device
        self._refresh_detail()
        self._update_3d_items()

    def _selected_zone_item(self):
        items = self.zone_tree.selectedItems()
        if not items:
            return None
        item = items[0]
        if item.parent() is None:
            return None
        return item

    def _refresh_detail(self):
        zone = self._current_zone
        self.hull_tree.blockSignals(True)
        self.chk_relative.blockSignals(True)
        self.combo_relative.blockSignals(True)
        try:
            if zone is None:
                self.hull_tree.clear()
                self.chk_relative.setChecked(False)
                self.combo_relative.setEnabled(False)
                return

            has_rel = zone.relative_to is not None
            self.chk_relative.setChecked(has_rel)
            self.combo_relative.setEnabled(has_rel)
            if has_rel:
                rel_name = zone.relative_to.name()
                idx = self.combo_relative.findText(rel_name)
                if idx >= 0:
                    self.combo_relative.setCurrentIndex(idx)

            self.hull_tree.setContext(self.manager, self._current_device, zone)
            self.hull_tree.populate(zone)
        finally:
            self.hull_tree.blockSignals(False)
            self.chk_relative.blockSignals(False)
            self.combo_relative.blockSignals(False)

    # ------------------------------------------------------------------
    # Relative-to controls
    # ------------------------------------------------------------------

    def _on_relative_toggled(self, checked):
        self.combo_relative.setEnabled(checked)
        zone = self._current_zone
        device = self._current_device
        if zone is None:
            return

        new_rel = self.combo_relative.getSelectedObj() if checked else None
        old_rel = zone.relative_to

        if new_rel is old_rel:
            return

        pts = np.asarray(zone.hull_points)
        if len(pts) > 0:
            answer = Qt.QMessageBox.question(
                self,
                "Change coordinate frame",
                "Changing the reference device will clear all hull points. Continue?",
            )
            if answer != Qt.QMessageBox.StandardButton.Yes:
                self.chk_relative.blockSignals(True)
                self.combo_relative.blockSignals(True)
                self.chk_relative.setChecked(old_rel is not None)
                self.combo_relative.setEnabled(old_rel is not None)
                self.chk_relative.blockSignals(False)
                self.combo_relative.blockSignals(False)
                return
            zone.clear_points()

        zone.set_relative_to(new_rel)
        self._refresh_detail()
        if device is not None:
            self.manager.deviceZones.save_device_zones(device)
        self._update_3d_items()

    def _on_relative_combo_changed(self, _index):
        if not self.chk_relative.isChecked():
            return
        self._on_relative_toggled(True)

    # ------------------------------------------------------------------
    # Add / Remove / Rename
    # ------------------------------------------------------------------

    def _on_add_zone(self):
        item = self._selected_zone_item()
        if item is not None:
            dev_item = item.parent()
        else:
            sel = self.zone_tree.selectedItems()
            dev_item = sel[0] if sel else None

        if dev_item is None or dev_item.parent() is not None:
            if self.zone_tree.topLevelItemCount() == 0:
                return
            dev_item = self.zone_tree.topLevelItem(0)

        device = dev_item.data(0, _UserRole)
        zone = self.manager.deviceZones.add_zone(device, "New Zone", save=True)
        zone_item = self._make_zone_item(zone)
        dev_item.addChild(zone_item)
        dev_item.setExpanded(True)
        self._update_in_zone_column()
        self.zone_tree.setCurrentItem(zone_item)
        self.zone_tree.editItem(zone_item, 0)

    def _on_remove_zone(self):
        item = self._selected_zone_item()
        if item is None:
            return
        zone = item.data(0, _UserRole)
        dev_item = item.parent()
        device = dev_item.data(0, _UserRole)
        answer = Qt.QMessageBox.question(
            self, "Remove Zone", f"Remove zone '{zone.name}'?"
        )
        if answer != Qt.QMessageBox.StandardButton.Yes:
            return
        self.manager.deviceZones.remove_zone(device, zone.name, save=True)
        dev_item.removeChild(item)
        self._current_zone = None
        self._current_device = None
        self._refresh_detail()
        self._clear_3d_items()

    def _on_zone_item_renamed(self, item, column):
        if column != 0 or item.parent() is None:
            return
        zone = item.data(0, _UserRole)
        dev_item = item.parent()
        device = dev_item.data(0, _UserRole)
        new_name = item.text(0)
        if new_name == zone.name:
            return
        old_name = zone.name
        self.manager.deviceZones.rename_zone(device, old_name, new_name, save=True)

    # ------------------------------------------------------------------
    # Hull-point operations
    # ------------------------------------------------------------------

    def _on_clear_points(self):
        zone = self._current_zone
        if zone is None:
            return
        answer = Qt.QMessageBox.question(
            self, "Clear Points", "Remove all hull points from this zone?"
        )
        if answer != Qt.QMessageBox.StandardButton.Yes:
            return
        zone.clear_points()
        self.hull_tree.populate(zone)
        if self._current_device is not None:
            self.manager.deviceZones.save_device_zones(self._current_device)
        self._update_3d_items()

    def _on_hull_points_changed(self):
        self._update_3d_items()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def _on_record_toggled(self, checked):
        self._recording = checked
        if checked:
            self._last_record_pt = None
            self._record_timer.start()
        else:
            self._record_timer.stop()
            if self._current_device is not None and self._current_zone is not None:
                self.manager.deviceZones.save_device_zones(self._current_device)
            self._update_3d_mesh()

    def _on_record_point(self):
        if self._current_device is None or self._current_zone is None:
            return
        self._add_current_position(save=True)

    def _record_tick(self):
        if self._current_device is None or self._current_zone is None:
            return
        self._add_current_position(save=False)

    def _add_current_position(self, save=True):
        device = self._current_device
        zone = self._current_zone
        pos = np.asarray(device.globalPosition(), dtype=float)

        rel = zone.relative_to
        if rel is not None:
            pos = np.asarray(rel.mapFromGlobal(pos), dtype=float)

        pos = pos.ravel()[:3]

        if self._last_record_pt is not None:
            if np.linalg.norm(pos - self._last_record_pt) < 1e-6:
                return

        self._last_record_pt = pos.copy()
        zone.add_point(pos)

        # If the last 3 points are collinear, the spatially middle one is redundant — drop it.
        pts = np.asarray(zone.hull_points)
        if len(pts) >= 3 and _points_collinear(pts[-3], pts[-2], pts[-1]):
            last3 = pts[-3:]
            direction = last3[-1] - last3[0]
            norm = np.linalg.norm(direction)
            projs = last3 @ (direction / norm) if norm > 0 else np.arange(3, dtype=float)
            spatial_mid = len(pts) - 3 + int(np.argsort(projs)[1])
            zone.remove_points([spatial_mid])

        self.hull_tree.populate(zone)

        if save and self._current_device is not None:
            self.manager.deviceZones.save_device_zones(self._current_device)

        self._update_3d_scatter()
        self._update_3d_mesh()

    # ------------------------------------------------------------------
    # 3D visualisation (delegated to DeviceZonesVisualizerAdapter)
    # ------------------------------------------------------------------

    def _adapter(self):
        return self.module._3d_adapter

    def _clear_3d_items(self):
        a = self._adapter()
        if a is not None:
            a.clear_items()

    def _update_3d_items(self):
        self._update_3d_scatter()
        if not self._recording:
            self._update_3d_mesh()

    def _update_3d_scatter(self):
        a = self._adapter()
        if a is None:
            return
        zone = self._current_zone
        if zone is None:
            a.clear_items()
            return
        selected = set(self.hull_tree.selectedIndices())
        a.update_scatter(zone, selected)

    def _update_3d_mesh(self):
        a = self._adapter()
        if a is None:
            return
        a.update_mesh(self._current_zone)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _do_cleanup(self):
        self._in_zone_timer.stop()
        if self._recording:
            self._record_timer.stop()
            self._recording = False
        self._clear_3d_items()

    def quit(self):
        if self._quitting:
            return
        self._quitting = True
        self._do_cleanup()
        self.module.quit(fromUi=True)
        self.close()

    def closeEvent(self, event):
        if not self._quitting:
            self._quitting = True
            self._do_cleanup()
            self.module.quit(fromUi=True)
        event.accept()
