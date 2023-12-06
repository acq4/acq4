from __future__ import print_function
from acq4.util import Qt


class PatchPipetteDeviceGui(Qt.QWidget):
    def __init__(self, dev, win):
        self.cleanFuture = None
        self.dev = dev

        Qt.QWidget.__init__(self)
        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)

        self.cleanBtn = Qt.QPushButton('Clean Pipette')
        self.setCleanBtn = Qt.QPushButton('Set Clean Pos')
        self.setRinseBtn = Qt.QPushButton('Set Rinse Pos')
        self.setCollectBtn = Qt.QPushButton('Set Collect Pos')
        self.positionBtnLayout = Qt.QHBoxLayout()
        self.positionBtnLayout.addWidget(self.cleanBtn)
        self.cleanBtn.setCheckable(True)
        self.positionBtnLayout.addWidget(self.setCleanBtn)
        self.positionBtnLayout.addWidget(self.setRinseBtn)
        self.positionBtnLayout.addWidget(self.setCollectBtn)
        row = self.layout.rowCount()
        self.layout.addLayout(self.positionBtnLayout, row, 0)

        self.cleanBtn.clicked.connect(self.cleanClicked)
        self.setCleanBtn.clicked.connect(self.setCleanClicked)
        self.setRinseBtn.clicked.connect(self.setRinseClicked)
        self.setCollectBtn.clicked.connect(self.setCollectClicked)

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

    def setCleanClicked(self):
        self.dev.pipetteDevice.savePosition('clean')

    def setRinseClicked(self):
        self.dev.pipetteDevice.savePosition('rinse')

    def setCollectClicked(self):
        self.dev.pipetteDevice.savePosition('collect')
