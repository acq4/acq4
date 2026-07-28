"""Tests for ActionLogEntry and ExecutionContext.log_action()."""
import pytest

from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import AdvanceToNextCell, BrokenPipette
from acq4.experiment.log_entry import ActionLogEntry
from acq4.util.task import Stopped


def test_entry_created_with_name_and_running_state():
    ctx = ExecutionContext()
    with ctx.log_action("Patch") as entry:
        assert entry.name == "Patch"
        assert entry.end_time is None


def test_normal_exit_sets_done_outcome_and_end_time():
    ctx = ExecutionContext()
    with ctx.log_action("Patch") as entry:
        pass
    assert entry.outcome == "done"
    assert entry.end_time is not None


def test_stopped_propagates_and_sets_stopped_outcome():
    ctx = ExecutionContext()
    with pytest.raises(Stopped):
        with ctx.log_action("Patch") as entry:
            raise Stopped()
    assert entry.outcome == "stopped"


def test_advance_to_next_cell_propagates_and_sets_done_outcome():
    ctx = ExecutionContext()
    with pytest.raises(AdvanceToNextCell):
        with ctx.log_action("Patch") as entry:
            raise AdvanceToNextCell()
    assert entry.outcome == "done"


def test_broken_pipette_propagates_and_sets_error_outcome():
    ctx = ExecutionContext()
    with pytest.raises(BrokenPipette):
        with ctx.log_action("Patch") as entry:
            raise BrokenPipette()
    assert entry.outcome == "error"


def test_set_status_updates_status():
    entry = ActionLogEntry("Patch")
    entry.set_status("seeking")
    assert entry.status == "seeking"


def test_set_details_widget_stores_widget():
    entry = ActionLogEntry("Patch")
    widget = object()
    entry.set_details_widget(widget)
    assert entry.details_widget is widget


def test_on_log_action_hook_receives_entry():
    ctx = ExecutionContext()
    seen = []
    ctx.on_log_action = seen.append
    with ctx.log_action("Patch") as entry:
        pass
    assert seen == [entry]


def test_on_status_hook_sees_each_set_status_call():
    ctx = ExecutionContext()
    calls = []

    def hook(entry):
        entry.on_status = lambda e: calls.append(e.status)

    ctx.on_log_action = hook
    with ctx.log_action("Patch") as entry:
        entry.set_status("first")
        entry.set_status("second")
    assert calls == ["first", "second"]


def test_on_finish_hook_sees_final_outcome():
    ctx = ExecutionContext()
    finished = []

    def hook(entry):
        entry.on_finish = lambda e: finished.append(e.outcome)

    ctx.on_log_action = hook
    with ctx.log_action("Patch") as entry:
        pass
    assert finished == ["done"]


def test_headless_with_no_hook_runs_and_populates_entry():
    ctx = ExecutionContext()
    assert ctx.on_log_action is None
    with ctx.log_action("Patch") as entry:
        entry.set_status("running")
    assert entry.status == "running"
    assert entry.outcome == "done"
