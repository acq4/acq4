# -*- coding: utf-8 -*-
from __future__ import division, print_function

import threading
import time

from acq4.util import Qt, ptime
import numpy as np
from acq4.util.Mutex import Mutex
import pyqtgraph as pg
from .calibration import CalibrationWindow
from ..Device import Device
from ..OptomechDevice import OptomechDevice
from six.moves import range


class Stage(Device, OptomechDevice):
    """Base class for mechanical stages with motorized control and/or position feedback.

    This is an optomechanical device that modifies its own transform based on position or orientation
    information received from a position control device. The transform is calculated as::

        totalTransform = baseTransform * stageTransform

    where *baseTransform* is defined in the configuration for the device, and *stageTransform* is
    defined by the hardware.
    """

    sigPositionChanged = Qt.Signal(object, object, object)  # self, new position, old position
    sigLimitsChanged = Qt.Signal(object)
    sigSwitchChanged = Qt.Signal(object, object)  # self, {switch_name: value, ...}

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        OptomechDevice.__init__(self, dm, config, name)

        # total device transform will be composed of a base transform (defined in the config)
        # and a dynamic translation provided by the hardware.
        self._baseTransform = self.deviceTransform() * 1  # *1 makes a copy
        self._inverseBaseTransform = None

        self._stageTransform = Qt.QMatrix4x4()
        self._invStageTransform = Qt.QMatrix4x4()

        self.config = config
        self.lock = Mutex(Qt.QMutex.Recursive)

        nAxes = len(self.axes())
        self._lastPos = [0] * nAxes

        # default implementation just uses this matrix to
        # convert from device position to translation vector
        self._axisTransform = None
        self._inverseAxisTransform = None

        self._defaultSpeed = 'fast'
        self.setFastSpeed(config.get('fastSpeed', 1e-3))
        self.setSlowSpeed(config.get('slowSpeed', 10e-6))

        self._limits = [(None, None)] * nAxes

        self._progressDialog = None
        self._progressTimer = Qt.QTimer()
        self._progressTimer.timeout.connect(self.updateProgressDialog)

        calibration = self.readConfigFile('calibration')
        axisTr = calibration.get('transform', None)
        if axisTr is not None:
            self._axisTransform = pg.Transform3D(axisTr)

        # set up joystick callbacks if requested
        jsdevs = set()
        self._jsAxes = set()   # just used to listen for specific events
        self._jsButtons = set()
        if 'joystick' in config:
            for axis, axcfg in config['joystick'].items():
                jsname, jsaxis = axcfg['axis']
                try:
                    js = dm.getDevice(jsname)
                except Exception:
                    print('Joystick device "%s" not found; disabling control from this device.' % jsname)
                    continue
                jsdevs.add(js)
                self._jsAxes.add((js, jsaxis))
                for jsname, button, scale in axcfg.get('modifiers', []):
                    js = dm.getDevice(jsname)
                    self._jsButtons.add((js, button))
        for jsdev in jsdevs:
            jsdev.sigStateChanged.connect(self.joystickChanged)

        dm.declareInterface(name, ['stage'], self)

    def quit(self):
        self.stop()

    def axes(self):
        """Return a tuple of axis names implemented by this device, like ('x', 'y', 'z').

        The axes described in the above data structure correspond to the mechanical
        actuators on the device; they do not necessarily correspond to the axes in the 
        global coordinate system or the local coordinate system of the device.

        This method must be reimplemented by subclasses.
        """
        raise NotImplementedError("Must be implemented in subclass.")

    def capabilities(self):
        """Return a structure describing the capabilities of this device::
        
            {
                'getPos': (x, y, z),      # bool: whether each axis can be read from the device
                'setPos': (x, y, z),      # bool: whether each axis can be set on the device
                'limits': (x, y, z),      # bool: whether limits can be set for each axis
            }
            
        The axes described in the above data structure correspond to the mechanical
        actuators on the device; they do not necessarily correspond to the axes in the 
        global coordinate system or the local coordinate system of the device.

        Subclasses must reimplement this method.
        """
        # todo: add other capability flags like resolution, speed, closed-loop, etc?
        raise NotImplementedError

    def setFastSpeed(self, v):
        """Set the maximum speed of the stage (m/sec) when under programmed control.
        """
        self.fastSpeed = v

    def setSlowSpeed(self, v):
        """Set the slow speed of the stage (m/sec) when under programmed control.

        This speed is used when it is necessary to minimize vibration or maximize movement accuracy.
        """
        self.slowSpeed = v

    def _interpretSpeed(self, speed):
        """Return a speed in m/s where the argument *speed* can be any of
        'fast', 'slow', or a float m/s.
        """
        if speed == 'fast':
            speed = self.fastSpeed
        elif speed == 'slow':
            speed = self.slowSpeed
        return speed

    def stageTransform(self):
        """Return the transform that implements the translation/rotation generated
        by the current hardware state. 
        """
        return pg.SRTTransform3D(self._stageTransform)

    def inverseStageTransform(self):
        if self._inverseStageTransform is None:
            inv, invertible = self.stageTransform().inverted()
            if not invertible:
                raise Exception("Transform is not invertible.")
            self._inverseStageTransform = inv
        return pg.SRTTransform3D(self._inverseStageTransform)

    def _makeStageTransform(self, pos, axisTransform=None):
        """Return a stage transform (as should be returned by stageTransform)
        and an optional inverse, given a position reported by the device.

        If the inverse transform is None, then it will be automatically generated
        on demand by calling transform.inverted().

        Subclasses may override this method; the default uses _axisTransform to 
        map from the device position to a 3D translation matrix. This covers only cases
        where the stage axes perform linear translations. For rotation or nonlinear
        movement, this method must be reimplemented.
        """
        tr = pg.SRTTransform3D()
        if axisTransform is None:
            axisTransform = self.axisTransform()
        offset = pg.Vector(axisTransform.map(pg.Vector(pos)))
        tr.translate(offset)

        inv = pg.SRTTransform3D()
        inv.translate(-offset)

        return tr, inv

    def _solveStageTransform(self, posChange):
        """Given a desired change of local origin, return the device position required.

        The default implementation simply inverts _axisTransform to generate this solution;
        devices with more complex kinematics need to reimplement this method.
        """ 
        tr = self.stageTransform().getTranslation() + pg.Vector(posChange)
        pos = pg.Vector(self.inverseAxisTransform().map(tr))
        return pos

    def axisTransform(self):
        if self._axisTransform is None:
            self._axisTransform = pg.Transform3D()
            self._inverseAxisTransform = pg.Transform3D()
            scale = self.config.get('scale', None)
            if scale is not None:
                self._axisTransform.scale(*scale)
                self._inverseAxisTransform.scale(*[1.0 / x for x in scale])
        return pg.QtGui.QMatrix4x4(self._axisTransform)

    def inverseAxisTransform(self):
        if self._inverseAxisTransform is None:
            inv, invertible = self.axisTransform().inverted()
            if not invertible:
                raise Exception("Transform is not invertible.")
            self._inverseAxisTransform = inv
        return pg.QtGui.QMatrix4x4(self._inverseAxisTransform)

    def _solveAxisTransform(self, stagePos, parentPos, localPos):
        """Return an axis transform matrix that maps localPos to parentPos, given
        stagePos.


        """
        offset = pg.transformCoordinates(self.inverseBaseTransform(), parentPos, transpose=True) - localPos
        m = pg.solve3DTransform(stagePos[:4], offset[:4])[:3]
        return m

    # def mapToStage(self, obj):
    #     return self._mapTransform(obj, self._stageTransform)

    # def mapFromStage(self, obj):
    #     return self._mapTransform(obj, self._invStageTransform)

    def posChanged(self, pos):
        """Handle device position changes by updating the device transform and
        emitting sigPositionChanged.

        Subclasses must call this method when the device position has changed.
        """
        with self.lock:
            lastPos = self._lastPos
            self._lastPos = pos
            self._stageTransform, self._inverseStageTransform = self._makeStageTransform(pos)
            self._updateTransform()

        self.sigPositionChanged.emit(self, pos, lastPos)

    def baseTransform(self):
        """Return the base transform for this Stage.
        """
        return pg.Transform3D(self._baseTransform)

    def inverseBaseTransform(self):
        """Return the inverse of the base transform for this Stage.
        """
        if self._inverseBaseTransform is None:
            inv, invertible = self.baseTransform().inverted()
            if not invertible:
                raise Exception("Transform is not invertible.")
            self._inverseBaseTransform = inv
        return pg.Transform3D(self._inverseBaseTransform)

    def setBaseTransform(self, tr):
        """Set the base transform of the stage. 

        This sets the starting position and orientation of the stage before the 
        hardware-reported stage position is taken into account.
        """
        self._baseTransform = tr * 1  # *1 makes a copy
        self._inverseBaseTransform = None
        self._updateTransform()

    def _updateTransform(self):
        ## this informs rigidly-connected devices that they have moved
        self.setDeviceTransform(self._baseTransform * self._stageTransform)

    def getPosition(self, refresh=False):
        """Return the position of the stage as reported by the controller.

        If refresh==False, the last known position is returned. Otherwise, the
        current position is requested from the controller. If request is True,
        then the position request may block if the device is currently busy.
        """
        if self._lastPos is None:
            refresh = True
        if not refresh:
            with self.lock:
                return self._lastPos[:]
        else:
            return self._getPosition()

    def globalPosition(self):
        """Return the position of the local coordinate system origin relative to 
        the global coordinate system.
        """
        # note: the origin of the local coordinate frame is the center position of the device.
        return self.mapToGlobal([0, 0, 0])

    def _getPosition(self):
        """
        Must be reimplemented by subclass to re-read position from device.
        """
        raise NotImplementedError()

    def targetPosition(self):
        """If the stage is moving, return the target position. Otherwise return 
        the current position.
        """
        raise NotImplementedError()

    def globalTargetPosition(self):
        """Returns the target position mapped to the global coordinate system.

        See targetPosition().
        """
        # imagine what the global transform will look like after we reach the target..
        target = self.targetPosition()
        tr = self.baseTransform() * self._makeStageTransform(target)[0]
        pd = self.parentDevice()
        if pd is not None:
            tr = pd.globalTransform() * tr
        return self._mapTransform([0, 0, 0], tr)

    def getState(self):
        with self.lock:
            return (self._lastPos[:],)

    def deviceInterface(self, win):
        return StageInterface(self, win)

    def setDefaultSpeed(self, speed):
        """Set the default speed of the device when moving.
        
        Generally speeds are specified approximately in m/s, although many 
        devices lack the capability to accurately set speed. This value may 
        also be 'fast' to indicate the device should move as quickly as 
        possible, or 'slow' to indicate the device should minimize vibrations
        while moving.        
        """
        if speed not in ('fast', 'slow'):
            speed = abs(float(speed))
        self._defaultSpeed = speed

    def isMoving(self):
        """Return True if the device is currently moving.
        """
        raise NotImplementedError()        

    def move(self, abs=None, rel=None, globalPos=None, speed=None, progress=False, linear=False, **kwds):
        """Move the device to a new position.
        
        Position may be specified using one of three arguments:

        * *abs* specifies the absolute position in the stage coordinate system (as defined by the device)
        * *rel* specifies a relative step in the stage coordinate system (as defined by the device)
        * *globalPos* specifies the position (in meters) in the global coordinate system

        Optionally, *abs* or *rel* values may be None to indicate no movement along that axis.
        
        If the *speed* argument is given, it temporarily overrides the default
        speed that was defined by the last call to setSpeed().

        If *linear* is True, then the movement is required to be in a straight line. By default,
        this argument is False, which means movement on each axis is conducted independently (the axis
        order depends on hardware).
        
        If *progress* is True, then display a progress bar until the move is complete.

        Return a MoveFuture instance that can be used to monitor the progress 
        of the move.
        """
        if speed is None:
            speed = self._defaultSpeed
        if speed is None:
            raise TypeError("Must specify speed or set default speed before moving.")
        if abs is None and rel is None and globalPos is None:
            raise TypeError("Must specify one of abs, rel, or globalPos arguments.")

        if globalPos is not None:
            localPos = self.mapFromGlobal(globalPos)
            abs = self._solveStageTransform(localPos)

        mfut = self._move(abs, rel, speed, linear=linear, **kwds)

        if progress:
            self._progressDialog = Qt.QProgressDialog("%s moving..." % self.name(), None, 0, 100)
            self._progressDialog.mf = mfut
            self._progressTimer.start(100)

        return mfut
        
    def _move(self, abs, rel, speed, linear, **kwds):
        """Must be reimplemented by subclasses and return a MoveFuture instance.
        """
        raise NotImplementedError()
        
    def moveBy(self, pos, speed, progress=False, linear=False):
        """Move by the specified relative distance. See move() for more 
        information.
        """
        return self.move(rel=pos, speed=speed, progress=progress, linear=linear)

    def moveTo(self, pos, speed, progress=False, linear=False):
        """Move to the specified absolute position. See move() for more 
        information.
        """
        return self.move(abs=pos, speed=speed, progress=progress, linear=linear)

    def moveToGlobal(self, pos, speed, progress=False, linear=False):
        """Move the stage to a position expressed in the global coordinate frame.
        """
        return self.move(globalPos=pos, speed=speed, progress=progress, linear=linear)

    def movePath(self, path):
        """Move the stage along a path with multiple waypoints.

        The format of *path* is a list of dicts, where each dict specifies keyword arguments
        to self.move().
        """
        return MovePathFuture(self, path)

    def _toAbsolutePosition(self, abs, rel):
        """Helper function to convert absolute or relative position (possibly 
        containing Nones) to an absolute position.
        """
        if rel is None:
            if any([x is None for x in abs]):
                pos = self.getPosition()
                for i,x in enumerate(abs):
                    if x is not None:
                        pos[i] = x
            else:
                pos = abs
        else:
            pos = self.getPosition()
            for i,x in enumerate(rel):
                if x is not None:
                    pos[i] += x
        return pos

    def setVelocity(self, vel):
        """Begin moving the stage with a constant velocity.
        """
        # pick a far-away distance within limits
        print(vel)

    def stop(self):
        """Stop moving the device immediately.
        """
        raise NotImplementedError()

    def updateProgressDialog(self):
        done = int(self._progressDialog.mf.percentDone())
        self._progressDialog.setValue(done)
        if done == 100:
            self._progressTimer.stop()

    def setLimits(self, x=None, y=None, z=None):
        """Set the (min, max) position limits to enforce for each axis.

        Accepts keyword arguments 'x', 'y', 'z'; each supplied argument must be
        a (min, max) tuple where either value may be None to disable the limit.

        Note that some devices do not support limits.
        """
        changed = []
        for axis, limit in enumerate((x, y, z)):
            if limit is None:
                continue
            assert len(limit) == 2
            if self.capabilities()['limits'][axis] is not True:
                raise TypeError("Device does not support settings limits for axis %d." % axis)
            if tuple(self._limits[axis]) != tuple(limit):
                changed.append(axis)
                self._limits[axis] = tuple(limit)

        if len(changed) > 0:
            self.sigLimitsChanged.emit(changed)

    def getLimits(self):
        """Return a list the (min, max) position limits for each axis.
        """
        return self._limits[:]

    def homePosition(self):
        """Return the stored home position of this stage in global coordinates.
        """
        return self.readConfigFile('stored_locations').get('home', None)

    def goHome(self, speed='fast'):
        homePos = self.homePosition()
        if homePos is None:
            raise Exception("No home position set for %s" % self.name())
        return self.moveToGlobal(homePos, speed=speed)

    def setHomePosition(self, pos=None):
        """Set the home position in global coordinates.
        """
        if pos is None:
            pos = self.globalPosition()
        locations = self.readConfigFile('stored_locations')
        locations['home'] = list(pos)
        self.writeConfigFile(locations, 'stored_locations')

    def joystickChanged(self, js, event):
        if 'axis' in event:
            ax = event['axis']
            if (js, ax) not in self._jsAxes:
                return
        else:
            btn = event['button']
            if (js, btn) not in self._jsButtons:
                return

        # calculate new velocity
        jsStates = {}
        vel = [None, None, None]
        for axis, axcfg in self.config['joystick'].items():
            axis = int(axis)
            jsname, jsaxis = axcfg['axis']
            state = jsStates.setdefault(jsname, self.dm.getDevice(jsname).state())
            vel[axis] = axcfg['speed'] * state['axes'][jsaxis]
            for jsname, button, scale in axcfg.get('modifiers', []):
                state = jsStates.setdefault(jsname, self.dm.getDevice(jsname).state())
                if state['buttons'][button]:
                    vel[axis] *= scale

        self.setVelocity(vel)


class MoveFuture(object):
    """Used to track the progress of a requested move operation.
    """
    class Timeout(Exception):
        """Raised by wait() if the timeout period elapses.
        """

    def __init__(self, dev, pos, speed):
        self.startTime = pg.ptime.time()
        self.dev = dev
        self.speed = speed
        self.targetPos = pos
        self.startPos = dev.getPosition()
        self._wasStopped = False

    def percentDone(self):
        """Return the percent of the move that has completed.
        
        The default implementation calls getPosition on the device to determine
        the percent complete. Devices that do not provide position updates while 
        moving should reimplement this method.
        """
        if self.isDone():
            return 100
        s = np.array(self.startPos)
        t = np.array(self.targetPos)
        p = np.array(self.dev.getPosition())
        d1 = ((p - s)**2).sum()**0.5
        d2 = ((t - s)**2).sum()**0.5
        if d2 == 0:
            return 100
        return 100 * d1 / d2

    def stop(self):
        """Stop the move in progress.
        """
        if not self.isDone():
            self.dev.stop()
            self._wasStopped = True

    def wasInterrupted(self):
        """Return True if the move was interrupted before completing.
        """
        raise NotImplementedError()

    def isDone(self):
        """Return True if the move has completed or was interrupted.
        """
        return self.percentDone() == 100 or self.wasInterrupted()

    def errorMessage(self):
        """Return a string description of the reason for a move failure,
        or None if there was no failure (or if the reason is unknown).
        """
        return None
        
    def wait(self, timeout=None, updates=False):
        """Block until the move has completed, has been interrupted, or the
        specified timeout has elapsed.

        If *updates* is True, process Qt events while waiting.

        If the move did not complete, raise an exception.
        """
        start = ptime.time()
        while True:
            if self.isDone():
                break
            if updates is True:
                Qt.QTest.qWait(100)
            else:
                time.sleep(0.1)
            if (timeout is not None) and (ptime.time() > start + timeout):
                raise self.Timeout("Timed out waiting for move to complete.")

        self._raiseError()
    
    def _raiseError(self):
        """Raise an exception if the move did not complete, otherwise just return.
        """
        err = self.errorMessage()
        if err is not None:
            raise RuntimeError("Move did not complete: %s" % err)
        elif self.wasInterrupted():
            raise RuntimeError("Move did not complete.")


class MovePathFuture(MoveFuture):
    def __init__(self, dev, path):
        MoveFuture.__init__(self, dev, None, None)

        self.path = path
        self._currentFuture = None
        self._done = False
        self._wasInterrupted = False
        self._errorMessage = None
        self._stopped = False

        self._moveThread = threading.Thread(target=self._movePath)
        self._moveThread.start()

    def percentDone(self):
        fut = self._currentFuture
        if fut is None:
            return 0.0
        pd = (100 * fut._pathStep + fut.percentDone()) / len(self.path)
        return pd

    def isDone(self):
        return self._done

    def wasInterrupted(self):
        return self._wasInterrupted

    def errorMessage(self):
        return self._errorMessage

    def stop(self):
        fut = self._currentFuture
        if fut is not None:
            fut.stop()
        self._stopped = True

    def _movePath(self):
        try:
            for i, step in enumerate(self.path):
                print("Move path step %d    %r" % (i, step))
                fut = self.dev.move(**step)
                fut._pathStep = i
                self._currentFuture = fut
                while not fut.isDone():
                    try:
                        fut.wait(timeout=0.1)
                    except fut.Timeout:
                        pass
                    if self._stopped:
                        fut.stop()
                        break
                
                if self._stopped:
                    self._errorMessage = "Move was cancelled"
                    self._wasInterrupted = True
                    break

                if fut.wasInterrupted():
                    self._errorMessage = "Path step %d/%d: %s" % (i+1, len(self.path), fut.errorMessage())
                    self._wasInterrupted = True
                    break
        except Exception as exc:
            self._errorMessage = "Error in path move thread: %s" % exc
            self._wasInterrupted = True
        finally:
            self._done = True


class StageInterface(Qt.QWidget):
    def __init__(self, dev, win):
        Qt.QWidget.__init__(self)
        self.win = win
        self.dev = dev

        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)
        self.axCtrls = {}
        self.posLabels = {}
        self.limitChecks = {}

        self.positionLabelWidget = Qt.QWidget()
        self.layout.addWidget(self.positionLabelWidget, 0, 0)
        self.positionLabelLayout = Qt.QGridLayout()
        self.positionLabelWidget.setLayout(self.positionLabelLayout)
        self.positionLabelLayout.setContentsMargins(0, 0, 0, 0)

        self.globalLabel = Qt.QLabel('global')
        self.positionLabelLayout.addWidget(self.globalLabel, 0, 1)
        self.stageLabel = Qt.QLabel('stage')
        self.positionLabelLayout.addWidget(self.stageLabel, 0, 2)

        cap = dev.capabilities()
        for axis, axisName in enumerate(self.dev.axes()):
            if cap['getPos'][axis]:
                axLabel = Qt.QLabel(axisName)
                axLabel.setMaximumWidth(15)
                globalPosLabel = Qt.QLabel('0')
                stagePosLabel = Qt.QLabel('0')
                self.posLabels[axis] = (globalPosLabel, stagePosLabel)
                widgets = [axLabel, globalPosLabel, stagePosLabel]
                if cap['limits'][axis]:
                    minCheck = Qt.QCheckBox('Min:')
                    minCheck.tag = (axis, 0)
                    maxCheck = Qt.QCheckBox('Max:')
                    maxCheck.tag = (axis, 1)
                    self.limitChecks[axis] = (minCheck, maxCheck)
                    widgets.extend([minCheck, maxCheck])
                    for check in (minCheck, maxCheck):
                        check.clicked.connect(self.limitCheckClicked)

                nextRow = self.positionLabelLayout.rowCount()
                for i,w in enumerate(widgets):
                    self.positionLabelLayout.addWidget(w, nextRow, i)
                self.axCtrls[axis] = widgets

        self.btnContainer = Qt.QWidget()
        self.btnLayout = Qt.QGridLayout()
        self.btnContainer.setLayout(self.btnLayout)
        self.layout.addWidget(self.btnContainer, self.layout.rowCount(), 0)
        self.btnLayout.setContentsMargins(0, 0, 0, 0)

        self.goHomeBtn = Qt.QPushButton('Home')
        self.btnLayout.addWidget(self.goHomeBtn, 0, 0)
        self.goHomeBtn.clicked.connect(self.goHomeClicked)

        self.setHomeBtn = Qt.QPushButton('Set Home')
        self.btnLayout.addWidget(self.setHomeBtn, 0, 1)
        self.setHomeBtn.clicked.connect(self.setHomeClicked)

        self.calibrateBtn = Qt.QPushButton('Calibrate')
        self.btnLayout.addWidget(self.calibrateBtn, 0, 2)
        self.calibrateBtn.clicked.connect(self.calibrateClicked)

        self.calibrateWindow = None

        self.updateLimits()
        self.dev.sigPositionChanged.connect(self.update)
        self.dev.sigLimitsChanged.connect(self.updateLimits)
        self.update()

    def update(self):
        globalPos = self.dev.globalPosition()
        stagePos = self.dev.getPosition()
        for i in self.posLabels:
            text = pg.siFormat(globalPos[i], suffix='m', precision=5)
            self.posLabels[i][0].setText(text)
            self.posLabels[i][1].setText(str(stagePos[i]))

    def updateLimits(self):
        limits = self.dev.getLimits()
        cap = self.dev.capabilities()
        for axis in range(len(cap['limits'])):
            if not cap['limits'][axis]:
                continue
            for i,limit in enumerate(limits[axis]):
                check = self.limitChecks[axis][i]
                pfx = ('Min:', 'Max:')[i]
                if limit is None:
                    check.setText(pfx)
                    check.setChecked(False)
                else:
                    check.setText(pfx + ' %s' % pg.siFormat(limit, suffix='m'))
                    check.setChecked(True)

    def limitCheckClicked(self, b):
        check = self.sender()
        axis, minmax = check.tag
        limit = list(self.dev.getLimits()[axis])
        if b:
            limit[minmax] = self.dev.getPosition()[axis]
        else:
            limit[minmax] = None
        self.dev.setLimits(**{self.dev.axes()[axis]: tuple(limit)})

    def goHomeClicked(self):
        self.dev.goHome()

    def setHomeClicked(self):
        self.dev.setHomePosition()

    def calibrateClicked(self):
        if self.calibrateWindow is None:
            self.calibrateWindow = CalibrationWindow(self.dev)
        self.calibrateWindow.show()
        self.calibrateWindow.raise_()


class StageHold(object):
    def __init__(self, stage):
        self.stage = stage

    def __enter__(self):
        self.stage.setHolding(True)
        return self

    def __exit__(self, *args):
        self.stage.setHolding(False)
