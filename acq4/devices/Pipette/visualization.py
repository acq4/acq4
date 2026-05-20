import collections
import numpy as np
from acq4.util import ptime
from coorx import TTransform
from pyqtgraph import opengl as gl
from acq4.util import Qt
from acq4.devices.Pipette.pipette import Pipette
from acq4.devices.OptomechDevice import OptomechDeviceVisualizerAdapter
from acq4.modules.Visualize3D import VisualizePathSearch


class PipetteVisualizerAdapter(OptomechDeviceVisualizerAdapter):
    sigPathUpdate = Qt.Signal(object, bool, object)  # path, is_error, failed_at

    def __init__(self, dev: Pipette, win):
        self._obstacles = {}
        self._history = []  # list of (position, time) tuples for target history visualization
        super().__init__(dev, win)
        self._target = win.target()
        self._path = win.path(color=[0.5, 0, 1, 1])
        self._actual_path = win.path(color=[1, 0.6, 0, 0.8])  # orange: actual motion
        self._error = win.target(color=[1, 0.2, 0.2, 0.6])
        # Path history: deque of (seq_id, path, is_error, failed_at) tuples
        self._path_history = collections.deque(maxlen=10)
        self._next_seq = 0
        # _pinned_seq: None = follow latest; int = pinned to that seq_id
        self._pinned_seq = None
        # _error_pinned: True when pinned due to an error path (highest priority)
        self._error_pinned = False
        # Guard flag to suppress slider signals during programmatic updates
        self._updating_slider = False
        if dev.target is not None:
            self.handleTargetChanged(dev, dev.targetPosition())
        # TODO obstacles and voxels
        # TODO signal connections for obstacle and voxel updates
        # TODO tie in with prime caches?

        dev.sigCalibrationChanged.connect(self.handleCalibrationUpdate)
        dev.sigTargetChanged.connect(self.handleTargetChanged)
        dev.sigGlobalTransformChanged.connect(self.deviceMoved)
        self.sigPathUpdate.connect(self._handlePathUpdate)

    def deviceMoved(self, dev, transform):
        pos = self.device.globalPosition()
        now = ptime.time()
        self._history.append((pos, now))

    def _buildControlParam(self):
        from pyqtgraph.parametertree import Parameter

        param = super()._buildControlParam()

        path_param = Parameter.create(
            name='Path plan',
            type='bool',
            value=False,
            children=[
                dict(name='History', type='slider', value=0, limits=[0, 0], step=1),
            ],
        )
        path_param.sigValueChanged.connect(self._handlePathVisible)
        path_param.child('History').sigValueChanged.connect(self._handleHistorySliderMoved)
        param.addChild(path_param)

        target_param = Parameter.create(name='Target', type='bool', value=False)
        param.addChild(target_param)
        target_param.sigValueChanged.connect(self._handleTargetVisible)

        # TODO figure all the geometry-aware stuff out
        # obstacle_devices = [d for d in getManager().listInterfaces("OptomechDevice") if d != self.device.name()]
        obstacle_devices = []
        for other_dev in obstacle_devices:
            other_dev_param = Parameter.create(
                name=f"{other_dev} obstacles",
                type='bool',
                value=False,
                children=[
                    dict(name='Obstacle', type='bool', value=True),
                    dict(name='Raw Obstacle Voxels', type='bool', value=False),
                ],
            )
            param.addChild(other_dev_param)
            self._obstacles[other_dev] = {
                "device param": other_dev_param,
                "obstacle param": other_dev_param.child('Obstacle'),
                "voxels param": other_dev_param.child('Raw Obstacle Voxels'),
            }

        return param

    def _handleDeviceToggle(self, param, value):
        super()._handleDeviceToggle(param, value)
        self._updateTargetVisibility()
        self._updatePathVisibility()

    def _handleTargetVisible(self, param, value):
        self._updateTargetVisibility()

    def _handlePathVisible(self, param, value):
        self._updatePathVisibility()

    def _updateTargetVisibility(self):
        visible = self._param.value() and self._param.child('Target').value()
        self._target.setVisible(visible)

    def _updatePathVisibility(self):
        visible = self._param.value() and self._param.child('Path plan').value()
        self._path.setVisible(visible)
        self._actual_path.setVisible(visible)
        self._error.setVisible(visible)

    def handleCalibrationUpdate(self, dev):
        if bounds := dev.getBoundaries():
            if self._limits is not None:
                self.win.remove3DItem(self._limits)
            self._limits = self.createBounds(bounds, False)
            self._updateLimitsVisibility()
        self.handleTransformUpdate(dev, dev)

    def handleTargetChanged(self, dev, pos):
        self._target.setData(pos=np.asarray([pos]))

    def pathSearchVisualizer(self):
        return VisualizePathSearch(self)

    def setPathError(self, path, failed_at=None):
        self.sigPathUpdate.emit(path, True, failed_at)

    def setPath(self, path):
        self.sigPathUpdate.emit(path, False, None)

    def _handlePathUpdate(self, path, is_error, failed_at):
        seq = self._next_seq
        self._next_seq += 1
        self._path_history.append((seq, path, is_error, failed_at, ptime.time()))

        if is_error:
            # Error paths have highest priority: always pin to them
            self._pinned_seq = seq
            self._error_pinned = True
            if self._param is not None:
                self._param.child('Path plan').setValue(True)
            self.win.focus()
        elif self._pinned_seq is not None:
            # Check if the pinned entry is still in history (may have fallen off)
            seqs = {entry[0] for entry in self._path_history}
            if self._pinned_seq not in seqs:
                self._pinned_seq = None
                self._error_pinned = False

        self._syncSlider()

    def _syncSlider(self):
        """Update the history slider range and position, then render the selected path."""
        if self._param is None:
            return
        n = len(self._path_history)
        if n == 0:
            return

        slider_param = self._param.child('Path plan').child('History')
        self._updating_slider = True
        try:
            slider_param.setLimits([0, n - 1])
            if self._pinned_seq is not None:
                seqs = [entry[0] for entry in self._path_history]
                try:
                    idx = seqs.index(self._pinned_seq)
                except ValueError:
                    idx = n - 1
            else:
                idx = n - 1
            slider_param.setValue(idx)
        finally:
            self._updating_slider = False

        idx = int(slider_param.value())
        _, path, is_error, failed_at, _ = self._path_history[idx]
        self._displayPath(path, is_error, failed_at, idx)

    def _displayPath(self, path, is_error, failed_at, path_idx=None):
        """Render path and error marker for the given history entry."""
        self._path.setData(pos=np.asarray(path))
        if failed_at is None:
            self._error.setData(pos=np.empty((0, 3)))
        else:
            self._error.setData(pos=np.asarray([failed_at]))
        if path_idx is not None:
            self._actual_path.setData(pos=self._getActualPath(path_idx))
        else:
            self._actual_path.setData(pos=np.empty((0, 3)))

    def _getActualPath(self, path_idx):
        """Return actual pipette positions spanning the time window of path_history[path_idx].

        Includes the last known position before the move started and the first
        position after it ended, with all positions in between.
        """
        if not self._history:
            return np.empty((0, 3))

        _, _, _, _, t_start = self._path_history[path_idx]

        if path_idx + 1 < len(self._path_history):
            _, _, _, _, t_end = self._path_history[path_idx + 1]
        else:
            t_end = None

        times = [t for _, t in self._history]
        positions = [p for p, _ in self._history]

        # Last index with time <= t_start (last position before move)
        i_start = 0
        for i, t in enumerate(times):
            if t <= t_start:
                i_start = i

        # First index with time >= t_end (first position after move)
        if t_end is not None:
            i_end = len(times) - 1
            for i, t in enumerate(times):
                if t >= t_end:
                    i_end = i
                    break
        else:
            i_end = len(times) - 1

        pts = positions[i_start:i_end + 1]
        if len(pts) < 2:
            return np.empty((0, 3))
        return np.array(pts)

    def _handleHistorySliderMoved(self, param, value):
        """Handle manual slider movement to navigate path history."""
        if self._updating_slider:
            return
        n = len(self._path_history)
        if n == 0:
            return
        idx = max(0, min(int(value), n - 1))
        # Clear error pin on any manual move
        self._error_pinned = False
        if idx >= n - 1:
            # At the latest position: switch back to follow-latest mode
            self._pinned_seq = None
        else:
            self._pinned_seq = self._path_history[idx][0]
        _, path, is_error, failed_at, _ = self._path_history[idx]
        self._displayPath(path, is_error, failed_at, idx)

    def createBounds(self, bounds, visible):
        limits = self.device.parentDevice().getLimits()
        local_to_global = (
            TTransform(offset=self.device.offset) * self.device.parentDevice().axisTransform()
        )
        edges = set()
        ndim = len(limits)
        vertices = list(np.ndindex(tuple([2] * ndim)))
        vertices = [tuple(limits[i][v] for i, v in enumerate(vertex)) for vertex in vertices]
        # find every edge between vertices that differ in exactly one coordinate
        for v1 in vertices:
            for v2 in vertices:
                if sum(a != b for a, b in zip(v1, v2)) == 1:
                    # dedup by sorting
                    edge = tuple(sorted((v1, v2)))
                    edges.add(edge)
        edges = [local_to_global.map(v) for edge in edges for v in edge]
        plot = gl.GLLinePlotItem(pos=np.array(edges), color=(1, 0, 0, 0.2), width=4, mode="lines")
        plot.setVisible(False)
        self.win.add3DItem(plot)
        return plot
