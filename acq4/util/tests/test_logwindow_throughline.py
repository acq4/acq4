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


def test_qt_log_handler_applies_its_filters(qapp):
    """The Qt handler feeding the log window runs its filters before delivering a record.

    The Task column reads record.throughline, which the throughline filter attaches.
    A handler that skips filters shows a blank Task column for every record it is the
    first (or only) handler to see.
    """
    import logging

    from gentletask import throughline
    from teleprox.log.logviewer.viewer import QtLogHandler

    from acq4.logging_config import add_throughline_filter

    handler = QtLogHandler()
    add_throughline_filter(handler)

    delivered = []
    handler.new_record.connect(delivered.append)

    record = logging.LogRecord("acq4.probe", logging.DEBUG, __file__, 1, "hi", None, None)
    with throughline(name="cleaning pipette"):
        handler.handle(record)

    assert len(delivered) == 1
    assert delivered[0].throughline == ("cleaning pipette",)
