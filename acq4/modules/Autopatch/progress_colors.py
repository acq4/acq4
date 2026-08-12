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


# (label, key, brush function). Key is what the combo carries as item data and
# what legendFor takes, following SearchPanel.regionShape()'s precedent of
# keying on data rather than display text.
COLOR_SOURCES = [
    ("Survey outcome", "success", successBrushes),
]

_LEGENDS = {
    "success": _successLegend,
}


def brushesFor(key, ctx) -> dict:
    """The brushes for colour source `key`."""
    for _label, sourceKey, func in COLOR_SOURCES:
        if sourceKey == key:
            return func(ctx)
    raise KeyError(f"no such colour source: {key!r}")


def legendFor(key, ctx) -> list:
    """(label, brush) pairs naming what colour source `key` can draw."""
    return _LEGENDS[key](ctx)
