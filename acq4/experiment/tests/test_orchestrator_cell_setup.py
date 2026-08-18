"""Tests for what the Orchestrator does around each cell's protocol: the setup
before it (the pipette's target and the managed Cell data directory, each done
once per cell rather than once per attempt) and the close-out after it (the
cell's .acqtrack tracking history, saved however the pass ended)."""
import os

import pytest

import acq4.util.DataManager as dm
from acq4.experiment.exceptions import AbortExperiment, RetryCurrentCell
from acq4.experiment.context import ExecutionContext
from acq4.experiment.orchestrator import Orchestrator

from .test_actions_prompt_storage import FakeManager


class FakePatchPipette:
    """Records setCell() calls; optionally raises, standing in for a pipette that
    cannot take the cell (an unmappable position, say)."""

    def __init__(self, error=None, on_call=None):
        self.setCell_calls = []
        self.error = error
        self.on_call = on_call

    def setCell(self, cell, target=True):
        self.setCell_calls.append((cell, target))
        if self.on_call is not None:
            self.on_call(cell)
        if self.error is not None:
            raise self.error


def _orch(pf, pipette):
    return Orchestrator(
        pf, contextFactory=lambda cell: ExecutionContext(cell=cell, pipette=pipette)
    )


def test_each_cell_is_given_to_the_pipette_before_the_protocol_runs(make_pf):
    pf = make_pf()
    events = []
    pip = FakePatchPipette(on_call=lambda cell: events.append(("target", cell)))
    pf.run = lambda ctx, **kwargs: events.append(("run", ctx.cell))
    orch = _orch(pf, pip)
    orch.enqueue("c1")
    orch.enqueue("c2")
    orch.run_sync()
    assert events == [("target", "c1"), ("run", "c1"), ("target", "c2"), ("run", "c2")]


def test_a_retry_does_not_hand_the_same_cell_over_again(make_pf):
    # A retry restarts the protocol in place for a cell the pipette already has;
    # handing it over again would close the cell it is working (dropping its
    # tracking) between attempts.
    pf = make_pf()
    pip = FakePatchPipette()
    attempts = {"n": 0}

    def spy_run(ctx, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RetryCurrentCell("first attempt fails")

    pf.run = spy_run
    _orch(pf, pip).run_sync_cell("c1")
    assert attempts["n"] == 2
    assert pip.setCell_calls == [("c1", True)]


def test_a_context_without_a_pipette_hands_the_cell_nowhere(make_pf):
    # Headless / the engine's own default context: no pipette to target, and the
    # protocol still runs.
    pf = make_pf()
    finished = []
    orch = Orchestrator(pf)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.run_sync_cell("c1")
    assert finished == [("c1", "done")]


def test_a_pipette_that_cannot_take_the_cell_halts_the_run(make_pf):
    # No target means every subsequent move in the protocol would be made
    # against the previous cell's coordinate, so this halts rather than running.
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    pip = FakePatchPipette(error=ValueError("no mapping for that position"))
    orch = _orch(pf, pip)
    finished = []
    errors = []
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.sigRunError.connect(errors.append)
    with pytest.raises(AbortExperiment):
        orch.run_sync_cell("c1")
    assert ran == []
    assert finished == [("c1", "error")]
    assert [r.exc_type for r in errors] == ["OrchestrationError"]


# -- the cell's data directory -------------------------------------------


@pytest.fixture
def root_dir(tmp_path):
    return dm.getDirHandle(str(tmp_path), create=True)


def _dir_orch(pf, manager, entries=None):
    return Orchestrator(
        pf,
        contextFactory=lambda cell: ExecutionContext(
            cell=cell,
            manager=manager,
            on_log_action=(None if entries is None else entries.append),
        ),
    )


def test_each_cell_gets_its_own_managed_cell_directory(make_pf, root_dir):
    man = FakeManager(root_dir)
    pf = make_pf()
    seen = []
    pf.run = lambda ctx, **kwargs: seen.append(ctx.manager.getCurrentDir())
    orch = _dir_orch(pf, man)
    orch.enqueue("c1")
    orch.enqueue("c2")
    orch.run_sync()
    # Current by the time the protocol runs, so everything the run saves lands
    # in it without a protocol having to ask for one.
    assert [d.info().get("dirType") for d in seen] == ["Cell", "Cell"]
    assert seen[0].name() != seen[1].name()
    # Siblings under the storage directory, not one nested inside the other.
    assert [d.parent().name() for d in seen] == [root_dir.name()] * 2


def test_the_cell_directory_is_reported_to_the_ui(make_pf, root_dir):
    # The operator has to be able to find a cell's data; Area 5's timeline is
    # where the run says where it went.
    man = FakeManager(root_dir)
    pf = make_pf()
    entries = []
    _dir_orch(pf, man, entries).run_sync_cell("c1")
    assert [e.name for e in entries] == ["New Data Directory"]


def test_a_retry_reuses_the_cell_directory_it_already_made(make_pf, root_dir):
    # A retry is another attempt at the same cell, so its data belongs with the
    # first attempt's rather than in a second directory that looks like another
    # cell.
    man = FakeManager(root_dir)
    pf = make_pf()
    seen = []

    def spy_run(ctx, **kwargs):
        seen.append(ctx.manager.getCurrentDir())
        if len(seen) == 1:
            raise RetryCurrentCell("first attempt fails")

    pf.run = spy_run
    _dir_orch(pf, man).run_sync_cell("c1")
    assert len(seen) == 2
    assert seen[0].info().get("dirType") == "Cell"
    assert seen[0].name() == seen[1].name()


def test_a_context_without_a_manager_makes_no_directory(make_pf):
    # Headless / the engine's own default context: nowhere to save, and the
    # protocol still runs.
    pf = make_pf()
    finished = []
    orch = Orchestrator(pf)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.run_sync_cell("c1")
    assert finished == [("c1", "done")]


def test_a_storage_failure_halts_the_run(make_pf, root_dir):
    # Nowhere to save is not a cell to run: without this the run would patch
    # cell after cell into the previous cell's directory (or none at all).
    class _NoCellLevelManager(FakeManager):
        def folderTypesConfig(self):
            return {}

    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    orch = _dir_orch(pf, _NoCellLevelManager(root_dir))
    finished = []
    errors = []
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.sigRunError.connect(errors.append)
    with pytest.raises(AbortExperiment):
        orch.run_sync_cell("c1")
    assert ran == []
    assert finished == [("c1", "error")]
    assert [r.exc_type for r in errors] == ["OrchestrationError"]


# -- closing the cell's directory out ------------------------------------


class FakeTracker:
    """Stands in for a CellTracker: the attributes saveTrackingHistory checks and
    the save AcqTrackFile delegates to."""

    def __init__(self):
        self.tracking_results = [object()]
        self.saved_to = []

    def save_history(self, path):
        self.saved_to.append(path)
        with open(path, "w") as fh:
            fh.write("tracking history")


class FakeTrackedCell:
    """A cell that has been tracked, which is what makes it worth saving."""

    def __init__(self, name):
        self._name = name
        self._tracker = FakeTracker()

    def __repr__(self):
        return f"<cell {self._name}>"


def _acqtrack_files(dir_handle):
    return sorted(
        f for f in os.listdir(dir_handle.name()) if f.endswith(".acqtrack")
    )


def test_the_cells_tracking_history_is_saved_into_its_own_directory(make_pf, root_dir):
    man = FakeManager(root_dir)
    pf = make_pf()
    seen = []
    pf.run = lambda ctx, **kwargs: seen.append(ctx.manager.getCurrentDir())
    orch = _dir_orch(pf, man)
    first, second = FakeTrackedCell("c1"), FakeTrackedCell("c2")
    orch.enqueue(first)
    orch.enqueue(second)
    orch.run_sync()
    assert [_acqtrack_files(d) for d in seen] == [["tracking_history.acqtrack"]] * 2
    # Each cell's history in its own cell's directory, not both in one.
    assert first._tracker.saved_to == [
        os.path.join(seen[0].name(), "tracking_history.acqtrack")
    ]
    assert second._tracker.saved_to == [
        os.path.join(seen[1].name(), "tracking_history.acqtrack")
    ]


def test_the_tracking_history_is_saved_when_the_protocol_fails(make_pf, root_dir):
    # A failed attempt is exactly when an operator wants the tracking history:
    # it is the record of what the tracker saw before it went wrong.
    man = FakeManager(root_dir)
    pf = make_pf()
    seen = []

    def failing_run(ctx, **kwargs):
        seen.append(ctx.manager.getCurrentDir())
        raise RuntimeError("something in the protocol broke")

    pf.run = failing_run
    cell = FakeTrackedCell("c1")
    with pytest.raises(AbortExperiment):
        _dir_orch(pf, man).run_sync_cell(cell)
    assert _acqtrack_files(seen[0]) == ["tracking_history.acqtrack"]


def test_the_history_goes_to_the_cells_directory_not_the_current_one(make_pf, root_dir):
    # A protocol is free to move the current directory (a TaskRunner sequence
    # does), so the save must go to the directory this cell was given rather
    # than wherever the run left off.
    man = FakeManager(root_dir)
    elsewhere = root_dir.mkdir("elsewhere")
    pf = make_pf()
    seen = []

    def wandering_run(ctx, **kwargs):
        seen.append(ctx.manager.getCurrentDir())
        ctx.manager.setCurrentDir(elsewhere)

    pf.run = wandering_run
    _dir_orch(pf, man).run_sync_cell(FakeTrackedCell("c1"))
    assert _acqtrack_files(seen[0]) == ["tracking_history.acqtrack"]
    assert _acqtrack_files(elsewhere) == []


def test_the_current_directory_steps_back_out_of_the_finished_cell(make_pf, root_dir):
    # Whatever happens between cells -- the survey imaging a tile, most of all --
    # must not land inside the directory of the cell that just finished.
    man = FakeManager(root_dir)
    pf = make_pf()
    _dir_orch(pf, man).run_sync_cell(FakeTrackedCell("c1"))
    assert man.getCurrentDir().name() == root_dir.name()


def test_an_untracked_cell_leaves_no_history_behind(make_pf, root_dir):
    # Nothing to save is not a failure: a cell whose protocol never tracked it
    # (or never got that far) simply has no history.
    man = FakeManager(root_dir)
    pf = make_pf()
    seen = []
    pf.run = lambda ctx, **kwargs: seen.append(ctx.manager.getCurrentDir())
    _dir_orch(pf, man).run_sync_cell("c1")
    assert _acqtrack_files(seen[0]) == []
