"""Tests for the Orchestrator queue loop, pause/resume, stop, and next-cell."""
import gc
import weakref

import pytest

from acq4.util.task import Stopped, Event, sleep
from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import (
    AbortExperiment,
    AdvanceToNextCell,
    BrokenPipette,
    RetryCurrentCell,
)
from acq4.experiment.orchestrator import Orchestrator


def test_run_sync_processes_whole_queue(make_pf):
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    orch = Orchestrator(pf)
    orch.enqueue("c1")
    orch.enqueue("c2")
    orch.run_sync()
    assert ran == ["c1", "c2"]  # ran once per cell, in queue order


def test_requestnextcell_skips_current(make_pf):
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    orch = Orchestrator(pf)
    finished = []
    orch.sigCellFinished.connect(lambda cell, status: finished.append((cell, status)))
    orch.enqueue("c1")
    orch.requestNextCell()  # before running: the cell boundary check skips c1
    orch.run_sync()
    assert ran == []                          # run() never called
    assert finished == [("c1", "skipped")]


def test_requestnextcell_cleared_when_cell_ends_normally_does_not_skip_following_cell(
    make_pf,
):
    """A "Next cell" request must apply to at most the cell it was made
    during. If that cell's protocol simply returns without raising a flow
    signal (e.g. a survey-only protocol with no ctx.next_cell() call), the
    flag must not survive into the next queue iteration -- otherwise the
    following queued cell is skipped without ever being attempted, with no
    error and no indication anything went wrong."""
    pf = make_pf()
    ran = []

    def run(ctx, **kwargs):
        ran.append(ctx.cell)
        if ctx.cell == "cell1":
            orch.requestNextCell()
        # returns normally -- no flow signal raised

    pf.run = run
    orch = Orchestrator(pf)
    orch.enqueue("cell1")
    orch.enqueue("cell2")
    finished = []
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.run_sync()
    assert ran == ["cell1", "cell2"]
    assert finished == [("cell1", "done"), ("cell2", "done")]


def test_stop_then_restart_does_not_skip_queued_cell(make_pf):
    """The operator flow: press Next cell mid-cell (nothing visible happens --
    the request is only ever consumed at a cell boundary), get impatient and
    press Stop, then press Start again. A request that arrived during the
    aborted cell must not outlive the run loop it was made during and consume
    a cell in the second run that was never its subject."""
    pf = make_pf()
    ran = []

    def run(ctx, **kwargs):
        ran.append(ctx.cell)
        if ctx.cell == "cell1":
            orch.requestNextCell()
            raise Stopped("operator pressed stop")

    pf.run = run
    orch = Orchestrator(pf)
    orch.enqueue("cell1")
    orch.enqueue("cell2")
    finished = []
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))

    orch.run_sync()  # a cooperative stop is a normal end to the run, not a raise

    assert orch._nextCellRequested is False  # must not survive the aborted run

    orch.run_sync()  # a second run, over the remaining queue
    assert ran == ["cell1", "cell2"]  # cell2 was actually attempted, not skipped
    # cell1 is reported "stopped" (the interrupted cell), then cell2 "done".
    assert finished == [("cell1", "stopped"), ("cell2", "done")]


def test_run_sync_stop_mid_action_completes_without_raising_and_leaves_queue(make_pf):
    """A cooperative stop mid-action is a normal way for run_sync() to end --
    not an exception the caller must catch -- and the queue's remaining cells
    are still queued afterward (a stop is not a queue-drain)."""
    pf = make_pf()
    ran = []

    def run(ctx, **kwargs):
        ran.append(ctx.cell)
        if ctx.cell == "cell1":
            raise Stopped("operator pressed stop")

    pf.run = run
    orch = Orchestrator(pf)
    orch.enqueue("cell1")
    orch.enqueue("cell2")

    orch.run_sync()  # must not raise

    assert ran == ["cell1"]  # cell2 never attempted -- the run ended at the stop
    assert list(orch._queue) == ["cell2"]  # remaining cells still queued, not drained


def test_stop_logs_info_with_reason_not_error(make_pf, caplog):
    """The operator's Stop is not a bug, so it must not be logged as one:
    info level, with the reason if one was given, never error/exc_info."""
    import logging

    pf = make_pf()
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(Stopped("operator pressed stop"))
    orch = Orchestrator(pf)
    orch.enqueue("cell1")

    with caplog.at_level(logging.INFO, logger="acq4.experiment.orchestrator"):
        orch.run_sync()

    assert not any(r.levelno >= logging.WARNING for r in caplog.records)
    assert any(
        r.levelno == logging.INFO and "operator pressed stop" in r.getMessage()
        for r in caplog.records
    )


def test_start_then_stop_onLoopFinished_receives_no_exception(make_pf, monkeypatch):
    """start() + stop() must hand _onLoopFinished exc=None for a cooperative
    stop -- that hook's error log (see _onLoopFinished) must not fire for an
    operator-initiated Stop."""
    gate = Event()       # never set -> run() blocks
    started = Event()

    pf = make_pf()

    def blocking_run(ctx, **kwargs):
        started.set()
        gate.wait()  # stop-aware; raises Stopped on stop()

    pf.run = blocking_run
    orch = Orchestrator(pf)
    orch.enqueue("c1")

    received = []
    original = orch._onLoopFinished

    def spy(result, exc):
        received.append(exc)
        original(result, exc)

    monkeypatch.setattr(orch, "_onLoopFinished", spy)

    task = orch.start()
    started.wait(timeout=5)
    orch.stop("test stop")
    task.wait(timeout=5)  # must not raise

    assert received == [None]  # _onLoopFinished saw no exception for a cooperative stop


def test_cleanup_failure_during_stop_propagates_out_of_run_instead_of_stopped(
    make_pf, fake_pip_factory, monkeypatch
):
    """_safe_abort is called from inside _drive_fsm's `except (Stopped,
    AdvanceToNextCell)` clause; if the pipette's state job fails to stop (the
    pipette didn't respond), that failure must still surface to the operator
    -- it must propagate out of the run, and it must not be mistaken for the
    Stopped that triggered the abort."""
    from acq4.experiment.actions import fsm as fsm_mod
    from acq4.experiment.actions.fsm import patch as fsm_patch

    pip = fake_pip_factory([])  # "approach" repeats forever without a request

    def failing_stop(reason=None, wait=False):
        raise RuntimeError("pipette did not respond to stop")

    original_get_state = pip.getState

    def get_state_with_failing_stop():
        job = original_get_state()
        job.stop = failing_stop
        return job

    pip.getState = get_state_with_failing_stop

    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    calls = {"n": 0}

    def fake_check_stop():
        calls["n"] += 1
        if calls["n"] > 1:
            raise Stopped("stopped by operator")

    monkeypatch.setattr(fsm_mod, "check_stop", fake_check_stop)

    def run(ctx, **kwargs):
        fsm_patch(ctx)

    pf = make_pf()
    pf.run = run

    def contextFactory(cell):
        return ExecutionContext(cell=cell, pipette=pip)

    orch = Orchestrator(pf, contextFactory=contextFactory)
    orch.enqueue("cell1")

    with pytest.raises(AbortExperiment) as excinfo:
        orch.run_sync()

    # The RuntimeError from the failed cleanup propagated (wrapped in
    # AbortExperiment by _processCell's broad except, same as any other
    # unexpected exception) -- not the Stopped that triggered the abort.
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert not isinstance(excinfo.value.__cause__, Stopped)


def test_error_exit_then_restart_does_not_skip_queued_cell(make_pf):
    """Same leak as test_stop_then_restart_does_not_skip_queued_cell, but via
    the OrchestrationError exit (which re-raises as AbortExperiment) instead
    of Stopped -- both propagate out of _runLoopBody by raising rather than
    returning, so both must clear the request on the way out."""
    pf = make_pf()
    ran = []

    def run(ctx, **kwargs):
        ran.append(ctx.cell)
        if ctx.cell == "cell1":
            orch.requestNextCell()
            raise BrokenPipette("pipette broke mid-cell")

    pf.run = run
    orch = Orchestrator(pf)
    orch.enqueue("cell1")
    orch.enqueue("cell2")
    finished = []
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))

    with pytest.raises(AbortExperiment):
        orch.run_sync()

    assert orch._nextCellRequested is False  # must not survive the aborted run

    orch.run_sync()  # a second run, over the remaining queue
    assert ran == ["cell1", "cell2"]  # cell2 was actually attempted, not skipped
    assert finished == [("cell1", "error"), ("cell2", "done")]


def test_run_sync_cell_raising_then_run_sync_does_not_skip_queued_cell(make_pf):
    """run_sync_cell() has no _runLoopBody frame around it, so a request left
    set by a run_sync_cell() call that raises is not touched by
    _runLoopBody's finally at all. A later run_sync() over a queued cell must
    still attempt that cell rather than silently skip it for a request that
    was never its own."""
    pf = make_pf()
    ran = []

    def run(ctx, **kwargs):
        ran.append(ctx.cell)
        if ctx.cell == "solo-cell":
            orch.requestNextCell()
            raise Stopped("operator pressed stop")

    pf.run = run
    orch = Orchestrator(pf)
    finished = []
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))

    with pytest.raises(Stopped):
        orch.run_sync_cell("solo-cell")

    assert orch._nextCellRequested is False  # must not survive the raising call

    orch.enqueue("cell2")
    orch.run_sync()  # a separate run, over an unrelated queued cell
    assert ran == ["solo-cell", "cell2"]  # cell2 was actually attempted, not skipped
    # solo-cell is reported "stopped" (the interrupted cell), then cell2 "done".
    assert finished == [("solo-cell", "stopped"), ("cell2", "done")]


def test_pause_resume_toggle_status(make_pf):
    pf = make_pf()
    orch = Orchestrator(pf)
    statuses = []
    orch.sigStatus.connect(statuses.append)
    orch.pause()
    assert orch._pauseEvent.is_set() is False
    orch.resume()
    assert orch._pauseEvent.is_set() is True


def test_stop_aborts_running_action(make_pf, qtbot):
    gate = Event()       # never set -> run() blocks
    started = Event()
    aborted = []

    pf = make_pf()

    def blocking_run(ctx, **kwargs):
        started.set()
        try:
            gate.wait()  # stop-aware; raises Stopped on stop()
        finally:
            aborted.append("a")

    pf.run = blocking_run
    orch = Orchestrator(pf)
    orch.enqueue("c1")
    task = orch.start()
    started.wait()       # wait until the protocol function is running
    orch.stop("test stop")
    task.wait(timeout=5)  # a cooperative stop is a normal end to the run, not a raise
    assert aborted == ["a"]  # the protocol's own try/finally ran on stop


def test_pause_is_honored_across_a_retry(make_pf, qtbot):
    """A protocol retrying against a persistent failure restarts from the top
    of _processCell's own retry loop, not through _runLoopBody -- so Pause
    (checked only in _runLoopBody until this fix) must also be checked at the
    top of that retry loop, or a persistently-retrying protocol ignores
    Pause completely."""
    pf = make_pf()
    calls = {"n": 0}

    def run(ctx, **kwargs):
        calls["n"] += 1
        sleep(0.005)  # paces retries out so pause/resume can be observed
        raise RetryCurrentCell("always fails")

    pf.run = run
    orch = Orchestrator(pf, maxRetries=100_000)
    orch.enqueue("cell1")

    orch.start()
    qtbot.waitUntil(lambda: calls["n"] >= 2, timeout=5000)

    orch.pause()
    qtbot.wait(20)  # let any in-flight attempt finish and hit the retry loop's top
    countAtPause = calls["n"]
    qtbot.wait(100)
    assert calls["n"] == countAtPause, "retries continued after pause()"

    orch.resume()
    qtbot.waitUntil(lambda: calls["n"] > countAtPause, timeout=5000)

    orch.stop("test cleanup")
    orch.wait(timeout=5)  # a cooperative stop is a normal end to the run, not a raise


def test_pause_is_honored_between_actions_within_one_cell(make_pf, qtbot):
    """Pause used to be checked only at cell and retry boundaries, so a long
    protocol ignored it for the whole cell. The orchestrator binds
    ctx.checkpoint, and ctx.log_action() calls it, so a pause now lands at the
    next action boundary within the cell."""
    pf = make_pf()
    entered = []

    def run(ctx, **kwargs):
        while True:  # ended by the orch.stop() below, via sleep's Stopped
            with ctx.log_action("An Action"):
                entered.append(len(entered))
                sleep(0.005)  # paces actions out so pause/resume can be observed

    pf.run = run
    orch = Orchestrator(pf)
    orch.enqueue("cell1")

    orch.start()
    qtbot.waitUntil(lambda: len(entered) >= 2, timeout=5000)

    orch.pause()
    qtbot.wait(20)  # let the in-flight action finish and hit the next checkpoint
    countAtPause = len(entered)
    qtbot.wait(100)
    assert len(entered) == countAtPause, "actions continued after pause()"

    orch.resume()
    qtbot.waitUntil(lambda: len(entered) > countAtPause, timeout=5000)

    orch.stop("test cleanup")
    orch.wait(timeout=5)  # a cooperative stop is a normal end to the run


def test_stop_during_a_mid_action_pause_ends_the_run(make_pf, qtbot):
    """_pauseEvent is gentletask's stop-aware Event, so a Stop while parked at a
    mid-cell checkpoint raises Stopped rather than wedging until Resume. The
    checkpoint inherits that; this pins it so a future mechanism swap cannot
    quietly lose it."""
    pf = make_pf()
    entered = []

    def run(ctx, **kwargs):
        while True:
            with ctx.log_action("An Action"):
                entered.append(len(entered))
                sleep(0.005)

    pf.run = run
    orch = Orchestrator(pf)
    orch.enqueue("cell1")

    task = orch.start()
    qtbot.waitUntil(lambda: len(entered) >= 2, timeout=5000)
    orch.pause()
    qtbot.wait(50)  # parked at a checkpoint, not merely requested

    orch.stop("test stop")
    task.wait(timeout=5)  # must not need a resume() to come back


def test_checkpoint_binding_tolerates_a_context_factory_returning_none(make_pf):
    # Mirrors the next_cell_requested guard: a contextFactory is free to hand
    # back None, and the binding must not turn that into an AttributeError.
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx)
    orch = Orchestrator(pf, contextFactory=lambda cell: None)
    orch.enqueue("cell1")
    orch.run_sync()
    assert ran == [None]


def test_orchestrator_binds_checkpoint_onto_the_context(make_pf):
    pf = make_pf()
    seen = []
    pf.run = lambda ctx, **kwargs: seen.append(ctx.checkpoint)
    orch = Orchestrator(pf)
    orch.enqueue("cell1")
    orch.run_sync()
    # Bound to the orchestrator's own pause check, not left at the default no-op.
    assert seen == [orch._checkPause]


def test_requestnextcell_mid_poll_abandons_cell_and_advances_queue(
    make_pf, fake_pip_factory, qtbot
):
    """The operator flow: requesting the next cell while a protocol is parked
    inside actions.fsm's poll loop (where a cell spends nearly all its
    wall-clock) must abandon the current cell as "skipped" and let the queue
    advance to the next one -- not be silently dropped, as it was when the
    flag was only ever checked (and cleared) between whole cells."""
    from acq4.experiment.actions.fsm import patch as fsm_patch

    # No state_sequence: getState() reports whatever setState() last set
    # ("approach", not a Patch terminal) forever, so without the mid-poll
    # request this would never return on its own.
    pip = fake_pip_factory([])
    entered = Event()

    def run(ctx, **kwargs):
        if ctx.cell == "cell1":
            entered.set()
            fsm_patch(ctx)
        return None

    pf = make_pf()
    pf.run = run

    def contextFactory(cell):
        return ExecutionContext(cell=cell, pipette=pip)

    orch = Orchestrator(pf, contextFactory=contextFactory)
    orch.enqueue("cell1")
    orch.enqueue("cell2")
    finished = []
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))

    orch.start()
    entered.wait(timeout=5)
    qtbot.wait(50)  # let a few poll iterations actually happen
    orch.requestNextCell()
    # sigCellFinished is emitted from the worker thread and queued to the GUI
    # thread; waitUntil both pumps the event loop and polls, so the queued
    # deliveries actually arrive rather than sitting unprocessed while the
    # main thread blocks in a plain (non-pumping) orch.wait().
    qtbot.waitUntil(lambda: len(finished) == 2, timeout=5000)

    assert finished == [("cell1", "skipped"), ("cell2", "done")]
    # The pipette's in-flight FSM job was told to stop, not left running
    # underneath the cell the orchestrator already moved on from.
    assert len(pip.stop_calls) == 1


def test_requestnextcell_mid_poll_swallowed_by_protocol_halts_with_error(
    make_pf, fake_pip_factory
):
    """actions.fsm's poll-loop checkpoint raises AdvanceToNextCell the same
    way a flow action does -- so a protocol with a broad except around an
    FSM action must not be able to swallow a mid-poll abandon invisibly. The
    cell must be reported "error" and the run must halt with
    AbortExperiment, not report a false "done" while the pipette was
    actually abandoned mid-FSM."""
    from acq4.experiment.actions.fsm import patch as fsm_patch

    # No state_sequence: "approach" is not a Patch terminal, so without the
    # mid-poll request this would poll forever.
    pip = fake_pip_factory([])

    def run(ctx, **kwargs):
        # Simulates the operator's "Next cell" button firing before the poll
        # loop's next checkpoint (run_sync is single-threaded, so this simply
        # has to happen before fsm_patch's first check to reproduce it).
        orch.requestNextCell()
        try:
            fsm_patch(ctx)
        except Exception:
            pass  # a protocol author's broad except, swallowing the abandon
        return None

    pf = make_pf()
    pf.run = run

    def contextFactory(cell):
        return ExecutionContext(cell=cell, pipette=pip)

    orch = Orchestrator(pf, contextFactory=contextFactory)
    orch.enqueue("cell1")
    finished = []
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))

    with pytest.raises(AbortExperiment):
        orch.run_sync()

    assert finished == [("cell1", "error")]
    # The FSM job was still safely aborted even though the protocol swallowed
    # the exception -- the orchestrator's detection is independent of that.
    assert len(pip.stop_calls) == 1


def test_finished_task_does_not_leave_qobject_cycle(make_pf, qtbot):
    """Regression test for the exit-segfault root cause: Orchestrator and its
    QtFriendlyTask are both QObjects, so a permanent orch<->task reference cycle
    can only be reclaimed by Python's cyclic GC -- non-deterministically, off
    Qt's safe teardown path. Once a run has finished, plain refcounting alone
    (cyclic GC disabled) must be enough to free both.
    """
    gate = Event()
    started = Event()

    pf = make_pf()

    def blocking_run(ctx, **kwargs):
        started.set()
        gate.wait()

    pf.run = blocking_run
    # A plain function, not a bound method of orch, so the orchestrator's own
    # self._contextFactory attribute does not itself create a self-cycle --
    # this test is targeted at the orch<->task cycle specifically.
    orch = Orchestrator(pf, contextFactory=lambda cell: None)
    orch.enqueue("c1")
    task = orch.start()
    started.wait()  # protocol function is parked in run(), definitely not finished

    # Connect to sigFinished BEFORE releasing the gate, so there is no race
    # between the task starting/finishing and us starting to listen.
    with qtbot.waitSignal(task.sigFinished, timeout=5000):
        gate.set()  # let the protocol function, and the run loop, finish

    # task.wait() is NOT a sufficient barrier here: _TaskCore._finish() (which
    # sets the done event sigFinished waits on) runs inside ThreadTask._run(),
    # which is itself the target of the worker's own threading.Thread --
    # still inside Thread.run()'s try/finally at that point. Thread.run()'s
    # own finally clears self._target/self._args/self._kwargs only AFTER
    # _run() returns, and until that unwind completes, the worker thread's
    # frame keeps task._run (a bound method of task) alive via Thread._args,
    # which keeps task itself alive -- exactly the kind of retainer that
    # makes the refcounting proof below flaky under gc.disable(). There is no
    # public join() on Task/ThreadTask, so join the underlying
    # threading.Thread directly: once it returns, Thread.run()'s finally has
    # already cleared that reference, so no race remains between "sigFinished
    # delivered" and "the worker thread has fully unwound".
    task._thread.join(timeout=5)
    assert not task._thread.is_alive()

    task_ref = weakref.ref(task)
    orch_ref = weakref.ref(orch)

    gc.disable()
    try:
        del task
        del orch
        assert orch_ref() is None, "Orchestrator survived refcounting alone -- a cycle remains"
        assert task_ref() is None, "Task survived refcounting alone -- a cycle remains"
    finally:
        gc.collect()
        gc.enable()


def test_current_cell_names_the_popped_cell_only_while_it_is_processed(make_pf):
    """currentCell() is the cell being processed right now: the one popped off
    the queue, from the pop until that pass ends, and nothing before or after."""
    pf = make_pf()
    seen = []
    pf.run = lambda ctx, **kwargs: seen.append(orch.currentCell())
    orch = Orchestrator(pf)
    orch.enqueue("c1")
    orch.enqueue("c2")

    assert orch.currentCell() is None  # queued is not in hand

    orch.run_sync()

    assert seen == ["c1", "c2"]  # each cell in hand while its own protocol ran
    assert orch.currentCell() is None  # the queue drained; nothing left in hand


def test_the_cell_is_in_hand_before_the_context_factory_runs(make_pf):
    """The assertion that pins the race abandonCellInHand() closes: the cell
    must be in hand from the moment it leaves the queue, not from whenever its
    context is built and sigCurrentCell announced. contextFactory is
    caller-supplied work -- a device query, an image load -- so anything that
    keys off the announcement instead has a window as wide as whatever that
    factory does, widening silently as it grows.

    A factory that raises proves both halves at once: it observed the cell
    already in hand with nothing yet announced, and the finally released it
    anyway on a path that leaves _processCell without any disposition at all.
    """
    pf = make_pf()
    observed = []
    announced = []

    def contextFactory(cell):
        observed.append(orch.currentCell())
        raise RuntimeError("context construction failed")

    orch = Orchestrator(pf, contextFactory=contextFactory)
    orch.sigCurrentCell.connect(announced.append)
    orch.enqueue("c1")

    with pytest.raises(RuntimeError):
        orch.run_sync()

    assert observed == ["c1"]  # in hand before any context existed for it
    # sigCurrentCell(None) from _runLoopBody's finally, and never "c1": the cell
    # was in hand strictly earlier than anything announced about it.
    assert announced == [None]
    assert orch.currentCell() is None


@pytest.mark.parametrize(
    "raised, status, escapes",
    [
        (None, "done", None),
        (AdvanceToNextCell("protocol asked for the next cell"), "skipped", None),
        (RetryCurrentCell("always fails"), "retry-exhausted", None),
        (Stopped("operator pressed stop"), "stopped", None),
        (BrokenPipette("pipette broke mid-cell"), "error", AbortExperiment),
    ],
    ids=["done", "skipped", "retry-exhausted", "stopped", "error"],
)
def test_the_cell_in_hand_is_released_on_every_terminal_outcome(
    make_pf, raised, status, escapes
):
    """Every way a pass can end has to release the cell -- including the three
    that leave by raising -- or the orchestrator goes on naming a cell it is not
    working, and keeps it alive with it. The release comes after the terminal
    disposition is reported, so a slot handling that disposition can still ask
    what it was about."""
    pf = make_pf()

    def run(ctx, **kwargs):
        if raised is not None:
            raise raised

    pf.run = run
    # maxRetries=0 so the one RetryCurrentCell above exhausts immediately.
    orch = Orchestrator(pf, maxRetries=0)
    atFinish = []
    orch.sigCellFinished.connect(
        lambda cell, s: atFinish.append((s, orch.currentCell()))
    )
    orch.enqueue("c1")

    if escapes is None:
        orch.run_sync()
    else:
        with pytest.raises(escapes):
            orch.run_sync()

    assert atFinish == [(status, "c1")]  # still in hand as the disposition lands
    assert orch.currentCell() is None


def test_the_cell_in_hand_is_released_when_the_boundary_check_skips_it(make_pf):
    """A "Next cell" request consumed at the top of _processCell's retry loop
    reports "skipped" without the protocol, or even the context, ever existing --
    the earliest a pass can end, and the cell is in hand for all of it because
    the pop already happened."""
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    orch = Orchestrator(pf)
    atFinish = []
    orch.sigCellFinished.connect(
        lambda cell, s: atFinish.append((s, orch.currentCell()))
    )
    orch.enqueue("c1")
    orch.requestNextCell()

    orch.run_sync()

    assert ran == []  # run() never called
    assert atFinish == [("skipped", "c1")]
    assert orch.currentCell() is None


def test_the_cell_stays_in_hand_across_a_retry_that_loops_in_place(make_pf):
    """A retry restarts the same cell inside the same _processCell call, so it
    never leaves the orchestrator's hand -- releasing it on the mid-flight
    "retry" disposition would report nothing in hand while the pipette is still
    being driven at that cell."""
    pf = make_pf()
    seen = []
    calls = {"n": 0}

    def run(ctx, **kwargs):
        seen.append(orch.currentCell())
        calls["n"] += 1
        if calls["n"] < 3:
            raise RetryCurrentCell("not yet")

    pf.run = run
    orch = Orchestrator(pf, maxRetries=10)
    atFinish = []
    orch.sigCellFinished.connect(
        lambda cell, s: atFinish.append((s, orch.currentCell()))
    )
    orch.enqueue("c1")

    orch.run_sync()

    assert seen == ["c1", "c1", "c1"]  # in hand for every pass at the same cell
    assert atFinish == [("retry", "c1"), ("retry", "c1"), ("done", "c1")]
    assert orch.currentCell() is None


def test_run_sync_cell_takes_the_cell_in_hand_and_releases_it(make_pf):
    """The single-cell entry point never goes through _runLoopBody's popleft, so
    currentCell() has to be honest for it too -- headless callers and
    Autopatch/tests/test_teardown.py both reach a cell this way."""
    pf = make_pf()
    seen = []
    pf.run = lambda ctx, **kwargs: seen.append(orch.currentCell())
    orch = Orchestrator(pf)

    orch.run_sync_cell("solo-cell")

    assert seen == ["solo-cell"]
    assert orch.currentCell() is None


def test_run_sync_cell_releases_the_cell_in_hand_when_the_pass_raises(make_pf):
    """Stopped propagates straight out of run_sync_cell -- there is no
    _runLoopBody frame around it to end the run normally -- so the release
    cannot depend on that call returning."""
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(
        Stopped("operator pressed stop")
    )
    orch = Orchestrator(pf)

    with pytest.raises(Stopped):
        orch.run_sync_cell("solo-cell")

    assert orch.currentCell() is None


def test_a_stopped_run_leaves_no_cell_in_hand(make_pf):
    """A run abandoned rather than completed must leave the orchestrator holding
    no cell: it would otherwise be a retention leak reachable from an
    orchestrator nothing is looking after any more (see
    Autopatch/tests/test_teardown.py for the segfault that makes that matter).
    The cooperative stop unwinds the protocol, which unwinds _processCell, whose
    finally is what does the release."""
    gate = Event()  # never set -> run() blocks until the stop raises
    started = Event()

    pf = make_pf()

    def blocking_run(ctx, **kwargs):
        started.set()
        gate.wait()  # stop-aware; raises Stopped on stop()

    pf.run = blocking_run
    orch = Orchestrator(pf)
    orch.enqueue("c1")

    task = orch.start()
    started.wait(timeout=5)
    assert orch.currentCell() == "c1"  # in hand while the run is in flight
    orch.stop("test stop")
    task.wait(timeout=5)  # a cooperative stop is a normal end to the run

    assert orch.currentCell() is None


@pytest.mark.parametrize(
    "raised, status, escapes",
    [
        (None, "done", None),
        (AdvanceToNextCell("protocol asked for the next cell"), "skipped", None),
        (RetryCurrentCell("always fails"), "retry-exhausted", None),
        (Stopped("operator pressed stop"), "stopped", None),
        (BrokenPipette("pipette broke mid-cell"), "error", AbortExperiment),
    ],
    ids=["done", "skipped", "retry-exhausted", "stopped", "error"],
)
def test_an_abandoned_cell_reports_no_terminal_disposition(
    make_pf, raised, status, escapes
):
    """Every way a pass can terminate has to stay silent for a cell whose tissue
    is gone -- a terminal disposition is what makes a cell re-queueable, so any
    one of these leaking would offer a coordinate on discarded tissue back up
    for reuse.

    Each case is run twice, abandoning only the second time, so the empty list
    is measured against the disposition the very same scenario reports without
    the abandon rather than against a default that would hold either way.
    """

    def runScenario(abandon):
        pf = make_pf()

        def run(ctx, **kwargs):
            if abandon:
                orch.abandonCellInHand()
            if raised is not None:
                raise raised

        pf.run = run
        # maxRetries=0 so the one RetryCurrentCell above exhausts immediately.
        orch = Orchestrator(pf, maxRetries=0)
        finished = []
        statuses = []
        orch.sigCellFinished.connect(lambda cell, s: finished.append((cell, s)))
        orch.sigStatus.connect(statuses.append)
        orch.enqueue("c1")
        if escapes is None:
            orch.run_sync()
        else:
            with pytest.raises(escapes):
                orch.run_sync()
        return finished, statuses

    reported, reportedStatuses = runScenario(abandon=False)
    assert reported == [("c1", status)]

    suppressed, suppressedStatuses = runScenario(abandon=True)
    assert suppressed == []
    # Only sigCellFinished is suppressed: the run's own status stream is what
    # Area 3 reads, and an abandoned cell that errors is still an error.
    assert suppressedStatuses == reportedStatuses


def test_an_abandoned_cell_still_leaves_the_run_loop_free_to_continue(make_pf):
    """Suppressing the disposition must not swallow the cell's release from the
    in-hand state or wedge the loop: the cells queued behind it still run."""
    pf = make_pf()
    ran = []

    def run(ctx, **kwargs):
        ran.append(ctx.cell)
        if ctx.cell == "c1":
            orch.abandonCellInHand()

    pf.run = run
    orch = Orchestrator(pf)
    orch.enqueue("c1")
    orch.enqueue("c2")

    orch.run_sync()

    assert ran == ["c1", "c2"]
    assert orch.currentCell() is None


def test_the_abandoned_marking_does_not_leak_onto_a_later_cell(make_pf):
    """The mirror-image defect, and the worse one: a marking left set would
    silently swallow the disposition of a cell on perfectly good tissue, so its
    row would never become reusable and the operator would lose that record."""
    pf = make_pf()

    def run(ctx, **kwargs):
        if ctx.cell == "c1":
            orch.abandonCellInHand()

    pf.run = run
    orch = Orchestrator(pf)
    finished = []
    orch.sigCellFinished.connect(lambda cell, s: finished.append((cell, s)))
    orch.enqueue("c1")
    orch.enqueue("c2")

    orch.run_sync()

    assert finished == [("c2", "done")]


def test_abandoning_with_nothing_in_hand_marks_nothing(make_pf):
    """A call made between passes -- a New slice click delivered while the queue
    is draining or a survey is imaging -- has no cell to abandon, and must not
    arm itself against whichever cell the loop reaches next."""
    pf = make_pf()
    orch = Orchestrator(pf)
    finished = []
    orch.sigCellFinished.connect(lambda cell, s: finished.append((cell, s)))
    orch.enqueue("c1")

    orch.abandonCellInHand()  # nothing in hand: the queue has not been popped
    orch.run_sync()

    assert finished == [("c1", "done")]


def test_an_abandoned_cell_still_reports_a_retry_that_loops_in_place(make_pf):
    """"retry" is mid-flight, not a disposition, so it is not suppressed and the
    marking is not consumed by it: the terminal disposition the retries lead to
    is the one that has to stay silent."""
    pf = make_pf()
    calls = {"n": 0}

    def run(ctx, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            orch.abandonCellInHand()
        if calls["n"] < 3:
            raise RetryCurrentCell("not yet")

    pf.run = run
    orch = Orchestrator(pf, maxRetries=10)
    finished = []
    orch.sigCellFinished.connect(lambda cell, s: finished.append((cell, s)))
    orch.enqueue("c1")

    orch.run_sync()

    assert calls["n"] == 3  # the retries really did loop in place
    assert finished == [("c1", "retry"), ("c1", "retry")]  # and no "done"


def test_an_abandoned_cell_skipped_at_the_boundary_check_stays_silent(make_pf):
    """The earliest a pass can terminate: the "Next cell" request consumed at the
    top of _processCell's retry loop, before the protocol or even the context
    exists on that iteration. Reached here by abandoning and requesting during
    the first pass and then retrying, so the request is waiting when the loop
    comes back round -- the cell is in hand for all of it."""
    pf = make_pf()
    calls = {"n": 0}

    def run(ctx, **kwargs):
        calls["n"] += 1
        orch.abandonCellInHand()
        orch.requestNextCell()
        raise RetryCurrentCell("go round once so the boundary check runs again")

    pf.run = run
    orch = Orchestrator(pf, maxRetries=10)
    finished = []
    orch.sigCellFinished.connect(lambda cell, s: finished.append((cell, s)))
    orch.enqueue("c1")

    orch.run_sync()

    assert calls["n"] == 1  # the second pass was skipped before run() was reached
    assert finished == [("c1", "retry")]  # and no "skipped"


def test_an_abandoned_cells_swallowed_flow_signal_stays_silent(make_pf):
    """The safety net for a protocol that catches its own flow signal reports
    "error" from the else branch, a separate emit site from the except clauses --
    it has to be suppressed too."""
    pf = make_pf()

    def run(ctx, **kwargs):
        orch.abandonCellInHand()
        try:
            ctx.next_cell()
        except AdvanceToNextCell:
            pass  # the bug the safety net exists to catch

    pf.run = run
    orch = Orchestrator(pf, contextFactory=lambda cell: ExecutionContext(cell=cell))
    finished = []
    orch.sigCellFinished.connect(lambda cell, s: finished.append((cell, s)))
    orch.enqueue("c1")

    with pytest.raises(AbortExperiment):
        orch.run_sync()

    assert finished == []


def test_run_sync_cell_honours_an_abandoned_cell_too(make_pf):
    """The single-cell entry point never goes through _runLoopBody's popleft, so
    the suppression has to cover it as well -- headless callers and
    Autopatch/tests/test_teardown.py both reach a cell this way."""
    pf = make_pf()

    def run(ctx, **kwargs):
        if ctx.cell == "solo-cell":
            orch.abandonCellInHand()

    pf.run = run
    orch = Orchestrator(pf)
    finished = []
    orch.sigCellFinished.connect(lambda cell, s: finished.append((cell, s)))

    orch.run_sync_cell("solo-cell")

    assert finished == []
    # Not left armed for the next call on this instance, the same way
    # run_sync_cell's finally refuses to let a next-cell request outlive it.
    orch.run_sync_cell("next-cell")
    assert finished == [("next-cell", "done")]


def test_an_abandoned_cell_is_not_retained_once_its_pass_is_over(make_pf):
    """The marking holds the cell itself, so it must be dropped with the in-hand
    state -- an orchestrator nothing is looking after any more must not keep a
    Cell (and its tracker and reference image stack) reachable. See
    Autopatch/tests/test_teardown.py for the segfault that makes retention here
    matter."""

    class _Cell:
        pass

    pf = make_pf()
    pf.run = lambda ctx, **kwargs: orch.abandonCellInHand()
    orch = Orchestrator(pf)
    cell = _Cell()
    orch.enqueue(cell)

    orch.run_sync()
    cellRef = weakref.ref(cell)

    gc.disable()
    try:
        del cell
        # No gc.collect() -- pure refcounting, since gc is disabled.
        assert cellRef() is None, "the abandoned marking outlived the cell in hand"
    finally:
        gc.enable()
