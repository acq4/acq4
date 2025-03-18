from pyqtgraph.parametertree import ParameterTree, Parameter
from acq4.modules.Module import Module
from acq4.util import Qt


class PipetteDetector(Module):

    moduleDisplayName = "Pipette Detector"
    moduleCategory = "Utilities"


    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.manager = manager

        self.camera = manager.getDevice('Camera')
        self.pipette = manager.getDevice('Pipette1')

        self.params = Parameter.create(name='params', type='group', children=[
            {'name': 'offset distance', 'type': 'float', 'value': 100e-6, 'suffix': 'm', 'siPrefix': True, 'limits': [1e-6, 1e-3]},
            {'name': 'move speed', 'type': 'float', 'value': 100e-6, 'suffix': 'm/s', 'siPrefix': True, 'limits': [1e-6, 1e-3]},
        ])

        self.win = Qt.QWidget()
        self.win.setWindowTitle('Pipette Detector')
        self.layout = Qt.QGridLayout()
        self.win.setLayout(self.layout)

        self.ptree = ParameterTree()
        self.layout.addWidget(self.ptree, 0, 0)
        self.ptree.setParameters(self.params, showTop=False)

        self.acquireBtn = Qt.QPushButton('acquire')
        self.layout.addWidget(self.acquireBtn, 1, 0)

        self.win.resize(300, 400)
        self.win.show()

        self.acquireBtn.clicked.connect(self.acquire)

    def acquire(self):
        self.acquireBtn.setEnabled(False)
        try:
            self._acquire()
        finally:
            self.acquireBtn.setEnabled(True)

    def _acquire(self):
        cam = self.camera
        pip = self.pipette

        center = cam.globalCenterPosition()
        pipetteDirection = pip.globalDirection()
        offset = pipetteDirection * self.params['offset distance']
        start = center - offset
        stop = center + offset

        pip._moveToGlobal(start, 'fast').wait()

        pipRecord = pip.startRecording()

        task = cam.createTask({'params': {}}, self)
        task.configure()
        task.start()

        fut = pip._moveToGlobal(stop, self.params['move speed'])
        fut.wait(updates=True)

        task.stop()
        pipRecord.stop()
        camResult = task.getResult()

        self.results = camResult, pipRecord

        dh = self.manager.currentDir.mkdir('pipette_detection', autoIncrement=True)
        task.storeResult(dh)
        pipRecord.store(dh[pip.name()].name())


