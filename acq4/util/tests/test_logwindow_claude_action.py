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
