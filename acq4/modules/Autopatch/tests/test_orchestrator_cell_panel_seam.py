"""Integration test for the Orchestrator <-> CellPanel seam: cells a real
producer finds inside a real refill get Area 5 rows reading their real finish
status, and an orchestrator bound afterward inherits none of them."""

import os

import pytest
from coorx import Point

from acq4.util import Qt

_NOOP_PROTOCOL = '''"""Seam test fixture: resolves immediately without touching ctx."""


def run(ctx, **kwargs):
    return None
'''

# 100x80 um tiles over a 300x80 um region: exactly three tiles, each yielding
# one cell, which is comfortably under the default cell-density cap for a tile
# of this volume.
FOV = (100e-6, 80e-6)
REGION = (0.0, 0.0, 300e-6, 80e-6)
TILE_COUNT = 3


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def _protocolFile(tmp_path, name="demo.py"):
    from acq4.experiment.protocol_file import ProtocolFile

    path = os.path.join(str(tmp_path), name)
    with open(path, "w") as fh:
        fh.write(_NOOP_PROTOCOL)
    pf = ProtocolFile(path)
    pf.load()
    return pf


def _detector(center, constraints):
    """The imaging seam, stubbed to find exactly one real Cell in each tile.

    A genuine acq4_automation Cell rather than a stand-in: it is a QObject, and
    CellPanel's parenting and strong-reference bookkeeping are written around
    precisely that.
    """
    from acq4_automation.feature_tracking.cell import Cell

    near, far = constraints.depth_range
    cell = Cell(Point((center[0], center[1], (near + far) / 2), "global"))
    cell.score = 1.0
    return [cell]


def _orchestrator(tmp_path, name="demo.py"):
    from acq4.experiment.orchestrator import Orchestrator

    return Orchestrator(_protocolFile(tmp_path, name))


def _survey(tmp_path, name="demo.py"):
    """A real Orchestrator with a real CellPanel bound and a real producer installed."""
    from acq4.experiment.search_region import RectRegion
    from acq4.experiment.slice import Slice
    from acq4.modules.Autopatch.cell_panel import CellPanel

    orch = _orchestrator(tmp_path, name)
    panel = CellPanel()
    panel.bindOrchestrator(orch)
    sliceState = Slice(fov=FOV)
    sliceState.addRegion(RectRegion(*REGION))
    orch.setCellProducer(sliceState.makeCellProducer(_detector))
    return orch, panel, sliceState


def test_produced_cells_get_rows_reading_their_finish_status(qapp, tmp_path):
    """Nothing is seeded by hand: every row in Area 5 got there because the
    orchestrator's refill asked the producer, announced what came back, and the
    panel picked those announcements up."""
    orch, panel, sliceState = _survey(tmp_path)
    assert panel.cellList.count() == 0

    orch.run_sync()

    assert panel.cellList.count() == TILE_COUNT
    rows = [panel.cellList.item(i).text() for i in range(TILE_COUNT)]
    for row in rows:
        assert "done" in row, f"row does not read its finish status: {row!r}"
    # Each row names a distinct cell, and each is the cell the panel is holding.
    assert len(set(rows)) == TILE_COUNT
    assert len(panel._cells) == TILE_COUNT
    allRows = " ".join(rows)
    for cellId, cell in panel._cells.items():
        assert f"cell {cellId}" in allRows
        assert cell in sliceState.cellsNearTile(cell.position[:2])

    # The whole region was surveyed on the way.
    assert sliceState.surveyStats() == (TILE_COUNT, TILE_COUNT, pytest.approx(100.0))


def test_binding_a_later_orchestrator_enqueues_none_of_the_surveyed_cells(
    qapp, tmp_path
):
    """The regression guard for the flush, at the level the hazard actually
    lives at. Every cell a completed survey produced has a row in Area 5, and
    binding the orchestrator a second protocol load builds must enqueue none of
    them: they have already been patched, and after a "New slice" their
    coordinates name tissue that is gone.
    """
    orch, panel, _sliceState = _survey(tmp_path)
    orch.run_sync()
    assert panel.cellList.count() == TILE_COUNT

    # No producer on this one, so the flush is the only thing that could fill it.
    second = _orchestrator(tmp_path, name="second.py")
    panel.bindOrchestrator(second)

    assert list(second._queue) == []
    # Proved by running it, not just by reading the deque: a second pass over an
    # already-patched cell is the thing that must not happen.
    ran = []
    second.protocolFile.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    second.run_sync()
    assert ran == [], "a cell from the finished survey was patched again"


def test_a_cell_seeded_before_any_orchestrator_still_reaches_a_later_one(
    qapp, tmp_path
):
    """The other half of the same rule, so "flush nothing" cannot pass: a cell
    the operator seeded into an unbound panel is still handed to the orchestrator
    bound afterward, and is actually run by it."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    class _FakePipette:
        pipetteDevice = None

    pipette = _FakePipette()
    pipette.pipetteDevice = type(
        "_FakeManipulator", (), {"targetPosition": lambda self: (1e-3, 2e-3, 3e-3)}
    )()
    panel = CellPanel(pipetteGetter=lambda: pipette)

    panel.addFromTargetBtn.click()
    assert panel.cellList.count() == 1
    seeded = list(panel._cells.values())[0]

    orch = _orchestrator(tmp_path)
    ran = []
    orch.protocolFile.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    panel.bindOrchestrator(orch)

    assert list(orch._queue) == [seeded]
    orch.run_sync()
    assert ran == [seeded]
