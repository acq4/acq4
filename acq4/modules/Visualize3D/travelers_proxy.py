import queue
import time
from threading import Thread

import numpy as np

from acq4.util import Qt
from acq4.util.future import future_wrap
from acq4.util.threadrun import inGuiThread, runInGuiThread
from coorx import TTransform
from pyqtgraph import opengl as gl


class VisualizePathPlan(Qt.QObject):
    def __init__(self, window, traveler: "OptomechDevice"):
        super().__init__()
        self.moveToThread(Qt.QApplication.instance().thread())
        self._window = window
        self._traveler = traveler

        self._initGui(blocking=True)

        self._bounds = None
        self._obstacles = {}
        self._voxels = {}

        self._stopThread = False
        self._pathUpdates = queue.Queue()
        self._pathWatcherThread = Thread(target=self._watchForPathUpdates, daemon=True)
        self._pathWatcherThread.start()

    @inGuiThread
    def _initGui(self):
        show_path = self._window.ensurePathTogglerExists(self._traveler)
        self._startTarget = self._window.target(show_path)
        self._destTarget = self._window.target(show_path, color=(0, 1, 0, 1))
        self._activePath = self._window.path((0.1, 1, 0.7, 0.5), show_path)
        self._previousPath = self._window.path((1, 0.7, 0, 0.01), show_path)

    @inGuiThread
    def reset(self):
        # todo mutexes?
        self._bounds.setVisible(False)
        self._startTarget.setVisible(False)
        self._destTarget.setVisible(False)
        self._activePath.setVisible(False)
        self._activePath.setData(pos=[])
        self._previousPath.setVisible(False)
        self._previousPath.setData(pos=[])

    @future_wrap
    def startPath(self, path, bounds, _future):
        if self._bounds is None:
            self._bounds = self._window.createBounds(bounds, False)
        self._startPath(path, bounds)

    @inGuiThread
    def _startPath(self, path, bounds):
        self.reset(blocking=True)
        visible = self.shouldShowPath

        self._bounds.setVisible(visible)
        self._startTarget.setData(pos=np.array([path[0]]))
        self._startTarget.setVisible(visible)
        self._destTarget.setData(pos=np.array([path[-1]]))
        self._destTarget.setVisible(visible)
        self._activePath.setVisible(visible)
        self._previousPath.setVisible(visible)
        self._appendPath(path)

    def focus(self):
        self._window.focus()

    def endPath(self, path):
        self.updatePath(path, skip=1)

    @inGuiThread
    def setVisible(self, visible):
        self._startTarget.setVisible(visible)
        self._destTarget.setVisible(visible)
        self._activePath.setVisible(visible)
        self._previousPath.setVisible(visible)
        self._bounds.setVisible(visible)
        for name, obstacle in self._obstacles.items():
            obst_toggle = self._window.getDeviceCheckboxes(name)["obstacle"]
            dev_obst_visible = obst_toggle.checkState(0) == Qt.Qt.Checked
            dev_visible = obst_toggle.parent().checkState(0) == Qt.Qt.Checked
            obstacle.setVisible(visible and dev_visible and dev_obst_visible)
        for name, voxels in self._voxels.items():
            vox_toggle = self._window.getDeviceCheckboxes(name)["voxels"]
            dev_vox_visible = vox_toggle.checkState(0) == Qt.Qt.Checked
            dev_visible = vox_toggle.parent().checkState(0) == Qt.Qt.Checked
            voxels.setVisible(visible and dev_visible and dev_vox_visible)

    def updatePath(self, path, skip=3):
        self._pathUpdates.put((path, skip))

    def _watchForPathUpdates(self):
        n_updates = 0
        while not self._stopThread:
            path, skip = self._pathUpdates.get()
            n_updates += 1
            if self._window.testing or n_updates % skip == 0:
                self._appendPath(path)
                time.sleep(0.05)

    @inGuiThread
    def _appendPath(self, path):
        if len(self._activePath.pos) > 0:
            prev = self._activePath.pos
        else:
            prev = path
        if len(self._previousPath.pos) > 0:
            prev = np.vstack((self._previousPath.pos, prev))

        self._previousPath.setData(pos=prev)
        self._activePath.setData(pos=np.array(path + path[:-1][::-1]))  # it needs to walk back to the origin

    @future_wrap
    def addObstacle(self, name, obstacle, to_global, _future):
        if name not in self._obstacles:
            self._buildObstacleMesh(name, *obstacle.surface_mesh, blocking=True)
        cs_name = obstacle.transform.systems[0].name
        recenter_voxels = TTransform(
            offset=(0.5, 0.5, 0.5),
            from_cs=f"[isosurface of {cs_name}]",
            to_cs=cs_name,
        )
        mesh_xform = (to_global * obstacle.transform * recenter_voxels).as_pyqtgraph()
        runInGuiThread(self._obstacles[name].setTransform, mesh_xform)

        # build voxel volume
        if name not in self._voxels:
            # Create volumetric visualization for raw voxels
            vol_data = np.zeros(obstacle.volume.T.shape + (4,), dtype=np.ubyte)
            vol_data[..., :3] = (30, 10, 10)
            vol_data[..., 3] = obstacle.volume.T * 5
            self._buildVoxelVolume(name, vol_data, blocking=True)
        vol_xform = (to_global * obstacle.transform).as_pyqtgraph()
        runInGuiThread(self._voxels[name].setTransform, vol_xform)

        self._setInitialObstacleVisibility(name)

    @property
    def shouldShowPath(self):
        togglers = self._window.getDeviceCheckboxes(self._traveler.name())
        generally_visible = togglers["geometry"].parent().checkState(0) == Qt.Qt.Checked
        return generally_visible and togglers["path"].checkState(0) == Qt.Qt.Checked

    @inGuiThread
    def _setInitialObstacleVisibility(self, name):
        togglers = self._window.getDeviceCheckboxes(name)
        general_checkbox = togglers["geometry"].parent()
        generally_visible = general_checkbox.checkState(0) == Qt.Qt.Checked

        obst_visible = togglers["obstacle"].checkState(0) == Qt.Qt.Checked
        self._obstacles[name].setVisible(generally_visible and obst_visible and self.shouldShowPath)

        voxels_visible = togglers["voxels"].checkState(0) == Qt.Qt.Checked
        self._voxels[name].setVisible(generally_visible and voxels_visible and self.shouldShowPath)

    @inGuiThread
    def _buildVoxelVolume(self, name, vol_data):
        self._voxels[name] = gl.GLVolumeItem(vol_data, sliceDensity=10, smooth=False, glOptions="additive")
        self._window.view.addItem(self._voxels[name])

    @inGuiThread
    def _buildObstacleMesh(self, name, verts, faces):
        mesh_data = gl.MeshData(vertexes=verts, faces=faces)
        self._obstacles[name] = gl.GLMeshItem(
            meshdata=mesh_data, smooth=True, color=(0.1, 0.1, 0.3, 0.25), shader="balloon", glOptions="additive"
        )
        self._window.view.addItem(self._obstacles[name])

    @inGuiThread
    def removeDevice(self, dev):
        for name, obst in self._obstacles.items():
            if dev.name() in name:
                self._window.view.removeItem(obst)
                obst.deleteLater()
                del self._obstacles[name]
                break
        for name, voxels in self._voxels.items():
            if dev.name() in name:
                self._window.view.removeItem(voxels)
                voxels.deleteLater()
                del self._voxels[name]
                break

    def toggleDeviceVisibility(self, component: str, dev, visible: bool):
        items = self._obstacles if component == "obstacle" else self._voxels
        for name, obst in items.items():
            if dev.name() in name:
                obst.setVisible(visible)
                break

    @inGuiThread
    def safelyDestroy(self):
        self._stopThread = True
        self._window.view.removeItem(self._startTarget)
        self._startTarget.deleteLater()
        self._window.view.removeItem(self._destTarget)
        self._destTarget.deleteLater()
        self._window.view.removeItem(self._activePath)
        self._activePath.deleteLater()
        self._window.view.removeItem(self._previousPath)
        self._previousPath.deleteLater()
        self._window.view.removeItem(self._bounds)
        self._bounds.deleteLater()
        for obst in self._obstacles.values():
            self._window.view.removeItem(obst)
        self._obstacles = None
        for voxels in self._voxels.values():
            self._window.view.removeItem(voxels)
        self._voxels = None
