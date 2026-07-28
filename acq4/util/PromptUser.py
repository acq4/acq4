"""User-prompt helper: show a non-modal choice dialog and return the clicked label.

The dialog is built, shown, and destroyed entirely on the GUI thread. A worker
thread calling prompt() only ever receives the clicked button's label (a plain
str); no QWidget/QObject reference crosses the thread boundary.
"""

from acq4.util import Qt
from acq4.util.task import Event, run_in_gui_thread

# Boxes currently on screen, keyed by id(box). Appended in _make_message_box and
# discarded in _on_button_clicked, both of which only ever run on the GUI
# thread, so this keeps each box alive between show() and the user's click
# without ever handing a widget reference to the calling (possibly worker)
# thread.
_live_boxes = {}


def prompt(title, text, choices, extra_text=None, parent=None):
    """
    Prompt the user with a choice.

    Args:
        title (str): Title of the message box.
        text (str): Main text of the message box.
        choices (list): List of button labels.
        extra_text (str): Additional text to display.
        parent (optional Qt.QWidget): Parent widget for the message box.

    Returns:
        str: The label of the button that was clicked.
    """
    done = Event()
    result = {}
    run_in_gui_thread(_make_message_box, title, text, choices, extra_text, parent, done, result)
    done.wait()
    return result["text"]


def _make_message_box(title, text, choices, extra_text, parent, done, result):
    """Build and show the message box, and arrange for its own teardown -- all on the GUI thread.

    Runs on the GUI thread via run_in_gui_thread. The box is held alive in
    _live_boxes until a button is clicked; the click handler below (also
    GUI-thread code, since Qt delivers a widget's own signals on its own
    thread) records the clicked text into `result`, releases the box, and
    schedules its deletion, then signals `done`. Only `result` (a dict holding
    a plain str) and `done` ever cross back to the caller.
    """
    msg_box = Qt.QMessageBox(parent)
    msg_box.setWindowTitle(title)
    msg_box.setText(text)
    msg_box.setInformativeText(extra_text)
    for choice in reversed(choices):
        msg_box.addButton(choice, Qt.QMessageBox.ButtonRole.AcceptRole)
    msg_box.setWindowModality(Qt.Qt.NonModal)

    def _on_button_clicked(button):
        result["text"] = button.text()
        _live_boxes.pop(id(msg_box), None)
        msg_box.close()
        msg_box.deleteLater()
        done.set()

    msg_box.buttonClicked.connect(_on_button_clicked)
    _live_boxes[id(msg_box)] = msg_box
    msg_box.show()
    msg_box.raise_()
