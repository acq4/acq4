import os
import random

from acq4.devices.Camera import Camera
from acq4.devices.Microscope import Microscope
from acq4.devices.Pipette import Pipette
from acq4.modules.Camera import CameraWindow
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.future import Future, future_wrap
from acq4.util.imaging.sequencer import acquire_z_stack
from pyqtgraph import mkPen, SpinBox
from pyqtgraph.units import µm


class AutomationDebugWindow(Qt.QMainWindow):
    def __init__(self, module: "AutomationDebug"):
        super().__init__()
        self._layout = Qt.FlowLayout()
        widget = Qt.QWidget()
        widget.setLayout(self._layout)
        self.setCentralWidget(widget)
        self.module = module
        self.setWindowTitle('Automation Debug')
        self._previousBoxWidgets = []

        self._clearBtn = Qt.QPushButton('Clear')
        self._clearBtn.clicked.connect(self.clearBoundingBoxes)
        self._layout.addWidget(self._clearBtn)

        self._zStackDetectBtn = Qt.QPushButton('Neurons in z-stack?')
        self._zStackDetectBtn.clicked.connect(self.startZStackDetect)
        self._layout.addWidget(self._zStackDetectBtn)

        self._flatDetectBtn = Qt.QPushButton('Neurons in single frame?')
        self._flatDetectBtn.clicked.connect(self.startFlatDetect)
        self._layout.addWidget(self._flatDetectBtn)

        auto_space = Qt.QWidget(self)
        self._layout.addWidget(auto_space)
        auto_layout = Qt.QGridLayout()
        auto_space.setLayout(auto_layout)

        auto_layout.addWidget(Qt.QLabel('Top-left'), 0, 0)
        self._setTopLeftButton = Qt.QPushButton('>')
        self._setTopLeftButton.setProperty('maximumWidth', 15)
        self._setTopLeftButton.clicked.connect(self._setTopLeft)
        auto_layout.addWidget(self._setTopLeftButton, 0, 1)
        self._xLeftSpin = SpinBox()
        self._xLeftSpin.setOpts(value=0, suffix="m", siPrefix=True, step=10e-6, decimals=6)
        auto_layout.addWidget(self._xLeftSpin, 0, 2)
        self._yTopSpin = SpinBox()
        self._yTopSpin.setOpts(value=0, suffix="m", siPrefix=True, step=10e-6, decimals=6)
        auto_layout.addWidget(self._yTopSpin, 0, 3)
        self._setBottomRightButton = Qt.QPushButton('>')
        self._setBottomRightButton.setProperty('maximumWidth', 15)
        self._setBottomRightButton.clicked.connect(self._setBottomRight)
        auto_layout.addWidget(Qt.QLabel('Bottom-right'), 1, 0)
        auto_layout.addWidget(self._setBottomRightButton, 1, 1)
        self._xRightSpin = SpinBox()
        self._xRightSpin.setOpts(value=0, suffix="m", siPrefix=True, step=10e-6, decimals=6)
        auto_layout.addWidget(self._xRightSpin, 1, 2)
        self._yBottomSpin = SpinBox()
        self._yBottomSpin.setOpts(value=0, suffix="m", siPrefix=True, step=10e-6, decimals=6)
        auto_layout.addWidget(self._yBottomSpin, 1, 3)

        self._autoTargetBtn = Qt.QPushButton('Find a \nrandom target')
        self._autoTargetBtn.clicked.connect(self.startAutoTarget)
        auto_layout.addWidget(self._autoTargetBtn, 0, 4, 1, 2)

        self.show()

    def _setWorkingState(self, working: bool):
        self.module.manager.getModule('Camera').window()  # make sure camera window is open
        self._clearBtn.setEnabled(not working)
        self._zStackDetectBtn.setEnabled(not working)
        self._flatDetectBtn.setEnabled(not working)
        self._autoTargetBtn.setEnabled(not working)

    @property
    def cameraDevice(self) -> Camera:
        return self.module.manager.getDevice('Camera')  # TODO

    @property
    def scopeDevice(self) -> Microscope:
        return self.cameraDevice.scopeDev  # TODO

    @property
    def pipetteDevice(self) -> Pipette:
        return self.module.manager.getDevice('Pipette1')  # TODO

    def _setTopLeft(self):
        cam = self.cameraDevice
        region = cam.getParam("region")
        bound = cam.globalTransform().map(Qt.QPointF(region[0], region[1]))
        self._xLeftSpin.setValue(bound.x())
        self._yTopSpin.setValue(bound.y())

    def _setBottomRight(self):
        cam = self.cameraDevice
        region = cam.getParam("region")
        bound = cam.globalTransform().map(Qt.QPointF(region[0] + region[2], region[1] + region[3]))
        self._xRightSpin.setValue(bound.x())
        self._yBottomSpin.setValue(bound.y())

    def startZStackDetect(self):
        self._setWorkingState(True)
        neurons_fut = self._detectNeuronsZStack()
        neurons_fut.sigFinished.connect(self._handleFlatResults)

    def startFlatDetect(self):
        self._setWorkingState(True)
        neurons_fut = self._detectNeuronsFlat()
        neurons_fut.sigFinished.connect(self._handleFlatResults)

    def startAutoTarget(self):
        self._setWorkingState(True)
        target_fut = self._autoTarget()
        target_fut.sigFinished.connect(self._handleAutoFinish)

    def clearBoundingBoxes(self):
        cam_win: CameraWindow = self.module.manager.getModule('Camera').window()
        for widget in self._previousBoxWidgets:
            cam_win.removeItem(widget)
        self._previousBoxWidgets = []

    def _handleFlatResults(self, neurons_fut: Future) -> list:
        try:
            self._displayBoundingBoxes(neurons_fut.getResult())
        finally:
            self._setWorkingState(False)
        return self._previousBoxWidgets

    def _displayBoundingBoxes(self, bounding_boxes):
        cam_win: CameraWindow = self.module.manager.getModule('Camera').window()
        self.clearBoundingBoxes()
        for start, end in bounding_boxes:
            box = Qt.QGraphicsRectItem(Qt.QRectF(Qt.QPointF(*start), Qt.QPointF(*end)))
            box.setPen(mkPen('r', width=2))
            box.setBrush(Qt.QBrush(Qt.QColor(0, 0, 0, 0)))
            cam_win.addItem(box)
            self._previousBoxWidgets.append(box)
            # TODO label boxes
            # label = TextItem('Neuron')
            # label.setPen(mkPen('r', width=1))
            # label.setPos(*end)
            # cam_win.addItem(label)
            # self._previousBoxWidgets.append(label)

    @future_wrap
    def _detectNeuronsFlat(self, _future: Future):
        from acq4.util.imaging.object_detection import detect_neurons

        with self.cameraDevice.ensureRunning():
            frame = _future.waitFor(self.cameraDevice.acquireFrames(1)).getResult()[0]
        return _future.waitFor(detect_neurons(frame)).getResult()

    @future_wrap
    def _detectNeuronsZStack(self, _future: Future) -> list:
        from acq4.util.imaging.object_detection import detect_neurons

        depth = self.cameraDevice.getFocusDepth()
        start = depth - 10 * µm
        stop = depth + 10 * µm
        z_stack = _future.waitFor(acquire_z_stack(self.cameraDevice, start, stop, 1 * µm)).getResult()
        self.cameraDevice.setFocusDepth(depth)  # no need to wait
        return _future.waitFor(detect_neurons(z_stack)).getResult()

    @future_wrap
    def _autoTarget(self, _future):
        x = random.uniform(self._xLeftSpin.value(), self._xRightSpin.value())
        y = random.uniform(self._yBottomSpin.value(), self._yTopSpin.value())
        _future.waitFor(self.scopeDevice.setGlobalPosition((x, y)))
        # TODO don't know why this hangs when using waitFor, but it does
        depth = self.scopeDevice.findSurfaceDepth(
            self.cameraDevice, searchDistance=50*µm, searchStep=15*µm, block=True
        ).getResult()
        depth -= 50 * µm
        self.cameraDevice.setFocusDepth(depth)
        neurons_fut = _future.waitFor(self._detectNeuronsFlat())
        self._displayBoundingBoxes(neurons_fut.getResult())

    def _handleAutoFinish(self, fut: Future):
        try:
            fut.wait()  # to raise errors
            if self._previousBoxWidgets:
                box = random.choice(self._previousBoxWidgets)
                center = box.rect().center()
                # tODO translate? depth?
                center = (center.x(), center.y(), self.cameraDevice.getFocusDepth())
                self.pipetteDevice.setTarget(center)
        finally:
            self._setWorkingState(False)

    def quit(self):
        self.close()


class AutomationDebug(Module):
    moduleDisplayName = "Automation Debug"
    moduleCategory = "Utilities"

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.ui = AutomationDebugWindow(self)
        manager.declareInterface(name, ['automationDebugModule'], self)
        this_dir = os.path.dirname(__file__)
        self.ui.setWindowIcon(Qt.QIcon(os.path.join(this_dir, 'Manager', 'icon.png')))

    def quit(self, fromUi=False):
        if not fromUi:
            self.ui.quit()
        super().quit()
