from __future__ import print_function

import numpy as np
import scipy.optimize
import scipy.stats
from six.moves import range
from six.moves import zip

import pyqtgraph as pg
from acq4.Manager import getManager
from acq4.devices.Stage import Stage
from acq4.util import Qt
from acq4.util.HelpfulException import HelpfulException
from acq4.util.target import Target


class StageAxesCalibrationWindow(Qt.QWidget):
    def __init__(self, device: Stage):
        super(StageAxesCalibrationWindow, self).__init__()
        self._dev = device
        self._camera = device.getPreferredImagingDevice()
        self._automation = AutomatedStageCalibration(device)
        self.setWindowTitle("Calibrate Axes for %s" % device.name())
        self._layout = Qt.QGridLayout()
        self.setLayout(self._layout)
        self.resize(600, 300)

        self._viewDocsButton = Qt.QPushButton("View Documentation (manual only)")
        self._layout.addWidget(self._viewDocsButton, 0, 0)
        self._viewDocsButton.clicked.connect(self._viewDocsButtonClicked)

    def _viewDocsButtonClicked(self, *args):
        # TODO point this at the real docs once they're done
        url = "https://docs.google.com/document/d/1YtrAK3Gk8FvSrXxcjEd6sm7wyTAhjw4u5NtMXHhta3k/edit?usp=sharing"
        Qt.QDesktopServices.openUrl(Qt.QUrl(url))

    def _eventual_todo_init(self):
        # TODO what belongs in this window?
        #   * current orientation, scale and angle of stage
        #   * link to documentation
        #   * text which should be pasted into the devices.cfg to save this calibration :bleh:
        #   * "Save" button that puts transform in config/devices/Stage_config/transform
        #       * pop up instructions to remove manual transform if that is in the way
        #       * pop that up at config-read time, too, in case things are in conflict

        # TODO eventually
        #   * wizard instructions for current step e.g. "move the stage to the right relative to the operator"
        #   * indication of which parts of the transform have been calibrated, or is currently being calibrated

        self._btnPanel = Qt.QWidget()
        self._btnPanelLayout = Qt.QHBoxLayout()
        self._btnPanelLayout.setContentsMargins(0, 0, 0, 0)
        self._btnPanel.setLayout(self._btnPanelLayout)
        self._layout.addWidget(self._btnPanel, 1, 0)

        self._autodetectButton = Qt.QPushButton("Autodetect")
        self._btnPanelLayout.addWidget(self._autodetectButton)
        self._autodetectButton.clicked.connect(self.autodetectClicked)

        self._saveButton = Qt.QPushButton("Save")
        self._saveButton.setEnabled(False)
        self._btnPanelLayout.addWidget(self._saveButton)
        self._saveButton.clicked.connect(self.saveClicked)

    def autodetectClicked(self):
        # TODO
        #  * make sure Camera module is open
        #  * button should toggle and be cancelable
        #  * appropriate hardware should be locked
        self._automation.calibrate()

    def saveClicked(self):
        pass  # TODO


class ManipulatorAxesCalibrationWindow(Qt.QWidget):
    def __init__(self, device: Stage):
        self.dev = device
        self._cammod = None
        self._camdev = None
        self.transform = None
        self.calibration = None

        Qt.QWidget.__init__(self)
        self.resize(600, 300)
        self.setWindowTitle("Calibrate Axes for %s" % device.name())

        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)

        # tree columns:
        #   stage x, y, z   global x, y, z   error
        self.pointTree = Qt.QTreeWidget()
        self.pointTree.setHeaderLabels(["stage pos", "parent pos", "error"])
        self.pointTree.setColumnCount(3)
        self.layout.addWidget(self.pointTree, 0, 0)
        self.pointTree.setColumnWidth(0, 200)
        self.pointTree.setColumnWidth(1, 200)
        self.pointTree.itemClicked.connect(self.enableRemoveBtnIfPossible)

        self.btnPanel = Qt.QWidget()
        self.btnPanelLayout = Qt.QHBoxLayout()
        self.btnPanelLayout.setContentsMargins(0, 0, 0, 0)
        self.btnPanel.setLayout(self.btnPanelLayout)
        self.layout.addWidget(self.btnPanel, 1, 0)

        self.addPointBtn = Qt.QPushButton("add point")
        self.addPointBtn.setCheckable(True)
        self.btnPanelLayout.addWidget(self.addPointBtn)

        self.removePointBtn = Qt.QPushButton("remove point")
        self.removePointBtn.setEnabled(False)
        self.btnPanelLayout.addWidget(self.removePointBtn)

        self.saveBtn = Qt.QPushButton("save calibration")
        self.btnPanelLayout.addWidget(self.saveBtn)

        self.addPointBtn.toggled.connect(self.addPointToggled)
        self.removePointBtn.clicked.connect(self.removePointClicked)
        self.saveBtn.clicked.connect(self.saveClicked)

        # TODO eventually: more controls
        #  * Show calibration points (in camera module)
        #  * Force orthogonal on any pair of axes: xy, xz, yz

        self.loadCalibrationFromDevice()

        cam = self.getCameraDevice()
        cam.sigGlobalTransformChanged.connect(self.cameraTransformChanged)

    def addPointToggled(self):
        cammod = self.getCameraModule()
        if self.addPointBtn.isChecked():
            cammod.window().getView().scene().sigMouseClicked.connect(self.cameraModuleClicked)
            self.addPointBtn.setText("click new point..")
        else:
            pg.disconnect(cammod.window().getView().scene().sigMouseClicked, self.cameraModuleClicked)
            self.addPointBtn.setText("add point")

    def cameraModuleClicked(self, ev):
        if ev.button() != Qt.Qt.LeftButton:
            return

        camera = self.getCameraDevice()
        cameraPos = camera.mapToGlobal([0, 0, 0])

        globalPos = self._cammod.window().getView().mapSceneToView(ev.scenePos())
        globalPos = [globalPos.x(), globalPos.y(), cameraPos[2]]
        parentDev = self.dev.parentDevice()
        if parentDev is None:
            parentPos = globalPos
        else:
            parentPos = parentDev.mapFromGlobal(globalPos)

        stagePos = self.dev.getPosition()

        self.calibration["points"].append((stagePos, parentPos))
        item = self._addCalibrationPoint(stagePos, parentPos)

        target = Target(movable=False)
        self._cammod.window().addItem(target)
        target.setPos(pg.Point(globalPos[:2]))
        target.setDepth(globalPos[2])
        target.setFocusDepth(globalPos[2])
        item.target = target

        self.addPointBtn.setChecked(False)
        self.recalculate()
        self.saveBtn.setText("*save calibration*")

    def cameraTransformChanged(self):
        cam = self.getCameraDevice()
        fdepth = cam.mapToGlobal([0, 0, 0])[2]

        items = [self.pointTree.topLevelItem(i) for i in range(self.pointTree.topLevelItemCount())]
        for item in items:
            if item.target is None:
                continue
            item.target.setFocusDepth(fdepth)

    def enableRemoveBtnIfPossible(self):
        self.removePointBtn.setEnabled(len(self.pointTree.selectedItems()) > 0)

    def removePointClicked(self):
        selected_items = self.pointTree.selectedItems()
        if len(selected_items) <= 0:
            raise HelpfulException("No points selected for removal")
        sel = selected_items[0]
        index = self.pointTree.indexOfTopLevelItem(sel)
        self.pointTree.takeTopLevelItem(index)
        if sel.target is not None:
            sel.target.scene().removeItem(sel.target)
        items = [self.pointTree.topLevelItem(i) for i in range(self.pointTree.topLevelItemCount())]
        self.calibration["points"] = [(item.stagePos, item.parentPos) for item in items]
        self.recalculate()
        self.enableRemoveBtnIfPossible()
        self.saveBtn.setText("*save calibration*")

    def saveClicked(self):
        self.saveCalibrationToDevice()

    def loadCalibrationFromDevice(self):
        self.calibration = self.dev.readConfigFile("calibration")
        self.calibration.setdefault("points", [])
        for stagePos, parentPos in self.calibration["points"]:
            self._addCalibrationPoint(stagePos, parentPos)
        self.recalculate()

    def saveCalibrationToDevice(self):
        self.recalculate(raiseOnInsufficientPoints=True)
        self.calibration["transform"] = (
            None if self.transform is None else [list(row) for row in self.transform.matrix()]
        )
        self.dev.writeConfigFile(self.calibration, "calibration")
        self.saveBtn.setText("save calibration")

    def _addCalibrationPoint(self, stagePos, parentPos):
        item = Qt.QTreeWidgetItem(
            ["%0.3g, %0.3g, %0.3g" % tuple(stagePos), "%0.3g, %0.3g, %0.3g" % tuple(parentPos), ""]
        )
        self.pointTree.addTopLevelItem(item)
        item.stagePos = stagePos
        item.parentPos = parentPos
        item.target = None
        return item

    def recalculate(self, raiseOnInsufficientPoints=False):
        # identity affine axis transform matrix

        # method: user generates many calibration points that are all colinear along each of the
        # stage axes. In this way, we can independently determine the orientation of each stage axis,
        # and combine these into a full transformation matrix.

        parentPos, stagePos = self._unzippedCalibrationPoints()

        axisPoints = self._groupPointsByAxis(stagePos)
        if not self._hasSufficientPoints(axisPoints):
            self._clearCalibration()
            if raiseOnInsufficientPoints:
                raise Exception("Could not find colinear points along all 3 axes")
            else:
                return

        axStagePos = [stagePos[list(axisPoints[ax]), ax] for ax in (0, 1, 2)]
        axParentPos = [parentPos[list(axisPoints[ax])] for ax in (0, 1, 2)]

        # find optimal linear mapping for each axis
        m = np.eye(4)
        for i in (0, 1, 2):
            for j in (0, 1, 2):
                line = scipy.stats.linregress(axStagePos[j], axParentPos[j][:, i])
                m[i, j] = line.slope

        transform = pg.Transform3D(m)

        # find optimal offset
        offset = (parentPos - pg.transformCoordinates(transform, stagePos, transpose=True)).mean(axis=0)
        m[:3, 3] = offset
        self.transform = pg.Transform3D(m)

        # measure and display errors for each point
        def mapPoint(axisTr, _stage_pos, localPos):
            # given a stage position and axis transform, map from localPos to parent coordinate system
            if isinstance(axisTr, np.ndarray):
                ident = np.eye(4)
                ident[:3] = axisTr.reshape(3, 4)
                axisTr = pg.Transform3D(ident)
            st = self.dev._makeStageTransform(_stage_pos, axisTr)[0]
            tr = pg.Transform3D(self.dev.baseTransform() * st)
            return tr.map(localPos)

        def mapError(axisTr, _stage_pos, _parent_pos):
            # Goal is to map origin to parent position correctly
            return [mapPoint(axisTr, sp, [0, 0, 0]) - pp for sp, pp in zip(_stage_pos, _parent_pos)]

        error = mapError(self.transform, stagePos, parentPos)
        for i in range(len(self.calibration["points"])):
            item = self.pointTree.topLevelItem(i)
            dist = np.linalg.norm(error[i])
            item.setText(2, "%0.2f um  (%0.3g, %0.3g, %0.3g)" % (1e6 * dist, error[i][0], error[i][1], error[i][2]))

        # send new transform to device
        self.dev.setAxisTransform(self.transform)

    def _unzippedCalibrationPoints(self):
        npts = len(self.calibration["points"])
        stagePos = np.empty((npts, 3))
        parentPos = np.empty((npts, 3))
        for i, pt in enumerate(self.calibration["points"]):
            stagePos[i] = pt[0]
            parentPos[i] = pt[1]
        return parentPos, stagePos

    @staticmethod
    def _groupPointsByAxis(points):
        def changeAxis(p1, p2):
            # Which single axis has changed between 2 points?
            diff = np.abs(p2 - p1)
            dist = np.linalg.norm(diff)
            axis = np.argmax(diff)
            if diff[axis] > dist * 0.99:
                return axis
            else:
                return None

        axisPoints = [set(), set(), set()]
        for i in range(1, len(points)):
            currentAxis = changeAxis(points[i - 1], points[i])
            if currentAxis is None:
                continue
            axisPoints[currentAxis].add(i - 1)
            axisPoints[currentAxis].add(i)

        # Choose longest contiguous group of calibration points for each axis
        for axis, pts in enumerate(axisPoints):
            current_group = []
            contig_groups = [current_group]
            for p in sorted(pts):
                if len(current_group) == 0 or current_group[-1] == p - 1:
                    current_group.append(p)
                else:
                    current_group = [p]
                    contig_groups.append(current_group)
            idx_at_longest = np.argmax([len(g) for g in contig_groups])
            axisPoints[axis] = contig_groups[idx_at_longest]
        return axisPoints

    @staticmethod
    def _hasSufficientPoints(axisPoints):
        return all(len(axisPoints[ax]) > 2 for ax in (0, 1, 2))

    def _clearCalibration(self):
        for i in range(len(self.calibration["points"])):
            item = self.pointTree.topLevelItem(i)
            item.setText(2, "")
        self.transform = None

    def getCameraModule(self):
        if self._cammod is None:
            manager = getManager()
            mods = manager.listInterfaces("cameraModule")
            if len(mods) == 0:
                raise Exception("Calibration requires an open camera module")
            self._cammod = manager.getModule(mods[0])
        return self._cammod

    def getCameraDevice(self):
        if self._camdev is None:
            self._camdev = self.dev.getPreferredImagingDevice()
        return self._camdev

    def closeEvent(self, ev):
        for i in range(self.pointTree.topLevelItemCount()):
            target = self.pointTree.topLevelItem(i).target
            if target is not None:
                target.hide()

    def show(self):
        Qt.QWidget.show(self)
        for i in range(self.pointTree.topLevelItemCount()):
            target = self.pointTree.topLevelItem(i).target
            if target is not None:
                target.show()


class AutomatedStageCalibration(object):
    sigFinished = Qt.Signal()

    def __init__(self, stage: Stage):
        self._stage = stage
        self._frame_delay = None
        self._is_running = False
        self._steps_per_axis = 10
        self._move = None
        self._camera = stage.getPreferredImagingDevice()
        self._offsets = np.empty((2, self._steps_per_axis, 2))
        self._frames = ([], [])
        self._axis_index = 0
        self._frame_index = 0
        self._positions = None

    def calibrate(self):
        if self._is_running:
            raise RuntimeError("Automated axes calibration is already running")
        self._is_running = True
        self._build_movement_plan()
        self._camera.sigNewFrame.connect(self.handleNewFrame)

    def _build_movement_plan(self):
        step_size = 10e-6  # TODO this should be magnification-dependent
        # current stage position
        pos = self._stage.getPosition()
        # where to move on each update
        if len(self._stage.axes()) == 2:
            self._positions = np.zeros((2, self._steps_per_axis, 2))
        else:
            self._positions = np.zeros((2, self._steps_per_axis, 3))
            self._positions[:, :, 2] = pos[2]
        self._positions[0, :, 0] = pos[0] + np.arange(self._steps_per_axis) * step_size
        self._positions[0, :, 1] = pos[1]
        self._positions[1, :, 0] = pos[0]
        self._positions[1, :, 1] = pos[1] + np.arange(self._steps_per_axis) * step_size

    def handleNewFrame(self, frame):
        try:
            if self._move is not None and not self._move.isDone():
                # stage is still moving; ignore frame
                return

            if self._frame_delay is None:
                # stage has stopped; ignore 2 more frames to be sure
                # we get the right image.
                self._frame_delay = pg.ptime.time() + 1.0 / frame.info()["fps"]
            elif self._frame_delay < frame.info()["time"]:
                # now we are ready to keep this frame.
                self._frame_delay = None
                self._addFrameForAnalysis(frame)
        except Exception:
            pg.disconnect(self._camera.sigNewFrame, self.handleNewFrame)
            self.sigFinished.emit()
            raise

    def _addFrameForAnalysis(self, frame):
        index = self._frame_index
        axis_index = index // self._steps_per_axis
        step_index = index % self._steps_per_axis
        self._frames[axis_index].append(frame)

        # update index for next iteration
        self._frame_index += 1

        # decide whether to move the stage
        finished = self._frame_index >= self._steps_per_axis * 2
        if not finished:
            self._move = self._stage.move(self.positions[self.index], "slow")

        self._offsets[axis_index, step_index] = self._calculate_offset(axis_index, step_index)

        # finish up if there are no more positions
        if finished:
            pg.disconnect(self._camera.sigNewFrame, self.handleNewFrame)
            self.analyze()

    def _calculate_offset(self, axis_index: int, step_index: int):
        """calculate offset (while stage moves to next location)"""
        import imreg_dft  # FFT image registration by Chris Gohlke; available via pip

        frame = self._frames[axis_index][step_index]
        if step_index == 0:
            return 0, 0

        compareIndex = max(0, step_index - 5)
        translation = imreg_dft.translation(frame.getImage(), self._frames[compareIndex].getImage())
        if not translation["success"]:
            raise RuntimeError(f"Could not determine offset at frame ({axis_index}, {step_index})")
        offset = translation["tvec"]
        px = self._camera.getPixelSize()
        return self._offsets[axis_index, compareIndex] + offset.astype(float) * px

    def analyze(self):
        self._do_x_axis_analysis()

    def _do_x_axis_analysis(self):
        # linear regression to determine scale between stage steps and camera microns
        axis_index = 0  # x
        pos_real = self._positions[axis_index, :, :2]  # exclude z axis if present
        pos_real -= pos_real[0]  # shift everything so that we start at 0
        pos_real = (pos_real ** 2).sum(axis=1) ** 0.5

        pos_measured = (self._offsets[axis_index] ** 2).sum(axis=1) ** 0.5
        lin_regress = scipy.stats.linregress(pos_real, pos_measured)

        # subtract linear approximation to get residual error
        pos_prediction = pos_real * lin_regress.slope + lin_regress.intercept
        error = pos_measured - pos_prediction
        errorPlot = pg.plot(
            pos_real,
            error,
            title=f"X axis error (slope = {lin_regress.slope * 1e6:0.2f} um/step)",
            labels={"left": ("Error", "m"), "bottom": ("position", "steps")},
        )

        # TODO what is this for?
        # fit residual to combination of sine waves
        def fn(p, x):
            return (
                p[2] * np.sin((x + p[0]) * 1 * p[1])
                + p[3] * np.sin((x + p[0]) * 2 * p[1])
                + p[4] * np.sin((x + p[0]) * 3 * p[1])
                + p[5] * np.sin((x + p[0]) * 4 * p[1])
            )

        def erf(p, x, y):
            return fn(p, x) - y

        f0 = 6 * np.pi / pos_real.max()  # guess there are 3 cycles in the data
        amp = error.max()
        # noinspection PyTypeChecker
        fit = scipy.optimize.leastsq(erf, [0, f0, amp, amp, amp, amp], (pos_real, error))[0]
        errorPlot.plot(pos_real, fn(fit, pos_real), pen="g")
        self.sigFinished.emit()
