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

    ids = list(range(len(TERMINAL)))
    ctx = makeContext(
        cellIds=ids,
        dispositions=dict(zip(ids, sorted(TERMINAL))),
        attempted=set(ids),
    )

    brushes = successBrushes(ctx)

    assert set(brushes) == set(ids)


def test_success_legend_names_every_colour_it_can_draw():
    from acq4.modules.Autopatch.progress_colors import legendFor

    labels = [label for label, _brush in legendFor("success", makeContext())]

    assert labels == ["Patched", "Failed", "Abandoned", "In flight", "To do"]
