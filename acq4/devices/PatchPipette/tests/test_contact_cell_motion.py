"""Motion geometry of the contact-cell descent, against a recording fake pipette.

These pin where the pipette is actually commanded to go: that reaching the descent start
never drags the tip sideways through the slice, that overshootDistance aims the descent at
the cell's displaced position exactly once, and that the descent stops where it was told to.
"""
from __future__ import annotations

from collections import namedtuple

import numpy as np
import pytest

from acq4.devices.PatchPipette.states import contact_cell as contact_cell_module
from acq4.devices.PatchPipette.states.contact_cell import ContactCellState

PITCH_DEG = 30.0
SURFACE = 0.0
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


class _FakeScope:
    def __init__(self, surface_depth):
        self._surfaceDepth = surface_depth

    def getSurfaceDepth(self):
        return self._surfaceDepth


class _RecordingPipette:
    """Records every commanded move and reports the tip as having arrived."""

    def __init__(
        self,
        position,
        target,
        pitch_deg=PITCH_DEG,
        yaw_deg=0.0,
        arrival_error=0.0,
        surface_depth=SURFACE,
    ):
        self._pos = np.array(position, dtype=float)
        self._target = np.array(target, dtype=float)
        pitch, yaw = np.radians(pitch_deg), np.radians(yaw_deg)
        flat = np.cos(pitch)
        self._direction = np.array([flat * np.cos(yaw), flat * np.sin(yaw), -np.sin(pitch)])
        # Real stages do not land exactly where they were sent, and findPipetteTip() can
        # revise the tip offset between the move and the sample. A fake that teleports
        # exactly cannot tell a sampled _startZ from an assumed one.
        self._arrival_error = arrival_error
        self._scope = _FakeScope(surface_depth)
        self.moves = []

    def globalDirection(self):
        return self._direction.copy()

    def globalPosition(self):
        return self._pos.copy()

    def targetPosition(self):
        return self._target.copy()

    def scopeDevice(self):
        return self._scope

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
    """ContactCellState with the test-pulse machinery stubbed out.

    Only the motion path is under test. Detection is driven by *detectAfter* -- the number
    of loop iterations to report no cell for -- rather than by simulated resistance, so the
    geometry can be exercised with and without contact. Every position, comparison and move
    in run() remains the real one.
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
    surface_depth=SURFACE,
    tracking=False,
    detect_after=None,
    depth_past_contact=3e-6,
):
    # A non-zero yaw by default: at yaw 0 the overshoot's y component is identically zero,
    # so every assertion about it would compare 0 to 0.
    pipette = _RecordingPipette(
        start_position,
        TARGET,
        yaw_deg=yaw_deg,
        arrival_error=arrival_error,
        surface_depth=surface_depth,
    )
    dev = _FakeDev(pipette)
    state = _MotionOnlyState(
        dev,
        config={
            "stepSize": step_size,
            "initialApproachHeight": approach_height,
            "overshootDistance": overshoot,
            "depthPastContact": depth_past_contact,
            "maxTravelWithoutContact": steps * step_size - step_size / 2,
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


LIFT = "lift to tissue clearance height"
CROSS = "traverse above the slice to the descent start"
APPROACH = "move to initial approach position"


def test_each_descent_step_moves_exactly_one_step_size():
    """The overshoot must not be added again to positions derived from _startZ.

    _startZ is sampled after the move to the descent start, so it already carries the
    overshoot's z component. Adding the whole axial vector again in the loop doubles that
    component, and the first step becomes a single uninterrupted plunge of
    stepSize + overshoot*sin(pitch) -- past the cell, with no detection in between.
    """
    step = 1e-6
    # An arrival error makes the commanded descent start differ from where the tip really
    # is, so the steps can only line up if _startZ was sampled rather than assumed.
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
    """overshootDistance assumes the cell is pushed along the pipette axis by that much.

    So the whole descent -- start and every step -- is aimed at target + d*axis, and the
    descent start sits initialApproachHeight above that displaced position.
    """
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
        assert move.pos[:2] == pytest.approx(displaced[:2]), "every step aims at the displaced cell"


def test_nothing_traverses_laterally_below_the_sample_surface():
    """The descent start is below the surface, so it cannot set the clearance height.

    A descent that gave up without contact leaves the tip deep and off to one side. Crossing
    to the next target at that depth drags the shaft through the slice, and
    moveToGlobalNoPlanning does no collision avoidance whatsoever.
    """
    start_z = -58e-6  # where a 'traveled without contact' descent leaves the tip
    _state, pipette, _result = _run(start_position=(150e-6, 0.0, start_z), overshoot=3e-6)

    assert _named(pipette, APPROACH).pos[2] < SURFACE, "precondition: the descent start is in tissue"
    for move in pipette.moves:
        if move.pos[:2] == pytest.approx(move.start[:2]):
            continue  # a pure rise or fall carries the shaft nowhere new
        assert min(move.start[2], move.pos[2]) >= SURFACE, (
            f"{move.name!r} moves the tip sideways while below the surface"
        )


def test_a_tip_in_the_tissue_rises_in_place_to_the_surface():
    """The clearance move is a lift, straight up, to the height that actually clears tissue."""
    start_xy = (150e-6, 0.0)
    start_z = -58e-6
    _state, pipette, _result = _run(start_position=(*start_xy, start_z), overshoot=3e-6)

    lift = _named(pipette, LIFT)
    assert lift.pos[2] == pytest.approx(SURFACE), "lifted to the surface, not to the descent start"
    assert lift.pos[:2] == pytest.approx(start_xy), "and lifted in place, before traversing"
    assert _named(pipette, CROSS).pos[2] == pytest.approx(SURFACE), "crosses at the clearance height"


def test_a_tip_already_clear_is_not_driven_down_to_traverse():
    """From above, the tip crosses at the height it is already at and only then descends."""
    start_z = 300e-6
    _state, pipette, _result = _run(start_position=(150e-6, 0.0, start_z), overshoot=3e-6)

    first = pipette.moves[0]
    assert first.pos[2] == pytest.approx(start_z), "the traverse holds the tip's own height"
    assert first.pos[:2] == pytest.approx(_named(pipette, APPROACH).pos[:2]), "and reaches the descent xy"


def test_a_descent_start_already_above_the_surface_needs_no_separate_traverse():
    """When the clearance height is the descent start itself, one lift is the whole climb."""
    surface = -60e-6  # marked below this target, so the descent start already clears it
    _state, pipette, _result = _run(
        start_position=(150e-6, 0.0, -80e-6), overshoot=3e-6, surface_depth=surface
    )

    approach = _named(pipette, APPROACH)
    assert approach.pos[2] > surface, "precondition: the descent start is above the surface"
    assert _named(pipette, LIFT).pos[2] == pytest.approx(approach.pos[2])
    assert [move.name for move in pipette.moves if move.name == CROSS] == []


def test_no_move_is_commanded_to_where_the_tip_already_is():
    """A zero-length move is a manipulator round trip for nothing, and per-driver behaviour."""
    for start in [(150e-6, 0.0, 300e-6), (150e-6, 0.0, -58e-6), (150e-6, 0.0, SURFACE)]:
        _state, pipette, _result = _run(start_position=start, overshoot=3e-6)
        for move in pipette.moves:
            assert not np.array_equal(move.start, move.pos), f"{move.name!r} is a zero-length move"


def test_overshoot_with_visual_target_tracking_warns():
    """The tracker already follows the cell, so the fixed axial offset is counted twice."""
    state, _pipette, _result = _run(start_position=(0.0, 0.0, 0.0), overshoot=3e-6, tracking=True)

    warnings = [m for m in state.messages if 'overshootDistance' in m and 'tracking' in m]
    assert len(warnings) == 1, state.messages


def test_overshoot_without_visual_target_tracking_does_not_warn():
    """The combination the option is actually for must stay quiet."""
    state, _pipette, _result = _run(start_position=(0.0, 0.0, 0.0), overshoot=3e-6, tracking=False)

    assert [m for m in state.messages if 'overshootDistance' in m] == []


def test_the_descent_stops_at_the_configured_depth_past_contact():
    """Float error in the accumulated depth must not cost a whole extra step of glass.

    The descent is quantised to stepSize, so depthPastContact of three 1 µm steps is reached
    on the third step; 2.9999999999999984e-06 failing `>= 3e-6` buys a fourth.
    """
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
