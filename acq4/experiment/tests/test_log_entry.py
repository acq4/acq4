"""Tests for ActionLogEntry and ExecutionContext.log_action()."""
import pytest

from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import AdvanceToNextCell, BrokenPipette
from acq4.experiment.log_entry import ActionLogEntry
from acq4.util.task import Stopped


def test_entry_created_with_name_and_running_state():
    ctx = ExecutionContext()
    with ctx.log_action("Patch") as action_entry:
        assert action_entry.name == "Patch"
        assert action_entry.end_time is None


def test_normal_exit_sets_done_outcome_and_end_time():
    ctx = ExecutionContext()
    with ctx.log_action("Patch") as action_entry:
        pass
    assert action_entry.outcome == "done"
    assert action_entry.end_time is not None


def test_stopped_propagates_and_sets_stopped_outcome():
    ctx = ExecutionContext()
    with pytest.raises(Stopped):
        with ctx.log_action("Patch") as action_entry:
            raise Stopped()
    assert action_entry.outcome == "stopped"


def test_advance_to_next_cell_propagates_and_sets_abandoned_outcome():
    # A FlowSignal escaping an action's block means that action was abandoned
    # partway, not completed -- it must never propagate to the operator as
    # "done", and it must still propagate (log_action never suppresses).
    ctx = ExecutionContext()
    with pytest.raises(AdvanceToNextCell):
        with ctx.log_action("Patch") as action_entry:
            raise AdvanceToNextCell()
    assert action_entry.outcome == "abandoned"


def test_broken_pipette_propagates_and_sets_error_outcome():
    ctx = ExecutionContext()
    with pytest.raises(BrokenPipette):
        with ctx.log_action("Patch") as action_entry:
            raise BrokenPipette()
    assert action_entry.outcome == "error"


def test_set_status_updates_status():
    action_entry = ActionLogEntry("Patch")
    action_entry.set_status("seeking")
    assert action_entry.status == "seeking"


def test_set_details_widget_stores_widget():
    action_entry = ActionLogEntry("Patch")
    widget = object()
    action_entry.set_details_widget(widget)
    assert action_entry.details_widget is widget


def test_on_log_action_hook_receives_entry():
    ctx = ExecutionContext()
    seen = []
    ctx.on_log_action = seen.append
    with ctx.log_action("Patch") as action_entry:
        pass
    assert seen == [action_entry]


def test_on_status_hook_sees_each_set_status_call():
    ctx = ExecutionContext()
    calls = []

    def hook(action_entry):
        action_entry.on_status = lambda e: calls.append(e.status)

    ctx.on_log_action = hook
    with ctx.log_action("Patch") as action_entry:
        action_entry.set_status("first")
        action_entry.set_status("second")
    assert calls == ["first", "second"]


def test_on_finish_hook_sees_final_outcome():
    ctx = ExecutionContext()
    finished = []

    def hook(action_entry):
        action_entry.on_finish = lambda e: finished.append(e.outcome)

    ctx.on_log_action = hook
    with ctx.log_action("Patch") as action_entry:
        pass
    assert finished == ["done"]


def test_headless_with_no_hook_runs_and_populates_entry():
    ctx = ExecutionContext()
    assert ctx.on_log_action is None
    with ctx.log_action("Patch") as action_entry:
        action_entry.set_status("running")
    assert action_entry.status == "running"
    assert action_entry.outcome == "done"


def test_error_outcome_captures_type_message_and_traceback():
    ctx = ExecutionContext()
    with pytest.raises(BrokenPipette):
        with ctx.log_action("Patch") as action_entry:
            raise BrokenPipette("tip sheared off")
    assert action_entry.outcome == "error"
    assert action_entry.exc_type == "BrokenPipette"
    assert action_entry.exc_message == "tip sheared off"
    assert "BrokenPipette: tip sheared off" in action_entry.traceback_text
    assert "test_error_outcome_captures" in action_entry.traceback_text


def test_successful_action_captures_nothing():
    ctx = ExecutionContext()
    with ctx.log_action("Patch") as action_entry:
        pass
    assert action_entry.exc_type is None
    assert action_entry.exc_message is None
    assert action_entry.traceback_text is None


def test_stopped_captures_nothing():
    # An operator-initiated stop is ordinary control flow; a traceback for it
    # would fill Area 5's pane with noise.
    ctx = ExecutionContext()
    with pytest.raises(Stopped):
        with ctx.log_action("Patch") as action_entry:
            raise Stopped()
    assert action_entry.outcome == "stopped"
    assert action_entry.exc_type is None
    assert action_entry.traceback_text is None


def test_flow_signal_captures_nothing():
    ctx = ExecutionContext()
    with pytest.raises(AdvanceToNextCell):
        with ctx.log_action("Patch") as action_entry:
            raise AdvanceToNextCell("next")
    assert action_entry.outcome == "abandoned"
    assert action_entry.exc_type is None
    assert action_entry.traceback_text is None


def test_error_fields_are_populated_before_on_finish_fires():
    # CellPanel's "finished" slot renders the error block straight from these
    # fields, and it is reached through on_finish -- so an ordering where
    # on_finish runs first would hand the UI an entry with nothing on it.
    seen = {}
    entry = ActionLogEntry("Patch")
    entry.on_finish = lambda e: seen.update(
        exc_type=e.exc_type, traceback_text=e.traceback_text
    )
    try:
        raise BrokenPipette("tip sheared off")
    except BrokenPipette as exc:
        entry._finish(exc)
    assert seen["exc_type"] == "BrokenPipette"
    assert "tip sheared off" in seen["traceback_text"]


def test_details_default_to_none():
    action_entry = ActionLogEntry("Patch")
    assert action_entry.details_kind is None
    assert action_entry.details_payload is None


def test_set_details_stores_kind_and_payload():
    action_entry = ActionLogEntry("Patch")
    action_entry.set_details("text", {"lines": ["hello"]})
    assert action_entry.details_kind == "text"
    assert action_entry.details_payload == {"lines": ["hello"]}


def test_on_details_hook_receives_entry_kind_and_payload():
    ctx = ExecutionContext()
    calls = []

    def hook(action_entry):
        action_entry.on_details = lambda e, kind, payload: calls.append((e, kind, payload))

    ctx.on_log_action = hook
    with ctx.log_action("Patch") as action_entry:
        action_entry.set_details("text", {"lines": ["a"]})
    assert calls == [(action_entry, "text", {"lines": ["a"]})]


def test_details_set_in_a_finally_arrive_before_finish():
    # CellPanel resolves an entry to its timeline row through bookkeeping that
    # the entry's finish tears down, so a payload set afterwards has no row to
    # attach to. An action's try/finally inside the `with` is what orders them.
    ctx = ExecutionContext()
    order = []

    def hook(action_entry):
        action_entry.on_details = lambda e, k, p: order.append("details")
        action_entry.on_finish = lambda e: order.append("finish")

    ctx.on_log_action = hook
    with ctx.log_action("Patch") as action_entry:
        try:
            pass
        finally:
            action_entry.set_details("text", {"lines": []})
    assert order == ["details", "finish"]


def test_details_survive_an_error_outcome():
    # An action that gathered data and then failed keeps the data: it is more
    # informative than the traceback, which the row's outcome also carries.
    ctx = ExecutionContext()
    with pytest.raises(BrokenPipette):
        with ctx.log_action("Patch") as action_entry:
            try:
                raise BrokenPipette("tip sheared off")
            finally:
                action_entry.set_details("text", {"lines": ["got this far"]})
    assert action_entry.outcome == "error"
    assert action_entry.details_payload == {"lines": ["got this far"]}
