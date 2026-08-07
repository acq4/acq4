"""Tests for Autopatch's shared error presentation: the log-window link and the
Area 5 error block."""
import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def test_show_in_log_raises_the_log_window(qapp, monkeypatch):
    from acq4.modules.Autopatch import error_display

    raised = []

    class _FakeLogWindow:
        def raise_window(self):
            raised.append(True)

    monkeypatch.setattr(
        "acq4.util.LogWindow.get_log_window", lambda: _FakeLogWindow()
    )
    error_display.showInLog()
    assert raised == [True]


def test_error_block_shows_headline_traceback_and_cell_token(qapp):
    from acq4.modules.Autopatch.error_display import ErrorBlock

    block = ErrorBlock(
        "BrokenPipette", "tip sheared off", "Traceback...\nBrokenPipette: tip sheared off\n",
        "<Cell at (1, 2, 3)>",
    )
    assert block.headlineLabel.text() == "BrokenPipette: tip sheared off"
    assert "BrokenPipette: tip sheared off" in block.tracebackView.toPlainText()
    assert "<Cell at (1, 2, 3)>" in block.cellLabel.text()
    assert block.cellLabel.isVisibleTo(block) is True


def test_error_block_hides_the_cell_row_when_there_is_no_cell(qapp):
    # A producer failure has no cell token to paste into the log search; an
    # empty row would read as "cell: (blank)" rather than as "not applicable".
    from acq4.modules.Autopatch.error_display import ErrorBlock

    block = ErrorBlock("RuntimeError", "camera unplugged", "Traceback...\n")
    assert block.cellLabel.isVisibleTo(block) is False


def test_error_block_traceback_is_read_only_and_selectable(qapp):
    from acq4.modules.Autopatch.error_display import ErrorBlock

    block = ErrorBlock("RuntimeError", "boom", "Traceback...\n")
    assert block.tracebackView.isReadOnly() is True


def test_copy_button_puts_the_traceback_on_the_clipboard(qapp):
    from acq4.modules.Autopatch.error_display import ErrorBlock

    traceback_text = "Traceback (most recent call last):\n  RuntimeError: boom\n"
    block = ErrorBlock("RuntimeError", "boom", traceback_text)
    Qt.QApplication.clipboard().clear()
    block.copyBtn.click()
    assert Qt.QApplication.clipboard().text() == traceback_text


def test_show_in_log_button_raises_the_log_window(qapp, monkeypatch):
    from acq4.modules.Autopatch.error_display import ErrorBlock

    raised = []

    class _FakeLogWindow:
        def raise_window(self):
            raised.append(True)

    monkeypatch.setattr(
        "acq4.util.LogWindow.get_log_window", lambda: _FakeLogWindow()
    )
    block = ErrorBlock("RuntimeError", "boom", "Traceback...\n")
    block.showInLogBtn.click()
    assert raised == [True]
