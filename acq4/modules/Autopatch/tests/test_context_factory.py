"""Tests for make_context_factory: builds an Orchestrator contextFactory that
binds the currently-selected pipette (fixing the P0b context-factory gap)."""
from acq4.experiment.context import ExecutionContext


def test_factory_binds_pipette_cell_and_manager():
    from acq4.modules.Autopatch.context_factory import make_context_factory

    pip = object()
    manager = object()
    factory = make_context_factory(pipetteGetter=lambda: pip, manager=manager)

    cell = object()
    ctx = factory(cell)

    assert isinstance(ctx, ExecutionContext)
    assert ctx.pipette is pip
    assert ctx.cell is cell
    assert ctx.manager is manager


def test_factory_rereads_pipette_getter_each_call():
    from acq4.modules.Autopatch.context_factory import make_context_factory

    pips = [object(), object()]
    factory = make_context_factory(pipetteGetter=lambda: pips.pop(0), manager=None)

    first = factory(object())
    second = factory(object())

    assert first.pipette is not second.pipette


def test_factory_forwards_log_callable():
    from acq4.modules.Autopatch.context_factory import make_context_factory

    messages = []
    factory = make_context_factory(
        pipetteGetter=lambda: None, manager=None, log=messages.append
    )

    ctx = factory(object())
    ctx.log("hello")

    assert messages == ["hello"]
