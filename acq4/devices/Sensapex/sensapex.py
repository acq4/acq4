# -*- coding: utf-8 -*-
from __future__ import print_function
import time
import numpy as np
from acq4.util import Qt
from ..Stage import Stage, MoveFuture, StageInterface
from acq4.drivers.sensapex import SensapexDevice, UMP, UMPError
from acq4.util.Mutex import Mutex
from acq4.util.Thread import Thread
from acq4.pyqtgraph import debug, ptime, SpinBox, Transform3D, solve3DTransform


class Sensapex(Stage):
    """
    A Sensapex manipulator.
    """
    
    devices = {}
    
    def __init__(self, man, config, name):
        self.devid = config.get('deviceId')
        self.scale = config.pop('scale', (1e-9, 1e-9, 1e-9))
        self.xPitch = config.pop('xPitch', 0)  # angle of x-axis. 0=parallel to xy plane, 90=pointing downward
        
        address = config.pop('address', None)
        group = config.pop('group', None)
        all_devs = UMP.get_ump(address=address, group=group).list_devices()
        if self.devid not in all_devs:
            raise Exception("Invalid sensapex device ID %s. Options are: %r" % (self.devid, all_devs))

        Stage.__init__(self, man, config, name)

        # create handle to this manipulator
        # note: n_axes is used in cases where the device is not capable of answering this on its own 
        self.dev = SensapexDevice(self.devid, callback=self._positionChanged, n_axes=config.get('nAxes'))
        # force cache update for this device.
        # This should also verify that we have a valid device ID
        self.dev.get_pos()

        self._lastMove = None
        man.sigAbortAll.connect(self.stop)


        # clear cached position for this device and re-read to generate an initial position update
        self._lastPos = None
        self.getPosition(refresh=True)

        # TODO: set any extra parameters specified in the config        
        Sensapex.devices[self.devid] = self

    def axes(self):
        return ('x', 'y', 'z')

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

    def axisTransform(self):
        if self._axisTransform is None:
            # sensapex manipulators do not have orthogonal axes, so we set up a 3D transform to compensate:
            a = self.xPitch * np.pi / 180.
            s = self.scale
            pts1 = np.array([  # unit vector in sensapex space
                [0, 0, 0],
                [1, 0, 0],
                [0, 1, 0],
                [0, 0, 1],
            ])
            pts2 = np.array([  # corresponding vector in global space
                [0, 0, 0],
                [s[0] * np.cos(a), 0, -s[0] * np.sin(a)],
                [0, s[1], 0],
                [0, 0, s[2]],
            ])
            tr = solve3DTransform(pts1, pts2)
            tr[3,3] = 1
            self._axisTransform = Transform3D(tr)
            self._inverseAxisTransform = None
        return self._axisTransform

    def stop(self):
        """Stop the manipulator immediately.
        """
        with self.lock:
            self.dev.stop()
            self._lastMove = None

    def _getPosition(self):
        # Called by superclass when user requests position refresh
        with self.lock:
            # using timeout=0 forces read from cache (the monitor thread ensures
            # these values are up to date)
            pos = self.dev.get_pos(timeout=0)[:3]
            if self._lastPos is not None:
                dif = np.linalg.norm(np.array(pos, dtype=float) - np.array(self._lastPos, dtype=float))

            # do not report changes < 100 nm
            if self._lastPos is None or dif > 100:
                self._lastPos = pos
                emit = True
            else:
                emit = False

        if emit:
            # don't emit signal while locked
            self.posChanged(pos)

        return pos

    def _positionChanged(self, dev, newPos, oldPos):
        # called by driver poller when position has changed
        self._getPosition()

    def targetPosition(self):
        with self.lock:
            if self._lastMove is None or self._lastMove.isDone():
                return self.getPosition()
            else:
                return self._lastMove.targetPos

    def quit(self):
        Sensapex.devices.pop(self.devid, None)
        if len(Sensapex.devices) == 0:
            UMP.get_ump().poller.stop()
        Stage.quit(self)

    def _move(self, abs, rel, speed, linear):
        with self.lock:
            pos = self._toAbsolutePosition(abs, rel)
            speed = self._interpretSpeed(speed)
            self._lastMove = SensapexMoveFuture(self, pos, speed)
            return self._lastMove


class SensapexMoveFuture(MoveFuture):
    """Provides access to a move-in-progress on a Sensapex manipulator.
    """
    def __init__(self, dev, pos, speed):
        MoveFuture.__init__(self, dev, pos, speed)
        self._interrupted = False
        self._errorMsg = None
        self._finished = False
        self._moveReq = self.dev.dev.goto_pos(pos, speed * 1e6)
        self._checked = False
        
    def wasInterrupted(self):
        """Return True if the move was interrupted before completing.
        """
        return self._moveReq.interrupted

    def isDone(self):
        """Return True if the move is complete.
        """        
        return self._moveReq.finished

    def _checkError(self):
        if self._checked or not self.isDone():
            return

        # interrupted?
        if self._moveReq.interrupted:
            self._errorMsg = self._moveReq.interrupt_reason
        else:
            # did we reach target?
            pos = self._moveReq.last_pos
            dif = np.linalg.norm(np.array(pos) - np.array(self.targetPos))
            if dif > 1000:  # require 1um accuracy
                # missed
                self._errorMsg = "%s stopped before reaching target (start=%s, target=%s, position=%s, dif=%s, speed=%s)." % (self.dev.name(), self.startPos, self.targetPos, pos, dif, self.speed)

        self._checked = True

    def wait(self, timeout=None, updates=False):
            """Block until the move has completed, has been interrupted, or the
            specified timeout has elapsed.

            If *updates* is True, process Qt events while waiting.

            If the move did not complete, raise an exception.
            """
            if updates is False:
                # if we don't need gui updates, then block on the finished_event for better performance
                if not self._moveReq.finished_event.wait(timeout=timeout):
                    raise self.Timeout("Timed out waiting for %s move to complete." % self.dev.name())
                self._raiseError()
            else:
                return MoveFuture.wait(self, timeout=timeout, updates=updates)
    
    def errorMessage(self):
        self._checkError()
        return self._errorMsg



#class SensapexGUI(StageInterface):
    #def __init__(self, dev, win):
        #StageInterface.__init__(self, dev, win)

        ## Insert Sensapex-specific controls into GUI
        #self.zeroBtn = Qt.QPushButton('Zero position')
        #self.layout.addWidget(self.zeroBtn, self.nextRow, 0, 1, 2)
        #self.nextRow += 1

        #self.psGroup = Qt.QGroupBox('Rotary Controller')
        #self.layout.addWidget(self.psGroup, self.nextRow, 0, 1, 2)
        #self.nextRow += 1

        #self.psLayout = Qt.QGridLayout()
        #self.psGroup.setLayout(self.psLayout)
        #self.speedLabel = Qt.QLabel('Speed')
        #self.speedSpin = SpinBox(value=self.dev.userSpeed, suffix='m/turn', siPrefix=True, dec=True, limits=[1e-6, 10e-3])
        #self.psLayout.addWidget(self.speedLabel, 0, 0)
        #self.psLayout.addWidget(self.speedSpin, 0, 1)

        #self.zeroBtn.clicked.connect(self.dev.dev.zeroPosition)
        #self.speedSpin.valueChanged.connect(lambda v: self.dev.setDefaultSpeed(v))

