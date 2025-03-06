import os
import queue
import time
from threading import Thread
from typing import Union

import numpy as np

from acq4.devices.Device import Device
from acq4.devices.OptomechDevice import OptomechDevice
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.geometry import Plane, Volume, Geometry
from acq4.util.threadrun import runInGuiThread
from coorx import Transform, TTransform
from pyqtgraph import opengl as gl
from pyqtgraph.opengl.GLGraphicsItem import GLGraphicsItem


class Visualize3D(Module):
    moduleDisplayName = "3D Visualization"
    moduleCategory = "Utilities"

    win = None

    @classmethod
    def openWindow(cls):
        if cls.win is None:
            cls.win = VisualizerWindow()
        cls.win.show()
        cls.win.clear()

    def __init__(self, manager, name: str, config: dict):
        super().__init__(manager, name, config)
        runInGuiThread(self.openWindow)
        for dev in manager.listInterfaces("OptomechDevice"):
            dev = manager.getDevice(dev)
            self.win.addDevice(dev)


class VisualizerWindow(Qt.QMainWindow):
    pathStartSignal = Qt.pyqtSignal(object, object, list)
    newObstacleSignal = Qt.pyqtSignal(object, object, object, object)
    newDeviceSignal = Qt.pyqtSignal(object)
    pathUpdateSignal = Qt.pyqtSignal(object)
    focusEvent = Qt.pyqtSignal()

    def __init__(self, testing=False):
        super().__init__(None)
        self._testing = testing
        self.setWindowTitle("3D Visualization of all Optomech Devices")
        self.setGeometry(50, 50, 1000, 600)
        self.setWindowIcon(Qt.QIcon(os.path.join(os.path.dirname(__file__), "icons.svg")))

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
        self.deviceTree.itemChanged.connect(self.handleTreeItemChanged)
        self.controlLayout.addWidget(self.deviceTree)

        # Path planning controls
        self.pathPlanToggler = Qt.QCheckBox("Show Path Plan")
        self.pathPlanToggler.setEnabled(False)
        self.pathPlanToggler.stateChanged.connect(self.togglePathPlan)
        self.controlLayout.addWidget(self.pathPlanToggler)

        # Set splitter sizes
        self.splitter.setSizes([700, 300])

        # Connect signals
        self.pathStartSignal.connect(self._startPath)
        self.newObstacleSignal.connect(self._addObstacleVolumeOutline)
        self.newDeviceSignal.connect(self._addDevice)
        self.pathUpdateSignal.connect(self._appendPath)
        self.focusEvent.connect(self._focus)

        # Path planning thread
        self._pathUpdates = queue.Queue()
        self._pathWatcherThread = Thread(target=self._watchForPathUpdates)
        self._pathWatcherThread.daemon = True
        self._pathWatcherThread.start()

        # Data structures
        self._itemsByDevice = {}  # Maps devices to their visualization components
        self._path: dict[object, GLGraphicsItem | list] = {}  # Path planning visualization elements

    def clear(self):
        for dev in list(self._itemsByDevice.keys()):
            self._removeDevice(dev)
        self._itemsByDevice = {}
        self.removePath()

    def focus(self):
        self.focusEvent.emit()

    def _focus(self):
        self.show()
        self.activateWindow()
        self.raise_()

    def addDevice(self, dev: OptomechDevice):
        self.newDeviceSignal.emit(dev)

    def _addDevice(self, dev: Union[Device, OptomechDevice]):
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
        self._itemsByDevice[dev]["tree item"] = deviceItem

        # Create geometry sub-item
        geomItem = Qt.QTreeWidgetItem(deviceItem)
        geomItem.setText(0, "Geometry")
        geomItem.setFlags(geomItem.flags() | Qt.Qt.ItemIsUserCheckable)
        geomItem.setCheckState(0, Qt.Qt.Checked)
        geomItem.setData(0, Qt.Qt.UserRole, "geometry")
        self._itemsByDevice[dev]["checkboxes"]["geometry"] = geomItem

        # Add boundaries if available
        if bounds := dev.getBoundaries():
            self._itemsByDevice[dev]["limits"] = {}
            self.addBounds(bounds, self._itemsByDevice[dev]["limits"])

            # Create limits sub-item
            limitsItem = Qt.QTreeWidgetItem(deviceItem)
            limitsItem.setText(0, "Range of Motion")
            limitsItem.setFlags(limitsItem.flags() | Qt.Qt.ItemIsUserCheckable)
            limitsItem.setCheckState(0, Qt.Qt.Unchecked)
            limitsItem.setData(0, Qt.Qt.UserRole, "limits")
            self._itemsByDevice[dev]["checkboxes"]["limits"] = limitsItem

            # Initially hide limits
            self.toggleDeviceLimitsVisibility(Qt.QtCore.Qt.Unchecked, dev.name())

            if hasattr(dev, "sigCalibrationChanged"):
                dev.sigCalibrationChanged.connect(self.handleGeometryChange)

        # Create obstacle sub-item (initially disabled)
        obstacleItem = Qt.QTreeWidgetItem(deviceItem)
        obstacleItem.setText(0, "Obstacle")
        obstacleItem.setFlags(obstacleItem.flags() | Qt.Qt.ItemIsUserCheckable)
        obstacleItem.setCheckState(0, Qt.Qt.Checked)
        obstacleItem.setDisabled(True)  # Disabled until path planning starts
        obstacleItem.setData(0, Qt.Qt.UserRole, "obstacle")
        self._itemsByDevice[dev]["checkboxes"]["obstacle"] = obstacleItem

        # Create raw voxels sub-item (initially disabled)
        voxelsItem = Qt.QTreeWidgetItem(deviceItem)
        voxelsItem.setText(0, "Raw Obstacle Voxels")
        voxelsItem.setFlags(voxelsItem.flags() | Qt.Qt.ItemIsUserCheckable)
        voxelsItem.setCheckState(0, Qt.Qt.Unchecked)
        voxelsItem.setDisabled(True)  # Disabled until path planning starts
        voxelsItem.setData(0, Qt.Qt.UserRole, "voxels")
        self._itemsByDevice[dev]["checkboxes"]["voxels"] = voxelsItem

    def handleTreeItemChanged(self, item: Qt.QTreeWidgetItem, column):
        parentItem = item.parent()
        visible = item.checkState(0) == Qt.Qt.Checked

        # A top-level device item
        if parentItem is None:
            dev = item.data(0, Qt.Qt.UserRole)

            if dev not in self._itemsByDevice:
                return

            for ch in range(item.childCount()):
                child = item.child(ch)
                name = child.data(0, Qt.Qt.UserRole)
                child.setDisabled(not visible or name not in self._itemsByDevice[dev])
                if visible:
                    self.handleTreeItemChanged(child, None)

            if not visible:
                self.toggleDeviceLimitsVisibility(False, dev.name())
                for item in self._itemsByDevice[dev].values():
                    if hasattr(item, "setVisible"):
                        item.setVisible(False)
        else:  # This is a component item
            dev = parentItem.data(0, Qt.Qt.UserRole)
            componentType = item.data(0, Qt.Qt.UserRole)

            if dev not in self._itemsByDevice:
                return

            if componentType in self._itemsByDevice[dev]:
                if componentType == "limits":
                    self.toggleDeviceLimitsVisibility(
                        Qt.QtCore.Qt.Checked if visible else Qt.QtCore.Qt.Unchecked,
                        dev.name()
                    )
                else:
                    self._itemsByDevice[dev][componentType].setVisible(visible)

    def addBounds(self, bounds, displayables_container: dict):
        for a, b in Plane.wireframe(*bounds):
            for bound in bounds:
                if not (bound.allows_point(a) and bound.allows_point(b)):
                    continue
            if not self._testing and np.linalg.norm(a - b) > 0.1:
                continue  # ignore bounds that are really far away
            edge = gl.GLLinePlotItem(pos=np.array([a, b]), color=(1, 0, 0, 0.2), width=4)
            self.view.addItem(edge)
            displayables_container[(tuple(a), tuple(b))] = edge

    def toggleDeviceLimitsVisibility(self, state, dev_name=None):
        visible = state == Qt.QtCore.Qt.Checked
        for key, data in self._itemsByDevice.items():
            if key.name() == dev_name:
                for edge in data.get("limits", {}).values():
                    edge.setVisible(visible)

    def addGeometry(self, geom: Geometry, key=None):
        if key is None:
            key = geom.name
        self._itemsByDevice.setdefault(key, {})
        self._itemsByDevice[key]["geom"] = geom
        mesh = geom.glMesh()
        self.view.addItem(mesh)
        self._itemsByDevice[key]["geometry"] = mesh

    def _removeDevice(self, dev):
        if dev not in self._itemsByDevice:
            return

        # Disconnect signals
        if not self._testing:
            dev.sigGeometryChanged.disconnect(self.handleGeometryChange)
            dev.sigGlobalTransformChanged.disconnect(self.handleTransformUpdate)

        # Remove limits from view
        for edge in self._itemsByDevice[dev].pop("limits", {}).values():
            self.view.removeItem(edge)
            edge.deleteLater()

        # Remove tree item
        if "tree item" in self._itemsByDevice[dev]:
            tree_item = self._itemsByDevice[dev].pop("tree item")
            parent = tree_item.parent()
            parent.removeChild(tree_item)

        # Remove everything else from view
        for component in self._itemsByDevice[dev]:
            self.view.removeItem(component)

        del self._itemsByDevice[dev]

    def handleTransformUpdate(self, moved_device: OptomechDevice, cause_device: OptomechDevice):
        geom = self._itemsByDevice.get(moved_device, {}).get("geom")
        if geom is None:
            return
        xform = moved_device.globalPhysicalTransform() * geom.transform.as_pyqtgraph()
        self.setMeshTransform(moved_device, xform)

    def setMeshTransform(self, dev, xform):
        self._itemsByDevice[dev]["geometry"].setTransform(xform)

    def handleGeometryChange(self, dev: OptomechDevice):
        self._removeDevice(dev)
        self._itemsByDevice[dev] = {}
        self.addDevice(dev)

    def startPath(self, start, stop, bounds):
        self.pathStartSignal.emit(start, stop, bounds)

    def _startPath(self, start, stop, bounds):
        # Clear any existing path
        self.removePath()

        # Enable path planning controls
        self.pathPlanToggler.setEnabled(True)
        self.pathPlanToggler.setChecked(True)

        # Add initial path line
        self._appendPath([start, stop])

        # Add start and destination markers
        start_target = gl.GLScatterPlotItem(pos=np.array([start]), color=(0, 0, 1, 1), size=10, pxMode=True)
        self.view.addItem(start_target)
        self._path["start target"] = start_target

        dest_target = gl.GLScatterPlotItem(pos=np.array([stop]), color=(0, 1, 0, 1), size=10, pxMode=True)
        self.view.addItem(dest_target)
        self._path["dest target"] = dest_target

        # Add boundary visualization
        self.addBounds(bounds, self._path)

    def addObstacleVolumeOutline(self, obstacle: Volume, to_global: Transform):
        self.newObstacleSignal.emit(obstacle, to_global, *obstacle.surface_mesh)

    def _addObstacleVolumeOutline(self, obstacle: Volume, to_global: Transform, verts, faces):
        cs_name = obstacle.transform.systems[0].name
        device = next((dev for dev in self._itemsByDevice if dev.name() in cs_name))
        generally_visible = self._itemsByDevice[device]["checkboxes"]["geometry"].parent().checkState(
            0) == Qt.Qt.Checked

        # Create mesh for obstacle surface
        mesh_data = gl.MeshData(vertexes=verts, faces=faces)
        mesh = gl.GLMeshItem(
            meshdata=mesh_data, smooth=True, color=(0.1, 0.1, 0.3, 0.25), shader="balloon", glOptions="additive"
        )
        recenter_voxels = TTransform(
            offset=(0.5, 0.5, 0.5),
            from_cs=f"[isosurface of {cs_name}]",
            to_cs=cs_name,
        )
        mesh.setTransform((to_global * obstacle.transform * recenter_voxels).as_pyqtgraph())
        self.view.addItem(mesh)
        self._itemsByDevice[device]["obstacle"] = mesh

        # Create volumetric visualization for raw voxels
        vol_data = np.zeros(obstacle.volume.T.shape + (4,), dtype=np.ubyte)
        vol_data[..., :3] = (30, 10, 10)
        vol_data[..., 3] = obstacle.volume.T * 5
        vol = gl.GLVolumeItem(vol_data, sliceDensity=10, smooth=False, glOptions="additive")
        vol.setVisible(False)  # Initially hidden
        vol.setTransform((to_global * obstacle.transform).as_pyqtgraph())
        self.view.addItem(vol)
        self._itemsByDevice[device]["voxels"] = vol

        # Enable obstacle checkboxes for this device
        mesh_checkbox = self._itemsByDevice[device]["checkboxes"]["obstacle"]
        was_disabled = mesh_checkbox.isDisabled()
        mesh_checkbox.setDisabled(not generally_visible)
        if generally_visible and was_disabled:
            mesh.setVisible(generally_visible)
            mesh_checkbox.setCheckState(0, Qt.Qt.Checked)
        vol_checkbox = self._itemsByDevice[device]["checkboxes"]["voxels"]
        vol_checkbox.setDisabled(not generally_visible)

    def updatePath(self, path, skip=3):
        self._pathUpdates.put((path, skip))

    def _watchForPathUpdates(self):
        n_updates = 0
        while True:
            path, skip = self._pathUpdates.get()
            n_updates += 1
            if self._testing or n_updates % skip == 0:
                self.pathUpdateSignal.emit(path)
                time.sleep(0.02)

    @property
    def hasPath(self):
        return len(self._path) > 0

    def _appendPath(self, path):
        self._path.setdefault("paths", [])
        if len(self._path["paths"]) > 0:
            self._path["paths"][-1].color = (1, 0.7, 0, 0.02)
            self._path["paths"][-1].paint()
        path = gl.GLLinePlotItem(pos=np.array(path), color=(0.1, 1, 0.7, 1), width=1)
        self.view.addItem(path)
        self._path["paths"].append(path)

    def togglePathPlan(self, state):
        visible = state == Qt.QtCore.Qt.Checked

        # Update visibility of path elements
        for key, viz in self._path.items():
            if isinstance(viz, list):
                for v in viz:
                    v.setVisible(visible)
            else:
                viz.setVisible(visible)

        # Enable/disable obstacle checkboxes in the tree
        # for dev, data in self._itemsByDevice.items():
        #     if "checkboxes" in data:
        #         obstacle_item = data["checkboxes"].get("obstacle")
        #         voxels_item = data["checkboxes"].get("voxels")
        #
        #         if obstacle_item is not None:
        #             # Only enable if device has obstacles
        #             has_obstacles = dev in self._deviceObstacles and len(self._deviceObstacles[dev]) > 0
        #             obstacle_item.setDisabled(not (visible and has_obstacles))
        #
        #             # Update visibility based on checkbox state if path plan is visible
        #             if visible and has_obstacles:
        #                 show_obstacle = obstacle_item.checkState(0) == Qt.Qt.Checked
        #                 for obstacle in self._deviceObstacles[dev]:
        #                     if obstacle in self._path:
        #                         self._path[obstacle].setVisible(show_obstacle)
        #             else:
        #                 # Hide obstacles if path plan is hidden
        #                 for obstacle in self._deviceObstacles.get(dev, []):
        #                     if obstacle in self._path:
        #                         self._path[obstacle].setVisible(False)
        #
        #         if voxels_item is not None:
        #             # Only enable if device has voxels
        #             voxel_key = f"voxels of {dev.name()}"
        #             has_voxels = voxel_key in self._path
        #             voxels_item.setDisabled(not (visible and has_voxels))
        #
        #             # Update visibility based on checkbox state if path plan is visible
        #             if visible and has_voxels:
        #                 show_voxels = voxels_item.checkState(0) == Qt.Qt.Checked
        #                 self._path[voxel_key].setVisible(show_voxels)
        #             elif voxel_key in self._path:
        #                 self._path[voxel_key].setVisible(False)

    def removePath(self):
        for key, viz in list(self._path.items()):
            if isinstance(viz, list):
                for kid in viz:
                    self.view.removeItem(kid)
                    kid.deleteLater()
            else:
                self.view.removeItem(viz)
                viz.deleteLater()
        self._path = {}

        for items in self._itemsByDevice.values():
            if "obstacle" in items:
                items["obstacle"].setVisible(False)
                self.view.removeItem(items["obstacle"])
                items["obstacle"].deleteLater()
                items["checkboxes"]["obstacle"].setDisabled(True)
            if "voxels" in items:
                # todo reuse these components
                items["voxels"].setVisible(False)
                self.view.removeItem(items["voxels"])
                items["voxels"].deleteLater()
                items["checkboxes"]["voxels"].setDisabled(True)

        # Reset path plan toggle
        self.pathPlanToggler.setChecked(False)
        self.pathPlanToggler.setEnabled(False)
