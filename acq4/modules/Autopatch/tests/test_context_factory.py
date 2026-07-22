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
        pipetteGetter=lambda: None, manager=None, log=lambda cell, message: messages.append((cell, message))
    )

    cell = object()
    ctx = factory(cell)
    ctx.log("hello")

    assert messages == [(cell, "hello")]


def test_factory_binds_log_per_cell_so_lines_can_be_scoped():
    from acq4.modules.Autopatch.context_factory import make_context_factory

    messages = []
    factory = make_context_factory(
        pipetteGetter=lambda: None, manager=None, log=lambda cell, message: messages.append((cell, message))
    )

    cellA, cellB = object(), object()
    ctxA = factory(cellA)
    ctxB = factory(cellB)
    ctxA.log("from A")
    ctxB.log("from B")

    assert messages == [(cellA, "from A"), (cellB, "from B")]
