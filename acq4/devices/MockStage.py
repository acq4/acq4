# -*- coding: utf-8 -*-
import numpy as np
from acq4.Manager import getManager
from acq4.devices.Stage import Stage, MoveFuture
import acq4.pyqtgraph as pg
from acq4.pyqtgraph.Qt import QtGui, QtCore


class MockStage(Stage):

    def __init__(self, dm, config, name):
        Stage.__init__(self, dm, config, name)
        
        self.__pos = np.array([0., 0., 0.])
        self.__speed = np.array([0., 0., 0.])
        self._lastMove = None
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._updatePosition)
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

    def capabilities(self):
        """Return a structure describing the capabilities of this device"""
        if 'capabilities' in self.config:
            return self.config['capabilities']
        else:
            return {
                'getPos': (True, True, True),
                'setPos': (True, True, True),
                'limits': (False, False, False),
            }

    def _updatePosition(self):
        if np.all(self.__speed == 0):
            self.timer.stop()
        self._setPosition(self.__pos + self.__speed * self._posUpdateInterval)
        
    def _setPosition(self, pos):
        self.__pos = np.array(pos)
        tr = pg.SRTTransform3D()
        tr.translate(pos)
        self.setDeviceTransform(tr)
        self.posChanged(pos)

    def _move(self, abs, rel, speed, linear):
        with self.lock:
            pos = self._toAbsolutePosition(abs, rel)
            speed = self._interpretSpeed(speed)
            self._lastMove = MockMoveFuture(self, pos, speed)
            return self._lastMove

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
        return False

    def _updateKeySpeed(self):
        s = 400e-6
        for mod in self._modifiers:
            s = s * self.modifierScales[mod]
        
        vec = np.array([0, 0, 0])
        for key in self._directionKeys:
            vec = vec + self.keyDirections[key] * s
        
        self.startMoving(vec)

    def stop(self):
        self.abort()

    def abort(self):
        self.timer.stop()

    def setUserSpeed(self, v):
        pass

    def _getPosition(self):
        return self.__pos.copy()

    def targetPosition(self):
        with self.lock:
            if self._lastMove is None or self._lastMove.isDone():
                return self.getPosition()
            else:
                return self._lastMove.targetPos

    def startMoving(self, vel):
        """Begin moving the stage at a continuous velocity.
        """
        if np.all(vel==0):
            self.timer.stop()
        self.__speed[:len(vel)] = vel
        self.timer.start(int(self._posUpdateInterval * 1000))




class MockMoveFuture(MoveFuture):
    """Provides access to a move-in-progress on a mock manipulator.
    """
    def __init__(self, dev, pos, speed):
        MoveFuture.__init__(self, dev, pos, speed)
        self._interrupted = False
        self._errorMSg = None
        self._finished = False

        self.dev._setPosition(pos)
        
    def wasInterrupted(self):
        """Return True if the move was interrupted before completing.
        """
        return self._interrupted

    def isDone(self):
        """Return True if the move is complete.
        """
        return True

    def errorMessage(self):
        return self._errorMsg




#class MockStageInterface(QtGui.QWidget):
    #def __init__(self, dev, win, keys=None):
        #self.win = win
        #self.dev = dev
        #QtGui.QWidget.__init__(self)
        #self.layout = QtGui.QGridLayout()
        #self.setLayout(self.layout)
        #self.btn = pg.JoystickButton()
        #self.layout.addWidget(self.btn, 0, 0)
        #self.label = QtGui.QLabel()
        #self.layout.addWidget(self.label)
        #self.dev.sigPositionChanged.connect(self.update)
        #self.btn.sigStateChanged.connect(self.btnChanged)
        #self.label.setFixedWidth(300)
        
    #def btnChanged(self, btn, state):
        #self.dev.setSpeed((state[0] * 0.0001, state[1] * 0.0001))
        
    #def update(self):
        #pos = self.dev.getPosition()
        #text = [pg.siFormat(x, suffix='m', precision=5) for x in pos]
        #self.label.setText(", ".join(text))
