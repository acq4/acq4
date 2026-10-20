"""A cell's pass ends with the pipette out of the slice.

Two halves. parkCircle() is the queue's answer to "what does the tip have to
stay clear of" -- the cells this run has still to work, which nothing else on
the rig knows. _processCell's finally is the safety net that spends that answer:
a protocol should park itself at the point it knows the tip is finished with the
tissue, and this is what covers the protocol that does not, or that failed
before it got there.

The defect underneath both: a failed cell detect returns from the protocol with
the tip still down where detection stopped, and the *next* cell's tracker z-stack
is then taken through it -- while it goes on leaking internal into the tissue.
"""
from __future__ import annotations

import numpy as np
import pytest

from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import AbortExperiment
from acq4.experiment.orchestrator import PARK_PADDING, Orchestrator

from .test_actions_device import FakePipette


class _Cell:
    """A cell as the engine sees one: something with a global `position`."""

    def __init__(self, x, y, z=-50e-6, name=""):
        self.position = (x, y, z)
        self.name = name

    def __repr__(self):
        return f"<Cell {self.name or self.position}>"


def _orch(pf, pipette=None, cells=(), producer=None):
    orch = Orchestrator(
        pf, contextFactory=lambda cell: ExecutionContext(cell=cell, pipette=pipette)
    )
    for cell in cells:
        orch.enqueue(cell)
    if producer is not None:
        orch.setCellProducer(producer)
    return orch


# -- parkCircle --------------------------------------------------------------


def test_the_circle_covers_the_queue_and_the_cell_just_finished(make_pf):
    """Centre of mass of everything still to be worked, radius out to the
    furthest of them, plus the padding. The cell whose pass is ending is in
    there too: it can be re-queued from Area 5, the next tracker check re-images
    it, and it is the one the tip is standing over right now."""
    orch = _orch(make_pf(), cells=[_Cell(1e-3, 0.0), _Cell(-1e-3, 0.0)])

    center, radius = orch.parkCircle(_Cell(0.0, 0.0))

    assert center == pytest.approx(np.array([0.0, 0.0]))
    assert radius == pytest.approx(1e-3 + PARK_PADDING)


def test_the_circle_is_not_dragged_by_the_depth_the_cells_sit_at(make_pf):
    """An occlusion circle is a horizontal footprint; z says nothing about what
    the objective is looking through."""
    orch = _orch(make_pf(), cells=[_Cell(1e-3, 0.0, z=-500e-6)])

    center, radius = orch.parkCircle(_Cell(1e-3, 0.0, z=-20e-6))

    assert len(center) == 2
    assert radius == pytest.approx(PARK_PADDING)


def test_an_empty_queue_with_a_survey_still_to_come_clears_just_this_cell(make_pf):
    """Nothing is queued to stay clear of, so the circle collapses onto the cell
    that was being worked with a radius of just the padding: enough to get the
    tip out of the slice and off that cell, and no further, because the survey
    that follows re-parks against tiles this cannot know about yet."""
    orch = _orch(make_pf(), producer=lambda: [])

    center, radius = orch.parkCircle(_Cell(4e-3, -2e-3))

    assert center == pytest.approx(np.array([4e-3, -2e-3]))
    assert radius == pytest.approx(PARK_PADDING)


def test_nothing_queued_and_no_producer_sends_the_tip_home(make_pf):
    """The end of a run. A tip left hovering 100 um over the slice has nothing
    to be ready for."""
    orch = _orch(make_pf())

    assert orch.parkCircle(_Cell(0.0, 0.0)) is None


def test_an_exhausted_producer_sends_the_tip_home_too(make_pf):
    orch = _orch(make_pf(), producer=lambda: None)
    orch._refillQueue()  # the producer reports exhaustion

    assert orch.parkCircle(_Cell(0.0, 0.0)) is None


def test_cells_whose_position_cannot_be_read_produce_no_circle(make_pf):
    """A headless run or a test queue of bare sentinels cannot answer where the
    tip may stand, and home is the safe answer to a question with no answer."""
    orch = _orch(make_pf(), cells=["c1", "c2"], producer=lambda: [])

    assert orch.parkCircle("c3") is None


def test_a_cell_with_an_unreadable_position_does_not_spoil_the_others(make_pf):
    """One sentinel in the queue must not throw away the circle the real cells
    can still describe."""
    orch = _orch(make_pf(), cells=[_Cell(1e-3, 0.0), "not-a-cell"])

    center, radius = orch.parkCircle(_Cell(-1e-3, 0.0))

    assert center == pytest.approx(np.array([0.0, 0.0]))
    assert radius == pytest.approx(1e-3 + PARK_PADDING)


# -- the end-of-pass safety net ----------------------------------------------


def _parked(pip):
    return [call[1:3] for call in pip.pipetteDevice.park_calls]


def test_a_cell_that_fails_to_find_its_cell_still_leaves_the_slice(make_pf):
    """The reported defect, end to end: the protocol returns with the tip down
    in the tissue, and the pass does not finish until it is out."""
    pip = FakePipette()
    pip.state_name = "bath"
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None  # a protocol that parks nothing itself
    orch = _orch(pf, pipette=pip, cells=[_Cell(1e-3, 0.0)], producer=lambda: [])

    orch.run_sync_cell(_Cell(0.0, 0.0))

    assert len(pip.pipetteDevice.park_calls) == 1


def test_the_park_uses_the_circle_the_queue_describes(make_pf):
    pip = FakePipette()
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None
    orch = _orch(pf, pipette=pip, cells=[_Cell(2e-3, 0.0), _Cell(-2e-3, 0.0)])

    orch.run_sync_cell(_Cell(0.0, 0.0))

    (_speed, center, radius, _height), = pip.pipetteDevice.park_calls
    assert center == pytest.approx(np.array([0.0, 0.0]))
    assert radius == pytest.approx(2e-3 + PARK_PADDING)


def test_the_protocol_can_ask_for_the_same_circle_mid_run(make_pf):
    """The closure the orchestrator lends each context is what lets a protocol
    park at the point it knows the tip is done -- earlier, and better informed,
    than the safety net can."""
    seen = []
    pip = FakePipette()
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: seen.append(ctx.occlusion_circle())
    orch = _orch(pf, pipette=pip, cells=[_Cell(2e-3, 0.0)])

    orch.run_sync_cell(_Cell(0.0, 0.0))

    (center, radius), = seen
    assert center == pytest.approx(np.array([1e-3, 0.0]))
    assert radius == pytest.approx(1e-3 + PARK_PADDING)


def test_a_protocol_that_raises_still_leaves_the_tip_out_of_the_slice(make_pf):
    """The failures that most need the retraction are exactly the ones that
    skip a park written as the protocol's last statement."""
    pip = FakePipette()
    pf = make_pf()

    def _boom(ctx, **kwargs):
        raise RuntimeError("the rig fell over")

    pf.run = _boom
    orch = _orch(pf, pipette=pip, cells=[_Cell(1e-3, 0.0)])

    with pytest.raises(AbortExperiment):
        orch.run_sync_cell(_Cell(0.0, 0.0))

    assert len(pip.pipetteDevice.park_calls) == 1


def test_a_protocol_that_parked_already_is_not_made_to_park_twice(make_pf):
    """go_park does nothing to a tip that is already clear, so the ordinary cost
    of the safety net on a protocol that parks properly is a geometric
    comparison."""
    pip = FakePipette()
    pip.pipetteDevice.parked = True
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None
    orch = _orch(pf, pipette=pip, cells=[_Cell(1e-3, 0.0)])

    orch.run_sync_cell(_Cell(0.0, 0.0))

    assert pip.pipetteDevice.park_calls == []


def test_a_failed_park_does_not_replace_what_actually_ended_the_pass(make_pf):
    """This runs in a finally. A park that raised out of it would bury the
    failure the operator actually needs to see."""
    pip = FakePipette()
    pip.pipetteDevice.park_error = RuntimeError("the manipulator is wedged")
    pf = make_pf()

    def _boom(ctx, **kwargs):
        raise ValueError("the real failure")

    pf.run = _boom
    orch = _orch(pf, pipette=pip, cells=[_Cell(1e-3, 0.0)])

    with pytest.raises(AbortExperiment) as exc:
        orch.run_sync_cell(_Cell(0.0, 0.0))

    assert "the real failure" in str(exc.value)


def test_a_failed_park_ends_the_run_instead_of_starting_the_next_cell(make_pf):
    """A park that failed leaves the tip wherever the pass left it, which may be
    down in the tissue. The next queued cell's tracker check and approach both
    assume it was cleared, so the run stops at the cell boundary rather than
    driving glass against a pipette nobody knows the position of."""
    pip = FakePipette()
    pip.pipetteDevice.park_error = RuntimeError("the manipulator is wedged")
    pf = make_pf()
    runs = []
    pf.run = lambda ctx, **kwargs: runs.append(ctx.cell)
    orch = _orch(pf, pipette=pip, cells=[_Cell(0.0, 0.0), _Cell(1e-3, 0.0)])

    with pytest.raises(AbortExperiment) as exc:
        orch.run_sync()

    assert len(runs) == 1
    assert "park" in str(exc.value)


def test_a_failed_park_stops_the_survey_too(make_pf):
    """Surveying drives the scope over the slice. A pipette left standing in the
    light path -- or in the tissue -- is exactly what the park exists to clear
    before that happens, so an unparked tip stops the refill as well."""
    pip = FakePipette()
    pip.pipetteDevice.park_error = RuntimeError("the manipulator is wedged")
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None
    asked = []

    def _producer():
        # Raises rather than returning cells: a survey that does run must end
        # the test, not feed the queue a fresh cell whose own park fails again.
        asked.append(True)
        raise RuntimeError("the survey must not run with the tip unparked")

    orch = _orch(pf, pipette=pip, cells=[_Cell(0.0, 0.0)], producer=_producer)

    with pytest.raises(AbortExperiment):
        orch.run_sync()

    assert asked == []


def test_a_park_that_succeeded_leaves_the_run_free_to_continue(make_pf):
    """The halt is the failure's doing, not the park's: an ordinary pass works
    the whole queue."""
    pip = FakePipette()
    pf = make_pf()
    runs = []
    pf.run = lambda ctx, **kwargs: runs.append(ctx.cell)
    orch = _orch(pf, pipette=pip, cells=[_Cell(0.0, 0.0), _Cell(1e-3, 0.0)])

    orch.run_sync()

    assert len(runs) == 2


def test_a_failed_park_does_not_brick_the_orchestrator_for_later_runs(make_pf):
    """Starting the queue again is the operator saying they have dealt with the
    pipette, so the halt is per-run rather than a latch the rig cannot clear."""
    pip = FakePipette()
    pip.pipetteDevice.park_error = RuntimeError("the manipulator is wedged")
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None
    orch = _orch(pf, pipette=pip, cells=[_Cell(0.0, 0.0), _Cell(1e-3, 0.0)])

    with pytest.raises(AbortExperiment):
        orch.run_sync()

    pip.pipetteDevice.park_error = None

    orch.run_sync()  # the cell left queued is worked, with no exception


def test_a_run_with_no_pipette_parks_nothing_and_does_not_complain(make_pf):
    """The engine's own default context carries no pipette; a headless run must
    not fail a cell over having nothing to retract."""
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None
    orch = Orchestrator(pf)
    orch.enqueue("c1")

    orch.run_sync()  # no exception
