from threading import Event

from acq4.util import Qt
from acq4.util.future import future_wrap
from acq4.util.threadrun import runInGuiThread


@future_wrap
def prompt(title, text, choices, extra_text=None, parent=None, _future=None):
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
    is_done = Event()
    msg_box = runInGuiThread(_make_message_box, title, text, choices, extra_text, parent, is_done)

    while not is_done.is_set():
        _future.sleep(0.1)
    return msg_box.clickedButton().text()


def _make_message_box(title, text, choices, extra_text, parent, is_done):
    msg_box = Qt.QMessageBox(parent)
    msg_box.setWindowTitle(title)
    msg_box.setText(text)
    msg_box.setInformativeText(extra_text)
    for choice in reversed(choices):
        msg_box.addButton(choice, Qt.QMessageBox.ButtonRole.AcceptRole)
    msg_box.setWindowModality(Qt.Qt.NonModal)
    msg_box.buttonClicked.connect(is_done.set)
    msg_box.buttonClicked.connect(msg_box.close)
    msg_box.show()
    msg_box.raise_()
    return msg_box
