"""Shared presentation for a failure in Autopatch: the link into acq4's log
window, and Area 5's error block (headline, cell token, traceback, Copy)."""
from __future__ import annotations

from acq4.util import Qt


def showInLog() -> None:
    """Raise acq4's log window so the operator can read the failure in context.

    Imported at call time rather than at module import: get_log_window()
    constructs the window on first use, and importing this module must not be
    what brings a top-level window into existence (tests import it headless).
    ErrorDialog.logClicked is the existing precedent for this hand-off.

    The link narrows the operator's view; it cannot anchor to the failing
    record, because teleprox's LogViewer exposes no select-a-record API. What
    makes the entry findable is the cell token the orchestrator's own messages
    carry -- ErrorBlock shows the same token so it can be pasted into the log
    window's search.
    """
    from acq4.util.LogWindow import get_log_window

    get_log_window().raise_window()


class ErrorBlock(Qt.QWidget):
    """Area 5's rendering of one failure, built from stored text.

    Takes strings, never an exception or an ActionLogEntry: this widget lives in
    the GUI tree for as long as the operator leaves the cell selected, and the
    panel that builds it must not become the thing keeping a traceback's frames
    alive (see acq4.experiment.error_record.describe_exception).
    """

    def __init__(
        self,
        exc_type: str,
        exc_message: str,
        traceback_text: str,
        cell_repr: str | None = None,
    ):
        super().__init__()
        self._tracebackText = traceback_text

        self.headlineLabel = Qt.QLabel(f"{exc_type}: {exc_message}")
        self.headlineLabel.setStyleSheet("color: red; font-weight: bold;")
        self.headlineLabel.setWordWrap(True)

        # Selectable so the token can be copied into the log window's search
        # box, which is the only way to reach the matching record.
        self.cellLabel = Qt.QLabel(f"while processing cell {cell_repr}")
        self.cellLabel.setTextInteractionFlags(Qt.Qt.TextSelectableByMouse)
        self.cellLabel.setVisible(cell_repr is not None)

        self.tracebackView = Qt.QPlainTextEdit(traceback_text)
        self.tracebackView.setReadOnly(True)
        font = Qt.QFont("monospace")
        font.setStyleHint(Qt.QFont.Monospace)
        self.tracebackView.setFont(font)

        self.copyBtn = Qt.QPushButton("Copy")
        self.showInLogBtn = Qt.QPushButton("Show in log")
        self.copyBtn.clicked.connect(self._onCopyClicked)
        self.showInLogBtn.clicked.connect(self._onShowInLogClicked)

        btnRow = Qt.QHBoxLayout()
        btnRow.addWidget(self.copyBtn)
        btnRow.addWidget(self.showInLogBtn)
        btnRow.addStretch()

        layout = Qt.QVBoxLayout()
        layout.addWidget(self.headlineLabel)
        layout.addWidget(self.cellLabel)
        layout.addWidget(self.tracebackView)
        layout.addLayout(btnRow)
        self.setLayout(layout)

    def _onCopyClicked(self) -> None:
        # Qt's clicked signal carries a `checked` bool, which setText would
        # otherwise receive as the clipboard contents.
        Qt.QApplication.clipboard().setText(self._tracebackText)

    def _onShowInLogClicked(self) -> None:
        showInLog()
