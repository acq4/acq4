import os
from typing import Union

import numpy as np

from acq4.devices.Device import Device
from acq4.modules.Visualize3D import VisualizePathPlan
from acq4.util import Qt
from acq4.util.geometry import Plane, Geometry
from pyqtgraph import opengl as gl


class VisualizerWindow(Qt.QMainWindow):
    newDeviceSignal = Qt.pyqtSignal(object)
    focusEvent = Qt.pyqtSignal()

    def __init__(self, expectedDevices=0, testing=False):
        super().__init__(None)
        self.testing = testing
        self._devicesBeingAdded = expectedDevices
        self._itemsByDevice = {}  # Maps devices to their visualization components
        self._moduleReadyEvent = None

        self.setWindowTitle("3D Visualization of all Optomech Devices")
        self.setGeometry(50, 50, 1000, 600)
        self.setWindowIcon(Qt.QIcon(os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons.svg")))

        # Main layout is a horizontal splitter
        self.splitter = Qt.QSplitter(Qt.Qt.Horizontal)
        self.setCentralWidget(self.splitter)

        # Left side: 3D view
        self.viewWidget = Qt.QWidget()
        self.viewLayout = Qt.QVBoxLayout()
        self.viewWidget.setLayout(self.viewLayout)
        self.splitter.addWidget(self.viewWidget)

        # Create 3D view
        self.view = gl.GLViewWidget()
        self.viewLayout.addWidget(self.view)
        self.view.setCameraPosition(distance=0.2, azimuth=-90, elevation=30)
        grid = gl.GLGridItem()
        grid.scale(0.001, 0.001, 0.001)
        self.view.addItem(grid)
        axes = gl.GLAxisItem()
        axes.setSize(0.1, 0.1, 0.1)
        self.view.addItem(axes)

        # Right side: Tree widget for device controls
        self.controlWidget = Qt.QWidget()
        self.controlLayout = Qt.QVBoxLayout()
        self.controlWidget.setLayout(self.controlLayout)
        self.splitter.addWidget(self.controlWidget)

        # Create tree widget for hierarchical device display
        self.deviceTree = Qt.QTreeWidget()
        self.deviceTree.setHeaderLabel("Devices")
        self.deviceTree.setMinimumWidth(250)
        self.deviceTree.itemChanged.connect(self.toggleVisibility)
        self.controlLayout.addWidget(self.deviceTree)

        # Set splitter sizes
        self.splitter.setSizes([700, 300])

        # Connect signals
        self.newDeviceSignal.connect(self._addDevice)
        self.focusEvent.connect(self._focus)

    def target(self, visible=False, color=(0, 0, 1, 1)):
        target = gl.GLScatterPlotItem(pos=[], color=color, size=10, pxMode=True)
        target.setVisible(visible)
        self.view.addItem(target)
        return target

    def path(self, color, visible=False):
        path = gl.GLLinePlotItem(pos=[], color=color, width=1)
        path.setVisible(visible)
        self.view.addItem(path)
        return path

    def clear(self):
        for dev in list(self._itemsByDevice.keys()):
            self._removeDevice(dev)
        self._itemsByDevice = {}

    def focus(self):
        self.focusEvent.emit()

    def _focus(self):
        self.show()
        self.activateWindow()
        self.raise_()

    def addDevice(self, dev: "OptomechDevice", ready_event=None):
        self._moduleReadyEvent = ready_event
        self.newDeviceSignal.emit(dev)

    def _addDevice(self, dev: Union[Device, "OptomechDevice"]):
        try:
            dev.sigGeometryChanged.connect(self.handleGeometryChange)
            if (geom := dev.getGeometry()) is None:
                return

            # Create device entry in data structure
            self._itemsByDevice[dev] = {"checkboxes": {}}

            # Add geometry to the scene
            self.addGeometry(geom, dev)
            dev.sigGlobalTransformChanged.connect(self.handleTransformUpdate)
            self.handleTransformUpdate(dev, dev)

            # Create tree item for this device
            deviceItem = Qt.QTreeWidgetItem(self.deviceTree)
            deviceItem.setText(0, dev.name())
            deviceItem.setFlags(deviceItem.flags() | Qt.Qt.ItemIsUserCheckable)
            deviceItem.setCheckState(0, Qt.Qt.Checked)
            deviceItem.setData(0, Qt.Qt.UserRole, dev)
            self._itemsByDevice[dev]["checkbox root"] = deviceItem

            # Create geometry sub-item
            geomItem = Qt.QTreeWidgetItem(deviceItem)
            geomItem.setText(0, "Geometry")
            geomItem.setFlags(geomItem.flags() | Qt.Qt.ItemIsUserCheckable)
            geomItem.setCheckState(0, Qt.Qt.Checked)
            geomItem.setData(0, Qt.Qt.UserRole, "geometry")
            self._itemsByDevice[dev]["checkboxes"]["geometry"] = geomItem

            # Add boundaries if available
            if bounds := dev.getBoundaries():
                self._itemsByDevice[dev]["limits"] = self.createBounds(bounds, False)

                # Create limits sub-item
                limitsItem = Qt.QTreeWidgetItem(deviceItem)
                limitsItem.setText(0, "Range of Motion")
                limitsItem.setFlags(limitsItem.flags() | Qt.Qt.ItemIsUserCheckable)
                limitsItem.setCheckState(0, Qt.Qt.Unchecked)
                limitsItem.setData(0, Qt.Qt.UserRole, "limits")
                self._itemsByDevice[dev]["checkboxes"]["limits"] = limitsItem

                if hasattr(dev, "sigCalibrationChanged"):
                    dev.sigCalibrationChanged.connect(self.handleGeometryChange)

            obstacleItem = Qt.QTreeWidgetItem(deviceItem)
            obstacleItem.setText(0, "Obstacle")
            obstacleItem.setFlags(obstacleItem.flags() | Qt.Qt.ItemIsUserCheckable)
            obstacleItem.setCheckState(0, Qt.Qt.Unchecked)
            obstacleItem.setData(0, Qt.Qt.UserRole, "obstacle")
            self._itemsByDevice[dev]["checkboxes"]["obstacle"] = obstacleItem

            voxelsItem = Qt.QTreeWidgetItem(deviceItem)
            voxelsItem.setText(0, "Raw Obstacle Voxels")
            voxelsItem.setFlags(voxelsItem.flags() | Qt.Qt.ItemIsUserCheckable)
            voxelsItem.setCheckState(0, Qt.Qt.Unchecked)
            voxelsItem.setData(0, Qt.Qt.UserRole, "voxels")
            self._itemsByDevice[dev]["checkboxes"]["voxels"] = voxelsItem
        finally:
            self._devicesBeingAdded -= 1
            if self._moduleReadyEvent is not None and self._devicesBeingAdded == 0:
                self._moduleReadyEvent.set()
                self._moduleReadyEvent = None

    def ensurePathTogglerExists(self, device):
        """Make sure the device has a toggle for showing its path plan. Returns whether that toggle is on."""
        toggles = self._itemsByDevice[device]["checkboxes"]
        generally_visible = self._itemsByDevice[device]["checkbox root"].checkState(0) == Qt.Qt.Checked
        if "path" not in toggles:
            path_item = Qt.QTreeWidgetItem(self._itemsByDevice[device]["checkbox root"])
            path_item.setText(0, "Path plan")
            path_item.setFlags(path_item.flags() | Qt.Qt.ItemIsUserCheckable)
            path_item.setCheckState(0, Qt.Qt.Checked)
            path_item.setDisabled(not generally_visible)
            path_item.setData(0, Qt.Qt.UserRole, "path")
            toggles["path"] = path_item
        return generally_visible and toggles["path"].checkState(0) == Qt.Qt.Checked

    def getDeviceCheckboxes(self, name: str):
        """This is an ugly code path. The `name` here is not an exact match; it's the coordinate system name for the
        geometry associated with a device. Further, some devices will have subdevices, and so their name won't even be
        uniquely present in only one geometry even if all devices had completely unique names."""
        # TODO handle subdevices
        device = next((dev for dev in self._itemsByDevice if dev.name() in name), None)
        if device is None:
            raise ValueError(f"Could not find device associated with '{name}'")
        return self._itemsByDevice[device]["checkboxes"]

    def toggleVisibility(self, item: Qt.QTreeWidgetItem, column):
        parentItem = item.parent()
        visible = item.checkState(0) == Qt.Qt.Checked

        # A top-level device item
        if parentItem is None:
            dev = item.data(0, Qt.Qt.UserRole)

            if dev not in self._itemsByDevice:
                return

            for ch in range(item.childCount()):
                child = item.child(ch)
                child.setDisabled(not visible)
                self.toggleVisibility(child, None)  # let each child decide if it's really visible

        else:  # This is a component item
            dev = parentItem.data(0, Qt.Qt.UserRole)
            visible = visible and parentItem.checkState(0) == Qt.Qt.Checked
            componentType = item.data(0, Qt.Qt.UserRole)

            if dev not in self._itemsByDevice:
                return

            if componentType in self._itemsByDevice[dev]:
                self._itemsByDevice[dev][componentType].setVisible(visible)
            elif componentType in ["obstacle", "voxels"]:
                for items in self._itemsByDevice.values():
                    if "path" in items:
                        items["path"].toggleDeviceVisibility(componentType, dev, visible)

    def pathPlanVisualizer(self, traveler) -> VisualizePathPlan:
        if traveler not in self._itemsByDevice:
            raise ValueError(f"{traveler.name()} is not known to the Visualizer")
        if "path" not in self._itemsByDevice[traveler]:
            self._itemsByDevice[traveler]["path"] = VisualizePathPlan(self, traveler)
        return self._itemsByDevice[traveler]["path"]

    def createBounds(self, bounds, visible):
        edges = []
        for a, b in Plane.wireframe(*bounds):
            for bound in bounds:
                if not (bound.allows_point(a) and bound.allows_point(b)):
                    continue
            if not self.testing and np.linalg.norm(a - b) > 0.1:
                continue  # ignore bounds that are really far away
            edge = [a, b]
            edges.extend(edge)
        plot = gl.GLLinePlotItem(pos=np.array(edges), color=(1, 0, 0, 0.2), width=4, mode="lines")
        plot.setVisible(visible)
        self.view.addItem(plot)
        return plot

    def addGeometry(self, geom: Geometry, key=None):
        if key is None:
            key = geom.name
        self._itemsByDevice.setdefault(key, {})
        self._itemsByDevice[key]["geometry object"] = geom
        mesh = geom.glMesh()
        self.view.addItem(mesh)
        self._itemsByDevice[key]["geometry"] = mesh

    def _removeDevice(self, dev):
        if dev not in self._itemsByDevice:
            return
        items = self._itemsByDevice[dev]
        items.pop("geometry object", None)

        # Disconnect signals
        if not self.testing:  # todo properly mock devices for the tests
            dev.sigGeometryChanged.disconnect(self.handleGeometryChange)
            dev.sigGlobalTransformChanged.disconnect(self.handleTransformUpdate)

        # Remove tree item
        tree_item = items.pop("checkbox root")
        index = self.deviceTree.indexOfTopLevelItem(tree_item)
        if index != -1:
            self.deviceTree.takeTopLevelItem(index)
        items.pop("checkboxes", None)

        if "path" in items:
            path = items.pop("path")
            path.safelyDestroy()

        # Remove everything else from view
        for component in items.values():
            self.view.removeItem(component)

        for other, o_items in self._itemsByDevice.items():
            if "path" in o_items:
                o_items["path"].removeDevice(dev)

        del self._itemsByDevice[dev]

    def handleTransformUpdate(self, moved_device: "OptomechDevice", cause_device: "OptomechDevice"):
        geom = self._itemsByDevice.get(moved_device, {}).get("geometry object")
        if geom is None:
            return
        xform = moved_device.globalPhysicalTransform() * geom.transform.as_pyqtgraph()
        self.setMeshTransform(moved_device, xform)

    def setMeshTransform(self, dev, xform):
        self._itemsByDevice[dev]["geometry"].setTransform(xform)

    def handleGeometryChange(self, dev: "OptomechDevice"):
        self._removeDevice(dev)
        self._itemsByDevice[dev] = {}
        self.addDevice(dev)
        # TODO reprime caches
