"""ACQ4's interface to a Dover Motion stage, over the MotionSynergy API.

MotionSynergy axis reference
============================

Measured 2026-10-03 against MotionSynergyAPI 4.0.15900 (SmartStageXY plus a linear Z),
except where marked [doc]. Vendor source: "Motion Synergy API User Manual v20251120.pdf",
sections 4.7.21 (IAxis) and 6.2.2 (the C++ interface, which documents MoveContinuous more
fully). Units below are mm, mm/s and mm/s^2; the API can be configured for um or nm.

Axis commands
-------------
Motion
    ``MoveAbsolute(position) -> Task``, ``MoveRelative(distance) -> Task``,
    ``MoveContinuous(position, acceleration, velocity, deceleration) -> InstrumentResult``
    (no Task; returns as soon as the move has started or the running move is updated),
    ``MoveRelativeToFlag``, ``MoveRelativeToFlagOpenLoop``, ``MoveRelativeUDP``, the
    ``N*`` named-parameter variants, ``Stop() -> Task``, ``EStop() -> Task``,
    ``WaitForContinuousMoveToComplete() -> Task``.
Trajectory
    ``Get/SetVelocity`` (a *maximum*, not the current velocity), ``Get/SetAcceleration``,
    ``Get/SetDeceleration``, ``Get/SetJerk``, ``SelectMoveProfile``, and the
    ``Get/SetNamed{MoveProfiles,Positions,Distances}`` pairs.
State
    ``GetActualPosition``, ``GetCommandedPosition``, ``GetPositionError``,
    ``GetMotorCurrent``, ``GetIsEnabled``, ``GetFlagStatus``, ``GetActiveControlMode``,
    ``Enable`` (energize motor), ``Disable`` (de-energize).
Other
    trace capture, trigger-on-position, homing mode, ``SetExternalControl``.

**There is no constant-velocity or jog primitive.** Every one of the 57 IAxis methods
that commands motion takes a destination. The only speed arguments are ``SetVelocity``
(a ceiling for profile-based moves) and ``MoveContinuous``'s velocity, both attached to
a target; ``SetExternalControl(moveDistancePerPulse)`` is a hardware pulse input, not a
software velocity command.

MoveContinuous
--------------
The only move command that may be issued to an axis that is already moving, and the
only one carrying its own trajectory parameters: it ignores the selected move profile
and supports trapezoidal moves only, hence the absent jerk argument [doc].

* In-flight redirect: a ``MoveContinuous`` issued during a ``MoveAbsolute`` or another
  ``MoveContinuous`` re-aims the axis without halting it.
* A reversal blends through zero with no dwell. From +0.5mm/s with acceleration =
  deceleration = 5mm/s^2, a redirect to a target behind the axis reached -0.45mm/s 196ms
  later, overshooting the turning point by 40um; the same reversal via ``Stop()`` took
  277ms.
* Speed changes in flight: re-issuing ``MoveContinuous`` with an unchanged target and a
  new velocity took the axis from 0.1498 to 0.7006mm/s, as commanded.
* ``SetVelocity`` is not re-read, and is refused outright during motion: called
  mid-move it returned ``Success`` false and the speed was unchanged (0.1495 ->
  0.1490mm/s). ``MoveContinuous``'s velocity argument is the only way to change speed
  without first stopping.

Completion and results
----------------------
``InstrumentResult`` carries ``Success`` and an ``Alert`` (``UserDescription``,
``Description``); ``ToString()`` is readable for diagnostics. A ``Task`` wraps one:
``Wait()`` blocks for it, ``IsCompleted`` tests it, ``Result`` is the
``InstrumentResult``, and reading ``Result`` blocks.

A move's Task completes when its axis comes to rest -- not when it reaches the position
that Task was issued for:

* A ``MoveAbsolute`` Task superseded by a ``MoveContinuous`` redirect stays pending and
  then completes with ``Success`` true, Alert "Success", on arrival at the *new* target.
* A ``MoveAbsolute`` Task interrupted by ``Stop()`` also completes with ``Success`` true.
* ``WaitForContinuousMoveToComplete()`` returns in under 0.05ms with a Task that is
  already complete if the axis is at rest and otherwise completes when it stops. It
  survives redirects; two taken either side of one redirect complete together.

A successful result is therefore never evidence that the commanded position was reached.

Costs
-----
Inside the MotionSynergy server process, per call: ``MoveContinuous`` 0.27ms median,
0.37ms p95, 2.0ms worst of 200; ``WaitForContinuousMoveToComplete`` 0.06ms; ``Stop()``
0.04ms, but awaiting its Task blocks 143ms. ``GetActualPosition`` is the expensive one:
three axes read back-to-back cost 83ms while any of them is moving, against ~12ms at
rest.

A three-axis retarget costs 1.3ms reusing an already-read position and ~85ms reading one
itself; the same retarget by stopping first cost ~230ms. 200 consecutive redirects of a
single moving axis, paced at 5ms, ran at 188Hz with none refused.

Across teleprox from an ACQ4 process, :meth:`SmartStage.move` costs 1.5ms median and the
control thread serves it on its next loop iteration -- ~35ms median from call to
completion of a zero-distance move. The request queue, not the hardware, is the throttle:
of targets produced faster than the ~20Hz loop, only the last of each batch holds the
stage for any length of time.
"""

from .control_thread import SmartStageControlThread, DEFAULT_TARGET_UPDATE_RATE


class SmartStage:
    def __init__(
            self,
            callback=None,
            target_update_rate=DEFAULT_TARGET_UPDATE_RATE,
            callback_threshold=2.5e-4,  # 2.5e-4mm == 250nm
            move_complete_threshold=5e-7,  # 5e-7mm == 0.5nm
            enabled_poll_interval=0.5,
            default_acceleration=10.0,
    ):
        """
        Parameters
        ----------
        callback : callable | None
            Invoked with a new position array whenever the stage has moved further than
            *callback_threshold* on any axis since the last time it was invoked.
        target_update_rate : float
            Rate (Hz) the control thread aims to poll and report position at; an
            aspiration the hardware may not meet, so use :meth:`updates_per_second` for
            the rate actually delivered.
        callback_threshold : float
            Smallest movement (mm, per axis) worth reporting. Also sets the slowest
            speed the stage can move at and still report every iteration.
        move_complete_threshold : float
            Distance (mm) below which an axis is treated as already at its target and
            is not commanded to move.
        enabled_poll_interval : float
            Seconds between per-axis enabled-state reads.
        default_acceleration : float
            Acceleration (mm/s^2) for moves that do not specify one.
        """
        self.default_acceleration = default_acceleration
        self.control_thread = SmartStageControlThread(
            callback, target_update_rate, callback_threshold, move_complete_threshold,
            enabled_poll_interval)

    def set_callback(self, cb):
        self.control_thread.set_callback(cb)

    def stop(self):
        """Stop the device immediately"""
        return self.control_thread.request('stop')

    def move(self, pos, speed, acceleration=None, name=None):
        """Move to a position and return a SmartStageRequestFuture.

        A move arriving while another is running re-aims the stage in flight; the
        request it replaces completes with ``superseded`` set, which is not an error.

        Parameters
        ----------
        pos : sequence of float
            Target position (mm) per axis; None leaves that axis where it is.
        speed : float
            Speed (mm/s) along the path.
        acceleration : float | None
            Acceleration (mm/s^2); None uses ``default_acceleration``.
        name : str | None
            Name for this move, used in log messages.
        """
        if acceleration is None:
            acceleration = self.default_acceleration
        return self.control_thread.request('move', pos=pos, speed=speed, acceleration=acceleration, name=name)

    def quit(self):
        """Quit the control thread"""
        return self.control_thread.request('quit')

    def enable(self):
        return self.control_thread.request('enable')

    def disable(self):
        return self.control_thread.request('disable')

    def enable_axis(self, axis_index):
        """Enable a specific axis by index"""
        return self.control_thread.request('enable_axis', axis_index=axis_index)

    def disable_axis(self, axis_index):
        """Disable a specific axis by index"""
        return self.control_thread.request('disable_axis', axis_index=axis_index)

    def axis_count(self):
        """Get the number of axes"""
        return len(self.control_thread.axes)

    def axis_names(self):
        """Get the names of all axes"""
        return [axis.Name for axis in self.control_thread.axes]

    def is_enabled(self, refresh=False):
        if refresh:
            return self.control_thread.request('enabled_state').wait()
        return self.control_thread.last_enabled_state

    def set_enabled_callback(self, cb):
        self.control_thread.set_enabled_callback(cb)

    def updates_per_second(self):
        """Return the measured rate (Hz) at which positions are polled and reported.

        A ceiling on the callback rate; see :meth:`SmartStageControlThread.loop_rate`.
        """
        return self.control_thread.loop_rate()

    def set_target_update_rate(self, rate):
        """Set the rate (Hz) the control thread aims to poll and report position at.

        Takes effect on the next iteration. Raises ValueError if *rate* is not positive.
        """
        if rate <= 0:
            raise ValueError(f"target update rate must be positive; got {rate!r}")
        self.control_thread.target_update_rate = rate

    def pos(self, refresh=False):
        if refresh:
            return self.control_thread.request('position').wait()
        else:
            return self.control_thread.last_known_pos


if __name__ == "__main__":
    import argparse
    import pyqtgraph as pg
    import acq4.drivers.dovermotion.motionsynergy_api as ms_server

    app = pg.mkQApp()
    print("app!")

    parser = argparse.ArgumentParser(description="Access MotionSynergyAPI from python prompt")
    parser.add_argument("--dll", type=str, help="Path to the MotionSynergyAPI.dll file")
    args = parser.parse_args()

    ms_server.install_tray_icon()
    motionSynergy, instrumentSettings = ms_server.get_motionsynergyapi(args.dll)


    def pos_cb(pos):
        print("Position change:", pos)


    ss = SmartStage(callback=pos_cb)
    ms_server.set_smartstage(ss)

#     parser.add_argument("--port", type=int, default=60738, help="Port to listen on")
#     parser.add_argument("--no-init", action="store_true", help="Do not initialize the MotionSynergyAPI")
#     args = parser.parse_args()

#     path = "C:\\Users\\lukec\\Desktop\\Devices\\Dover Stages\\MotionSynergyAPI_SourceCode_3.6.12025\\"
#     motionSynergy, instrumentSettings = get_motionsynergyapi(path + "MotionSynergyAPI.dll")
#     configure(motionSynergy, instrumentSettings)
#     if not args.no_init:
#         initialize()

#     server = teleprox.RPCServer(address=f"tcp://127.0.0.1:{args.port}")
#     server['motionSynergy'] = motionSynergy
#     server['instrumentSettings'] = instrumentSettings
#     server.run_forever()


# print("Current position:", pos())


# Perform a series of moves, appropriate for the selected product.
# These moves are wrapped in a try / catch block to ensure Shutdown is called prior to
# exit, ensuring each axis is disabled on exit.
# try:
#     if productType == "SmartStageLinear":
#         from SmartStageLinear import *
#         smartStage = SmartStageLinear(axes[0], motionSynergy.Diagnostics)
#         smartStage.PerformMoves()
#     elif productType == "SmartStageXY":
#         from SmartStageXY import *
#         smartStage = SmartStageXY(axes[0], axes[1], motionSynergy.Diagnostics)
#         smartStage.PerformMoves()
#     elif productType == "DOF5":
#         from DOF5 import *
#         dof5 = DOF5(axes[0], motionSynergy.Diagnostics)
#         dof5.PerformMoves()
#     elif productType == "DMCM":
#         from DMCM import *
#         dmcm = DMCM(axes[0], motionSynergy.Diagnostics)
#         dmcm.PerformMoves()
#     else:
#         print(
#             f"Unknown ProductType {productType} specified in configuration file {instrumentSettings.ConfigurationFilename}.")
# except Exception as e:
#     print(repr(e))
