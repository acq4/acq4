"""Tests for the orchestration exception taxonomy and control-flow signals."""
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
