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


def test_unscored_cells_are_visibly_distinct_from_scored_ones():
    """score is None means "nobody scored this", not "scored badly". Every
    hand-added cell is unscored, since only _build_cells scores.
    """
    from acq4.modules.Autopatch.progress_colors import healthBrushes

    ctx = makeContext(cellIds=[1, 2], scores={1: None, 2: 0.5}, minHealth=0.5)

    brushes = healthBrushes(ctx)

    assert brushes[1].color() != brushes[2].color()


def test_health_ramp_is_anchored_at_the_cutoff_not_at_zero():
    """Two cells scoring 0.6 and 0.9 against a 0.5 cutoff must look different.

    This is the test that kills a [0, 1] ramp, and the mutant a reader would
    not suspect: both values are perfectly legal [0, 1] scores, and a [0, 1]
    ramp renders them nearly identical because it spends half its range below
    the cutoff on scores that cannot occur.
    """
    from acq4.modules.Autopatch.progress_colors import healthBrushes

    anchored = healthBrushes(
        makeContext(cellIds=[1, 2], scores={1: 0.6, 2: 0.9}, minHealth=0.5)
    )
    full = healthBrushes(
        makeContext(cellIds=[1, 2], scores={1: 0.6, 2: 0.9}, minHealth=None)
    )

    anchoredGap = abs(anchored[1].color().green() - anchored[2].color().green())
    fullGap = abs(full[1].color().green() - full[2].color().green())
    assert anchoredGap > fullGap


def test_the_cutoff_score_sits_at_the_bottom_of_the_ramp():
    """The legend labels its first swatch "<cutoff> (cutoff)" and draws it at
    fraction 0.0 on _HEALTH_CMAP, promising that a cell scoring exactly the
    cutoff is drawn in the ramp's floor colour. This kills a mutant that
    compresses or offsets the fraction after the clamp (e.g.
    `fraction = fraction * 0.9 + 0.05`), which would still make 0.5 and 1.0
    differ but would no longer put the cutoff at the ramp's floor -- a
    user-visible disagreement between the legend swatch and the cells it
    claims to describe.
    """
    from acq4.modules.Autopatch.progress_colors import _HEALTH_CMAP, healthBrushes

    ctx = makeContext(cellIds=[1, 2], scores={1: 0.5, 2: 1.0}, minHealth=0.5)

    brushes = healthBrushes(ctx)

    assert brushes[1].color() != brushes[2].color()
    assert brushes[1].color() == _HEALTH_CMAP.map(0.0, mode="qcolor")
    assert brushes[2].color() == _HEALTH_CMAP.map(1.0, mode="qcolor")


def test_a_cutoff_of_one_does_not_divide_by_zero():
    """SearchConstraints constrains min_health to [0, 1], so a cutoff of
    exactly 1.0 is a legal input that leaves the ramp no width at all. The
    guard sets fraction = 0.0 in that case, so the cell must land on the
    ramp's floor rather than merely avoiding an exception.
    """
    from acq4.modules.Autopatch.progress_colors import _HEALTH_CMAP, healthBrushes

    ctx = makeContext(cellIds=[1], scores={1: 1.0}, minHealth=1.0)

    brushes = healthBrushes(ctx)

    assert brushes[1].color() == _HEALTH_CMAP.map(0.0, mode="qcolor")


def test_health_falls_back_to_a_zero_to_one_ramp_with_no_slice():
    """No slice means no constraints, and so no cutoff to anchor to.

    Asserts the fallback ramp's *shape*, not merely that a brush came back:
    across [0, 1], scores of 0.0 and 0.5 are half the range apart and must
    differ. Under a 0.5-anchored ramp both clamp to the bottom and collapse to
    the same colour, so this is the assertion that tells the two ramps apart.
    """
    from acq4.modules.Autopatch.progress_colors import healthBrushes

    brushes = healthBrushes(
        makeContext(cellIds=[1, 2], scores={1: 0.0, 2: 0.5}, minHealth=None)
    )

    assert brushes[1].color() != brushes[2].color()


def test_a_score_outside_the_ramp_is_clamped_not_raised():
    """Nothing queued can produce one; this guards a future detector."""
    from acq4.modules.Autopatch.progress_colors import healthBrushes

    ctx = makeContext(cellIds=[1, 2], scores={1: -0.5, 2: 1.5}, minHealth=0.5)

    brushes = healthBrushes(ctx)

    assert brushes[1].color() != brushes[2].color()


def test_a_crowded_neighbourhood_differs_from_a_lonely_one():
    from acq4.modules.Autopatch.progress_colors import densityBrushes

    # Three cells within one field of each other, and one far away.
    ctx = makeContext(
        cellIds=[1, 2, 3, 9],
        positions={
            1: (1.0e-3, 2.0e-3),
            2: (1.00002e-3, 2.00002e-3),
            3: (1.00004e-3, 2.00004e-3),
            9: (5.0e-3, 4.0e-3),
        },
        tileVolume=220e-6 * 170e-6 * 40e-6,
        maxCellDensity=5e12,
    )

    brushes = densityBrushes(ctx)

    assert brushes[1].color() != brushes[9].color()


def test_density_counts_neighbours_in_the_same_xy_window_as_the_engine():
    """Slice.cellsNearTile uses a +/- fov/2 box in x and y and ignores z, and
    the producer divides that count by tileVolume. Matching it is what keeps
    the display and the density cap from disagreeing about "crowded".
    """
    from acq4.modules.Autopatch.progress_colors import densityBrushes

    fov = (220e-6, 170e-6)
    # Just inside the window in x, and just outside it.
    inside = (1.0e-3 + fov[0] / 2 * 0.9, 2.0e-3)
    outside = (1.0e-3 + fov[0] / 2 * 1.1, 2.0e-3)

    withInside = densityBrushes(
        makeContext(
            cellIds=[1, 2],
            positions={1: (1.0e-3, 2.0e-3), 2: inside},
            fov=fov,
            tileVolume=fov[0] * fov[1] * 40e-6,
            maxCellDensity=5e12,
        )
    )
    withOutside = densityBrushes(
        makeContext(
            cellIds=[1, 2],
            positions={1: (1.0e-3, 2.0e-3), 2: outside},
            fov=fov,
            tileVolume=fov[0] * fov[1] * 40e-6,
            maxCellDensity=5e12,
        )
    )

    assert withInside[1].color() != withOutside[1].color()


def test_density_binds_the_y_window_to_the_field_height():
    """Kills a mutant that swaps `fovH / 2` for `fovW / 2` in
    `_neighbourCount`'s y-axis comparison.

    The sibling test `test_density_counts_neighbours_in_the_same_xy_window_as_the_engine`
    holds y constant across its `inside`/`outside` fixtures, so
    `abs(there[1] - here[1])` is always 0 there and clears either threshold --
    it cannot distinguish `fovH / 2` from `fovW / 2` in the y term. This test
    varies only y instead, mirroring the sibling's structure along the other
    axis.
    """
    from acq4.modules.Autopatch.progress_colors import densityBrushes

    fov = (220e-6, 170e-6)
    # Just inside the correct fovH-based window in y, and just outside it --
    # but still inside what a fovW-based window would wrongly allow.
    inside = (1.0e-3, 2.0e-3 + fov[1] / 2 * 0.9)
    outside = (1.0e-3, 2.0e-3 + 100e-6)

    withInside = densityBrushes(
        makeContext(
            cellIds=[1, 2],
            positions={1: (1.0e-3, 2.0e-3), 2: inside},
            fov=fov,
            tileVolume=fov[0] * fov[1] * 40e-6,
            maxCellDensity=5e12,
        )
    )
    withOutside = densityBrushes(
        makeContext(
            cellIds=[1, 2],
            positions={1: (1.0e-3, 2.0e-3), 2: outside},
            fov=fov,
            tileVolume=fov[0] * fov[1] * 40e-6,
            maxCellDensity=5e12,
        )
    )

    assert withInside[1].color() != withOutside[1].color()


def test_density_falls_back_to_a_raw_count_with_no_slice():
    """No slice means no tileVolume and no cap to normalise against.

    Asserts the raw scale still *ranks*, rather than merely that every cell got
    a brush: two neighbours must colour differently from a lonely cell. A
    fallback that returned one flat colour would satisfy a keys-only assertion
    while telling the operator nothing.
    """
    from acq4.modules.Autopatch.progress_colors import densityBrushes

    ctx = makeContext(
        cellIds=[1, 2, 9],
        positions={
            1: (1.0e-3, 2.0e-3),
            2: (1.00002e-3, 2.00002e-3),
            9: (5.0e-3, 4.0e-3),
        },
        tileVolume=None,
        maxCellDensity=None,
    )

    brushes = densityBrushes(ctx)

    assert brushes[1].color() != brushes[9].color()


def test_density_saturates_exactly_at_the_engines_cap():
    """Pins the display's crowded threshold to the same ratio
    CellProducer._isCrowded uses to skip a tile
    (len(cellsNearTile(tile)) / tileVolume() >= max_cell_density), not merely
    "crowded reads differently from lonely" -- which the raw, unnormalised
    fallback scale (count / _RAW_DENSITY_FULL_SCALE) also satisfies, and which
    is all `test_a_crowded_neighbourhood_differs_from_a_lonely_one` above
    checks.

    Arithmetic: four cells at the same position put _neighbourCount at 4 for
    each of them (every one of the four counts itself and its three
    neighbours, all at zero distance). tileVolume=1.0 and maxCellDensity=4.0
    make (4 / 1.0) / 4.0 == 1.0 -- exactly the cap, so the brush must be the
    ramp's saturated colour. Two cells at the same position, against the same
    maxCellDensity=4.0, put _neighbourCount at 2, so (2 / 1.0) / 4.0 == 0.5 --
    half the cap, and a strictly different point on the ramp.

    Setting `normalised = False` in densityBrushes (removing tileVolume and
    max_cell_density from the computation entirely) must make this fail: with
    the raw fallback, the four-cell case maps to 4 / _RAW_DENSITY_FULL_SCALE
    (10.0) == 0.4, not 1.0.
    """
    from acq4.modules.Autopatch.progress_colors import _DENSITY_CMAP, densityBrushes

    fov = (220e-6, 170e-6)
    atCap = densityBrushes(
        makeContext(
            cellIds=[1, 2, 3, 4],
            positions={cellId: (1.0e-3, 2.0e-3) for cellId in (1, 2, 3, 4)},
            fov=fov,
            tileVolume=1.0,
            maxCellDensity=4.0,
        )
    )
    halfCap = densityBrushes(
        makeContext(
            cellIds=[1, 2],
            positions={1: (1.0e-3, 2.0e-3), 2: (1.0e-3, 2.0e-3)},
            fov=fov,
            tileVolume=1.0,
            maxCellDensity=4.0,
        )
    )

    assert atCap[1].color() == _DENSITY_CMAP.map(1.0, mode="qcolor")
    assert halfCap[1].color() == _DENSITY_CMAP.map(0.5, mode="qcolor")
    assert halfCap[1].color() != atCap[1].color()


def test_density_legend_says_when_it_is_unnormalised():
    from acq4.modules.Autopatch.progress_colors import legendFor

    normalised = legendFor(
        "density", makeContext(tileVolume=1.0e-12, maxCellDensity=5e12)
    )
    raw = legendFor("density", makeContext(tileVolume=None, maxCellDensity=None))

    assert [label for label, _b in normalised] != [label for label, _b in raw]
