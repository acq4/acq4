from acq4.util import Qt
import pyqtgraph as pg


class PatchPipetteDeviceGui(Qt.QWidget):
    def __init__(self, dev, win):
        self.cleanFuture = None
        self.dev = dev

        Qt.QWidget.__init__(self)
        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)

        self.cleanBtn = Qt.QPushButton('Clean Pipette')
        self.cleanBtn.setCheckable(True)
        self.positionBtnLayout = Qt.QHBoxLayout()
        self.positionBtnLayout.addWidget(self.cleanBtn)
        self.cleanBtn.clicked.connect(self.cleanClicked)

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

    def cleanClicked(self):
        if self.cleanBtn.isChecked():
            self.cleanBtn.setText("Cleaning..")
            self.cleanFuture = self.dev.setState('clean')
            self.cleanFuture.sigFinished.connect(self.cleaningFinished)
        else:
            if self.cleanFuture is not None and not self.cleanFuture.isDone():
                self.cleanFuture.stop()
            self.cleanBtn.setText("Clean Pipette")

    def cleaningFinished(self):
        self.cleanBtn.setText("Clean Pipette")
        self.cleanBtn.setChecked(False)

    def setPositionClicked(self):
        btn = self.sender()
        self.dev.pipetteDevice.savePosition(btn.positionName)
        btn.success()
