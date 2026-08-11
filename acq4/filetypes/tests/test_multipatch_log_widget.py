"""Tests that the MultiPatch log viewer keeps its plots out of pyqtgraph's global view registry.
A named ViewBox that outlives its C++ object breaks ViewBox creation process-wide.
"""
import pyqtgraph as pg
import pytest

from acq4.filetypes.MultiPatchLog import MultiPatchLogWidget
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def test_widget_registers_no_global_view_names(qapp):
    """pyqtgraph's NamedViews is process-global and only weakly held, so a plot registered
    there can linger past its own destruction and poison every later ViewBox."""
    before = set(pg.ViewBox.NamedViews)

    widget = MultiPatchLogWidget()
    try:
        assert set(pg.ViewBox.NamedViews) == before
    finally:
        widget.close()


def test_widget_plots_are_unnamed(qapp):
    """The viewer links its axes by PlotItem reference, so its views need no registered names."""
    widget = MultiPatchLogWidget()
    try:
        plots = [item for item in widget._plots_widget.ci.items if isinstance(item, pg.PlotItem)]
        assert plots, "expected the viewer to build at least one plot"
        assert [plot.vb.name for plot in plots] == [None] * len(plots)
    finally:
        widget.close()
