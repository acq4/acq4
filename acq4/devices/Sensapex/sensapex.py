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
        self._internalTransform = Transform3D(tr)
        self._internalInvTransform = self._internalTransform.inverted()[0]
        
        all_devs = UMP.get_ump().list_devices()
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

    def stop(self):
        """Stop the manipulator immediately.
        """
        with self.lock:
            self.dev.stop()
            if self._lastMove is not None:
                self._lastMove._stopped()
            self._lastMove = None

    def _getPosition(self):
        # Called by superclass when user requests position refresh
        with self.lock:
            # using timeout=0 firces read from cache (the monitor thread ensures
            # these values are up to date)
            pos = self._internalTransform.map(self.dev.get_pos(timeout=0)[:3])
            if self._lastPos is None:
                dif = 1
            else:
                dif = ((np.array(pos) - np.array(self._lastPos))**2).sum()**0.5
            if dif > 0.1e-6:
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
        Sensapex.devices.pop(self.devid)
        if len(Sensapex.devices) == 0:
            UMP.get_ump().poller.stop()
        Stage.quit(self)

    def _move(self, abs, rel, speed, linear):
        with self.lock:
            if self._lastMove is not None and not self._lastMove.isDone():
                self.stop()
            pos = self._toAbsolutePosition(abs, rel)
            speed = self._interpretSpeed(speed)

            self._lastMove = SensapexMoveFuture(self, pos, speed)
            return self._lastMove

    #def deviceInterface(self, win):
        #return SensapexGUI(self, win)


class MonitorThread(Thread):
    """Thread to poll for all Sensapex manipulator position changes.
    """
    def __init__(self):
        self.lock = Mutex(recursive=True)
        self.stopped = False
        Thread.__init__(self)

    def start(self):
        self.stopped = False
        Thread.start(self)

    def stop(self):
        with self.lock:
            self.stopped = True

    def run(self):
        ump = UMP.get_ump()
        devices = Sensapex.devices
        while True:
            try:
                with self.lock:
                    if self.stopped:
                        break
                    
                # read all updates waiting in queue
                devids = ump.recv_all()
                
                if len(devids) == 0:
                    # no packets in queue; just wait for the next one.
                    try:
                        devids = [ump.recv()]
                    except UMPError as err:
                        if err.errno == -3:
                            # ignore timeouts
                            continue
                for devid in devids:
                    dev = devices.get(devid, None)
                    if dev is not None:
                        # received an update packet for this device; ask it to update its position
                        dev._getPosition()
                        
                time.sleep(0.03)  # rate-limit updates to 30 Hz 
            except:
                debug.printExc('Error in Sensapex monitor thread:')
                time.sleep(1)
                

class SensapexMoveFuture(MoveFuture):
    """Provides access to a move-in-progress on a Sensapex manipulator.
    """
    def __init__(self, dev, pos, speed):
        MoveFuture.__init__(self, dev, pos, speed)
        self._interrupted = False
        self._errorMsg = None
        self._finished = False
        #pos = np.array(pos) / np.array(self.dev.scale)
        pos = self.dev._internalInvTransform.map(pos)
        self.dev.dev.goto_pos(pos, speed * 1e6)
        
    def wasInterrupted(self):
        """Return True if the move was interrupted before completing.
        """
        return self._interrupted

    def isDone(self):
        """Return True if the move is complete.
        """
        return self._getStatus() != 0

    def _getStatus(self):
        # check status of move unless we already know it is complete.
        # 0: still moving; 1: finished successfully; -1: finished unsuccessfully
        if self._finished:
            if self._interrupted:
                return -1
            else:
                return 1
        busy = self.dev.dev.is_busy()
        if busy:
            # Still moving
            return 0
        # did we reach target?
        pos = self.dev._getPosition()
        dif = ((np.array(pos) - np.array(self.targetPos))**2).sum()**0.5
        if dif < 2.5e-6:
            # reached target
            self._finished = True
            return 1
        else:
            # missed
            self._finished = True
            self._interrupted = True
            self._errorMsg = "Move did not complete (target=%s, position=%s, dif=%s)." % (self.targetPos, pos, dif)
            return -1

    def _stopped(self):
        # Called when the manipulator is stopped, possibly interrupting this move.
        status = self._getStatus()
        if status == 1:
            # finished; ignore stop
            return
        elif status == -1:
            self._errorMsg = "Move was interrupted before completion."
        elif status == 0:
            # not actually stopped! This should not happen.
            raise RuntimeError("Interrupted move but manipulator is still running!")
        else:
            raise Exception("Unknown status: %s" % status)

    def errorMessage(self):
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

