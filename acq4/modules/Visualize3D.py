import os
import queue
import time
from threading import Thread
from typing import Union, Dict, Any, Optional

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
        self._geometries = {}  # Maps devices to their visualization components
        self._path: dict[object, GLGraphicsItem] = {}  # Path planning visualization elements
        self._deviceObstacles = {}  # Maps devices to their obstacles

    def clear(self):
        for dev in list(self._geometries.keys()):
            self._removeDevice(dev)
        self._geometries = {}
        self._deviceObstacles = {}
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
        self._geometries[dev] = {"checkboxes": {}}

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
        self._geometries[dev]["tree_item"] = deviceItem

        # Create geometry sub-item
        geomItem = Qt.QTreeWidgetItem(deviceItem)
        geomItem.setText(0, "Geometry")
        geomItem.setFlags(geomItem.flags() | Qt.Qt.ItemIsUserCheckable)
        geomItem.setCheckState(0, Qt.Qt.Checked)
        geomItem.setData(0, Qt.Qt.UserRole, "geometry")
        self._geometries[dev]["checkboxes"]["geometry"] = geomItem

        # Add boundaries if available
        if bounds := dev.getBoundaries():
            self._geometries[dev]["limits"] = {}
            self.addBounds(bounds, self._geometries[dev]["limits"])

            # Create limits sub-item
            limitsItem = Qt.QTreeWidgetItem(deviceItem)
            limitsItem.setText(0, "Range of Motion")
            limitsItem.setFlags(limitsItem.flags() | Qt.Qt.ItemIsUserCheckable)
            limitsItem.setCheckState(0, Qt.Qt.Unchecked)
            limitsItem.setData(0, Qt.Qt.UserRole, "limits")
            self._geometries[dev]["checkboxes"]["limits"] = limitsItem

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
        self._geometries[dev]["checkboxes"]["obstacle"] = obstacleItem

        # Create raw voxels sub-item (initially disabled)
        voxelsItem = Qt.QTreeWidgetItem(deviceItem)
        voxelsItem.setText(0, "Raw Obstacle Voxels")
        voxelsItem.setFlags(voxelsItem.flags() | Qt.Qt.ItemIsUserCheckable)
        voxelsItem.setCheckState(0, Qt.Qt.Unchecked)
        voxelsItem.setDisabled(True)  # Disabled until path planning starts
        voxelsItem.setData(0, Qt.Qt.UserRole, "voxels")
        self._geometries[dev]["checkboxes"]["voxels"] = voxelsItem

    def handleTreeItemChanged(self, item, column):
        # Get the device and component type
        parentItem = item.parent()

        # If this is a top-level device item
        if parentItem is None or parentItem.parent() is None:
            dev = item.data(0, Qt.Qt.UserRole)
            visible = item.checkState(0) == Qt.Qt.Checked

            # Update visibility of the device and enable/disable children
            if dev in self._geometries:
                # Update mesh visibility
                self._geometries[dev]["mesh"].setVisible(visible)

                # Enable/disable child items
                for i in range(item.childCount()):
                    childItem = item.child(i)
                    childItem.setDisabled(not visible)

                    # If device is visible, apply child item states
                    if visible:
                        componentType = childItem.data(0, Qt.Qt.UserRole)
                        childVisible = childItem.checkState(0) == Qt.Qt.Checked

                        if componentType == "geometry":
                            self._geometries[dev]["mesh"].setVisible(childVisible)
                        elif componentType == "limits" and "limits" in self._geometries[dev]:
                            self.toggleDeviceLimitsVisibility(
                                Qt.QtCore.Qt.Checked if childVisible else Qt.QtCore.Qt.Unchecked,
                                dev.name()
                            )
                        elif componentType == "obstacle" and dev in self._deviceObstacles:
                            for obstacle in self._deviceObstacles[dev]:
                                if obstacle in self._path:
                                    self._path[obstacle].setVisible(childVisible)
                        elif componentType == "voxels" and f"voxels of {dev.name()}" in self._path:
                            self._path[f"voxels of {dev.name()}"].setVisible(childVisible)

        # If this is a component item
        else:
            dev = parentItem.data(0, Qt.Qt.UserRole)
            componentType = item.data(0, Qt.Qt.UserRole)
            visible = item.checkState(0) == Qt.Qt.Checked

            if dev in self._geometries:
                if componentType == "geometry":
                    self._geometries[dev]["mesh"].setVisible(visible)
                elif componentType == "limits" and "limits" in self._geometries[dev]:
                    self.toggleDeviceLimitsVisibility(
                        Qt.QtCore.Qt.Checked if visible else Qt.QtCore.Qt.Unchecked,
                        dev.name()
                    )
                elif componentType == "obstacle" and dev in self._deviceObstacles:
                    for obstacle in self._deviceObstacles[dev]:
                        if obstacle in self._path:
                            self._path[obstacle].setVisible(visible)
                elif componentType == "voxels" and f"voxels of {dev.name()}" in self._path:
                    self._path[f"voxels of {dev.name()}"].setVisible(visible)

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
        for key, data in self._geometries.items():
            if key.name() == dev_name:
                for edge in data.get("limits", {}).values():
                    edge.setVisible(visible)

    def addGeometry(self, geom: Geometry, key=None):
        if key is None:
            key = geom.name
        self._geometries.setdefault(key, {})
        self._geometries[key]["geom"] = geom
        mesh = geom.glMesh()
        self.view.addItem(mesh)
        self._geometries[key]["mesh"] = mesh

    def _removeDevice(self, dev):
        if dev not in self._geometries:
            return

        # Disconnect signals
        if not self._testing:
            dev.sigGeometryChanged.disconnect(self.handleGeometryChange)
            dev.sigGlobalTransformChanged.disconnect(self.handleTransformUpdate)

        # Remove mesh from view
        mesh = self._geometries[dev].get("mesh")
        if mesh is not None:
            self.view.removeItem(mesh)

        # Remove limits from view
        for edge in self._geometries[dev].get("limits", {}).values():
            self.view.removeItem(edge)
            edge.deleteLater()

        # Remove obstacles associated with this device
        if dev in self._deviceObstacles:
            for obstacle in self._deviceObstacles[dev]:
                if obstacle in self._path:
                    self.view.removeItem(self._path[obstacle])
                    self._path[obstacle].deleteLater()
                    del self._path[obstacle]

            # Remove voxel visualization if it exists
            voxel_key = f"voxels of {dev.name()}"
            if voxel_key in self._path:
                self.view.removeItem(self._path[voxel_key])
                self._path[voxel_key].deleteLater()
                del self._path[voxel_key]

            del self._deviceObstacles[dev]

        # Remove tree item
        if "tree_item" in self._geometries[dev]:
            tree_item = self._geometries[dev]["tree_item"]
            parent = tree_item.parent()
            if parent is None:
                index = self.deviceTree.indexOfTopLevelItem(tree_item)
                self.deviceTree.takeTopLevelItem(index)
            else:
                parent.removeChild(tree_item)

    def handleTransformUpdate(self, moved_device: OptomechDevice, cause_device: OptomechDevice):
        geom = self._geometries.get(moved_device, {}).get("geom")
        if geom is None:
            return
        xform = moved_device.globalPhysicalTransform() * geom.transform.as_pyqtgraph()
        self.setMeshTransform(moved_device, xform)

    def setMeshTransform(self, dev, xform):
        self._geometries[dev]["mesh"].setTransform(xform)

    def handleGeometryChange(self, dev: OptomechDevice):
        self._removeDevice(dev)
        self._geometries[dev] = {}
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

        # Find the device this obstacle belongs to
        associated_device = None
        for dev in self._geometries:
            if dev.name() in cs_name:
                associated_device = dev
                break

        # Create mesh for obstacle surface
        mesh = gl.MeshData(vertexes=verts, faces=faces)
        m = gl.GLMeshItem(
            meshdata=mesh, smooth=True, color=(0.1, 0.1, 0.3, 0.25), shader="balloon", glOptions="additive"
        )
        recenter_voxels = TTransform(
            offset=(0.5, 0.5, 0.5),
            from_cs=f"[isosurface of {cs_name}]",
            to_cs=cs_name,
        )
        m.setTransform((to_global * obstacle.transform * recenter_voxels).as_pyqtgraph())
        self.view.addItem(m)
        self._path[obstacle] = m

        # Create volumetric visualization for raw voxels
        vol = np.zeros(obstacle.volume.T.shape + (4,), dtype=np.ubyte)
        vol[..., :3] = (30, 10, 10)
        vol[..., 3] = obstacle.volume.T * 5
        v = gl.GLVolumeItem(vol, sliceDensity=10, smooth=False, glOptions="additive")
        v.setTransform((to_global * obstacle.transform).as_pyqtgraph())
        v.setVisible(False)  # Initially hidden
        self.view.addItem(v)
        self._path[f"voxels of {cs_name}"] = v

        # Associate obstacle with device
        if associated_device is not None:
            self._deviceObstacles.setdefault(associated_device, []).append(obstacle)

            # Enable obstacle checkboxes for this device
            if associated_device in self._geometries:
                obstacle_item = self._geometries[associated_device]["checkboxes"].get("obstacle")
                voxels_item = self._geometries[associated_device]["checkboxes"].get("voxels")

                if obstacle_item is not None:
                    obstacle_item.setDisabled(False)
                if voxels_item is not None:
                    voxels_item.setDisabled(False)

                # If device has voxels item, associate it
                if f"voxels of {associated_device.name()}" not in self._path:
                    self._path[f"voxels of {associated_device.name()}"] = v

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

    def _appendPath(self, path):
        if "paths" not in self._path:
            self._path["paths"] = []
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
            if key == "paths" or key == "start target" or key == "dest target":
                if isinstance(viz, list):
                    for v in viz:
                        v.setVisible(visible)
                else:
                    viz.setVisible(visible)

        # Enable/disable obstacle checkboxes in the tree
        for dev, data in self._geometries.items():
            if "checkboxes" in data:
                obstacle_item = data["checkboxes"].get("obstacle")
                voxels_item = data["checkboxes"].get("voxels")

                if obstacle_item is not None:
                    # Only enable if device has obstacles
                    has_obstacles = dev in self._deviceObstacles and len(self._deviceObstacles[dev]) > 0
                    obstacle_item.setDisabled(not (visible and has_obstacles))

                    # Update visibility based on checkbox state if path plan is visible
                    if visible and has_obstacles:
                        show_obstacle = obstacle_item.checkState(0) == Qt.Qt.Checked
                        for obstacle in self._deviceObstacles[dev]:
                            if obstacle in self._path:
                                self._path[obstacle].setVisible(show_obstacle)
                    else:
                        # Hide obstacles if path plan is hidden
                        for obstacle in self._deviceObstacles.get(dev, []):
                            if obstacle in self._path:
                                self._path[obstacle].setVisible(False)

                if voxels_item is not None:
                    # Only enable if device has voxels
                    voxel_key = f"voxels of {dev.name()}"
                    has_voxels = voxel_key in self._path
                    voxels_item.setDisabled(not (visible and has_voxels))

                    # Update visibility based on checkbox state if path plan is visible
                    if visible and has_voxels:
                        show_voxels = voxels_item.checkState(0) == Qt.Qt.Checked
                        self._path[voxel_key].setVisible(show_voxels)
                    elif voxel_key in self._path:
                        self._path[voxel_key].setVisible(False)

    def removePath(self):
        # Remove path lines
        for path in self._path.pop("paths", []):
            self.view.removeItem(path)
            path.deleteLater()

        # Remove other path elements
        for key, viz in list(self._path.items()):
            self.view.removeItem(viz)
            viz.deleteLater()

        # Clear path data
        self._path = {}

        # Reset path plan toggle
        self.pathPlanToggler.setChecked(False)
        self.pathPlanToggler.setEnabled(False)

        # Disable obstacle checkboxes in the tree
        for dev, data in self._geometries.items():
            if "checkboxes" in data:
                obstacle_item = data["checkboxes"].get("obstacle")
                voxels_item = data["checkboxes"].get("voxels")

                if obstacle_item is not None:
                    obstacle_item.setDisabled(True)
                if voxels_item is not None:
                    voxels_item.setDisabled(True)

        # Clear device obstacles
        self._deviceObstacles = {}
