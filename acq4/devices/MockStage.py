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
        self._installedFilters = []
        self._directionKeys = set()
        man = getManager()
        man.sigModulesChanged.connect(self._installEventFilters)

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

    def _installEventFilters(self):
        # check for new module windows and install key event filters
        man = getManager()
        for modname in man.listModules():
            mod = man.getModule(modname)
            if mod not in self._installedFilters:
                w = mod.window()
                if w is None:
                    continue
                w.installEventFilter(self)
                self._installedFilters.append(mod)

    def eventFilter(self, obj, ev):
        if ev.type() not in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease, QtCore.QEvent.ShortcutOverride):
            return False
        if ev.isAutoRepeat():
            return False
        key = ev.text()
        keys = self.config.get('keys')
        if key == '' or key not in keys:
            return False
        
        direction = keys.index(key)
        if ev.type() == QtCore.QEvent.KeyRelease:
            self._directionKeys.remove(direction)
        else:
            self._directionKeys.add(direction)
            
        self._updateKeySpeed(ev.modifiers())
        return True

    def _updateKeySpeed(self, mods):
        s = 100e-6
        vecs = np.array([
            [0, 0, s],
            [0, s, 0],
            [0, 0, -s],
            [-s, 0, 0],
            [0, -s, 0],
            [s, 0, 0],
        ])
        vec = np.array([0, 0, 0])
        for key in self._pressedKeys:
            vec = vec + vecs[key]
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
