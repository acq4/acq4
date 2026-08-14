"""Colour sources for Area 1's progress overlay: pure mappings from the facts
recorded about a cell to the brush it is drawn with, plus their legends."""

from dataclasses import dataclass

import pyqtgraph as pg

_GREEN = (0, 170, 60)
_RED = (215, 45, 45)
_AMBER = (230, 160, 30)
_BLUE = (60, 130, 230)
_GREY = (140, 140, 140)

# Failure and abandonment are deliberately distinct: CellPanel's COMPLETED
# comment draws the same line, and an operator's own Stop must not read as dead
# tissue.
_FAILED = frozenset({"error", "retry-exhausted"})
_ABANDONED = frozenset({"stopped", "skipped"})


@dataclass
class ColorContext:
    """Everything a colour source may read, gathered by the window.

    Keyed by id(cell) throughout, and holding no cells: the same discipline
    every id-keyed dict in cell_panel.py follows.

    `fov`, `tileVolume`, `maxCellDensity` and `minHealth` are None when no
    slice exists, which is an ordinary state -- cells can be added by hand
    before a slice does.
    """

    cellIds: list
    positions: dict
    dispositions: dict
    attempted: set
    scores: dict
    fov: tuple | None
    tileVolume: float | None
    maxCellDensity: float | None
    minHealth: float | None


def successBrushes(ctx) -> dict:
    """One brush per cell, by what the run made of it."""
    brushes = {}
    for cellId in ctx.cellIds:
        disposition = ctx.dispositions.get(cellId)
        if disposition == "done":
            color = _GREEN
        elif disposition in _FAILED:
            color = _RED
        elif disposition in _ABANDONED:
            color = _AMBER
        elif cellId in ctx.attempted:
            color = _BLUE
        else:
            color = _GREY
        brushes[cellId] = pg.mkBrush(*color)
    return brushes


def _successLegend(_ctx) -> list:
    return [
        ("Patched", pg.mkBrush(*_GREEN)),
        ("Failed", pg.mkBrush(*_RED)),
        ("Abandoned", pg.mkBrush(*_AMBER)),
        ("In flight", pg.mkBrush(*_BLUE)),
        ("To do", pg.mkBrush(*_GREY)),
    ]


# Hollow, so "never scored" reads as absence rather than as a low score.
_UNSCORED_BRUSH = pg.mkBrush(0, 0, 0, 0)

# Dim violet to bright green across the scored range. Endpoints differ in every
# channel so no single-channel comparison can mistake one end for the other.
_HEALTH_CMAP = pg.ColorMap([0.0, 1.0], [(90, 50, 140, 255), (60, 225, 120, 255)])


def healthBrushes(ctx) -> dict:
    """One brush per cell, by the detector's health score.

    The ramp spans [min_health, 1], not [0, 1]: CellProducer._isHealthy drops
    every candidate below the cutoff before it becomes a cell, so a [0, 1] ramp
    would spend half its range on scores that cannot occur and render the
    cells that do occur nearly identical. With no slice there is no cutoff, so
    it falls back to [0, 1].
    """
    low = 0.0 if ctx.minHealth is None else float(ctx.minHealth)
    # A cutoff of exactly 1.0 would leave the ramp no width at all.
    span = 1.0 - low
    brushes = {}
    for cellId in ctx.cellIds:
        score = ctx.scores.get(cellId)
        if score is None:
            brushes[cellId] = _UNSCORED_BRUSH
            continue
        fraction = 0.0 if span <= 0 else (float(score) - low) / span
        fraction = min(1.0, max(0.0, fraction))
        brushes[cellId] = pg.mkBrush(_HEALTH_CMAP.map(fraction, mode="qcolor"))
    return brushes


def _healthLegend(ctx) -> list:
    low = 0.0 if ctx.minHealth is None else float(ctx.minHealth)
    return [
        (f"{low:.2f} (cutoff)", pg.mkBrush(_HEALTH_CMAP.map(0.0, mode="qcolor"))),
        ("1.00", pg.mkBrush(_HEALTH_CMAP.map(1.0, mode="qcolor"))),
        ("Unscored", _UNSCORED_BRUSH),
    ]


# Sparse to crowded. Deliberately not the success source's red: switching
# sources must not make a crowded neighbourhood read as a failed cell.
_DENSITY_CMAP = pg.ColorMap([0.0, 1.0], [(70, 110, 200, 255), (240, 140, 20, 255)])

# The count a raw, unnormalised scale saturates at, used only when there is no
# slice to supply tileVolume and the density cap. Ten cells inside one field is
# already crowded tissue by the default cap's standard.
_RAW_DENSITY_FULL_SCALE = 10.0


def _neighbourCount(cellId, ctx) -> int:
    """Cells inside `cellId`'s own field-sized xy window, including itself.

    The same window Slice.cellsNearTile uses -- +/- fov/2 in x and y, with no z
    term -- so this count is the one the density cap is expressed in.
    """
    here = ctx.positions.get(cellId)
    if here is None or ctx.fov is None:
        return 0
    fovW, fovH = ctx.fov
    count = 0
    for otherId in ctx.cellIds:
        there = ctx.positions.get(otherId)
        if there is None:
            continue
        if abs(there[0] - here[0]) <= fovW / 2 and abs(there[1] - here[1]) <= fovH / 2:
            count += 1
    return count


def densityBrushes(ctx) -> dict:
    """One brush per cell, by how crowded its own neighbourhood is.

    Normalised against constraints.max_cell_density so the colour means "how
    close is this neighbourhood to the cap the producer would skip a tile
    for". Reads ctx.positions rather than Slice.cellsNearTile(), which calls
    the thread-unsafe Cell.position.
    """
    normalised = ctx.tileVolume not in (None, 0) and ctx.maxCellDensity not in (None, 0)
    brushes = {}
    for cellId in ctx.cellIds:
        count = _neighbourCount(cellId, ctx)
        if normalised:
            fraction = (count / ctx.tileVolume) / ctx.maxCellDensity
        else:
            fraction = count / _RAW_DENSITY_FULL_SCALE
        fraction = min(1.0, max(0.0, fraction))
        brushes[cellId] = pg.mkBrush(_DENSITY_CMAP.map(fraction, mode="qcolor"))
    return brushes


def _densityLegend(ctx) -> list:
    normalised = ctx.tileVolume not in (None, 0) and ctx.maxCellDensity not in (None, 0)
    top = "At the density cap" if normalised else f"{int(_RAW_DENSITY_FULL_SCALE)}+ per field"
    return [
        ("Sparse", pg.mkBrush(_DENSITY_CMAP.map(0.0, mode="qcolor"))),
        (top, pg.mkBrush(_DENSITY_CMAP.map(1.0, mode="qcolor"))),
    ]


# (label, key, brush function). Key is what the combo carries as item data and
# what legendFor takes, following RegionPanel.regionShape()'s precedent of
# keying on data rather than display text.
COLOR_SOURCES = [
    ("Survey outcome", "success", successBrushes),
    ("Detection health", "health", healthBrushes),
    ("Local density", "density", densityBrushes),
]

_LEGENDS = {
    "success": _successLegend,
    "health": _healthLegend,
    "density": _densityLegend,
}


def brushesFor(key, ctx) -> dict:
    """The brushes for colour source `key`."""
    for _label, sourceKey, func in COLOR_SOURCES:
        if sourceKey == key:
            return func(ctx)
    raise KeyError(f"no such colour source: {key!r}")


def legendFor(key, ctx) -> list:
    """(label, brush) pairs naming what colour source `key` can draw."""
    if key not in _LEGENDS:
        raise KeyError(f"no such colour source: {key!r}")
    return _LEGENDS[key](ctx)
