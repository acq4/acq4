"""Tests for the progress overlay's colour sources — the mapping from a cell's
recorded facts to the brush that makes a bad search region obvious at a glance."""

import pytest


def makeContext(**overrides):
    from acq4.modules.Autopatch.progress_colors import ColorContext

    base = dict(
        cellIds=[],
        positions={},
        dispositions={},
        attempted=set(),
        scores={},
        fov=(220e-6, 170e-6),
        tileVolume=None,
        maxCellDensity=None,
        minHealth=None,
    )
    base.update(overrides)
    return ColorContext(**base)


def test_done_and_error_get_different_brushes():
    from acq4.modules.Autopatch.progress_colors import successBrushes

    ctx = makeContext(
        cellIds=[1, 2],
        dispositions={1: "done", 2: "error"},
        attempted={1, 2},
    )

    brushes = successBrushes(ctx)

    assert brushes[1].color() != brushes[2].color()


def test_abandonment_is_not_coloured_as_failure():
    """CellPanel's own COMPLETED comment insists "stopped"/"skipped" are
    abandonment while "error"/"retry-exhausted" are failures. Collapsing them
    would make an operator's own Stop look like dead tissue, which is the
    misreading this whole display exists to prevent.
    """
    from acq4.modules.Autopatch.progress_colors import successBrushes

    ctx = makeContext(
        cellIds=[1, 2, 3, 4],
        dispositions={
            1: "error",
            2: "retry-exhausted",
            3: "stopped",
            4: "skipped",
        },
        attempted={1, 2, 3, 4},
    )

    brushes = successBrushes(ctx)

    assert brushes[1].color() == brushes[2].color()
    assert brushes[3].color() == brushes[4].color()
    assert brushes[1].color() != brushes[3].color()


def test_attempted_but_unfinished_differs_from_never_attempted():
    """A cell in flight is not a to-do cell; the operator is watching it."""
    from acq4.modules.Autopatch.progress_colors import successBrushes

    ctx = makeContext(cellIds=[1, 2], dispositions={}, attempted={1})

    brushes = successBrushes(ctx)

    assert brushes[1].color() != brushes[2].color()


def test_every_terminal_disposition_is_mapped():
    """A disposition falling through to a default is a silent lie about a cell."""
    from acq4.modules.Autopatch.cell_panel import TERMINAL
    from acq4.modules.Autopatch.progress_colors import successBrushes

    dispositions = {
        1: "done",
        2: "error",
        3: "retry-exhausted",
        4: "stopped",
        5: "skipped",
    }
    assert set(dispositions.values()) == set(TERMINAL)
    # id 6 carries no disposition at all: it is attempted but still in flight,
    # the witness that abandonment's colour is its own bucket rather than a
    # coincidental match with "attempted, no verdict yet".
    ids = list(dispositions) + [6]
    ctx = makeContext(cellIds=ids, dispositions=dispositions, attempted=set(ids))

    brushes = successBrushes(ctx)

    assert set(brushes) == set(ids)
    doneColor = brushes[1].color()
    for cellId in (2, 3, 4, 5, 6):
        assert brushes[cellId].color() != doneColor
    assert brushes[2].color() == brushes[3].color()
    assert brushes[4].color() == brushes[5].color()
    assert brushes[2].color() != brushes[4].color()
    assert brushes[4].color() != brushes[6].color()


def test_success_legend_names_every_colour_it_can_draw():
    from acq4.modules.Autopatch.progress_colors import legendFor

    labels = [label for label, _brush in legendFor("success", makeContext())]

    assert labels == ["Patched", "Failed", "Abandoned", "In flight", "To do"]


def test_brushes_for_success_matches_success_brushes_directly():
    from acq4.modules.Autopatch.progress_colors import brushesFor, successBrushes

    ctx = makeContext(
        cellIds=[1, 2],
        dispositions={1: "done", 2: "error"},
        attempted={1, 2},
    )

    brushes = brushesFor("success", ctx)
    direct = successBrushes(ctx)

    assert {cellId: brush.color() for cellId, brush in brushes.items()} == {
        cellId: brush.color() for cellId, brush in direct.items()
    }


def test_brushes_for_unknown_key_raises_key_error():
    from acq4.modules.Autopatch.progress_colors import brushesFor

    with pytest.raises(KeyError):
        brushesFor("no-such-source", makeContext())


def test_legend_for_unknown_key_raises_key_error():
    from acq4.modules.Autopatch.progress_colors import legendFor

    with pytest.raises(KeyError):
        legendFor("no-such-source", makeContext())
