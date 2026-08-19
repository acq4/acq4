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
from acq4.util.task import Stopped

from .test_actions_prompt_storage import FakeManager


class FakePatchPipette:
    """Records setCell() calls; optionally raises, standing in for a pipette that
    cannot take the cell (an unmappable position, say).

    Keeps the cell it was last given, the way PatchPipette does. That holding is
    what makes the handover a place a tracking history can be lost: the real
    setCell() closes the cell it is holding -- tracking off, pushed onto
    previousCells -- before taking the new one.
    """

    def __init__(self, error=None, on_call=None, cell=None):
        self.setCell_calls = []
        self.error = error
        self.on_call = on_call
        self.cell = cell

    def setCell(self, cell, target=True):
        self.setCell_calls.append((cell, target))
        if self.on_call is not None:
            self.on_call(cell)
        if self.error is not None:
            raise self.error
        self.cell = cell


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


class _NoCellLevelManager(FakeManager):
    """A manager that cannot make a Cell directory, so a cell's pass ends
    without one -- the storage failure that halts a run."""

    def folderTypesConfig(self):
        return {}


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


# -- no cell directory to save into --------------------------------------


def test_the_history_is_saved_when_no_cell_directory_could_be_made(make_pf, root_dir):
    # The storage failure halts the run before the protocol runs, but the cell
    # in hand can already be carrying a history -- the survey tracked it into
    # existence, and a re-queued cell arrives with its earlier attempt's
    # results. Somewhere is the requirement; the manager's current directory is
    # the somewhere, with the name auto-incremented since it is shared.
    man = _NoCellLevelManager(root_dir)
    pf = make_pf()
    cell = FakeTrackedCell("c1")
    with pytest.raises(AbortExperiment):
        _dir_orch(pf, man).run_sync_cell(cell)
    assert _acqtrack_files(root_dir) == ["tracking_history_000.acqtrack"]


def test_the_history_is_saved_when_the_context_carries_no_manager(make_pf, root_dir):
    # A contextFactory is free to build a context without a manager, which
    # leaves the cell with no directory of its own. The orchestrator's own
    # manager is still a place to write, and writing there beats losing the
    # history over a context that was built thin.
    man = FakeManager(root_dir)
    pf = make_pf()
    orch = Orchestrator(
        pf, manager=man, contextFactory=lambda cell: ExecutionContext(cell=cell)
    )
    orch.run_sync_cell(FakeTrackedCell("c1"))
    assert _acqtrack_files(root_dir) == ["tracking_history_000.acqtrack"]


def test_cells_sharing_the_fallback_directory_do_not_overwrite_each_other(
    make_pf, root_dir
):
    # The fallback directory is shared by every cell that lands in it, so the
    # second cell's history must not be written over the first's.
    man = FakeManager(root_dir)
    pf = make_pf()
    orch = Orchestrator(
        pf, manager=man, contextFactory=lambda cell: ExecutionContext(cell=cell)
    )
    orch.enqueue(FakeTrackedCell("c1"))
    orch.enqueue(FakeTrackedCell("c2"))
    orch.run_sync()
    assert _acqtrack_files(root_dir) == [
        "tracking_history_000.acqtrack",
        "tracking_history_001.acqtrack",
    ]


def test_a_run_with_nowhere_to_write_loses_the_history_quietly(make_pf):
    # The one silent path: a headless run has no manager at all, so there is no
    # directory to fall back to. Nothing to write into is not a reason to fail
    # the pass.
    pf = make_pf()
    finished = []
    cell = FakeTrackedCell("c1")
    orch = Orchestrator(pf)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.run_sync_cell(cell)
    assert finished == [(cell, "done")]
    assert cell._tracker.saved_to == []


# -- however the pass ended ----------------------------------------------


def test_the_tracking_history_is_saved_when_the_operator_stops_the_run(
    make_pf, root_dir
):
    # A stop lands mid-approach as often as anywhere, and what the tracker saw
    # up to that point is exactly the record of why the operator stopped.
    man = FakeManager(root_dir)
    pf = make_pf()
    seen = []

    def stopping_run(ctx, **kwargs):
        seen.append(ctx.manager.getCurrentDir())
        raise Stopped("operator pressed stop")

    pf.run = stopping_run
    with pytest.raises(Stopped):
        _dir_orch(pf, man).run_sync_cell(FakeTrackedCell("c1"))
    assert _acqtrack_files(seen[0]) == ["tracking_history.acqtrack"]


def test_the_tracking_history_is_saved_when_the_protocol_aborts_the_experiment(
    make_pf, root_dir
):
    # AbortExperiment leaves _processCell by propagating, past every return the
    # ordinary paths take; the save is in the finally so that route is covered
    # too.
    man = FakeManager(root_dir)
    pf = make_pf()
    seen = []

    def aborting_run(ctx, **kwargs):
        seen.append(ctx.manager.getCurrentDir())
        raise AbortExperiment("the region is unusable")

    pf.run = aborting_run
    with pytest.raises(AbortExperiment):
        _dir_orch(pf, man).run_sync_cell(FakeTrackedCell("c1"))
    assert _acqtrack_files(seen[0]) == ["tracking_history.acqtrack"]


# -- the handover to the pipette -----------------------------------------


def _pip_dir_orch(pf, manager, pipette):
    return Orchestrator(
        pf,
        manager=manager,
        contextFactory=lambda cell: ExecutionContext(
            cell=cell, manager=manager, pipette=pipette
        ),
    )


def test_a_cell_the_pipette_still_holds_is_saved_before_it_is_handed_a_new_one(
    make_pf, root_dir
):
    # setCell() closes the cell the pipette is holding -- tracking off, pushed
    # onto previousCells -- so a cell put there by anything other than this
    # orchestrator (AutomationDebug, a manual newCell) would go out of reach
    # with its history unwritten.
    man = FakeManager(root_dir)
    pf = make_pf()
    stranger = FakeTrackedCell("stranger")
    atHandover = []
    pip = FakePatchPipette(
        cell=stranger, on_call=lambda cell: atHandover.append(_acqtrack_files(root_dir))
    )
    _pip_dir_orch(pf, man, pip).run_sync_cell(FakeTrackedCell("c1"))
    # Written before the handover, not after it: by the time setCell() runs the
    # file is already on disk.
    assert atHandover == [["tracking_history_000.acqtrack"]]
    assert stranger._tracker.saved_to == [
        os.path.join(root_dir.name(), "tracking_history_000.acqtrack")
    ]


def test_tracking_recorded_after_a_cell_closed_out_is_saved_at_the_next_handover(
    make_pf, root_dir
):
    # A pipette's FSM state job is detached from the protocol that asked for it,
    # so it can still be tracking -- and still appending to that cell's tracker
    # -- after the cell's pass was closed out and its history written. Those
    # late results reach disk at the handover that drops the cell, or not at all.
    man = FakeManager(root_dir)
    pf = make_pf()
    seen = []
    pf.run = lambda ctx, **kwargs: seen.append(ctx.manager.getCurrentDir())
    first, second = FakeTrackedCell("c1"), FakeTrackedCell("c2")
    pip = FakePatchPipette()

    def contextFactory(cell):
        if cell is second:
            # Stands in for that still-running state job, deterministically, at
            # the one moment that matters: after c1's close-out, before the
            # handover that closes c1 on the pipette.
            first._tracker.tracking_results.append(object())
        return ExecutionContext(cell=cell, manager=man, pipette=pip)

    orch = Orchestrator(pf, manager=man, contextFactory=contextFactory)
    orch.enqueue(first)
    orch.enqueue(second)
    orch.run_sync()

    # Beside the close-out's file in c1's own directory, not over it and not in
    # the directory of the cell that displaced it.
    assert _acqtrack_files(seen[0]) == [
        "tracking_history.acqtrack",
        "tracking_history_000.acqtrack",
    ]
    assert _acqtrack_files(seen[1]) == ["tracking_history.acqtrack"]


def test_the_ordinary_handover_writes_no_second_copy(make_pf, root_dir):
    # The common case: a cell whose tracker gained nothing after its close-out
    # is already fully saved, and a duplicate file in every cell directory of
    # every run is noise an operator has to read past.
    man = FakeManager(root_dir)
    pf = make_pf()
    seen = []
    pf.run = lambda ctx, **kwargs: seen.append(ctx.manager.getCurrentDir())
    pip = FakePatchPipette()
    orch = _pip_dir_orch(pf, man, pip)
    orch.enqueue(FakeTrackedCell("c1"))
    orch.enqueue(FakeTrackedCell("c2"))
    orch.run_sync()
    assert [_acqtrack_files(d) for d in seen] == [["tracking_history.acqtrack"]] * 2
    assert _acqtrack_files(root_dir) == []


class _NoStorageDirManager(FakeManager):
    """A manager the operator never chose a storage directory for: asking it for
    the current directory raises, exactly as Manager.getCurrentDir does."""

    def __init__(self):
        FakeManager.__init__(self, None)
        self.asked = 0

    def getCurrentDir(self):
        self.asked += 1
        raise RuntimeError("Storage directory has not been set.")


def test_an_untracked_cell_goes_looking_for_no_fallback_directory(make_pf):
    # Asking is not free -- a manager with no storage directory raises -- so a
    # cell with no history to place must not ask. Otherwise every untracked cell
    # of such a run logs a failure to save a file that was never going to exist.
    man = _NoStorageDirManager()
    pf = make_pf()
    orch = Orchestrator(
        pf, manager=man, contextFactory=lambda cell: ExecutionContext(cell=cell)
    )
    orch.run_sync_cell("c1")
    assert man.asked == 0


def test_a_manager_that_cannot_say_where_to_write_does_not_fail_the_pass(make_pf):
    # And when there *is* something to place, the ask can still fail. The cell's
    # pass is already over; a bookkeeping failure must not become its outcome.
    man = _NoStorageDirManager()
    pf = make_pf()
    finished = []
    cell = FakeTrackedCell("c1")
    orch = Orchestrator(
        pf, manager=man, contextFactory=lambda cell: ExecutionContext(cell=cell)
    )
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.run_sync_cell(cell)
    assert man.asked == 1
    assert finished == [(cell, "done")]
