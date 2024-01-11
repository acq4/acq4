import os

from acq4.devices.Camera import Camera
from acq4.modules.Camera import CameraWindow
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.future import Future
from acq4.util.imaging.object_detection import detect_neurons
from pyqtgraph import mkPen


class AutomationDebugWindow(Qt.QMainWindow):
    def __init__(self, module):
        super().__init__()
        self._layout = Qt.QGridLayout()
        widget = Qt.QWidget()
        widget.setLayout(self._layout)
        self.setCentralWidget(widget)
        self.module = module
        self.setWindowTitle('Automation Debug')
        self._layout.addWidget(Qt.QLabel('Imaging'))
        btn = Qt.QPushButton('Detect Neurons')
        btn.clicked.connect(self.detectNeurons)
        self._layout.addWidget(btn)
        self.show()

    def detectNeurons(self):
        cam_win: CameraWindow = self.module.manager.getModule('Camera').window()
        frame_image_item = cam_win.interfaces["Camera"].frameDisplay.imageItem()
        view = frame_image_item.getViewBox()
        for start, end in self._detectNeurons().getResult():
            box = Qt.QGraphicsRectItem(Qt.QRectF(Qt.QPointF(*start), Qt.QPointF(*end)))
            box.setPen(mkPen('r', width=2))
            box.setBrush(Qt.QBrush(Qt.QColor(255, 0, 0, 5)))
            view.addItem(box)
        # TODO clear old boxes
        # TODO add labels

    @Future.wrap
    def _detectNeurons(self, _future: Future) -> list:
        cam: Camera = self.module.manager.getDevice('Camera')
        with cam.run():
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
