"""Tests for error_record: an exception rendered to retainable text, and the
run-level record the orchestrator emits when a run halts."""
import gc
import weakref

from acq4.experiment.error_record import RunErrorRecord, describe_exception


class _Boom(Exception):
    """A pure-Python exception subclass.

    Built-in exception types have no __weakref__ slot, so the retention proof
    below cannot take a weak reference to a bare ValueError. Anything raised in
    real use is a project-defined subclass (OrchestrationError and friends), so
    this is also the shape the retention property actually has to hold for.
    """


def _raise_and_describe():
    """Raise, catch, and describe -- in a frame that has returned by the time
    the caller inspects the result, so nothing this frame held is still live."""
    try:
        raise _Boom("boom")
    except _Boom as exc:
        return describe_exception(exc), weakref.ref(exc)


def test_describe_exception_renders_type_message_and_traceback():
    (exc_type, message, tb_text), _ref = _raise_and_describe()
    assert exc_type == "_Boom"
    assert message == "boom"
    assert "_Boom: boom" in tb_text
    assert "_raise_and_describe" in tb_text


def test_describe_exception_includes_the_cause_chain():
    # Every orchestrator halt is `raise AbortExperiment(...) from exc`, so the
    # frames that explain the failure are in the cause, not the wrapper.
    try:
        try:
            raise KeyError("inner-detail")
        except KeyError as inner:
            raise RuntimeError("outer-wrapper") from inner
    except RuntimeError as exc:
        _type, _message, tb_text = describe_exception(exc)
    assert "inner-detail" in tb_text
    assert "outer-wrapper" in tb_text
    assert "direct cause" in tb_text


def test_describe_exception_keeps_no_reference_to_the_exception():
    # The property the whole module exists for: a retained rendering must not
    # pin the exception, its traceback, its frames, or those frames' locals.
    (_type, _message, _tb), ref = _raise_and_describe()
    gc.disable()
    try:
        assert ref() is None, "describe_exception is keeping the exception alive"
    finally:
        gc.enable()


def test_record_from_exception_carries_the_cell_token():
    class _Cell:
        def __repr__(self):
            return "<Cell at (1, 2, 3)>"

    try:
        raise ValueError("boom")
    except ValueError as exc:
        record = RunErrorRecord.from_exception(exc, _Cell())
    assert record.exc_type == "ValueError"
    assert record.exc_message == "boom"
    assert record.cell_repr == "<Cell at (1, 2, 3)>"


def test_record_has_no_cell_token_when_there_is_no_cell():
    # A producer raising during a refill is attributed to no cell -- which is
    # why the run-level record exists at all, instead of living only on the
    # failing action's log entry.
    try:
        raise ValueError("boom")
    except ValueError as exc:
        record = RunErrorRecord.from_exception(exc)
    assert record.cell_repr is None


def test_record_is_frozen():
    record = RunErrorRecord("ValueError", "boom", "traceback text")
    try:
        record.exc_type = "OtherError"
    except Exception as exc:
        assert type(exc).__name__ == "FrozenInstanceError"
    else:
        raise AssertionError("RunErrorRecord should be immutable")
