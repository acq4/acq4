"""Tests that DocumentedLogModel renders the gentletask throughline in the Task column."""
from types import SimpleNamespace

import pytest

from acq4.util import Qt
from teleprox.log.logviewer.constants import LogColumns


@pytest.fixture(scope="module")
def qapp():
    """A QApplication is required to instantiate the Qt-backed log model."""
    return Qt.QApplication.instance() or Qt.QApplication([])


def _record(**attrs):
    rec = SimpleNamespace(taskName="", throughline=None)
    rec.__dict__.update(attrs)
    return rec


def test_task_column_renders_throughline(qapp):
    """A record's throughline chain is shown joined with ' > ' in the Task column."""
    from acq4.util.LogWindow import DocumentedLogModel

    model = DocumentedLogModel()
    rec = _record(throughline=("CellDetector._detectNeuronsZStack", "detect_neurons"))
    text = model._get_column_text(rec, LogColumns.TASK)
    assert text == "CellDetector._detectNeuronsZStack > detect_neurons"


def test_task_column_falls_back_to_taskname(qapp):
    """A record without a throughline falls back to the base taskName text."""
    from acq4.util.LogWindow import DocumentedLogModel

    model = DocumentedLogModel()
    rec = _record(throughline=(), taskName="legacy-task")
    text = model._get_column_text(rec, LogColumns.TASK)
    assert text == "legacy-task"
