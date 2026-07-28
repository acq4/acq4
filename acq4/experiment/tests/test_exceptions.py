"""Tests for the orchestration exception taxonomy and control-flow signals."""
import pytest

from acq4.experiment import exceptions as exc


def test_base_typename():
    assert exc.OrchestrationError.typeName == "Exception"


def test_subclass_typenames():
    assert exc.BrokenPipette.typeName == "BrokenPipette"
    assert exc.Fouled.typeName == "Fouled"
    assert exc.Uncleanable.typeName == "Uncleanable"
    assert exc.NoSolution.typeName == "NoSolution"
    assert exc.ScriptError.typeName == "ScriptError"


def test_subclasses_are_orchestration_errors():
    for cls in (exc.BrokenPipette, exc.Fouled, exc.Uncleanable,
                exc.NoSolution, exc.ScriptError):
        assert issubclass(cls, exc.OrchestrationError)


def test_flow_signals_are_not_orchestration_errors():
    for cls in (exc.AdvanceToNextCell, exc.RetryCurrentCell, exc.AbortExperiment):
        assert issubclass(cls, exc.FlowSignal)
        assert not issubclass(cls, exc.OrchestrationError)


def test_abnormal_state_exceptions_mapping():
    assert exc.ABNORMAL_STATE_EXCEPTIONS == {
        "broken": exc.BrokenPipette,
        "fouled": exc.Fouled,
    }


def test_raise_if_abnormal_does_not_raise_for_expected_state():
    exc.raise_if_abnormal("broken", expected=("broken", "fouled"))


def test_raise_if_abnormal_raises_broken_pipette_when_unexpected():
    with pytest.raises(exc.BrokenPipette):
        exc.raise_if_abnormal("broken", expected=("whole cell",))


def test_raise_if_abnormal_raises_fouled_when_unexpected():
    with pytest.raises(exc.Fouled):
        exc.raise_if_abnormal("fouled", expected=("whole cell",))


def test_raise_if_abnormal_returns_for_unmapped_internal_hop():
    exc.raise_if_abnormal("seal", expected=("whole cell",))


def test_raise_if_abnormal_message_includes_context():
    with pytest.raises(exc.BrokenPipette, match="reseal"):
        exc.raise_if_abnormal("broken", expected=(), context="reseal")
