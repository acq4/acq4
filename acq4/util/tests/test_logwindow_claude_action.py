"""Tests for the "Debug with Claude" entry points in the error dialog and log window."""

import logging
from unittest import mock

import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def make_record(level=logging.ERROR, msg="boom"):
    return logging.LogRecord(
        name="acq4.devices.Pipette",
        level=level,
        pathname="/fake/p.py",
        lineno=7,
        msg=msg,
        args=(),
        exc_info=None,
    )


def test_dialog_has_a_claude_button(qapp, qtbot):
    from acq4.util.LogWindow import ErrorDialog

    dlg = ErrorDialog()
    qtbot.addWidget(dlg)
    assert dlg.claudeBtn.text() == "Debug with Claude"


def test_dialog_button_sends_the_displayed_record(qapp, qtbot):
    from acq4.util.LogWindow import ErrorDialog

    dlg = ErrorDialog()
    qtbot.addWidget(dlg)
    record = make_record(msg="headstage stalled")
    dlg.show(record)

    with mock.patch("acq4.util.claude_debug.debugRecordWithClaude") as debug:
        dlg.claudeBtn.click()
    debug.assert_called_once()
    assert debug.call_args[0][0] is record


def test_dialog_button_follows_the_queue(qapp, qtbot):
    """Stepping to the next queued error re-points the button at that record."""
    from acq4.util.LogWindow import ErrorDialog

    dlg = ErrorDialog()
    qtbot.addWidget(dlg)
    first, second = make_record(msg="first"), make_record(msg="second")
    dlg.show(first)
    dlg.show(second)  # dialog is visible, so this queues
    assert dlg.currentRecord is first

    dlg.nextMessage()
    assert dlg.currentRecord is second

    with mock.patch("acq4.util.claude_debug.debugRecordWithClaude") as debug:
        dlg.claudeBtn.click()
    assert debug.call_args[0][0] is second


def test_dialog_button_forwards_the_confirmation(qapp, qtbot):
    from acq4.util import LogWindow

    dlg = LogWindow.ErrorDialog()
    qtbot.addWidget(dlg)
    dlg.show(make_record())

    with mock.patch("acq4.util.claude_debug.debugRecordWithClaude") as debug:
        dlg.claudeBtn.click()
    assert debug.call_args.kwargs["confirm"] is not None


def test_button_does_nothing_without_a_record(qapp, qtbot):
    from acq4.util.LogWindow import ErrorDialog

    dlg = ErrorDialog()
    qtbot.addWidget(dlg)
    with mock.patch("acq4.util.claude_debug.debugRecordWithClaude") as debug:
        dlg.claudeBtn.click()
    debug.assert_not_called()


def test_confirmation_defaults_to_no(qapp, qtbot):
    """The teleprox confirmation must not be accept-by-default."""
    from acq4.util.LogWindow import confirmTeleproxServer

    with mock.patch.object(Qt.QMessageBox, "exec_", return_value=Qt.QMessageBox.No):
        assert confirmTeleproxServer() is False
    with mock.patch.object(Qt.QMessageBox, "exec_", return_value=Qt.QMessageBox.Yes):
        assert confirmTeleproxServer() is True


from teleprox.log.logviewer.constants import ItemDataRole


def _model_with_records(records):
    """A DocumentedLogModel whose top-level rows carry *records*."""
    from acq4.util.LogWindow import DocumentedLogModel

    model = DocumentedLogModel()
    for record in records:
        item = Qt.QStandardItem(record.getMessage())
        item.setData(record, ItemDataRole.LOG_RECORD)
        model.appendRow([item])
    return model


def test_menu_keeps_copy_and_adds_claude(qapp, qtbot):
    from acq4.util.LogWindow import DocumentedLogViewer

    viewer = DocumentedLogViewer(logger="test.claude.menu")
    qtbot.addWidget(viewer)
    with mock.patch.object(viewer, "_recordAtIndex", return_value=make_record()):
        menu = viewer._buildRowContextMenu(Qt.QModelIndex())
    labels = [a.text() for a in menu.actions()]
    assert "Copy" in labels
    assert "Debug with Claude" in labels


def test_menu_omits_claude_without_a_record(qapp, qtbot):
    from acq4.util.LogWindow import DocumentedLogViewer

    viewer = DocumentedLogViewer(logger="test.claude.menu2")
    qtbot.addWidget(viewer)
    with mock.patch.object(viewer, "_recordAtIndex", return_value=None):
        menu = viewer._buildRowContextMenu(Qt.QModelIndex())
    assert "Debug with Claude" not in [a.text() for a in menu.actions()]


def test_record_at_index_walks_up_to_the_top_level_row(qapp, qtbot):
    """Right-clicking a child detail row must resolve to its parent's record."""
    from acq4.util.LogWindow import DocumentedLogViewer

    viewer = DocumentedLogViewer(logger="test.claude.walk")
    qtbot.addWidget(viewer)
    record = make_record(msg="parent row")
    model = _model_with_records([record])
    child = Qt.QStandardItem("a detail row")
    model.item(0, 0).appendRow([child])

    viewer.model = model
    with mock.patch.object(viewer, "map_index_to_model", side_effect=lambda i: i):
        assert viewer._recordAtIndex(model.indexFromItem(child)) is record


def test_log_tail_returns_preceding_records_only(qapp, qtbot):
    from acq4.util.LogWindow import DocumentedLogViewer

    viewer = DocumentedLogViewer(logger="test.claude.tail")
    qtbot.addWidget(viewer)
    records = [make_record(msg=f"r{i}") for i in range(5)]
    model = _model_with_records(records)

    viewer.model = model
    with mock.patch.object(viewer, "map_index_to_model", side_effect=lambda i: i):
        tail = viewer._logTailForIndex(model.index(3, 0))
    assert [r.getMessage() for r in tail] == ["r0", "r1", "r2"]


def test_log_tail_is_capped(qapp, qtbot):
    from acq4.util.LogWindow import DocumentedLogViewer, LOG_TAIL_COUNT

    viewer = DocumentedLogViewer(logger="test.claude.cap")
    qtbot.addWidget(viewer)
    records = [make_record(msg=f"r{i}") for i in range(LOG_TAIL_COUNT + 10)]
    model = _model_with_records(records)

    viewer.model = model
    with mock.patch.object(viewer, "map_index_to_model", side_effect=lambda i: i):
        tail = viewer._logTailForIndex(model.index(LOG_TAIL_COUNT + 5, 0))
    assert len(tail) == LOG_TAIL_COUNT
    assert tail[-1].getMessage() == f"r{LOG_TAIL_COUNT + 4}"


def test_menu_action_sends_record_and_tail(qapp, qtbot):
    from acq4.util.LogWindow import DocumentedLogViewer

    viewer = DocumentedLogViewer(logger="test.claude.send")
    qtbot.addWidget(viewer)
    records = [make_record(msg=f"r{i}") for i in range(3)]
    model = _model_with_records(records)

    viewer.model = model
    with mock.patch.object(viewer, "map_index_to_model", side_effect=lambda i: i):
        menu = viewer._buildRowContextMenu(model.index(2, 0))
        action = next(a for a in menu.actions() if a.text() == "Debug with Claude")
        with mock.patch("acq4.util.claude_debug.debugRecordWithClaude") as debug:
            action.trigger()

    assert debug.call_args[0][0] is records[2]
    tail = debug.call_args.kwargs["log_tail"]
    assert [r.getMessage() for r in tail] == ["r0", "r1"]
    assert debug.call_args.kwargs["confirm"] is not None
