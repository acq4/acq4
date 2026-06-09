# Tests for acq4.util.gentle, the Qt bridge over the gentletask concurrency library.
# Covers GuiTask, the set_state idiom, cooperative stop, stop cascade, event-pumping
# wait(updates=True), run_in_gui_thread, and the gentletask-backed FutureButton.

import threading
import time

from PyQt5.QtWidgets import QApplication

from acq4.util import Qt
from acq4.util.gentle import (
    GuiTask,
    FutureButton,
    Stopped,
    ThreadTask,
    check_stop,
    current_state,
    run_in_gui_thread,
    set_state,
    sleep,
)

app = QApplication.instance() or QApplication([])


def _pump(duration=0.5, until=None):
    """Pump the Qt event loop for up to *duration* seconds, optionally until *until*()."""
    deadline = time.time() + duration
    while time.time() < deadline:
        QApplication.processEvents()
        if until is not None and until():
            return
        time.sleep(0.005)


class TestGuiTask:
    def test_runs_fn_in_thread_and_emits_finished(self):
        # Deterministic "connect before start" contract: construct with
        # start=False, connect, then start(). No Event gate papering over a race.
        worker_thread = []
        got = []

        def body():
            worker_thread.append(threading.current_thread())
            return 42

        t = GuiTask(body, start=False)
        t.sigFinished.connect(lambda task: got.append(task))
        t.start()
        result = t.wait()
        _pump(until=lambda: bool(got))

        assert result == 42
        assert t.is_done
        assert worker_thread[0] is not threading.current_thread()
        assert got == [t]

    def test_set_state_from_body_emits_signal(self):
        states = []

        def body():
            set_state("measuring")
            return "done"

        t = GuiTask(body, start=False)
        t.sigStateChanged.connect(lambda task, state: states.append(state))
        t.start()
        t.wait()
        _pump(until=lambda: "measuring" in states)

        assert "measuring" in states
        assert t.state == "measuring"

    def test_current_state_reads_running_task(self):
        seen = []

        def body():
            set_state("phase-1")
            seen.append(current_state())
            return None

        GuiTask(body).wait()
        assert seen == ["phase-1"]

    def test_set_state_from_nested_task_reports_via_current_state(self):
        # A child task created from inside a parent GuiTask body sets its own
        # state; current_state() inside the child must report the child's state,
        # not the parent's.
        seen = []

        def child_body():
            set_state("child-state")
            seen.append(current_state())
            return "child-result"

        def parent_body():
            set_state("parent-state")
            child = GuiTask(child_body)
            return child.wait()

        result = GuiTask(parent_body).wait()

        assert result == "child-result"
        assert seen == ["child-state"]

    def test_set_state_outside_task_is_noop(self):
        # No current task: must not raise.
        set_state("nobody home")
        assert current_state() is None

    def test_cooperative_stop(self):
        started = threading.Event()
        cleaned_up = []

        def body():
            started.set()
            try:
                while True:
                    check_stop()
                    sleep(0.01)
            finally:
                cleaned_up.append(True)

        t = GuiTask(body)
        started.wait(timeout=1)
        t.stop()
        try:
            t.wait()
        except Stopped:
            pass
        assert t.is_stopped
        assert cleaned_up == [True]

    def test_stop_cascades_to_child_task(self):
        # The headline gentletask feature: stopping a parent GuiTask stops a
        # child task it created. Confirm the Qt bridge did not break it.
        parent_started = threading.Event()
        child_started = threading.Event()
        child_cleaned = []

        def child_body():
            child_started.set()
            try:
                while True:
                    check_stop()
                    sleep(0.01)
            finally:
                child_cleaned.append(True)

        child_box = []

        def parent_body():
            parent_started.set()
            child = ThreadTask(child_body)
            child_box.append(child)
            # The parent waits on the child; a stop on the parent cascades to
            # the child and unwinds both.
            return child.wait()

        parent = GuiTask(parent_body)
        parent_started.wait(timeout=1)
        child_started.wait(timeout=1)
        parent.stop()
        try:
            parent.wait()
        except Stopped:
            pass
        _pump(until=lambda: bool(child_cleaned))

        assert child_box[0].is_stopped
        assert child_cleaned == [True]

    def test_gui_task_from_worker_thread_fires_slot_on_gui_thread(self):
        # C2 regression guard: a GuiTask constructed on a worker thread must
        # still deliver its queued sigFinished to the GUI thread (where the
        # event loop lives), thanks to moveToThread(app.thread()) in __init__.
        #
        # The receiver is a QObject living on the GUI thread (the realistic
        # acq4 pattern — FutureButton, dialogs, etc.). With the sender's
        # affinity pinned to the GUI thread, Qt's AutoConnection from a worker
        # thread to a GUI-thread receiver resolves to a queued delivery that
        # runs on the GUI thread. Without the moveToThread fix, the sender's
        # affinity would be the dead worker thread and the slot would never fire.
        gui_thread = QApplication.instance().thread()

        class Receiver(Qt.QObject):
            def __init__(self):
                Qt.QObject.__init__(self)
                self.slot_threads = []

            def on_finished(self, task):
                self.slot_threads.append(Qt.QtCore.QThread.currentThread())

        receiver = Receiver()  # constructed here, on the GUI thread
        affinity_at_connect = []
        constructed = threading.Event()

        def constructor():
            t = GuiTask(lambda: "result", start=False)
            affinity_at_connect.append(t.thread() is gui_thread)
            t.sigFinished.connect(receiver.on_finished)
            constructed.set()
            t.start()

        worker = threading.Thread(target=constructor)
        worker.start()
        constructed.wait(timeout=1)
        worker.join(timeout=2)

        _pump(until=lambda: bool(receiver.slot_threads))

        assert affinity_at_connect == [True], "task affinity was not the GUI thread"
        assert receiver.slot_threads, "sigFinished slot never fired"
        assert receiver.slot_threads[0] is gui_thread

    def test_wait_with_updates_returns_result_without_deadlock(self):
        # A timer firing on the GUI thread proves the event loop stays responsive
        # while wait(updates=True) blocks.
        ticks = []
        timer = Qt.QTimer()
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start(10)

        def body():
            time.sleep(0.2)
            return "slow result"

        t = GuiTask(body)
        result = t.wait(updates=True)
        timer.stop()

        assert result == "slow result"
        assert ticks, "event loop was not pumped during wait(updates=True)"

    def test_wait_with_updates_reraises_exception(self):
        def body():
            time.sleep(0.05)
            raise ValueError("kaboom")

        t = GuiTask(body)
        try:
            t.wait(updates=True)
            assert False, "expected ValueError"
        except ValueError as e:
            assert "kaboom" in str(e)

    def test_wait_with_updates_timeout_returns_none(self):
        # Documents the CURRENT bridge behavior: wait(updates=True) returns None
        # on timeout. NOTE: this DIVERGES from the old Future.wait, which raised
        # Future.Timeout. This divergence is to be reconciled during call-site
        # migration; for now the bridge returns None and this test pins that.
        def body():
            time.sleep(0.3)
            return "too late"

        t = GuiTask(body)
        result = t.wait(timeout=0.02, updates=True)

        assert result is None
        assert not t.is_done
        t.wait()  # let it finish so the thread is not left dangling


class TestRunInGuiThread:
    def test_returns_result_inline_on_gui_thread(self):
        assert run_in_gui_thread(lambda x: x * 2, 21) == 42

    def test_runs_on_gui_thread_when_called_from_worker(self):
        # Assert the function actually ran on the GUI thread, not just that a
        # result came back.
        gui_thread = QApplication.instance().thread()
        result_box = []

        def fn():
            return Qt.QtCore.QThread.currentThread()

        def worker():
            result_box.append(run_in_gui_thread(fn))

        t = threading.Thread(target=worker)
        t.start()
        _pump(until=lambda: bool(result_box))
        t.join(timeout=2)

        assert result_box, "run_in_gui_thread never returned"
        assert result_box[0] is gui_thread


class TestFutureButton:
    def test_click_starts_task_and_shows_success(self):
        produced = []

        def producer():
            t = GuiTask(lambda: "ok")
            produced.append(t)
            return t

        button = FutureButton(producer, "Go", success="Completed")
        button.click()
        _pump(until=lambda: button.text() == "Completed")

        assert len(produced) == 1
        assert button.text() == "Completed"

    def test_click_shows_failure(self):
        def boom():
            raise ValueError("nope")

        button = FutureButton(
            lambda: GuiTask(boom), "Go", failure="Failed", raiseOnError=False
        )
        button.click()
        _pump(until=lambda: button.text() == "Failed")

        assert button.text() == "Failed"

    def test_stoppable_second_click_stops(self):
        started = threading.Event()

        def body():
            started.set()
            while True:
                check_stop()
                sleep(0.01)

        the_task = []

        def producer():
            t = GuiTask(body)
            the_task.append(t)
            return t

        button = FutureButton(producer, "Run", stoppable=True)
        button.click()
        started.wait(timeout=1)
        assert not the_task[0].is_stopped

        button.click()  # second click stops
        _pump(until=lambda: the_task[0].is_stopped)
        assert the_task[0].is_stopped
