# Regression test for the cross-thread QWidget-destruction segfault in
# acq4.util.PromptUser: the QMessageBox it shows must be created, shown, and
# destroyed entirely on the GUI thread, with only a plain str crossing back
# to the worker thread that called prompt().
import threading
import weakref

import pytest

from acq4.util import Qt
from acq4.util.PromptUser import prompt
from acq4.util.task import asynch


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def _wait_for_box(qtbot):
    """The QMessageBox prompt() put on screen, once it is up."""
    for _ in range(500):
        Qt.QApplication.processEvents()
        boxes = [
            w
            for w in Qt.QApplication.topLevelWidgets()
            if isinstance(w, Qt.QMessageBox) and w.isVisible()
        ]
        if boxes:
            return boxes[0]
        qtbot.wait(5)
    raise AssertionError("prompt() never showed a QMessageBox")


def test_a_cancel_label_answers_the_window_close_button(qapp, qtbot):
    """Closing the window emits no buttonClicked, so this used to wait forever."""
    task = asynch(lambda: prompt("title", "message", ["Go"], cancel="Cancel"))()
    box = _wait_for_box(qtbot)

    box.close()

    qtbot.waitUntil(lambda: task.is_done, timeout=2000)
    assert task.wait() == "Cancel"


def test_clicking_the_cancel_button_returns_its_label(qapp, qtbot):
    task = asynch(lambda: prompt("title", "message", ["Go"], cancel="Cancel"))()
    box = _wait_for_box(qtbot)

    next(b for b in box.buttons() if b.text() == "Cancel").click()

    qtbot.waitUntil(lambda: task.is_done, timeout=2000)
    assert task.wait() == "Cancel"


def test_prompt_returns_text_and_destroys_box_on_gui_thread(qapp, qtbot):
    gui_thread_id = threading.get_ident()
    death = {}

    def _record_death():
        death["thread"] = threading.get_ident()

    def worker_body():
        return prompt("title", "message", ["OK", "Cancel"])

    task = asynch(worker_body)()

    def _find_box():
        Qt.QApplication.processEvents()
        boxes = [
            w
            for w in Qt.QApplication.topLevelWidgets()
            if isinstance(w, Qt.QMessageBox) and w.isVisible()
        ]
        return boxes[0] if boxes else None

    box = None
    for _ in range(500):
        box = _find_box()
        if box:
            break
        qtbot.wait(5)
    assert box is not None, "prompt() never showed a QMessageBox"

    weakref.finalize(box, _record_death)
    ok_button = next(b for b in box.buttons() if b.text() == "OK")
    ok_button.click()
    box = None  # drop this test's own reference

    qtbot.waitUntil(lambda: task.is_done, timeout=2000)
    result = task.wait()

    assert result == "OK"

    # The finalizer may fire lazily under refcounting; nudge the collector on
    # both threads (mirroring the original thread-of-death investigation)
    # before asserting where the destruction actually happened.
    import gc

    if "thread" not in death:
        gc.collect()
    if "thread" not in death:
        t = threading.Thread(target=gc.collect)
        t.start()
        t.join()

    assert "thread" in death, "msg_box was never collected at all (leaked)"
    assert death["thread"] == gui_thread_id, (
        "QMessageBox was destroyed on a non-GUI thread "
        f"(gui={gui_thread_id}, death={death['thread']})"
    )
