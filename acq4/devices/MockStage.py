# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.devices.OptomechDevice import *
import time
import numpy as np
from acq4.Manager import getManager
from acq4.devices.Stage import Stage, MoveFuture
from acq4.util.Thread import Thread
import acq4.pyqtgraph as pg
from acq4.util import Qt
from acq4.pyqtgraph import ptime
from acq4.util.Mutex import Mutex


class MockStage(Stage):

    def __init__(self, dm, config, name):
        Stage.__init__(self, dm, config, name)
        
        self._lastMove = None
        self.stageThread = MockStageThread()
        self.stageThread.positionChanged.connect(self.posChanged)
        self.stageThread.start()
        
        dm.declareInterface(name, ['stage'], self)
        
        # Global key press handling
        self.modifierScales = {
            Qt.Qt.Key_Control: 4.0,
            Qt.Qt.Key_Alt: 0.25,
            Qt.Qt.Key_Shift: 0.1,
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
        if 'keys' in config:
            Qt.QCoreApplication.instance().installEventFilter(self)
        self._quit = False
        dm.sigAbortAll.connect(self.abort)

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

    def _move(self, abs, rel, speed, linear):
        """Called by base stage class when the user requests to move to an
        absolute or relative position.
        """
        with self.lock:
            self._interruptMove()
            pos = self._toAbsolutePosition(abs, rel)
            speed = self._interpretSpeed(speed)
            self._lastMove = MockMoveFuture(self, pos, speed)
            return self._lastMove

    def eventFilter(self, obj, ev):
        """Catch key press/release events used for driving the stage.
        """
        #if self._quit:
            #return False
        if ev.type() not in (Qt.QEvent.KeyPress, Qt.QEvent.KeyRelease, Qt.QEvent.ShortcutOverride):
            return False
        if ev.isAutoRepeat():
            return False
        
        key = str(ev.text()).lower()
        keys = self.config.get('keys')
        if key != '' and key in keys:
            direction = keys.index(key)
            if ev.type() == Qt.QEvent.KeyRelease:
                self._directionKeys.discard(direction)
            else:
                self._directionKeys.add(direction)
        elif ev.key() in self.modifierScales:
            if ev.type() == Qt.QEvent.KeyRelease:
                self._modifiers.discard(ev.key())
            else:
                self._modifiers.add(ev.key())
        else:
            return False
        
        self._updateKeySpeed()
        return False

    def _updateKeySpeed(self):
        s = 1000e-6
        for mod in self._modifiers:
            s = s * self.modifierScales[mod]
        
        vec = np.array([0, 0, 0])
        for key in self._directionKeys:
            vec = vec + self.keyDirections[key] * s
        
        self.startMoving(vec)

    def stop(self):
        with self.lock:
            self.abort()
    
    def abort(self):
        self._interruptMove()
        self.stageThread.stop()
        
    def _interruptMove(self):
        if self._lastMove is not None and not self._lastMove.isDone():
            self._lastMove._interrupted = True

    def setUserSpeed(self, v):
        pass

    def _getPosition(self):
        return self.stageThread.getPosition()

    def targetPosition(self):
        with self.lock:
            if self._lastMove is None or self._lastMove.isDone():
                return self.getPosition()
            else:
                return self._lastMove.targetPos

    def startMoving(self, vel):
        """Begin moving the stage at a continuous velocity.
        """
        with self.lock:
            self._interruptMove()
            vel1 = np.zeros(3)
            vel1[:len(vel)] = vel
            self.stageThread.setVelocity(vel1)
        
    def quit(self):
        self.abort()
        self.stageThread.quit()
        self._quit = True
        

class MockMoveFuture(MoveFuture):
    """Provides access to a move-in-progress on a mock manipulator.
    """
    def __init__(self, dev, pos, speed):
        MoveFuture.__init__(self, dev, pos, speed)
        self.targetPos = pos
        self._finished = False
        self._interrupted = False
        self._errorMsg = None
        
        self.dev.stageThread.setTarget(self, pos, speed)
        
    def wasInterrupted(self):
        """Return True if the move was interrupted before completing.
        """
        return self._interrupted

    def isDone(self):
        """Return True if the move is complete or was interrupted.
        """
        return self._finished or self._interrupted

    def errorMessage(self):
        return self._errorMsg


class MockStageThread(Thread):
    """Thread used to simulate stage hardware.
    
    It is necessary for this to be in a thread because some stage users will
    block while waiting for a stage movement to complete.
    """
    
    positionChanged = Qt.Signal(object)
    
    def __init__(self):
        self.pos = np.zeros(3)
        self.target = None
        self.speed = None
        self.velocity = None
        self._quit = False
        self.lock = Mutex()
        self.interval = 30e-3
        self.lastUpdate = None
        self.currentMove = None
        Thread.__init__(self)
        
    def start(self):
        self._quit = False
        self.lastUpdate = ptime.time()
        Thread.start(self)
        
    def stop(self):
        with self.lock:
            self.target = None
            self.speed = None
            self.velocity = None
            
    def quit(self):
        with self.lock:
            self._quit = True
            
    def setTarget(self, future, target, speed):
        """Begin moving toward a target position.
        """
        with self.lock:
            self.currentMove = future
            self.target = target
            self.speed = speed
            self.velocity = None
    
    def setVelocity(self, vel):
        with self.lock:
            self.currentMove = None
            self.target = None
            self.speed = None
            self.velocity = vel
    
    def getPosition(self):
        with self.lock:
            return self.pos.copy()
    
    def run(self):
        lastUpdate = ptime.time()
        while True:
            with self.lock:
                if self._quit:
                    break
                target = self.target
                speed = self.speed
                velocity = self.velocity
                currentMove = self.currentMove
                pos = self.pos
                
            now = ptime.time()
            dt = now - lastUpdate
            lastUpdate = now
            
            if target is not None:
                dif = target - pos
                dist = np.linalg.norm(dif)
                stepDist = speed * dt
                if stepDist >= dist:
                    self._setPosition(target)
                    self.currentMove._finished = True
                    self.stop()
                else:
                    unit = dif / dist
                    step = unit * stepDist
                    self._setPosition(pos + step)
            elif self.velocity is not None and not np.all(velocity == 0):
                self._setPosition(pos + velocity * dt)
                
            time.sleep(self.interval)
    
    def _setPosition(self, pos):
        self.pos = np.array(pos)
        self.positionChanged.emit(pos)


#class MockStageInterface(Qt.QWidget):
    #def __init__(self, dev, win, keys=None):
        #self.win = win
        #self.dev = dev
        #Qt.QWidget.__init__(self)
        #self.layout = Qt.QGridLayout()
        #self.setLayout(self.layout)
        #self.btn = pg.JoystickButton()
        #self.layout.addWidget(self.btn, 0, 0)
        #self.label = Qt.QLabel()
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
