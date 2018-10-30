from __future__ import print_function
import numpy as np
import scipy.stats, scipy.optimize
import acq4.pyqtgraph as pg
from acq4.Manager import getManager
from acq4.util import Qt


class CalibrationWindow(Qt.QWidget):
    def __init__(self, device):
        self.dev = device
        self._cammod = None
        self._camdev = None

        Qt.QWidget.__init__(self)
        self.resize(600, 300)
        self.setWindowTitle("Calibration: %s" % device.name())

        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)

        # tree columns:
        #   stage x, y, z   global x, y, z   error
        self.pointTree = Qt.QTreeWidget()
        self.pointTree.setHeaderLabels(['stage pos', 'global pos', 'error'])
        self.pointTree.setColumnCount(3)
        self.layout.addWidget(self.pointTree, 0, 0)

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

        self.calibration['points'].append((stagePos, globalPos))
        item = Qt.QTreeWidgetItem(["%0.3g, %0.3g, %0.3g" % tuple(stagePos), "%0.3g, %0.3g, %0.3g" % tuple(parentPos), ""])
        self.pointTree.addTopLevelItem(item)

        # self.calibration.append({'global': pos, 'stage': self.dev.}

        self.addPointBtn.setChecked(False)

    def removePointClicked(self):
        self.recalculate()

    def saveClicked(self):
        self.saveCalibrationToDevice()

    def loadCalibrationFromDevice(self):
        self.calibration = self.dev.readConfigFile('calibration')
        self.calibration.setdefault('points', [])
        self.recalculate()

    def saveCalibrationToDevice(self):
        self.dev.writeConfigFile(cal, 'calibration')

    def recalculate(self):
        pass

    def getCameraModule(self):
        if self._cammod is None:
            manager = getManager()
            mods = manager.listInterfaces('cameraModule')
            if len(mods) == 0:
                raise Exception("Calibration requires an open camera module")
            self._cammod = manager.getModule(mods[0])
        return self._cammod

    def getCameraDevice(self):
        if self._camdev is None:
            manager = getManager()
            camName = self.dev.config.get('calibrationImagingDevice', None)
            if camName is None:
                raise Exception("Calibration requires 'calibrationImagingDevice' key in stage configuration.")
            self._camdev = manager.getDevice(camName)
        return self._camdev



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
        self.positions[:,0] = pos[0] + np.arange(n) * dx
        self.positions[:,1] = pos[1]

        camera.sigNewFrame.connect(self.newFrame)

    def newFrame(self, frame):
        try:
            if self.move is not None and not self.move.isDone():
                # stage is still moving; discard frame
                return

            if self.framedelay is None:
                # stage has stopped; discard 2 more frames to be sure
                # we get the right image.
                self.framedelay = pg.ptime.time() + 1./frame.info()['fps']
            elif self.framedelay < frame.info()['time']:
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
            self.move = self.stage.moveTo(self.positions[self.index], 'slow')

        # calculate offset (while stage moves no next location)
        if index == 0:
            offset = (0, 0)
        else:
            compareIndex = max(0, index-10)
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
        x = ((self.positions - self.positions[0])**2).sum(axis=1)**0.5
        y = (self.offsets**2).sum(axis=1)**0.5
        slope, yint, r, p, stdev = scipy.stats.linregress(x, y)

        # subtract linear approximation to get residual error
        y1 = x * slope + yint
        self.xvals = x
        self.error = y - y1
        self.errorPlot = pg.plot(x, self.error, title='X axis error (slope = %0.2f um/step)' % (slope*1e6), labels={'left': ('Error', 'm'), 'bottom': ('position', 'steps')})

        # fit residual to combination of sine waves
        def fn(p, x):
            return (p[2] * np.sin((x + p[0]) * 1 * p[1]) + 
                    p[3] * np.sin((x + p[0]) * 2 * p[1]) + 
                    p[4] * np.sin((x + p[0]) * 3 * p[1]) + 
                    p[5] * np.sin((x + p[0]) * 4 * p[1]))

        def erf(p, x, y):
            return fn(p, x) - y

        f0 = 6 * np.pi / x.max()  # guess there are 3 cycles in the data
        amp = self.error.max()
        self.fit = scipy.optimize.leastsq(erf, [0, f0, amp, amp, amp, amp], (x, self.error))[0]
        self.errorPlot.plot(x, fn(self.fit, x), pen='g')



