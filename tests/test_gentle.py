# Tests for acq4.util.gentle, the Qt bridge over the gentletask concurrency library.
# Covers GuiTask, the set_state idiom, cooperative stop, stop cascade, event-pumping
# wait(updates=True), run_in_gui_thread, and the gentletask-backed FutureButton.

import threading
import time

from PyQt5.QtWidgets import QApplication

from acq4.util import Qt
from acq4.util.gentle import (
    ManualGuiTask,
    GuiTask,
    FutureButton,
    MultiException,
    MultiFuture,
    MultiTask,
    Promise,
    Stopped,
    ThreadTask,
    check_stop,
    current_state,
    current_task,
    gui_asynch,
    raise_errors,
    run_in_gui_thread,
    set_state,
    sleep,
    synch,
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

    def test_returns_when_calling_task_is_stopped(self):
        # Regression: a cancelled FutureButton fires its finish callback, which
        # marshals to the GUI thread via run_in_gui_thread. _GuiCall's done-signal
        # must be a plain threading.Event so it returns even though current_task()
        # is the just-stopped task; a stop-aware Event would raise Stopped here.
        result_box = []

        def body():
            current_task().stop()  # this task is now stopped
            result_box.append(run_in_gui_thread(lambda: 42))

        ThreadTask(body, name="stopped-caller")
        _pump(until=lambda: bool(result_box))

        assert result_box == [42]


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


class TestManualGuiTask:
    def test_resolve_returns_value_and_fires_finished_on_gui_thread(self):
        # The producer resolves from a worker thread; wait() returns the value
        # and the sigFinished slot must run on the GUI thread.
        gui_thread = QApplication.instance().thread()
        slot_threads = []

        p = ManualGuiTask()
        p.sigFinished.connect(
            lambda task: slot_threads.append(Qt.QtCore.QThread.currentThread())
        )

        def producer():
            p.resolve(99)

        worker = threading.Thread(target=producer)
        worker.start()
        result = p.wait()
        worker.join(timeout=2)
        _pump(until=lambda: bool(slot_threads))

        assert result == 99
        assert p.is_done
        assert slot_threads, "sigFinished slot never fired"
        assert slot_threads[0] is gui_thread

    def test_fail_makes_wait_raise(self):
        p = ManualGuiTask()
        p.fail(ValueError("boom"))
        try:
            p.wait()
            assert False, "expected ValueError"
        except ValueError as e:
            assert "boom" in str(e)

    def test_stop_before_resolve_raises_stopped_and_fires_finished(self):
        got = []
        p = ManualGuiTask()
        p.sigFinished.connect(lambda task: got.append(task))
        p.stop()
        try:
            p.wait()
            assert False, "expected Stopped"
        except Stopped:
            pass
        _pump(until=lambda: bool(got))

        assert p.is_stopped
        assert got == [p]

    def test_set_state_from_producer_emits_on_gui_thread(self):
        # The external producer calls guipromise.set_state(...) directly (the
        # module-level free set_state would not reach it). The signal must be
        # delivered on the GUI thread with the right value.
        gui_thread = QApplication.instance().thread()
        states = []
        slot_threads = []

        p = ManualGuiTask()

        def on_state(task, state):
            states.append(state)
            slot_threads.append(Qt.QtCore.QThread.currentThread())

        p.sigStateChanged.connect(on_state)

        def producer():
            p.set_state("waiting")
            p.resolve(None)

        worker = threading.Thread(target=producer)
        worker.start()
        p.wait()
        worker.join(timeout=2)
        _pump(until=lambda: "waiting" in states)

        assert "waiting" in states
        assert p.state == "waiting"
        assert slot_threads[0] is gui_thread

    def test_constructed_on_worker_thread_delivers_on_gui_thread(self):
        # C2 guard: a ManualGuiTask constructed on a worker thread must still
        # deliver its queued sigFinished to the GUI thread.
        gui_thread = QApplication.instance().thread()

        class Receiver(Qt.QObject):
            def __init__(self):
                Qt.QObject.__init__(self)
                self.slot_threads = []

            def on_finished(self, task):
                self.slot_threads.append(Qt.QtCore.QThread.currentThread())

        receiver = Receiver()  # constructed on the GUI thread
        affinity_at_connect = []
        constructed = threading.Event()
        promise_box = []

        def constructor():
            p = ManualGuiTask()
            promise_box.append(p)
            affinity_at_connect.append(p.thread() is gui_thread)
            p.sigFinished.connect(receiver.on_finished)
            constructed.set()
            p.resolve("ok")

        worker = threading.Thread(target=constructor)
        worker.start()
        constructed.wait(timeout=1)
        worker.join(timeout=2)
        _pump(until=lambda: bool(receiver.slot_threads))

        assert affinity_at_connect == [True], "promise affinity was not the GUI thread"
        assert receiver.slot_threads, "sigFinished slot never fired"
        assert receiver.slot_threads[0] is gui_thread

    def test_resolve_spawns_no_thread(self):
        before = threading.active_count()
        p = ManualGuiTask()
        p.resolve(1)
        p.wait()
        # No worker thread should have been spawned for a Promise.
        assert threading.active_count() == before

    def test_wait_with_updates_returns_result_without_deadlock(self):
        # A GUI-thread caller blocks on the promise; the event loop stays live so
        # a timer keeps firing and a queued resolve from a worker is delivered.
        ticks = []
        timer = Qt.QTimer()
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start(10)

        p = ManualGuiTask()

        def producer():
            time.sleep(0.1)
            p.resolve("late result")

        worker = threading.Thread(target=producer)
        worker.start()
        result = p.wait(updates=True)
        worker.join(timeout=2)
        timer.stop()

        assert result == "late result"
        assert ticks, "event loop was not pumped during wait(updates=True)"

    def test_promise_is_reexported(self):
        # The gentletask Promise must be re-exported from the facade.
        assert Promise is not None


class TestGuiAsynch:
    def test_launcher_returns_started_gui_task(self):
        # gui_asynch auto-starts (like asynch). Verify the launcher builds a
        # started GuiTask and the result flows through. Finish is checked via
        # add_finish_callback (race-free) rather than the sigFinished signal,
        # which a fast body can emit before an external connect (documented).
        got = []

        @gui_asynch
        def body(x):
            set_state("running")
            return x * 2

        task = body(21)
        assert isinstance(task, GuiTask)
        task.add_finish_callback(lambda result, exc: got.append(result))
        result = task.wait()

        assert result == 42
        assert task.is_done
        assert got == [42]

    def test_synch_dewraps_to_run_inline(self):
        # synch(gui_asynch(fn)) runs fn inline (no GuiTask/thread) and returns the value.
        ran_in = []

        @gui_asynch
        def body():
            ran_in.append(threading.current_thread())
            return "inline"

        value = synch(body)()
        assert value == "inline"
        assert ran_in[0] is threading.current_thread()


class TestRaiseErrors:
    def _capture(self):
        captured = []
        old = threading.excepthook
        threading.excepthook = lambda args: captured.append(args.exc_value)
        return captured, old

    def test_failure_raised_on_background_thread(self):
        captured, old = self._capture()
        try:
            p = Promise()
            raise_errors(p, "boom: {error}")
            p.fail(ValueError("kaboom"))
            for _ in range(200):
                if captured:
                    break
                time.sleep(0.005)
        finally:
            threading.excepthook = old
        assert captured and isinstance(captured[0], RuntimeError)
        assert "boom: kaboom" in str(captured[0])

    def test_stopped_is_not_an_error(self):
        captured, old = self._capture()
        try:
            p = Promise()
            raise_errors(p, "boom: {error}")
            p.stop("deliberate")
            time.sleep(0.1)
        finally:
            threading.excepthook = old
        assert captured == []


class TestMultiFuture:
    def test_resolves_to_list_of_results_and_fires_finished_on_gui_thread(self):
        # MultiFuture over two ManualGuiTasks: wait() returns the child results in
        # order, and its own sigFinished slot runs on the GUI thread.
        gui_thread = QApplication.instance().thread()
        slot_threads = []

        a = ManualGuiTask()
        b = ManualGuiTask()
        multi = MultiFuture([a, b], name="pair")
        multi.sigFinished.connect(
            lambda task: slot_threads.append(Qt.QtCore.QThread.currentThread())
        )

        def producer():
            a.resolve("first")
            b.resolve("second")

        worker = threading.Thread(target=producer)
        worker.start()
        result = multi.wait()
        worker.join(timeout=2)
        _pump(until=lambda: bool(slot_threads))

        assert result == ["first", "second"]
        assert multi.is_done
        assert slot_threads, "sigFinished slot never fired"
        assert slot_threads[0] is gui_thread

    def test_child_state_change_reemitted_with_child_as_sender_on_gui_thread(self):
        # A child's sigStateChanged is re-emitted by the MultiFuture, with the
        # CHILD as sender (matching the old MultiFuture), on the GUI thread.
        gui_thread = QApplication.instance().thread()
        senders = []
        states = []
        slot_threads = []

        a = ManualGuiTask()
        b = ManualGuiTask()
        multi = MultiFuture([a, b])

        def on_state(sender, state):
            senders.append(sender)
            states.append(state)
            slot_threads.append(Qt.QtCore.QThread.currentThread())

        multi.sigStateChanged.connect(on_state)

        def producer():
            a.set_state("moving")
            a.resolve(1)
            b.resolve(2)

        worker = threading.Thread(target=producer)
        worker.start()
        multi.wait()
        worker.join(timeout=2)
        _pump(until=lambda: bool(states))

        assert "moving" in states
        assert a in senders, "child should be the sender of the relayed state"
        assert slot_threads[0] is gui_thread

    def test_one_child_failing_makes_wait_raise_that_exception(self):
        a = ManualGuiTask()
        b = ManualGuiTask()
        multi = MultiFuture([a, b])

        a.resolve("ok")
        b.fail(ValueError("child boom"))
        try:
            multi.wait()
            assert False, "expected ValueError"
        except ValueError as e:
            assert "child boom" in str(e)

    def test_stop_stops_all_children(self):
        started = [threading.Event(), threading.Event()]
        stopped = []

        def make_body(i):
            def body():
                started[i].set()
                while True:
                    check_stop()
                    sleep(0.01)
            return body

        a = GuiTask(make_body(0))
        b = GuiTask(make_body(1))
        multi = MultiFuture([a, b])
        for ev in started:
            ev.wait(timeout=1)

        multi.stop("done with you")
        for child in (a, b):
            try:
                child.wait()
            except Stopped:
                pass
            stopped.append(child.is_stopped)

        assert stopped == [True, True]
        assert a.is_stopped and b.is_stopped

    def test_percent_done_returns_min_across_children(self):
        # Children carry a percentDone; the MultiFuture reports the minimum.
        class FakeChild:
            def __init__(self, pct):
                self._pct = pct

            def percentDone(self):
                return self._pct

            def add_finish_callback(self, cb):
                # Never completes during this test; we only probe percentDone.
                pass

        a = FakeChild(0.3)
        b = FakeChild(0.7)
        multi = MultiFuture([a, b])

        assert multi.percentDone() == 0.3

    def test_percent_done_robust_when_child_lacks_percent_done(self):
        # A child without percentDone must not break the min computation.
        a = ManualGuiTask()  # ManualGuiTask has no percentDone
        multi = MultiFuture([a])
        assert multi.percentDone() == 0.0
        a.resolve(None)
        multi.wait()

    def test_multitask_and_multiexception_reexported(self):
        assert MultiTask is not None
        assert MultiException is not None
