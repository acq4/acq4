# -*- coding: utf-8 -*-
from acq4.Manager import getManager
from acq4.devices.OptomechDevice import *
import acq4.pyqtgraph as pg

class MockStage(Device, OptomechDevice):

    sigPositionChanged = QtCore.Signal(object)

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        OptomechDevice.__init__(self, dm, config, name)
        
        self.config = config
        self.pos = np.array([0., 0., 0.])
        self.speed = np.array([0., 0., 0.])
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.updatePosition)
        self._posUpdateInterval = 100e-3
        dm.declareInterface(name, ['stage'], self)
        
        # Global key press handling
        self.modifierScales = {
            QtCore.Qt.Key_Control: 4.0,
            QtCore.Qt.Key_Alt: 0.25,
            QtCore.Qt.Key_Shift: 0.1,
        }
        self.keyDirections = np.array([
            [0, 0, 1],
            [0, 1, 0],
            [0, 0, -1],
            [-1, 0, 0],
            [0, -1, 0],
            [1, 0, 0],
        ])
        self._directionKeys = set()
        self._modifiers = set()
        QtCore.QCoreApplication.instance().installEventFilter(self)

    def updatePosition(self):
        if np.all(self.speed == 0):
            self.timer.stop()
        self.setPosition(self.pos + self.speed * self._posUpdateInterval)
        
    def setSpeed(self, spd):
        self.speed[:len(spd)] = spd
        self.timer.start(int(self._posUpdateInterval * 1000))

    def getPosition(self):
        return self.pos.copy()
        
    def setPosition(self, pos):
        self.pos = np.array(pos)
        tr = pg.SRTTransform3D()
        tr.translate(pos)
        self.setDeviceTransform(tr)
        self.sigPositionChanged.emit(self)

    def deviceInterface(self, win):
        return MockStageInterface(self, win)

    def eventFilter(self, obj, ev):
        if ev.type() not in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease, QtCore.QEvent.ShortcutOverride):
            return False
        if ev.isAutoRepeat():
            return False
        
        key = str(ev.text()).lower()
        keys = self.config.get('keys')
        if key != '' and key in keys:
            direction = keys.index(key)
            if ev.type() == QtCore.QEvent.KeyRelease:
                self._directionKeys.discard(direction)
            else:
                self._directionKeys.add(direction)
        elif ev.key() in self.modifierScales:
            if ev.type() == QtCore.QEvent.KeyRelease:
                self._modifiers.discard(ev.key())
            else:
                self._modifiers.add(ev.key())
        else:
            return False
        
        self._updateKeySpeed()
        return True

    def _updateKeySpeed(self):
        s = 100e-6
        for mod in self._modifiers:
            s = s * self.modifierScales[mod]
        
        vec = np.array([0, 0, 0])
        for key in self._directionKeys:
            vec = vec + self.keyDirections[key] * s
        
        self.setSpeed(vec)
        

class MockStageInterface(QtGui.QWidget):
    def __init__(self, dev, win, keys=None):
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
