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
