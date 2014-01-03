# -*- coding: utf-8 -*-
from acq4.devices.OptomechDevice import *
import acq4.pyqtgraph as pg

class MockStage(Device, OptomechDevice):

    sigPositionChanged = QtCore.Signal(object)

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        OptomechDevice.__init__(self, dm, config, name)
        
        self.config = config
        self.pos = [0, 0, 0]
        self.speed = [0,0]
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.updatePosition)
        dm.declareInterface(name, ['stage'], self)

    def updatePosition(self):
        if self.speed[0] == 0 and self.speed[1] == 0:
            self.timer.stop()
        self.setPosition([self.pos[0]+self.speed[0], self.pos[1]+self.speed[1], self.pos[2]])
        
    def setSpeed(self, spd):
        self.speed = spd
        self.timer.start(20)

    def getPosition(self):
        return self.pos[:]
        
    def setPosition(self, pos):
        self.pos = pos
        tr = pg.SRTTransform3D()
        tr.translate(pos)
        self.setDeviceTransform(tr)
        self.sigPositionChanged.emit(self)

    def deviceInterface(self, win):
        return MockStageInterface(self, win)


class MockStageInterface(QtGui.QWidget):
    def __init__(self, dev, win):
        self.win = win
        self.dev = dev
        QtGui.QWidget.__init__(self)
        self.layout = QtGui.QGridLayout()
        self.setLayout(self.layout)
        self.btn = pg.JoystickButton()
        self.layout.addWidget(self.btn, 0, 0)
        self.label = QtGui.QLabel()
        self.layout.addWidget(self.label)
        self.dev.sigPositionChanged.connect(self.update)
        self.btn.sigStateChanged.connect(self.btnChanged)
        self.label.setFixedWidth(300)
        
    def btnChanged(self, btn, state):
        self.dev.setSpeed((state[0] * 0.0001, state[1] * 0.0001))
        
    def update(self):
        pos = self.dev.getPosition()
        text = [pg.siFormat(x, suffix='m', precision=5) for x in pos]
        self.label.setText(", ".join(text))
