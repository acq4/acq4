"""User-prompt helper: show a non-modal choice dialog and return the clicked label.

The dialog is built on the GUI thread and awaited as a gentletask task, so a
caller can wait on it stop-awarely and cancel it.
"""

from acq4.util import Qt
from acq4.util.task import Event, asynch, run_in_gui_thread


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
    msg_box = run_in_gui_thread(_make_message_box, title, text, choices, extra_text, parent, done)
    done.wait()
    return msg_box.clickedButton().text()


def _make_message_box(title, text, choices, extra_text, parent, done):
    msg_box = Qt.QMessageBox(parent)
    msg_box.setWindowTitle(title)
    msg_box.setText(text)
    msg_box.setInformativeText(extra_text)
    for choice in reversed(choices):
        msg_box.addButton(choice, Qt.QMessageBox.ButtonRole.AcceptRole)
    msg_box.setWindowModality(Qt.Qt.NonModal)
    msg_box.buttonClicked.connect(done.set)
    msg_box.buttonClicked.connect(msg_box.close)
    msg_box.show()
    msg_box.raise_()
    return msg_box
