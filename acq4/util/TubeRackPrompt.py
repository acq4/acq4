"""Tube-rack swap dialog: a grid of id fields laid out like the rack, with a
start-number spinbox and a fill-order toggle that refill it.

The dialog is built, shown, and destroyed entirely on the GUI thread. A worker
thread calling prompt_tube_rack() only ever receives plain data -- a dict of
strings and an int, or None; no QWidget/QObject reference crosses the thread
boundary.

This module knows nothing about id templates, dates or tube counters. It is
handed a `make_ids(start_n, column_major) -> {site index: id}` callable and
calls it whenever either control changes.
"""
from __future__ import annotations

from acq4.util import Qt
from acq4.util.task import Event, run_in_gui_thread

# Dialogs currently on screen, keyed by id(dialog), for the same reason
# PromptUser keeps _live_boxes: it holds each one alive between show() and the
# operator's click without handing a widget reference to the calling thread.
_live_dialogs = {}


def _gui_available() -> bool:
    return Qt.QApplication.instance() is not None


class TubeRackDialog(Qt.QDialog):
    """The grid itself. Built and driven only on the GUI thread."""

    def __init__(self, title, text, rows, cols, make_ids, start_n, extra_text=None, parent=None):
        Qt.QDialog.__init__(self, parent)
        self.setWindowTitle(title)
        self.setWindowModality(Qt.Qt.WindowModality.NonModal)
        self._make_ids = make_ids
        # Indices the operator has typed into; these keep their text through
        # every refill.
        self._overrides = {}
        self.fields = {}

        layout = Qt.QVBoxLayout(self)
        layout.addWidget(Qt.QLabel(text))

        controls = Qt.QHBoxLayout()
        controls.addWidget(Qt.QLabel("First tube number:"))
        self.startSpin = Qt.QSpinBox()
        self.startSpin.setRange(0, 999999)
        self.startSpin.setValue(start_n)
        controls.addWidget(self.startSpin)
        self.columnMajorCheck = Qt.QCheckBox("Fill down columns")
        controls.addWidget(self.columnMajorCheck)
        controls.addStretch()
        layout.addLayout(controls)

        gridWidget = Qt.QWidget()
        self.gridLayout = Qt.QGridLayout(gridWidget)
        for index in range(rows * cols):
            row, col = divmod(index, cols)
            field = Qt.QLineEdit()
            # textEdited, not textChanged: it fires only for the operator's own
            # typing, so a refill below never records itself as an override.
            field.textEdited.connect(lambda _text, i=index: self._onFieldEdited(i))
            self.gridLayout.addWidget(field, row, col)
            self.fields[index] = field
        layout.addWidget(gridWidget)

        self.errorLabel = Qt.QLabel("")
        layout.addWidget(self.errorLabel)

        if extra_text:
            report = Qt.QPlainTextEdit(extra_text)
            report.setReadOnly(True)
            layout.addWidget(report)

        buttons = Qt.QDialogButtonBox(
            Qt.QDialogButtonBox.StandardButton.Ok | Qt.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.startSpin.valueChanged.connect(self._refill)
        self.columnMajorCheck.toggled.connect(self._refill)
        self._refill()

    def _onFieldEdited(self, index):
        self._overrides[index] = self.fields[index].text()

    def _refill(self):
        try:
            ids = self._make_ids(self.startSpin.value(), self.columnMajorCheck.isChecked())
        except Exception as exc:
            self.errorLabel.setText(str(exc))
            ids = {}
        else:
            self.errorLabel.setText("")
        for index, field in self.fields.items():
            if index in self._overrides:
                continue
            field.setText(ids.get(index, ""))

    def result_ids(self) -> dict:
        return {index: field.text() for index, field in self.fields.items()}

    def start_n(self) -> int:
        return self.startSpin.value()


def prompt_tube_rack(title, text, rows, cols, make_ids, start_n, extra_text=None, parent=None):
    """Ask the operator to label a freshly loaded rack.

    Returns ({site index: id string}, confirmed start number), or None if they
    cancelled.

    Headless (no QApplication) returns the generated ids unedited, the way
    actions.prompt.prompt returns its first choice when there is no UI. A
    make_ids that raises there comes back as empty ids rather than as a failed
    run: an id is a label, and losing one must not stop an experiment.

    If the dialog cannot be built at all, run_in_gui_thread raises the exception
    in this thread rather than returning None: a cancel means the operator chose
    not to label, and a broken dialog is not that.
    """
    if not _gui_available():
        try:
            return make_ids(start_n, False), start_n
        except ValueError:
            return {}, start_n
    done = Event()
    result = {}
    run_in_gui_thread(
        _make_dialog, title, text, rows, cols, make_ids, start_n, extra_text, parent, done, result
    )
    done.wait()
    return result["value"]


def _make_dialog(title, text, rows, cols, make_ids, start_n, extra_text, parent, done, result):
    """Build and show the dialog, and arrange for its own teardown -- all on the
    GUI thread, for the reason PromptUser._make_message_box is."""
    dialog = TubeRackDialog(title, text, rows, cols, make_ids, start_n, extra_text, parent)

    def _finished(code):
        if code == Qt.QDialog.DialogCode.Accepted:
            result["value"] = (dialog.result_ids(), dialog.start_n())
        else:
            result["value"] = None
        _live_dialogs.pop(id(dialog), None)
        dialog.deleteLater()
        done.set()

    dialog.finished.connect(_finished)
    _live_dialogs[id(dialog)] = dialog
    dialog.show()
    dialog.raise_()
