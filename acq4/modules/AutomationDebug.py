import os

from acq4.devices.Camera import Camera
from acq4.modules.Camera import CameraWindow
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.future import Future
from pyqtgraph import mkPen


class AutomationDebugWindow(Qt.QMainWindow):
    def __init__(self, module: "AutomationDebug"):
        super().__init__()
        self._layout = Qt.QGridLayout()
        widget = Qt.QWidget()
        widget.setLayout(self._layout)
        self.setCentralWidget(widget)
        self.module = module
        self.setWindowTitle('Automation Debug')
        self._previousBoxWidgets = []
        self._layout.addWidget(Qt.QLabel('Imaging'))
        self._neuronDetectBtn = Qt.QPushButton('Detect Neurons')
        self._neuronDetectBtn.clicked.connect(self.detectNeurons)
        self._layout.addWidget(self._neuronDetectBtn)
        self.show()

    def detectNeurons(self):
        self._neuronDetectBtn.setEnabled(False)
        self.module.manager.getModule('Camera').window()  # make sure camera window is open
        neurons_fut = self._detectNeurons()
        neurons_fut.sigFinished.connect(self._postDetectNeurons)

    def _postDetectNeurons(self, neurons_fut: Future):
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
            self._neuronDetectBtn.setEnabled(True)

    @Future.wrap
    def _detectNeurons(self, _future: Future) -> list:
        from acq4.util.imaging.object_detection import detect_neurons

        cam: Camera = self.module.manager.getDevice('Camera')
        with cam.ensureRunning():
            frame = _future.waitFor(cam.acquireFrames(1)).getResult()[0]
        return _future.waitFor(detect_neurons(frame)).getResult()

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
