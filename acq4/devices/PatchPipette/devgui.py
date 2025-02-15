from acq4.util import Qt
import pyqtgraph as pg
from acq4.util.future import FutureButton


class PatchPipetteDeviceGui(Qt.QWidget):
    def __init__(self, dev, win):
        self.cleanFuture = None
        self.dev = dev

        Qt.QWidget.__init__(self)
        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)

        self.cleanBtn = FutureButton(
            self.doClean, 'Clean Pipette', stoppable=True, processing='Cleaning...', failure='Interrupted!')
        self.positionBtnLayout = Qt.QHBoxLayout()
        self.positionBtnLayout.addWidget(self.cleanBtn)

        positions = ['clean', 'rinse', 'extract', 'collect']
        self.positionBtns = {}
        for pos in positions:
            btn = pg.FeedbackButton(f'Set {pos.capitalize()} Pos')
            btn.positionName = pos
            self.positionBtns[pos] = btn
            btn.clicked.connect(self.setPositionClicked)
            self.positionBtnLayout.addWidget(btn)

        row = self.layout.rowCount()
        self.layout.addLayout(self.positionBtnLayout, row, 0)

    def doClean(self):
        return self.dev.setState('clean')

    def setPositionClicked(self):
        btn = self.sender()
        self.dev.pipetteDevice.savePosition(btn.positionName)
        btn.success()
