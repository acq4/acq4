"""Tests for the moves ContactCellState commands, recorded by a fake pipette.

Covers the lift before the move to the descent start, the overshootDistance offset, and
the depth limits that end the descent.
"""
from __future__ import annotations

from collections import namedtuple

import numpy as np
import pytest

from acq4.devices.PatchPipette.states import contact_cell as contact_cell_module
from acq4.devices.PatchPipette.states.contact_cell import ContactCellState

PITCH_DEG = 30.0
TARGET = (0.0, 0.0, -50e-6)

# Where the pipette was told to go, where it was when told, and where it ended up.
_Move = namedtuple("_Move", "name start pos end")


class _FakeSignal:
    def connect(self, *args, **kwargs):
        pass

    def disconnect(self, *args, **kwargs):
        pass

    def emit(self, *args, **kwargs):
        pass


class _DoneFuture:
    is_done = True

    def wait(self, *args, **kwargs):
        return None

    def stop(self, *args, **kwargs):
        pass


class _RecordingPipette:
    """Records every commanded move and reports the tip as having arrived."""

    def __init__(
        self,
        position,
        target,
        pitch_deg=PITCH_DEG,
        yaw_deg=0.0,
        arrival_error=0.0,
    ):
        self._pos = np.array(position, dtype=float)
        self._target = np.array(target, dtype=float)
        pitch, yaw = np.radians(pitch_deg), np.radians(yaw_deg)
        flat = np.cos(pitch)
        self._direction = np.array([flat * np.cos(yaw), flat * np.sin(yaw), -np.sin(pitch)])
        # z offset added to every arrival, so tests can tell a measured
        # ContactCellState._startZ from one computed from the commanded position.
        self._arrival_error = arrival_error
        self.moves = []

    def globalDirection(self):
        return self._direction.copy()

    def globalPosition(self):
        return self._pos.copy()

    def targetPosition(self):
        return self._target.copy()

    def moveToGlobalNoPlanning(self, pos, speed=None, name=None, **kwargs):
        pos = np.array(pos, dtype=float)
        start = self._pos.copy()
        self._pos = pos + np.array([0.0, 0.0, self._arrival_error])
        self.moves.append(_Move(name, start, pos, self._pos.copy()))
        return _DoneFuture()


class _FakeDev:
    def __init__(self, pipette):
        self.active = True
        self.cell = object()  # non-None, so newCell() is not exercised here
        self.sigTargetChanged = _FakeSignal()
        self.sigActiveChanged = _FakeSignal()
        self.pipetteDevice = pipette
        self._patchrec = {}

    def patchRecord(self):
        return self._patchrec

    def newCell(self):
        pass

    def focusOnTarget(self, speed):
        return _DoneFuture()


class _MotionOnlyState(ContactCellState):
    """ContactCellState with test pulses, tip finding and tracking stubbed out.

    Contact is reported after *detectAfter* loop iterations (never if None).
    """

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.messages = []
        self.detectAfter = None
        self._detectChecks = 0

    def monitorTestPulse(self):
        pass

    def processAtLeastOneTestPulse(self):
        pass

    def _cellDetected(self):
        if self.detectAfter is None:
            return False
        self._detectChecks += 1
        return self._detectChecks > self.detectAfter

    def startVisualTargetTracking(self, **kwargs):
        pass

    def findPipetteTip(self, **kwargs):
        pass

    def setState(self, message):
        self.messages.append(message)


class _NeverBroken:
    def tip_is_broken(self):
        return False


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch):
    monkeypatch.setattr(contact_cell_module, "check_stop", lambda *a, **k: None)
    monkeypatch.setattr(contact_cell_module, "sleep", lambda *a, **k: None)


def _run(
    start_position,
    overshoot=0.0,
    step_size=1e-6,
    approach_height=7e-6,
    steps=3,
    yaw_deg=37.0,
    arrival_error=0.0,
    tracking=False,
    detect_after=None,
    depth_past_contact=3e-6,
    max_travel=None,
):
    # Non-zero yaw by default so the overshoot has a non-zero y component.
    pipette = _RecordingPipette(
        start_position,
        TARGET,
        yaw_deg=yaw_deg,
        arrival_error=arrival_error,
    )
    dev = _FakeDev(pipette)
    state = _MotionOnlyState(
        dev,
        config={
            "stepSize": step_size,
            "initialApproachHeight": approach_height,
            "overshootDistance": overshoot,
            "depthPastContact": depth_past_contact,
            # Default: half a step short of the last step's depth, clear of float error.
            "maxTravelWithoutContact": (
                steps * step_size - step_size / 2 if max_travel is None else max_travel
            ),
            "visualTargetTracking": tracking,
            "findPipette": False,
            "stepInterval": 0,
        },
    )
    state._analysis = _NeverBroken()
    state.detectAfter = detect_after
    result = state.run()
    return state, pipette, result


def _descent_steps(pipette):
    return [move for move in pipette.moves if move.name == "contact cell descent step"]


def _named(pipette, name):
    return next(move for move in pipette.moves if move.name == name)


LIFT = "lift to initial approach height"
APPROACH = "move to initial approach position"


def test_each_descent_step_moves_exactly_one_step_size():
    """With an overshoot, each descent step lowers the tip by exactly stepSize."""
    step = 1e-6
    # arrival_error makes the tip's actual z differ from the commanded descent start.
    _state, pipette, _result = _run(
        start_position=(0.0, 0.0, 0.0), overshoot=3e-6, step_size=step, arrival_error=0.4e-6
    )

    arrived = _named(pipette, APPROACH).end
    steps = _descent_steps(pipette)
    assert len(steps) == 3, "the loop must run to the travel limit, not stop early"

    heights = [arrived[2]] + [move.pos[2] for move in steps]
    drops = [a - b for a, b in zip(heights, heights[1:])]
    assert drops == [pytest.approx(step)] * len(steps)


def test_the_descent_is_aimed_at_the_cell_displaced_along_the_pipette_axis():
    """The descent start and every step aim at target + overshootDistance * pipette axis,
    with the start initialApproachHeight above it."""
    overshoot, height = 3e-6, 7e-6
    _state, pipette, _result = _run(
        start_position=(0.0, 0.0, 0.0), overshoot=overshoot, approach_height=height
    )

    axis = pipette.globalDirection()
    displaced = np.array(TARGET) + overshoot * axis
    descent_start = _named(pipette, APPROACH).pos

    assert descent_start[:2] == pytest.approx(displaced[:2])
    assert descent_start[2] == pytest.approx(displaced[2] + height)
    for move in _descent_steps(pipette):
        assert move.pos[:2] == pytest.approx(displaced[:2]), "every step aims at target + overshoot"


def test_the_tip_rises_in_place_before_crossing_to_the_descent_start():
    """The tip rises at its own x,y to the descent start's height, then moves across."""
    start_xy = (150e-6, 0.0)
    _state, pipette, _result = _run(start_position=(*start_xy, -58e-6), overshoot=3e-6)

    lift, approach = pipette.moves[0], pipette.moves[1]
    assert lift.name == LIFT and approach.name == APPROACH
    assert lift.pos[:2] == pytest.approx(start_xy), "the lift does not move the tip in x,y"
    assert lift.pos[2] == pytest.approx(approach.pos[2]), "the lift rises to the descent start's height"
    assert approach.start[2] == pytest.approx(approach.pos[2], abs=1e-12), (
        "the move across holds the descent start's height"
    )


def test_overshoot_with_visual_target_tracking_warns():
    """A non-zero overshootDistance with visual target tracking on logs one warning."""
    state, _pipette, _result = _run(start_position=(0.0, 0.0, 0.0), overshoot=3e-6, tracking=True)

    warnings = [m for m in state.messages if 'overshootDistance' in m and 'tracking' in m]
    assert len(warnings) == 1, state.messages


def test_overshoot_without_visual_target_tracking_does_not_warn():
    """A non-zero overshootDistance with visual target tracking off logs no warning."""
    state, _pipette, _result = _run(start_position=(0.0, 0.0, 0.0), overshoot=3e-6, tracking=False)

    assert [m for m in state.messages if 'overshootDistance' in m] == []


def test_the_descent_stops_at_the_configured_depth_past_contact():
    """A depthPastContact of three steps stops the descent after exactly three steps,
    despite float error in the accumulated depth."""
    state, pipette, result = _run(
        start_position=(0.0, 0.0, 0.0),
        step_size=1e-6,
        depth_past_contact=3e-6,
        detect_after=0,  # contact on the first loop iteration, before any descent step
        steps=40,
    )

    assert result == {"state": "seal"}
    assert len(_descent_steps(pipette)) == 3
    contact_depth = state.dev.patchRecord()['contactDepth']
    assert contact_depth - pipette.moves[-1].end[2] == pytest.approx(3e-6, abs=1e-12)


def test_the_descent_gives_up_at_the_configured_travel_limit():
    """A maxTravelWithoutContact of three steps ends the descent after exactly three steps,
    despite float error in the accumulated travel."""
    state, pipette, result = _run(
        start_position=(0.0, 0.0, 0.0),
        step_size=1e-6,
        max_travel=3e-6,
        detect_after=None,  # no contact ever, so only the travel limit can stop it
    )

    assert result == {"state": "bath"}
    assert len(_descent_steps(pipette)) == 3
    travelled = _named(pipette, APPROACH).end[2] - pipette.moves[-1].end[2]
    assert travelled == pytest.approx(3e-6, abs=1e-12)
    assert [m for m in state.messages if 'without contact' in m], state.messages
