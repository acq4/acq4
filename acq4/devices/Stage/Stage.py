from __future__ import annotations

import contextlib
import functools
import threading
from typing import Tuple, List

import numpy as np

import pyqtgraph as pg
from acq4.util import Qt, ptime
from acq4.util.Mutex import Mutex
from coorx import AffineTransform, TTransform
from pyqtgraph import siFormat
from .calibration import ManipulatorAxesCalibrationWindow, StageAxesCalibrationWindow
from ...panic import GlobalHaltException
from ..ControlSurface import UnsupportedControlFeature, acquireControlFromConfig
from ..Device import Device
from ..OptomechDevice import OptomechDevice
from ...modules.Visualize3D.travelers_proxy import MovePathException
from ...motion import MoveSpec
from ...util.HelpfulException import HelpfulException
from ...util.geometry import (
    Plane,
    limits_to_boundaries,
    load_transform,
    minimum_displacement_inverse_kinematics,
)
from ...util.task import ManualQtFriendlyTask, Stopped, FutureButton, throughline


class OutOfLimitsError(ValueError):
    """A position lies outside a device's configured limits.

    Distinct from the other ``ValueError`` types raised along the position-mapping path --
    a missing ``previousPos`` for a 4-axis inverse mapping, a degenerate axis transform,
    an inverse-kinematics solution that fails its own check -- so that code probing
    whether a position is in range can catch *this* and let the faults through. Those
    faults say nothing about where the limits are, and swallowing them turns a bug into
    a confident wrong answer about the device's range of motion.

    Subclasses ``ValueError``, which is what this has always been raised as, so existing
    handlers keep working.
    """


class Stage(Device, OptomechDevice):
    """Base class for mechanical stages with motorized control and/or position feedback.

    Typically this device class is not used directly; instead use a subclass specific to
    the hardware in use.

    This is an optomechanical device that modifies its own transform based on position or orientation
    information received from a position control device. The transform is calculated as::

        totalTransform = baseTransform * stageTransform

    where *baseTransform* is defined in the configuration for the device, and *stageTransform* is
    defined by the hardware.

    Units and coordinate systems
    ----------------------------

    Three coordinate systems meet in this class, and a number here is only meaningful
    once you know which one it belongs to.

    *Global* (and local) coordinates are three-dimensional and always in **metres**.
    Everything named ``global`` lives here -- :meth:`globalPosition`,
    :meth:`moveToGlobalNoPlanning`, the positions a motion plan carries -- as do
    :attr:`fastSpeed`, :attr:`slowSpeed`, :attr:`hysteresisCorrection` and the ``step``
    of a ``controls:`` dial.

    *Device* coordinates have one value per mechanical axis (:meth:`axes`) in whatever
    units :meth:`_getPosition` reports -- µm for Sensapex and Scientifica, mm for Dover.
    The config's ``scale`` is the size of one device unit in metres
    (:meth:`getAxisScale`), and :meth:`axisTransform` is what applies it. Device
    coordinates are what :meth:`getPosition` returns and what :meth:`move`,
    :meth:`checkMove`, :meth:`_move`, :meth:`setLimits`/:meth:`getLimits`,
    :meth:`checkLimits` and ``MoveFuture.startPos``/``targetPos`` all speak. "Device
    units" means the units the subclass reports, not the ones on the vendor's
    datasheet: a subclass is free to scale inside its own driver layer, as
    ``SutterMPC200`` does -- it reports metres and leaves ``scale`` at 1.

    *Speed* is in **m/s** throughout this class, never device units per second.
    :meth:`move` also accepts ``'fast'``/``'slow'`` and hands *speed* to :meth:`_move`
    exactly as it was given, so each subclass's ``_move`` is what calls
    :meth:`_interpretSpeed` and then converts the resulting m/s into whatever its
    driver wants (``* 1e6`` for µm/s, ``* 1e3`` for mm/s).

    So a move mixes units by design: a position in device units beside a speed in m/s.
    Anything that compares the two -- a minimum duration, an estimated move time, a
    distance-dependent speed limit -- has to convert first, by multiplying the
    device-coordinate distance by :meth:`getAxisScale`. Subtracting two positions and
    dividing by a speed silently gives an answer wrong by the scale factor: a million
    for Sensapex, a thousand for Dover.

    *Acceleration* is not part of this API; no method here takes one. Where a driver
    supports it, it is configured per device in that driver's own units
    (``Sensapex.maxAcceleration`` is µm/s², ``DoverStage.defaultAcceleration`` is
    mm/s²).

    Additional config options::

        isManipulator : bool
            Default False. Whether this mechanical device is to be used as an e.g. pipette manipulator, rather than
            as a microscope stage.
        fastSpeed : float
            Speed (m/s) to use when a movement is requested with speed='fast'
        slowSpeed : float
            Speed (m/s) to use when a movement is requested with speed='slow'
        hysteresisCorrection : float
            Distance (m) to overshoot when approaching a position to correct for hysteresis.
            Default is 20e-6 (20 µm). Set to 0 to disable the correction step entirely.
        controls : dict
            Physical controls on a :class:`~acq4.devices.ControlSurface.ControlSurface`
            (a Stream Dock, an X-Keys pad) to bind to this stage. The block is a dict of
            *named actions*; each value is a control address as understood by
            :func:`~acq4.devices.ControlSurface.acquireControlFromConfig`, plus any
            options the action itself takes.

            The base class claims the device's own axis names (see :meth:`axes`): each is
            bound to one **relative** dial, whose rotation moves that axis by
            ``delta * step`` metres of real travel. Where the dial can draw text -- a
            Stream Dock knob strip can, an X-Keys jog wheel has no pixels at all -- its
            face also shows the axis name and live position, both as lengths; where it
            cannot, the axis still moves and the missing indicator is reported once.
            Pressing the dial is reserved for future use. A dial reporting
            ``mode: 'absolute'`` is rejected -- mapping an absolute axis onto a position
            is the velocity/jog question, which is not implemented. Subclasses add their
            own names (``DoverStage`` adds ``enableX``/``enableY``/``enableZ``); see
            :meth:`controlNames`.

            Per-axis options:

            step : float
                Required. Distance (m) to move per dial detent, in the *global*
                coordinate system rather than in the device's own units: one positive
                detent moves the axis ``+step`` metres along the global direction that
                axis points in, whatever the sign and magnitude of the device ``scale``.
                :meth:`move` takes device coordinates, so the value is divided by the
                axis scale (:meth:`getAxisScale`) on the way there; on an axis whose
                scale is negative a positive detent therefore *decreases* the raw
                device coordinate, which is exactly what keeps the knob turning the
                same way on every axis of every stage. (If a rig ever wants one knob
                turning the other way, that is a future per-axis ``invert:`` option,
                not a change to this rule.)
            speed : float or str
                Optional. Speed for the dial-driven move, as accepted by :meth:`move`.
                Defaults to this stage's default speed.

    The surface device must be declared *before* the stage in ``devices.cfg``, matching
    the existing ``parentDevice:`` convention.

    Example configuration::

        Manipulator1:
            driver: 'Sensapex'
            deviceId: 1
            controls:
                x: {'device': 'Dock', 'type': 'dial', 'page': 0, 'key': [0, 0], 'step': 5*um}
                y: {'device': 'Dock', 'type': 'dial', 'page': 0, 'key': [0, 1], 'step': 5*um}
                z: {'device': 'Dock', 'type': 'dial', 'page': 0, 'key': [0, 2], 'step': 5*um}
    """

    sigPositionChanged = Qt.Signal(object, object, object)  # self, new position, old position
    sigOrientationChanged = Qt.Signal(object)  # self
    sigLimitsChanged = Qt.Signal(object)
    sigSwitchChanged = Qt.Signal(object, object)  # self, {switch_name: value, ...}

    #: Minimum seconds between repaints of a dial bound through the ``controls:`` config
    #: block. Position updates arrive far faster than a knob face needs redrawing (~10 Hz
    #: on Sensapex), and each repaint costs a render plus a hardware write.
    axisControlPaintInterval = 0.25

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        OptomechDevice.__init__(self, dm, config, name)

        self._lastMove = None
        # total device transform will be composed of a base transform (defined in the config)
        # and a dynamic translation provided by the hardware.
        m = self._baseTransform = self.deviceTransform()
        angle, axis = m.rotation
        scale = m.scale
        if tuple(scale) != (1, 1, 1) or angle != 0:
            raise ValueError("Stage transform must be only translation.")

        self._stageTransform = AffineTransform(dims=(3, 3))
        self.isManipulator = config.get("isManipulator", False)

        self.lock = Mutex(Qt.QMutex.Recursive)

        self.nAxes = len(self.axes())
        self._lastPos = [0] * self.nAxes

        # default implementation just uses this matrix to
        # convert from device position to translation vector
        self._axisTransform = None
        self._calculatedXAxisOrientation = None

        self._defaultSpeed = 'fast'
        self.setFastSpeed(config.get('fastSpeed', 1e-3))
        self.setSlowSpeed(config.get('slowSpeed', 10e-6))
        self.hysteresisCorrection = config.get('hysteresisCorrection', 20e-6)

        self._limits = [(None, None)] * self.nAxes
        if 'limits' in config:
            self.setLimits(**config['limits'])

        self._progressDialog = None
        self._progressTimer = Qt.QTimer()
        self._progressTimer.timeout.connect(self.updateProgressDialog)

        calibration = self.readConfigFile('calibration')
        axis_tr = calibration.get('transform', None)
        if axis_tr is not None:
            self._axisTransform = load_transform(axis_tr)

        # set up joystick callbacks if requested
        jsdevs = set()
        self._jsAxes = set()  # just used to listen for specific events
        self._jsButtons = set()
        if 'joystick' in config:
            for axis, axcfg in config['joystick'].items():
                jsname, jsaxis = axcfg['axis']
                try:
                    js = dm.getDevice(jsname)
                except Exception:
                    print(
                        f'Joystick device "{jsname}" not found; disabling control from this device.'
                    )
                    continue
                jsdevs.add(js)
                self._jsAxes.add((js, jsaxis))
                for jsname, button, scale in axcfg.get('modifiers', []):
                    js = dm.getDevice(jsname)
                    self._jsButtons.add((js, button))
        for jsdev in jsdevs:
            jsdev.sigStateChanged.connect(self.joystickChanged)
        dm.globalHalt.add_abort_callback(self.abortForHalt, name=f"{name}.abort")
        dm.declareInterface(name, ['stage'], self)

        # control-surface bindings from the config's `controls:` block
        self._boundControls = {}  # config name -> Control
        self._axisControls = {}  # axis index -> binding dict
        self._axisControlByControl = {}  # Control -> binding dict
        self._axisControlTargetPos = None  # dial target, in device coordinates
        self._axisControlMove = None  # MoveFuture returned by the last dial-driven move
        self._axisControlMoveStarting = False  # guard while our own move() is running
        self._axisControlLastPaint = 0.0
        self._axisControlPaintPending = False
        self._axisControlPaintTimer = Qt.QTimer(self)
        self._axisControlPaintTimer.setSingleShot(True)
        self._axisControlPaintTimer.timeout.connect(self._axisControlPaintTimeout)
        self._setupControls(config)

    def abort(self):
        """Stop motion immediately.

        Subclasses that have a faster or lock-free way to stop -- one that does
        not wait for whoever is currently talking to the driver -- override this.
        Several already do (MockStage, MicroManagerStage, Scientifica), and their
        own ``stop()`` calls it, so this method means "hard stop" and nothing
        more; the Panic Lock callback is ``abortForHalt()``, which is what
        __init__ registers.
        """
        self.stop(reason="Received abort request from Manager")

    def abortForHalt(self):
        """The Panic Lock abort callback for every stage ("Panic Lock Spec.md" §5.2).

        §5.2 requires two things of a stage on halt: stop it, and fail any
        in-flight ``MoveFuture`` with ``GlobalHaltException``. Both are Allowed
        under §6.1 (``stop()``, and "Failing an in-flight MoveFuture"), so this
        cannot trip a guard and the §6.3 contract holds.

        Failing the move matters as much as stopping it. ``GlobalHaltException``
        deliberately does not subclass ``Stopped`` (§7) so that a halt propagates
        *past* handlers written for routine cancellation (§7.1). If the move
        future completed with a plain ``Stopped``, every ``except Stopped:`` site
        would read a panic as an ordinary cancellation and carry on.

        Order: fail first, then stop the hardware. ``MoveFuture`` is an
        externally-completed ``ManualQtFriendlyTask`` whose producer is the
        driver's monitor thread, so completion is a race between us and the
        driver. ``ManualTask._finish`` settles it -- it records result/exception
        and marks done together under one lock, so the first completer wins and
        every later one is a silent no-op. That makes both directions safe (we
        cannot fail an already-completed future; the driver cannot resolve after
        our fail), but only *this* order makes the outcome deterministic:
        stopping the hardware first wakes the producer, which would complete the
        future with its own ``Stopped``/``RuntimeError`` and win the race, and
        the caller would see a routine cancellation or a phantom hardware fault
        instead of the halt. ``MoveFuture.stop()`` orders itself the same way and
        for the same reason.

        Only ``self._lastMove`` is failed, which is always a single-step future --
        ``Stage.move()`` sets it, ``movePath()`` does not. A ``MovePathFuture``
        inherits the failure through its running step: its producer re-raises the
        step's exception, and ``_movePath`` passes a ``GlobalHaltException``
        through unwrapped (§7.1).
        """
        mfut = self._lastMove
        if mfut is not None and not mfut.is_done:
            mfut.fail(GlobalHaltException(
                f"{self.name()} move aborted; rig is halted: {self.dm.globalHalt.reason}"
            ))
        self.abort()

    def quit(self):
        self._releaseControls()
        self.dm.globalHalt.remove_abort_callback(self.abortForHalt)
        self.stop()

    def axes(self) -> Tuple[str]:
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
                'getPos': (axes...),      # bool: whether each axis can be read from the device
                'setPos': (axes...),      # bool: whether each axis can be set on the device
                'limits': (axes...),      # bool: whether limits can be set for each axis
            }

        The axes described in the above data structure correspond to the mechanical
        actuators on the device; they do not necessarily correspond to the axes in the
        global coordinate system or the local coordinate system of the device.

        Subclasses must reimplement this method. Only nAxes values are required.
        """
        # todo: add other capability flags like resolution, speed, closed-loop, etc?
        raise NotImplementedError

    def setFastSpeed(self, v):
        """Set the maximum speed of the stage (m/sec) when under programmed control."""
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
        return self._stageTransform

    def inverseStageTransform(self):
        return self.stageTransform().inverse

    def _makeStageTransform(self, pos, axisTransform=None):
        """Return a stage transform (as should be returned by stageTransform)
        given a position reported by the device.

        Subclasses may override this method; the default uses _axisTransform to
        map from the device position to a translation matrix. This covers only cases
        where the stage axes perform linear translations. For rotation or nonlinear
        movement, this method must be reimplemented.
        """
        if axisTransform is None:
            axisTransform = self.axisTransform()
        offset = axisTransform.map(pos)[:3]
        return TTransform(offset=offset, dims=(3, 3))

    def axisTransform(self) -> AffineTransform:
        """Transformation matrix with columns that point in the direction that each manipulator axis moves.

        This transform gives the relationship between the coordinates reported by the device and real world coordinates.
        It assumes a linear stage, where the axes are not necessarily orthogonal to each other.

        This matrix is usually derived from calibration points. Before calibration, it provides only scale
        factors.
        """
        if self._axisTransform is None:
            scale = self.getAxisScale()
            matrix = np.eye(self.nAxes) * scale
            # make sure it maps to 3D regardless of input
            matrix = matrix[:3]
            self._axisTransform = AffineTransform(matrix=matrix)
        return self._axisTransform

    def setAxisTransform(self, tr):
        self._axisTransform = tr
        self._calculatedXAxisOrientation = None
        self._updateTransform()
        self.calculatedAxisOrientation.cache_clear()
        self.sigOrientationChanged.emit(self)

    def getAxisScale(self):
        """Return the size of one device unit, in metres, for each axis.

        This is the config's ``scale``: multiply a device-coordinate distance by it to
        get metres (1e-6 for a stage reporting µm, 1e-3 for one reporting mm). Values
        may be negative where a device axis points along a negative global direction.
        """
        return np.asarray(list(self.config.get('scale', [1] * self.nAxes)))

    @functools.lru_cache
    def calculatedAxisOrientation(self, axis: str):
        """Return the pitch and yaw of a stage axis.

        The pitch is returned in degrees relative to global horizontal (positive values point downward),
        whereas the yaw is returned in degrees around the global Z axis relative to the global +X direction.

        The *axis* argument specifies which axis to return, one of '+x', '-x', '+y', '-y', '+z', or '-z'.
        """
        assert axis in {'+x', '-x', '+y', '-y', '+z', '-z', '+d', '-d'}
        m = self.axisTransform().full_matrix
        axis_index = {'x': 0, 'y': 1, 'z': 2, 'd': 3}[axis[1]]
        axis_sign = 1 if axis[0] == '+' else -1
        selected_axis = pg.Vector(axis_sign * m[:3, axis_index])
        globalz = pg.Vector([0, 0, 1])
        pitch = selected_axis.angle(globalz) - 90
        yaw = np.arctan2(selected_axis[1], selected_axis[0]) * 180 / np.pi
        return {'pitch': pitch, 'yaw': yaw}

    def inverseAxisTransform(self):
        if self.nAxes > 3:
            raise ValueError("Transform is not invertible.")
        return self.axisTransform().inverse

    def posChanged(self, pos):
        """Handle device position changes by updating the device transform and
        emitting sigPositionChanged.

        Subclasses must call this method when the device position has changed.
        """
        with self.lock:
            lastPos = self._lastPos
            self._lastPos = pos
            self._stageTransform = self._makeStageTransform(pos)
            self._updateTransform()

        self.sigPositionChanged.emit(self, pos, lastPos)

    def baseTransform(self):
        """Return the base transform for this Stage."""
        return self._baseTransform

    def inverseBaseTransform(self):
        """Return the inverse of the base transform for this Stage."""
        return self._baseTransform.inverse

    def setBaseTransform(self, tr):
        """Set the base transform of the stage.

        This sets the starting position and orientation of the stage before the
        hardware-reported stage position is taken into account.
        """
        self._baseTransform = tr
        self._updateTransform()

    def _updateTransform(self):
        ## this informs rigidly-connected devices that they have moved
        self.setDeviceTransform(self._baseTransform * self._stageTransform)

    @property
    def positionUpdatesPerSecond(self):
        """Return the rate at which the device reports position updates."""
        raise NotImplementedError()

    def getPosition(self, refresh=False):
        """Return the position of the stage as reported by the controller.

        The position is in device coordinates -- one value per axis in :meth:`axes`, in
        the controller's own units. Multiply by :meth:`getAxisScale` for metres, or use
        :meth:`globalPosition`.

        If refresh==False, the last known position is returned. Otherwise, the
        current position is requested from the controller. If refresh is True,
        then the position request may block if the device is currently busy.
        """
        if self._lastPos is None or refresh:
            return self._getPosition()
        with self.lock:
            return self._lastPos[:]

    def globalPosition(self):
        """Return the position of the local coordinate system origin relative to
        the global coordinate system.
        """
        # note: the origin of the local coordinate frame is the center position of the device.
        return self.mapToGlobal(np.array([0, 0, 0]))

    def _getPosition(self):
        """
        Must be reimplemented by subclass to re-read position from device.

        Returns one value per axis in the controller's own units. Whatever those units
        are, they are what the rest of this class means by "device coordinates", and
        the config's ``scale`` must give their size in metres.
        """
        raise NotImplementedError()

    def targetPosition(self):
        """Return the target position of the last move command."""
        if self.isMoving():
            return self._lastMove.targetPos
        else:
            return self.getPosition()

    def globalTargetPosition(self):
        """Returns the target position mapped to the global coordinate system.

        See targetPosition().
        """
        # imagine what the global transform will look like after we reach the target..
        target = self.targetPosition()
        if target is None:
            return None
        tr = self.baseTransform() * self._makeStageTransform(target)
        pd = self.parentDevice()
        if pd is not None:
            tr = pd.globalTransform() * tr
        return tr.map([0, 0, 0])

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
        return self._lastMove is not None and not self._lastMove.is_done

    def move(self, position, speed=None, progress=False, linear=False, **kwds) -> MoveFuture:
        """Move the device to a new position.

        *position* specifies the absolute position in device coordinates: one value per
        axis in :meth:`axes`, in the units :meth:`getPosition` reports (see "Units and
        coordinate systems" in the class docstring). To move to a point in the global
        frame, call :meth:`moveToGlobalNoPlanning`, which converts and then calls this.

        Optionally, *position* values may be None to indicate no movement along that axis.

        If the *speed* argument is given, it temporarily overrides the default
        speed that was defined by the last call to setSpeed(). It is a speed in m/s, or
        one of 'fast'/'slow' to use the configured ``fastSpeed``/``slowSpeed``. Note
        that the argument reaches :meth:`_move` unresolved; interpreting it is the
        subclass's job.

        If *linear* is True, then the movement is required to be in a straight line. By default,
        this argument is False, which means movement on each axis is conducted independently (the axis
        order depends on hardware).

        If *progress* is True, then display a progress bar until the move is complete.

        Return a MoveFuture instance that can be used to monitor the progress
        of the move.
        """
        self.dm.globalHalt.check()
        if speed is None:
            speed = self._defaultSpeed
        self.checkMove(position, speed=speed, progress=progress, linear=linear, **kwds)

        mfut = self._move(position, speed=speed, linear=linear, **kwds)
        self._lastMove = mfut

        if progress:
            self._progressDialog = Qt.QProgressDialog(f"{self.name()} moving...", None, 0, 100)
            self._progressDialog.mf = mfut
            self._progressTimer.start(100)

        return mfut

    def step(self, deltas: Tuple[float, ...], speed: str | float, name: str | None = None) -> MoveFuture:
        """Step method to move device by specified deltas along device axes.

        Args:
            deltas: Tuple of deltas for each device axis in global scale (SI units).
                   These represent movements along the device's internal axes,
                   accounting for axis orientations and scales.
            speed: Movement speed (string like 'fast'/'slow' or float in m/s)

        Returns:
            MoveFuture for tracking the movement

        Note:
            This method handles non-orthogonal axis orientations by mapping deltas
            through the axis transform to get the equivalent change in ortholinear
            device coordinates, which are then added to the current position.
        """
        # TODO this should use calculatedAxisOrientation and its ilk, or maybe go away
        # TODO hardware-specific implementations?
        # TODO throw this away
        pos = np.array(self.getPosition())
        axis_xform = self.axisTransform()

        # Map deltas through axis transform to get ortholinear coordinate changes
        ortho = np.array(axis_xform.map(deltas)) - np.array(axis_xform.map(np.zeros(len(deltas))))

        # Divide away the scale; we only wanted the orientation
        ortho /= self.getAxisScale()

        # Add changes to current position
        target = pos + ortho

        # Map it to a global position
        target_global = self.inverseBaseTransform().map(target)

        # Perform the move
        return self.move(target_global, speed=speed, name=name)

    def checkMove(self, position, speed=None, progress=None, linear=None, **kwds):
        """Raise an exception if arguments are invalid for move().

        *position* is in device coordinates and *speed* in m/s (or 'fast'/'slow'), the
        same as :meth:`move`; the limits *position* is checked against are in device
        coordinates too.
        """
        assert position is not None
        speed = speed or self._defaultSpeed
        speed = self._interpretSpeed(speed)
        if speed is None:
            raise ValueError("Must specify speed or set default speed before moving.")
        if speed <= 0:
            raise ValueError("Speed must be greater than 0")
        if len(self.axes()) != len(position):
            raise ValueError(f"Position {position} should have length {len(self.axes())}")
        self.checkLimits(position)

    def _move(self, pos, speed, linear, name=None, **kwds) -> MoveFuture:
        """Must be reimplemented by subclasses and return a MoveFuture instance.

        *pos* is an absolute position in device coordinates (the units
        :meth:`_getPosition` returns), already checked against the configured limits.

        *speed* arrives exactly as the caller gave it -- a float in m/s, or the string
        'fast'/'slow'. The subclass resolves it with :meth:`_interpretSpeed`, which
        returns m/s, and converts that into its driver's units itself. Do not assume a
        float here is already in m/s without calling :meth:`_interpretSpeed`, and do
        not hand m/s to a driver that wants µm/s or mm/s.

        *linear* asks for a straight-line path rather than per-axis motion in whatever
        order the hardware prefers.
        """
        raise NotImplementedError()

    def mapGlobalToDevicePosition(self, globalPos, previousPos=None):
        """Given a desired global position, return the device position required.
        Arguments:
            globalPos: 3-element array-like specifying the desired position in global coordinates
            previousPos: Optional n-element array-like specifying the previous position of the device in device
                coordinates. This is required for inverse kinematics calculations for 4-axis stages.
        """

        if self.nAxes > 3 and previousPos is None:
            raise ValueError(
                "Inverse mapping on 4-axis stages requires a previousPos"
            )
        if self.nAxes <= 3:
            # we can use a simple inverse transform
            tr = self.stageTransform().offset + np.array(self.mapFromGlobal(globalPos))
            return pg.Vector(self.inverseAxisTransform().map(tr))

        ik_pos = minimum_displacement_inverse_kinematics(
            globalPos, self.axisTransform(), self.getLimits(), previousPos
        )
        self.checkLimits(ik_pos)
        return ik_pos

    def mapDeviceToGlobalPosition(self, pos):
        pos = self.axisTransform().map(pos)[:3]
        return self.mapToGlobal(pos)

    def moveToGlobalNoPlanning(self, pos, speed, progress=False, linear=False, name=None):
        """Move the stage to a position expressed in the global coordinate frame."""
        return self.move(
            position=self.mapGlobalToDevicePosition(pos, self.getPosition()),
            speed=speed,
            progress=progress,
            linear=linear,
            name=name,
        )

    def movePath(self, path, name=None):
        """Move the stage along a path with multiple waypoints.

        The format of *path* is a list of dicts, where each dict specifies keyword arguments
        to self.move(). Optionally, each dict may specify `globalPos` instead of `position`.
        """
        return MovePathFuture(self, path, name=name)

    def _toAbsolutePosition(self, abs):
        """Helper function to convert absolute position (possibly
        containing Nones) to an absolute position.
        """
        if any(x is None for x in abs):
            pos = self.getPosition()
            for i, x in enumerate(abs):
                if x is not None:
                    pos[i] = x
        else:
            pos = abs
        return pos

    def setVelocity(self, vel):
        """Begin moving the stage with a constant velocity."""
        # Panic Lock guard (§6.1: Stage.setVelocity is Raise). This is still a stub
        # -- see §12 item 2 -- but the guard belongs with the entry point, not with
        # whatever eventually implements it.
        self.dm.globalHalt.check()
        # pick a far-away distance within limits
        print(vel)

    def stop(self, reason=None):
        """Stop moving the device immediately. When you call MoveFuture.stop() from here, look closely at infinite
        recursions.
        """
        raise NotImplementedError()

    def updateProgressDialog(self):
        done = int(self._progressDialog.mf.percentDone())
        self._progressDialog.setValue(done)
        if done == 100:
            self._progressTimer.stop()

    def getPreferredImagingDevice(self):
        camName = self.config.get("imagingDevice", None)
        if camName is None:
            cams = self.dm.listInterfaces("camera")
            if len(cams) == 1:
                camName = cams[0]
            else:
                raise Exception(
                    f"Could not determine preferred camera (found {len(cams)}). Set 'imagingDevice' key in stage "
                    f"configuration to specify."
                )
        return self.dm.getDevice(camName)

    def setLimits(self, x=None, y=None, z=None, d=None):
        """Set the (min, max) position limits to enforce for each axis.

        Accepts keyword arguments 'x', 'y', 'z', 'd'; each supplied argument must be
        a (min, max) tuple where either value may be None to disable the limit. Limits
        are in device coordinates, matching :meth:`getPosition` -- the ``limits:``
        config block for a Sensapex is in µm, for a Dover stage in mm.

        Note that some devices do not support limits.
        """
        changed = []
        for axis, limit in enumerate((x, y, z, d)):
            if limit is None:
                continue
            assert len(limit) == 2
            if self.capabilities()['limits'][axis] is True:
                self._setHardwareLimits(axis=axis, limit=limit)
            if tuple(self._limits[axis]) != tuple(limit):
                changed.append(axis)
                self._limits[axis] = tuple(limit)

        if len(changed) > 0:
            self.sigLimitsChanged.emit(changed)

    def getLimits(self) -> List[tuple[float | None, float | None]]:
        """Return a list of the (min, max) position limits for each axis."""
        return self._limits[:]

    def getBoundaries(self) -> List[Plane]:
        """Return the boundaries of the stage in global coordinates."""
        limits = self.getLimits()  # min, max
        if None in [m for ax in limits for m in ax]:
            return []
        # TODO do we need to use _baseTransform, too?
        xform = self.axisTransform()
        return limits_to_boundaries(limits, xform, self.name())

    def _setHardwareLimits(self, axis: int, limit: tuple):
        raise NotImplementedError("Must be implemented in subclass.")

    def checkGlobalLimits(self, globalPos, linear):
        """Raise an exception if *globalPos* (in global coordinates) is outside the configured limits"""
        stagePos = self.mapGlobalToDevicePosition(globalPos, self.getPosition())
        self.checkLimits(stagePos)

    def checkLimits(self, stagePos):
        """Raise an exception if *stagePos* is outside the configured limits.

        *stagePos* is in device coordinates, as are the limits themselves. Raises
        :class:`OutOfLimitsError`, which is a ``ValueError``.
        """
        for axis, limit in enumerate(self._limits):
            ax_name = 'xyzd'[axis]
            x = stagePos[axis]
            if x is None:
                continue
            if limit[0] is not None and x < limit[0]:
                raise OutOfLimitsError(
                    f"Position requested for device {self.name()} exceeds limits: {stagePos} {ax_name} axis < {limit[0]}"
                )
            if limit[1] is not None and x > limit[1]:
                raise OutOfLimitsError(
                    f"Position requested for device {self.name()} exceeds limits: {stagePos} {ax_name} axis > {limit[1]}"
                )

    def checkRangeOfMotion(self, pos, name, tolerance=500e-6):
        """Raise an exception if the specified global position is within *tolerance* of the limits of the device.

        An axis counts as bad only when the mapping actually reports the probe position
        as out of limits (:class:`OutOfLimitsError`). Any other failure of the mapping is
        a fault and propagates: it is not evidence that the position is near a limit, and
        treating it as such reports a range-of-motion problem for a position that may be
        nowhere near one. On a stage with more than three axes the mapping currently
        fails that way for every probe -- :meth:`mapGlobalToDevicePosition` needs a
        ``previousPos`` it is not given here -- so those calls now raise instead of
        quietly flagging x, y and z.
        """
        pos = np.array(pos)
        bad_axes = []
        for axis in (0, 1, 2):
            try:
                bound = pos.copy()
                bound[axis] -= tolerance
                self.checkLimits(self.mapGlobalToDevicePosition(bound))
                bound[axis] += 2 * tolerance
                self.checkLimits(self.mapGlobalToDevicePosition(bound))
            except OutOfLimitsError:
                bad_axes.append(axis)
        if bad_axes:
            axis_names = {0: 'x', 1: 'y', 2: 'z'}
            axes = ', '.join(axis_names[axis] for axis in bad_axes)
            stage_pos = self.mapGlobalToDevicePosition(pos)
            possible_problem = (
                "pipette pull consistency" if self.isManipulator else "hardware reliability"
            )
            raise HelpfulException(
                f"The specified position is within ±{siFormat(tolerance, suffix='m')} of the {axes} limit(s) of "
                f"{self.name()} and may not always be accessible, depending on your {possible_problem}.",
                reasons=[
                    f"Manipulator limits: {self.getLimits()}",
                    f"Position: ({stage_pos[0]:f}, {stage_pos[1]:f}, {stage_pos[2]:f})",
                    f"Position name: {name}",
                ],
            )

    def homePosition(self):
        """Return the stored home position of this stage in global coordinates."""
        return self.getStoredLocation('home')

    def goHome(self, speed='fast'):
        homePos = self.homePosition()
        if homePos is None:
            raise RuntimeError(f"No home position set for {self.name()}")
        return self.dm.move(MoveSpec(self, homePos, speed=speed), name=f"move {self.name()} to home")

    def setHomePosition(self):
        """Set the home position in global coordinates.

        Recording home with an axis close to its limit is allowed but warned about; see
        :meth:`setStoredLocation`.
        """
        self.setStoredLocation('home')

    def getStoredLocation(self, name):
        return self.readConfigFile('stored_locations').get(name, None)

    #: How close to an axis limit a stored location may sit before
    #: :meth:`setStoredLocation` warns about it, as a real distance in metres.
    storedLocationClearance = 500e-6

    def axesNearLimits(self, pos=None, tolerance=None):
        """Return the axes of *pos* that sit within *tolerance* of one of their limits.

        *pos* is in device coordinates and defaults to the current position; *tolerance*
        is a real distance in **metres** (default :attr:`storedLocationClearance`) and is
        converted to device units per axis through :meth:`getAxisScale`, because the
        limits themselves are in device units.

        Returns a list of ``(axis_name, position, (min, max))``, one per offending axis,
        empty when everything has room. Axes with no limit configured, no scale, or a
        None position are skipped.
        """
        if pos is None:
            pos = self.getPosition()
        if tolerance is None:
            tolerance = self.storedLocationClearance
        scale = np.abs(np.asarray(self.getAxisScale(), dtype=float))
        names = self.axes()
        near = []
        for axis, (low, high) in enumerate(self.getLimits()):
            if axis >= len(pos) or pos[axis] is None or (low is None and high is None):
                continue
            # a device may configure fewer scales than it has axes; the rest are assumed
            # to report in the same units as the last one given
            axis_scale = scale[axis] if axis < scale.size else scale[-1]
            if axis_scale == 0:
                continue
            margin = tolerance / axis_scale  # metres -> device units
            x = pos[axis]
            if (low is not None and x - low < margin) or (high is not None and high - x < margin):
                near.append((names[axis], x, (low, high)))
        return near

    def setStoredLocation(self, name: str):
        """Record the current position under *name*, in global coordinates.

        A position within :attr:`storedLocationClearance` of an axis limit is still
        stored -- the operator may have good reason, and refusing would lose the
        position entirely -- but it is warned about, because it is likely to fail when
        the device is later asked to go back to it. Two reasons it fails: an axis
        commanded to its own end of travel tends to stop a few µm short and miss the
        move's tolerance; and on a stage with a redundant axis, the stored *global*
        point does not record which device position produced it, so the inverse
        kinematics is free to come back with the spare axis parked on its bound.

        The check is per device axis, so it covers the fourth axis of a 4-axis
        manipulator -- the one a global position cannot describe.
        """
        pos = self.getPosition()
        self.checkLimits(pos)
        locations = self.readConfigFile('stored_locations')
        locations[name] = list(self.globalPosition())
        self.writeConfigFile(locations, 'stored_locations')

        near = self.axesNearLimits(pos)
        if near:
            detail = "; ".join(
                f"{ax} = {x:g} (limits {low}, {high})" for ax, x, (low, high) in near
            )
            self.logger.warning(
                "%s: stored location %r is within %s of the %s limit(s) and may not be "
                "reachable later: %s",
                self.name(),
                name,
                siFormat(self.storedLocationClearance, suffix='m'),
                ", ".join(ax for ax, _, _ in near),
                detail,
            )

    def clearStoredLocation(self, name):
        locations = self.readConfigFile('stored_locations')
        if name in locations:
            del locations[name]
            self.writeConfigFile(locations, 'stored_locations')

    # --------------------------------------------------------- control surface bindings

    def _setupControls(self, config):
        """Acquire and bind every control named in the ``controls:`` config block.

        A missing or empty block is a no-op, so a stage on a rig with no control surface
        costs nothing. Runs at the end of :meth:`Stage.__init__`, which means a subclass's
        binding must not touch hardware the subclass has not set up yet -- bind the signal
        and read the hardware when the signal arrives.

        Parameters
        ----------
        config : dict
            This device's configuration.
        """
        conf = config.get('controls', None)
        if not conf:
            return
        if not isinstance(conf, dict):
            raise TypeError(
                f"{self.name()}: 'controls' must be a dict of named control specs, not "
                f"{type(conf).__name__}"
            )
        for name, spec in conf.items():
            control = acquireControlFromConfig(spec, owner=self)
            self._boundControls[name] = control
            self.bindControl(name, control, spec)
        # paint once the subclass has finished constructing and read a real position
        Qt.QTimer.singleShot(0, self._scheduleAxisControlPaint)

    def controlNames(self) -> list:
        """Return the action names accepted in the ``controls:`` config block.

        The base class claims this device's axis names. Subclasses extend the list (and
        :meth:`bindControl`) rather than replacing it.
        """
        return list(self.axes())

    def bindControl(self, name, control, conf):
        """Give *control* the behaviour named *name* in the ``controls:`` config block.

        Dispatch is open: a subclass overrides this, handles its own names and delegates
        anything else back here with ``Stage.bindControl(self, name, control, conf)``.

        Parameters
        ----------
        name : str
            The key this control was declared under.
        control : Control
            The control, already acquired for this device.
        conf : dict
            The whole config entry, so that an action can read its own options (an axis
            dial's ``step``) alongside the address.

        Raises
        ------
        ValueError
            If *name* is not an action this device offers, or if *control* cannot drive it.
        """
        axes = list(self.axes())
        if name in axes:
            self._bindAxisDial(axes.index(name), name, control, conf)
            return
        raise ValueError(
            f"{self.name()}: unknown control name {name!r} in the 'controls:' config "
            f"block; {type(self).__name__} accepts {sorted(self.controlNames())}"
        )

    def _bindAxisDial(self, axis, name, control, conf):
        """Bind a relative dial to axis index *axis*.

        Raises
        ------
        ValueError
            If *control* is not a dial, reports ``mode: 'absolute'``, has no usable
            ``step``, or sits on an axis whose ``scale`` is 0.
        """
        if control.type != 'dial':
            raise ValueError(
                f"{self.name()}: axis control {name!r} is bound to {control}, which is a "
                f"{control.type!r} and not a dial"
            )
        caps = control.capabilities()
        mode = caps['input'].get('mode')
        if mode != 'relative':
            raise ValueError(
                f"{self.name()}: axis control {name!r} is bound to {control}, whose input "
                f"mode is {mode!r}. Stage binds relative dials only; driving an axis from "
                f"an absolute dial is the velocity/jog question and is not implemented."
            )
        if 'step' not in conf:
            raise ValueError(
                f"{self.name()}: axis control {name!r} needs a 'step' -- the distance (m) "
                f"to move per dial detent"
            )
        step = float(conf['step'])
        if step == 0:
            raise ValueError(f"{self.name()}: axis control {name!r} has a 'step' of 0")
        # Metres per device unit on this axis. Read once: it comes from the config, which
        # does not change for the life of the device, and dividing by it is how a 'step'
        # in metres reaches the device coordinates move() takes.
        scale = float(self.getAxisScale()[axis])
        if scale == 0:
            raise ValueError(
                f"{self.name()}: axis control {name!r} cannot convert its 'step' from "
                f"metres into device units, because the configured 'scale' for that axis "
                f"is 0"
            )
        if axis in self._axisControls:
            raise ValueError(
                f"{self.name()}: axis {name!r} already has a dial bound "
                f"({self._axisControls[axis]['control']})"
            )

        binding = {
            'axis': axis,
            'name': name,
            'control': control,
            'step': step,
            'scale': scale,
            'speed': conf.get('speed', None),
            # Drawing text is a property of the surface, not of dials in general: a Stream
            # Dock knob has a 200x100 strip to write on and an X-Keys jog wheel has no
            # pixels at all. Settled once, here, from what this control offers and says it
            # offers, so that _paintAxisControls is a call rather than a decision; an
            # unpaintable dial still drives its axis.
            'paintable': hasattr(control, 'setText') and bool(caps['output'].get('text')),
        }
        if not binding['paintable']:
            self.logger.warning(
                f"{self.name()}: {control} cannot draw text, so axis {name!r} will not show"
                f" its name and position on it. The dial still moves the axis."
            )
        if not self._axisControls:
            self.sigPositionChanged.connect(self._axisControlPositionChanged)
        self._axisControls[axis] = binding
        self._axisControlByControl[control] = binding
        control.sigMoved.connect(self._axisDialMoved)
        control.sigPressed.connect(self._axisDialPressedInternal)

    def _releaseControls(self):
        """Release every control claimed from the ``controls:`` config block.

        Called from :meth:`quit`. Signals are disconnected wholesale: acquisition is
        exclusive, so nothing else is listening to a control this device owns.
        """
        self._axisControlPaintTimer.stop()
        for control in self._boundControls.values():
            for signal in (
                control.sigMoved,
                control.sigPressed,
                control.sigReleased,
                control.sigTouched,
            ):
                try:
                    signal.disconnect()
                except (TypeError, RuntimeError):
                    pass
            try:
                control.release()
            except Exception:
                self.logger.exception(f"{self.name()}: failed to release {control}")
        self._boundControls = {}
        self._axisControls = {}
        self._axisControlByControl = {}

    # --- dial-driven axis movement ----------------------------------------------------

    def _axisControlTarget(self) -> list:
        """Return a mutable copy of the dial target, seeding it from the stage if unset."""
        if self._axisControlTargetPos is None:
            self._axisControlTargetPos = list(self.getPosition())
        return list(self._axisControlTargetPos)

    def _axisDialMoved(self, control, delta):
        """Move one axis by *delta* dial detents. Always runs on the GUI thread.

        ``step`` is a length in metres -- acq4 is SI throughout -- while the dial target
        and :meth:`move` are both in the device's own coordinates (millimetres on a Dover,
        micrometres on a Sensapex), so the step is divided by the axis scale on the way
        in. Dividing rather than taking the magnitude is deliberate: a positive detent
        then means "+step metres along the global direction this axis points in", so the
        knob turns the same way on every axis of every stage, and an axis configured with
        a negative scale has its raw device coordinate walked downwards to get there. The
        knob face is painted from the same signed length (:meth:`_paintAxisControls`), so
        a detent in the positive direction always makes the number on it go up.
        """
        binding = self._axisControlByControl.get(control)
        if binding is None:
            return
        target = self._axisControlTarget()
        target[binding['axis']] += delta * binding['step'] / binding['scale']
        try:
            # flag our own move, so that a position update delivered synchronously from
            # inside move() is not mistaken for somebody else driving the stage
            self._axisControlMoveStarting = True
            try:
                future = self.move(target, speed=binding['speed'])
            finally:
                self._axisControlMoveStarting = False
        except Exception:
            # leave the target where it was: a refused move (past a limit, or while the
            # rig is halted) must not let the knob wind the target off into space
            self.logger.exception(
                f"{self.name()}: dial-driven move of axis {binding['name']!r} failed"
            )
            return
        self._axisControlMove = future
        self._axisControlTargetPos = target
        self._scheduleAxisControlPaint()

    def _axisControlMotionIsOurs(self) -> bool:
        """Return whether the motion currently in flight was started by a dial.

        :meth:`move` records every move as ``self._lastMove``, whoever asked for it, so a
        dial-driven move is ours only while the future it returned is still the stage's
        current move *and* has not finished. Everything else -- another module calling
        :meth:`move`, a manual jog on the hardware, or our own move once it has completed
        and the hardware position is authoritative again -- re-seeds the target.
        """
        if self._axisControlMoveStarting:
            return True
        future = self._axisControlMove
        return future is not None and future is self._lastMove and not future.is_done

    def _axisControlPositionChanged(self, dev, pos, oldPos):
        """Re-seed the dial target from the hardware, and repaint the dials.

        Without the re-seed the knob fights anything else driving the stage: its target
        would still hold the last place *it* asked for, so the next detent would snap the
        stage back there.
        """
        if not self._axisControlMotionIsOurs():
            self._axisControlTargetPos = list(pos)
        self._scheduleAxisControlPaint()

    def _axisDialPressedInternal(self, control):
        """Route a dial press to :meth:`axisDialPressed`."""
        binding = self._axisControlByControl.get(control)
        if binding is not None:
            self.axisDialPressed(binding['axis'])

    def axisDialPressed(self, axis):
        """Hook: the dial bound to axis index *axis* was pressed.

        Deliberately empty. The press gesture is reserved for the velocity/jog work that
        a later pass owns; subclasses may override it in the meantime.
        """

    # --- dial appearance --------------------------------------------------------------

    def _scheduleAxisControlPaint(self):
        """Repaint the bound dials, coalescing bursts of position updates.

        Paints immediately if the last paint is older than
        :attr:`axisControlPaintInterval`, and otherwise arms a single-shot timer for the
        remainder of the interval, so that a 10 Hz position feed does not become a 10 Hz
        render-and-write loop.
        """
        if not self._axisControls or self._axisControlPaintPending:
            return
        delay = self.axisControlPaintInterval - (ptime.time() - self._axisControlLastPaint)
        if delay <= 0:
            self._paintAxisControls()
        else:
            self._axisControlPaintPending = True
            self._axisControlPaintTimer.start(int(delay * 1000) + 1)

    def _axisControlPaintTimeout(self):
        self._axisControlPaintPending = False
        self._paintAxisControls()

    def _paintAxisControls(self):
        """Draw the axis name and current position on each dial that can show it.

        The number is always millimetres to three decimal places -- ``40.762 mm`` -- and
        never rescales itself, so a detent is a visible change in the last digit (1 um per
        digit, against the 2-10 um steps a rig typically configures) rather than a number
        that jumps between um, mm and m as the stage travels.

        It is the distance along that axis, not a global coordinate: ``getPosition()`` is
        in device units, and the signed axis scale converts it to metres of travel. That
        keeps the face well defined for an axis with no global counterpart -- the ``d``
        axis of a four-axis manipulator -- and makes the number move with the knob, since
        a positive detent is "+step metres along this axis" (see :meth:`_axisDialMoved`).
        It is therefore not the reading the Camera module shows for the same stage.

        A dial that cannot show text -- see the ``paintable`` note in
        :meth:`_bindAxisDial` -- is skipped, and one that turns out to refuse the call
        anyway is dropped from painting rather than raising on every position update.
        """
        self._axisControlLastPaint = ptime.time()
        if not self._axisControls:
            return
        pos = self.getPosition()
        for binding in self._axisControls.values():
            if not binding['paintable']:
                continue
            control = binding['control']
            # getPosition() is in device units; scale it into metres so the face
            # reads "40.8 mm" rather than "40.8 m", and so that it moves in the same
            # direction as the knob (see :meth:`_axisDialMoved`).
            length = pos[binding['axis']] * binding['scale']
            try:
                control.setText(f"{binding['name']}\n{siFormat(length, suffix='m')}")
            except UnsupportedControlFeature:
                binding['paintable'] = False
            except Exception:
                self.logger.exception(f"{self.name()}: failed to paint {control}")
                binding['paintable'] = False

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


class CallOnce:
    """Used to prevent a callable from being called more than once in a stack. Note that this is not a mutex."""

    def __init__(self):
        self.called = False

    def __enter__(self):
        if self.called:
            return False
        self.called = True
        return True

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.called = False


class MoveFuture(ManualQtFriendlyTask):
    """Used to track the progress of a requested move operation.

    This is an externally-completed ManualQtFriendlyTask: it has no body and spawns no
    thread. The device subclass's hardware-monitor thread is the producer; it
    completes the move by calling ``self.resolve(...)`` when the target is
    reached or ``self.fail(exc)`` on error, and checks ``self.is_stopped`` (set
    by ``stop()``) to abort an in-progress move. Subclasses must not call the
    old ``_taskDone``/``_stopRequested`` API; use resolve/fail/is_stopped.
    """

    def __init__(self, dev: Stage, pos, speed, name=None):
        """Create a future tracking one move of *dev* to *pos*.

        *pos* is the target in device coordinates; :attr:`targetPos` and
        :attr:`startPos` are both kept in those units. *speed* is in m/s (subclasses
        resolve 'fast'/'slow' before getting here), so turning a distance between those
        two positions into a duration means scaling it by ``dev.getAxisScale()`` first.
        """
        if name is None:
            name = f"{dev.name()} move"
        ManualQtFriendlyTask.__init__(self, name=name)
        # A ManualTask has no body, so it never enters task_context and never puts its
        # own name on the throughline; and the producer threads that drive it are raw
        # threads, which start with an empty context. Capture the requesting context
        # here (plus this move's name) so producers can re-establish it via
        # throughlineContext() and everything logged during the move stays attached to
        # the operation that asked for it.
        self._throughlineFrames = throughline.frames() + ({"name": name},)
        self.startTime = ptime.time()
        self.dev = dev
        self.speed = speed
        self.targetPos = np.asarray(pos)
        self.startPos = np.asarray(dev.getPosition())
        self._isStopCallable = CallOnce()

    def throughlineContext(self):
        """Re-establish the throughline this move was requested under.

        Producer threads (a per-move monitor, or a stage's lifetime monitor thread
        handling this move) wrap the work that drives this move in this, so their log
        records carry the requesting operation's chain and this move's name.
        """
        return throughline.restore(self._throughlineFrames)

    def producerThread(self, target, name) -> threading.Thread:
        """Return an unstarted daemon thread running *target* under this move's throughline.

        The preferred way for a device subclass to spawn a per-move monitor thread:
        a raw thread would start with an empty context and orphan everything it logs
        from the operation that requested the move.
        """

        def run():
            with self.throughlineContext():
                target()

        return threading.Thread(target=run, daemon=True, name=name)

    def percentDone(self):
        """Return the percent of the move that has completed.

        The default implementation calls getPosition on the device to determine
        the percent complete. Devices that do not provide position updates while
        moving should reimplement this method.
        """
        if self.is_done:
            return 100
        s = np.array(self.startPos)
        t = np.array(self.targetPos)
        p = np.array(self.dev.getPosition())
        d1 = ((p - s) ** 2).sum() ** 0.5
        d2 = ((t - s) ** 2).sum() ** 0.5
        if d2 == 0:
            return 100
        return 100 * d1 / d2

    def stop(self, reason="stop requested", wait=False):
        """Stop the move in progress.

        Completes this promise with Stopped via ManualQtFriendlyTask.stop(reason)
        FIRST, then tells the device to halt. The order matters: halting the
        device interrupts the in-progress hardware move, which wakes the producer
        thread and makes it complete this promise with a RuntimeError (e.g.
        "stop requested before move finished"). Since ``_finish`` is idempotent
        (first completer wins), we must inject Stopped before that interrupt so
        the producer's later fail() is the harmless no-op it assumes it is.
        Doing the device halt first opens a race window in which the producer can
        win, leaving the promise failed with a RuntimeError that callers stopping
        cooperatively do not expect. The producer still sees ``is_stopped`` and
        aborts. When *wait* is True, block until the promise actually completes,
        swallowing the resulting Stopped.
        """
        with self._isStopCallable as can_call_stop:
            if can_call_stop and not self.is_done:
                super().stop(reason, wait=False)
                self.dev.stop()
                if wait:
                    # Reimplemented here so we can stop the device between the
                    # promise being completed and the hardware stop.
                    with contextlib.suppress(Stopped):
                        self.wait()


class MovePathFuture(MoveFuture):
    def __init__(self, dev: Stage, path, name=None):
        super().__init__(dev, None, None, name=name)

        self.path = path
        self.currentStep = 0
        self._currentFuture = None

        prev = dev.getPosition()
        global_path = [s.get("globalPos") for s in path if "globalPos" in s]
        for step in self.path:
            if step.get("globalPos") is not None:
                global_pos = step.pop("globalPos")
                try:
                    step["position"] = dev.mapGlobalToDevicePosition(global_pos, prev)
                except Exception as e:
                    raise MovePathException(
                        "Cannot map global position to device coordinates", global_path, global_pos
                    ) from e
                prev = step["position"]
        for i, step in enumerate(self.path):
            try:
                dev.checkMove(**step)
            except Exception as exc:
                raise Exception(
                    f"Cannot move {dev.name()} to path step {i}/{len(self.path)}: {step}"
                ) from exc

        self._moveThread = self.producerThread(self._movePath, name=f'{dev.name()} : {name}')
        self._moveThread.start()

    def percentDone(self):
        fut = self._currentFuture
        if fut is None:
            return 0.0
        return (100 * fut._pathStep + fut.percentDone()) / len(self.path)

    def stop(self, reason=None, wait=False):
        """Stop the path move: halt the current step, then complete with Stopped.

        Skips MoveFuture.stop (and its dev.stop()) because the current step
        future already owns the device; we just stop that step and self-complete
        this promise via ManualQtFriendlyTask.stop(reason).
        """
        fut = self._currentFuture
        if fut is not None:
            fut.stop(reason)
        # skip MoveFuture.stop to avoid the mess with dev.stop()
        ManualQtFriendlyTask.stop(self, reason, wait=wait)

    def _movePath(self):
        # Producer thread for this externally-completed promise. It is a raw
        # thread (not a gentletask task), so it honors our stop by polling
        # self.is_stopped rather than using check_stop(). It runs under this path's
        # throughline (see producerThread), which also puts each step's move under
        # this path, since the step futures are constructed on this thread.
        try:
            for i, step in enumerate(self.path):
                step = step.copy()
                explanation = step.pop('explanation', 'unnamed')
                try:
                    fut = self.dev.move(
                        **step, name=f'{self._name} step {i+1}/{len(self.path)}: {explanation}'
                    )
                except Exception as e:
                    # A step that is refused *synchronously* -- most importantly by the
                    # Panic Lock guard at the top of move(), but equally by a limit
                    # check -- never produces a step future for the wait() below to
                    # inspect. Without this the exception would escape into the
                    # producer thread and the `finally` clause would resolve this
                    # promise as a success, telling the caller a path completed while
                    # the rig was halted. The exception is passed through unwrapped so
                    # a GlobalHaltException reaches the caller as itself (§7.1).
                    self.fail(e)
                    return
                fut._pathStep = i
                self._currentFuture = fut

                # Wait for the step, honoring a stop request on this path future.
                while not fut.is_done:
                    try:
                        fut.wait(timeout=0.1)  # raises fut.Timeout on timeout
                    except fut.Timeout:
                        pass
                    except Exception:
                        # The step completed *while we were polling it*, with a
                        # failure or a Stopped. Left to propagate, it escapes into
                        # this raw producer thread and the `finally` below then
                        # resolves this promise as a success -- telling the caller
                        # a path completed when a step had just failed (and, once a
                        # panic can fail a step, when the rig is halted). Break out
                        # instead and let the single result-inspection block after
                        # the loop classify it, exactly as it does for a step that
                        # completed between two polls.
                        break
                    self.currentStep = i + 1
                    if self.is_stopped:
                        fut.stop(self.stop_reason)
                        break

                if self.is_stopped:
                    # self.stop() has already completed this promise with Stopped.
                    return

                # Inspect the step result: re-raising via wait() surfaces any
                # failure or Stopped from the step future.
                try:
                    fut.wait()
                except Stopped:
                    return
                except GlobalHaltException as e:
                    # A panic failed this step (§5.2, Stage.abortForHalt). It must
                    # reach the caller as itself: GlobalHaltException deliberately
                    # does not subclass Stopped so it propagates past handlers
                    # written for ordinary cancellation (§7.1), and wrapping it in
                    # a RuntimeError below would erase exactly that -- the caller
                    # could no longer tell a halted rig from a hardware fault.
                    # Passed through unwrapped, mirroring the synchronous refusal
                    # above; genuine failures keep their "Path step N/M" wrapper.
                    # The context is not lost either way, since the step future's
                    # own name carries "step N/M" and the path's throughline
                    # records it.
                    self.fail(e)
                    return
                except Exception as e:
                    self.fail(
                        RuntimeError(f"Path step {i + 1}/{len(self.path)} failed: {e}")
                    )
                    return
        finally:
            if not self.is_done:
                self.resolve()  # success!

    def undo(self):
        """Reverse the moves generated in this future and return a new future."""
        fwdPath = [{'position': self.startPos}] + self.path[:]
        revPath = []
        for i in range(min(self.currentStep, len(self.path) - 1), -1, -1):
            step = fwdPath[i + 1].copy()
            step['position'] = fwdPath[i]['position']
            step['explanation'] = f"undo {step.get('explanation')}"
            revPath.append(step)
        return self.dev.movePath(revPath, name=f"undo {self._name}")


class StageInterface(Qt.QWidget):
    def __init__(self, dev: Stage, win):
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
        if dev.isManipulator:
            self.stageLabel = Qt.QLabel('manipulator')
        else:
            self.stageLabel = Qt.QLabel('stage')
        self.positionLabelLayout.addWidget(self.stageLabel, 0, 2)

        cap = dev.capabilities()
        for axis, axisName in enumerate(self.dev.axes()):
            if cap['getPos'][axis]:
                axLabel = Qt.QLabel(axisName)
                axLabel.setMaximumWidth(15)
                globalPosLabel = Qt.QLabel('')
                stagePosLabel = Qt.QLabel('')
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
                for i, w in enumerate(widgets):
                    self.positionLabelLayout.addWidget(w, nextRow, i)
                self.axCtrls[axis] = widgets

        self.btnContainer = Qt.QWidget()
        self.btnLayout = Qt.QGridLayout()
        self.btnContainer.setLayout(self.btnLayout)
        self.layout.addWidget(self.btnContainer, self.layout.rowCount(), 0)
        self.btnLayout.setContentsMargins(0, 0, 0, 0)

        self.goHomeBtn = FutureButton(
            self.goHomeClicked, 'Home', stoppable=True, processing='Going home...'
        )
        self.btnLayout.addWidget(self.goHomeBtn, 0, 0)

        self.setHomeBtn = Qt.QPushButton('Set Home')
        self.btnLayout.addWidget(self.setHomeBtn, 0, 1)
        self.setHomeBtn.clicked.connect(self.setHomeClicked)

        self.calibrateBtn = Qt.QPushButton('Calibrate Axes')
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
        for i, v in enumerate(globalPos):
            text = pg.siFormat(v, suffix='m', precision=5)
            self.posLabels[i][0].setText(text)
        for i, v in enumerate(stagePos):
            self.posLabels[i][1].setText(str(v))

    def updateLimits(self):
        limits = self.dev.getLimits()
        cap = self.dev.capabilities()
        for axis in range(len(cap['limits'])):
            if not cap['limits'][axis]:
                continue
            for i, limit in enumerate(limits[axis]):
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
        return self.dev.goHome()

    def setHomeClicked(self):
        self.dev.setHomePosition()

    def calibrateClicked(self):
        if self.calibrateWindow is None:
            if self.dev.isManipulator:
                self.calibrateWindow = ManipulatorAxesCalibrationWindow(self.dev)
            else:
                self.calibrateWindow = StageAxesCalibrationWindow(self.dev)
        self.calibrateWindow.show()
        self.calibrateWindow.raise_()
