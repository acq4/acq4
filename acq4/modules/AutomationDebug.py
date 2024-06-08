import os

from acq4.devices.Camera import Camera
from acq4.modules.Camera import CameraWindow
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.future import Future, future_wrap
from acq4.util.imaging.sequencer import acquire_z_stack
from pyqtgraph import mkPen
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

        self._zStackDetectBtn = Qt.QPushButton('Neurons in z-stack?')
        self._zStackDetectBtn.clicked.connect(self.startZStackDetect)
        self._layout.addWidget(self._zStackDetectBtn)

        self._flatDetectBtn = Qt.QPushButton('Neurons in single frame?')
        self._flatDetectBtn.clicked.connect(self.startFlatDetect)
        self._layout.addWidget(self._flatDetectBtn)

        self._autoSampleBtn = Qt.QPushButton('Auto')
        self._autoSampleBtn.clicked.connect(self.startAutoSample)
        self._layout.addWidget(self._autoSampleBtn)

        self.show()

    def _setWorkingState(self, working: bool):
        self.module.manager.getModule('Camera').window()  # make sure camera window is open
        self._zStackDetectBtn.setEnabled(not working)
        self._flatDetectBtn.setEnabled(not working)
        self._autoSampleBtn.setEnabled(not working)

    def startZStackDetect(self):
        self._setWorkingState(True)
        neurons_fut = self._detectNeuronsZStack()
        neurons_fut.sigFinished.connect(self._handleFlatResults)

    def startFlatDetect(self):
        self._setWorkingState(True)
        neurons_fut = self._detectNeuronsFlat()
        neurons_fut.sigFinished.connect(self._handleFlatResults)

    def startAutoSample(self):
        self._setWorkingState(True)
        neurons_fut = self._autoSample()
        neurons_fut.sigStateChanged.connect(self._handleAutoUpdates)

    def _handleFlatResults(self, neurons_fut: Future):
        # TODO handle errors
        try:
            cam_win: CameraWindow = self.module.manager.getModule('Camera').window()
            for widget in self._previousBoxWidgets:
                cam_win.removeItem(widget)
            self._previousBoxWidgets = []
            for start, end in neurons_fut.getResult():
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
        finally:
            self._setWorkingState(False)

    @future_wrap
    def _detectNeuronsFlat(self, _future: Future):
        from acq4.util.imaging.object_detection import detect_neurons

        cam: Camera = self.module.manager.getDevice('Camera')
        with cam.ensureRunning():
            frame = _future.waitFor(cam.acquireFrames(1)).getResult()[0]
        return _future.waitFor(detect_neurons(frame)).getResult()

    @future_wrap
    def _detectNeuronsZStack(self, _future: Future) -> list:
        from acq4.util.imaging.object_detection import detect_neurons

        cam: Camera = self.module.manager.getDevice('Camera')
        depth = cam.getFocusDepth()
        start = depth - 10 * µm
        stop = depth + 10 * µm
        z_stack = _future.waitFor(acquire_z_stack(cam, start, stop, 1 * µm)).getResult()
        cam.setFocusDepth(depth)  # no need to wait
        return _future.waitFor(detect_neurons(z_stack)).getResult()

    @future_wrap
    def _autoSample(self):
        pass  # TODO

    def _handleAutoUpdates(self, *args):
        pass  # TODO

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
