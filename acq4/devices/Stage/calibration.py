from __future__ import print_function

import numpy as np
import pyqtgraph as pg
import scipy.optimize
import scipy.stats
from six.moves import range
from six.moves import zip

from acq4.Manager import getManager
from acq4.util import Qt
from acq4.util.target import Target


class CalibrationWindow(Qt.QWidget):
    def __init__(self, device):
        self.dev = device
        self._cammod = None
        self._camdev = None
        self.transform = None

        Qt.QWidget.__init__(self)
        self.resize(600, 300)
        self.setWindowTitle("Calibration: %s" % device.name())

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

        self.btnPanel = Qt.QWidget()
        self.btnPanelLayout = Qt.QHBoxLayout()
        self.btnPanelLayout.setContentsMargins(0, 0, 0, 0)
        self.btnPanel.setLayout(self.btnPanelLayout)
        self.layout.addWidget(self.btnPanel, 1, 0)

        self.addPointBtn = Qt.QPushButton("add point")
        self.addPointBtn.setCheckable(True)
        self.btnPanelLayout.addWidget(self.addPointBtn)

        self.removePointBtn = Qt.QPushButton("remove point")
        self.btnPanelLayout.addWidget(self.removePointBtn)

        self.saveBtn = Qt.QPushButton("save calibration")
        self.btnPanelLayout.addWidget(self.saveBtn)

        self.addPointBtn.toggled.connect(self.addPointToggled)
        self.removePointBtn.clicked.connect(self.removePointClicked)
        self.saveBtn.clicked.connect(self.saveClicked)

        # more controls:
        #    Show calibration points (in camera module)
        #    Force orthogonal axes: xy, xz, yz

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

    def removePointClicked(self):
        sel = self.pointTree.selectedItems()[0]
        index = self.pointTree.indexOfTopLevelItem(sel)
        self.pointTree.takeTopLevelItem(index)
        if sel.target is not None:
            sel.target.scene().removeItem(sel.target)
        items = [self.pointTree.topLevelItem(i) for i in range(self.pointTree.topLevelItemCount())]
        self.calibration["points"] = [(item.stagePos, item.parentPos) for item in items]
        self.recalculate()
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
        self.recalculate()
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

    def recalculate(self):
        # identity affine axis transform matrix

        # method: user generates many calibration points that are all colinear along each of the
        # stage axes. In this way, we can independently determine the orientation of each stage axis,
        # and combine these into a full transformation matrix.

        npts = len(self.calibration["points"])

        # build arrays of calibration points
        stagePos = np.empty((npts, 3))
        parentPos = np.empty((npts, 3))
        for i, pt in enumerate(self.calibration["points"]):
            stagePos[i] = pt[0]
            parentPos[i] = pt[1]

        def changeAxis(p1, p2):
            # Which single axis has changed between 2 points?
            diff = np.abs(p2 - p1)
            dist = np.linalg.norm(diff)
            axis = np.argmax(diff)
            if diff[axis] > dist * 0.99:
                return axis
            else:
                return None

        # find the point groupings for each axis
        axisPoints = [set(), set(), set()]
        currentAxis = None
        for i in range(1, npts):
            currentAxis = changeAxis(stagePos[i - 1], stagePos[i])
            if currentAxis is None:
                continue
            axisPoints[currentAxis].add(i - 1)
            axisPoints[currentAxis].add(i)

        for ax in (0, 1, 2):
            if len(axisPoints[ax]) < 2:
                for i in range(npts):
                    item = self.pointTree.topLevelItem(i)
                    item.setText(2, "")
                self.transform = None
                raise Exception("Could not find colinear points along all 3 axes")
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
        def mapPoint(axisTr, stagePos, localPos):
            # given a stage position and axis transform, map from localPos to parent coordinate system
            if isinstance(axisTr, np.ndarray):
                m = np.eye(4)
                m[:3] = axisTr.reshape(3, 4)
                axisTr = pg.Transform3D(m)
            st = self.dev._makeStageTransform(stagePos, axisTr)[0]
            tr = pg.Transform3D(self.dev.baseTransform() * st)
            return tr.map(localPos)

        def mapError(axisTr, stagePos, parentPos):
            # Goal is to map origin to parent position correctly
            return [mapPoint(axisTr, sp, [0, 0, 0]) - pp for sp, pp in zip(stagePos, parentPos)]

        error = mapError(self.transform, stagePos, parentPos)
        for i in range(npts):
            item = self.pointTree.topLevelItem(i)
            dist = np.linalg.norm(error[i])
            item.setText(2, "%0.2f um  (%0.3g, %0.3g, %0.3g)" % (1e6 * dist, error[i][0], error[i][1], error[i][2]))

        # send new transform to device
        self.dev._axisTransform = self.transform
        self.dev._inverseAxisTransform = None
        self.dev._updateTransform()

    def _recalculate(self):
        # identity affine axis transform matrix

        # method: given >= 4 arbitrarily-located calibration points, attempt to find the
        # affine transform that best matches all points.

        # For any 4 point-pairs, we can get an exact solution that may not work as well for other points.
        # With more points, we can try to pick an optimal transform that minimizes errors, but this
        # turns out to be a tricky minimization problem.

        npts = len(self.calibration["points"])

        # Need at least 4 points to generate a calibration
        if npts < 4:
            for i in range(npts):
                item = self.pointTree.topLevelItem(i)
                item.setText(2, "")
            self.transform = None
            return

        stagePos = np.empty((npts, 3))
        parentPos = np.empty((npts, 3))
        for i, pt in enumerate(self.calibration["points"]):
            stagePos[i] = pt[0]
            parentPos[i] = pt[1]

        def mapPoint(axisTr, stagePos, localPos):
            # given a stage position and axis transform, map from localPos to parent coordinate system
            if isinstance(axisTr, np.ndarray):
                m = np.eye(4)
                m[:3] = axisTr.reshape(3, 4)
                axisTr = pg.Transform3D(m)
            st = self.dev._makeStageTransform(stagePos, axisTr)[0]
            tr = pg.Transform3D(self.dev.baseTransform() * st)
            return tr.map(localPos)

        def mapError(axisTr, stagePos, parentPos):
            # Goal is to map origin to parent position correctly
            return [mapPoint(axisTr, sp, [0, 0, 0]) - pp for sp, pp in zip(stagePos, parentPos)]

        def errFn(axisTr, stagePos, parentPos):
            # reduce all point errors to a scalar error metric
            dist = [np.linalg.norm(err) for err in mapError(axisTr, stagePos, parentPos)]
            err = np.linalg.norm(dist)
            if err < best[0]:
                best[0] = err
                best[1] = axisTr
            return err

        def srtErrFn(x, stagePos, parentPos):
            # for solving with orthogonal axes and uniform scale factor
            axisTr = vecToSRT(x)
            return errFn(axisTr, stagePos, parentPos)

        def vecToSRT(x):
            return pg.SRTTransform3D({"pos": x[:3], "scale": x[3:6], "angle": x[6], "axis": [0, 0, 1]})

        # use random combinations of 4 points to get an average of exact solutions
        n_iter = min(100, 4 ** (stagePos.shape[0] - 4))
        m = []
        for i in range(n_iter):
            inds = list(range(len(stagePos)))
            np.random.shuffle(inds)
            Xa = stagePos[inds[:4]]
            Ya = parentPos[inds[:4]]
            m1 = self.dev._solveAxisTransform(Xa, Ya, np.zeros((4, 3)))
            m.append(m1)
        mGuess = np.mean(np.dstack(m), axis=2)

        # Fit the entire set of points, using the exact solution as initial guess
        best = [np.inf, None]
        self.result = scipy.optimize.minimize(
            errFn,
            x0=mGuess,
            args=(stagePos, parentPos),
            tol=1e-16,
            options={
                # 'eps': 1e-16,
                "gtol": 1e-16,
                # 'disp': True,
                "maxiter": 20000,
            },
            method="Nelder-Mead",
        )

        m = np.eye(4)
        m[:3] = best[1].reshape(3, 4)
        self.transform = pg.Transform3D(m)

        # measure and display errors for each point
        error = mapError(self.transform, stagePos, parentPos)
        for i in range(npts):
            item = self.pointTree.topLevelItem(i)
            dist = np.linalg.norm(error[i])
            item.setText(2, "%0.2f um  (%0.3g, %0.3g, %0.3g)" % (1e6 * dist, error[i][0], error[i][1], error[i][2]))

        # send new transform to device
        self.dev._axisTransform = self.transform
        self.dev._inverseAxisTransform = None
        self.dev._updateTransform()

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
            manager = getManager()
            camName = self.dev.config.get("imagingDevice", None)
            if camName is None:
                cams = manager.listInterfaces("camera")
                if len(cams) == 1:
                    camName = cams[0]
                else:
                    raise Exception("Calibration requires a single available camera device (found %d) or 'imagingDevice' key in stage configuration." % len(cams))
            self._camdev = manager.getDevice(camName)
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


class StageCalibration(object):
    # Old code, never used.. maybe just dump it!
    def __init__(self, stage):
        self.stage = stage
        self.framedelay = None

    def calibrate(self, camera):
        import imreg_dft  # FFT image registration by Chris Gohlke; available via pip
        n = 300
        dx = 10e-6

        self.move = None
        self.camera = camera
        self.offsets = np.empty((n, 2))
        self.frames = []
        self.index = 0
        # current stage position
        pos = self.stage.getPosition()

        # where to move on each update
        self.positions = np.zeros((n, 2))
        self.positions[:, 0] = pos[0] + np.arange(n) * dx
        self.positions[:, 1] = pos[1]

        camera.sigNewFrame.connect(self.newFrame)

    def newFrame(self, frame):
        try:
            if self.move is not None and not self.move.isDone():
                # stage is still moving; discard frame
                return

            if self.framedelay is None:
                # stage has stopped; discard 2 more frames to be sure
                # we get the right image.
                self.framedelay = pg.ptime.time() + 1.0 / frame.info()["fps"]
            elif self.framedelay < frame.info()["time"]:
                # now we are ready to keep this frame.
                self.framedelay = None
                self.processFrame(frame)
        except Exception:
            pg.disconnect(self.camera.sigNewFrame, self.newFrame)
            raise

    def processFrame(self, frame):
        self.frames.append(frame)
        index = self.index

        # update index for next iteration
        self.index += 1

        # decide whether to move the stage
        finished = self.index >= self.positions.shape[0]
        if not finished:
            self.move = self.stage.moveTo(self.positions[self.index], "slow")

        # calculate offset (while stage moves no next location)
        if index == 0:
            offset = (0, 0)
        else:
            compareIndex = max(0, index - 10)
            offset, _ = imreg_dft.translation(frame.getImage(), self.frames[compareIndex].getImage())
            px = self.camera.getPixelSize()
            offset = self.offsets[compareIndex] + offset.astype(float) * [px.x(), px.y()]
        self.offsets[index] = offset

        # finish up if there are no more positions
        if finished:
            pg.disconnect(self.camera.sigNewFrame, self.newFrame)
            self.analyze()

    def analyze(self):
        # frames = []
        # for frame in self.frames:
        #     frames.append(frame.getImage()[np.newaxis, ...])
        # self.frameArray = np.concatenate(frames, axis=0)
        # self.imageView = pg.image(self.frameArray)

        # linear regression to determine scale between stage steps and camera microns
        x = ((self.positions - self.positions[0]) ** 2).sum(axis=1) ** 0.5
        y = (self.offsets ** 2).sum(axis=1) ** 0.5
        slope, yint, r, p, stdev = scipy.stats.linregress(x, y)

        # subtract linear approximation to get residual error
        y1 = x * slope + yint
        self.xvals = x
        self.error = y - y1
        self.errorPlot = pg.plot(
            x,
            self.error,
            title="X axis error (slope = %0.2f um/step)" % (slope * 1e6),
            labels={"left": ("Error", "m"), "bottom": ("position", "steps")},
        )

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

        f0 = 6 * np.pi / x.max()  # guess there are 3 cycles in the data
        amp = self.error.max()
        self.fit = scipy.optimize.leastsq(erf, [0, f0, amp, amp, amp, amp], (x, self.error))[0]
        self.errorPlot.plot(x, fn(self.fit, x), pen="g")
