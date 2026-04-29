# Tests for acq4.util.future — v2 Future API plus TaskStack/task_stack infrastructure.
# Run with: pytest tests/test_future.py
import threading
import time
import unittest

from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])


class TestTaskStack(unittest.TestCase):
    def setUp(self):
        from acq4.util.future import task_stack
        self.task_stack = task_stack

    def test_get_returns_empty_tuple_by_default(self):
        self.assertEqual(self.task_stack.get(), ())

    def test_full_stack_returns_empty_string_when_empty(self):
        self.assertEqual(self.task_stack.full_stack(), "")

    def test_push_appends_name_and_restores(self):
        with self.task_stack.push("foo"):
            self.assertEqual(self.task_stack.get(), ("foo",))
        self.assertEqual(self.task_stack.get(), ())

    def test_nested_push_builds_chain(self):
        with self.task_stack.push("a"):
            with self.task_stack.push("b"):
                self.assertEqual(self.task_stack.get(), ("a", "b"))
                self.assertEqual(self.task_stack.full_stack(), "a > b")
            self.assertEqual(self.task_stack.get(), ("a",))
        self.assertEqual(self.task_stack.get(), ())

    def test_push_full_replaces_chain_and_restores(self):
        with self.task_stack.push("outer"):
            with self.task_stack.push_full(("a", "b")):
                self.assertEqual(self.task_stack.get(), ("a", "b"))
            self.assertEqual(self.task_stack.get(), ("outer",))

    def test_push_in_thread_does_not_affect_parent(self):
        results = {}

        def thread_fn():
            with self.task_stack.push("thread_name"):
                results["in_thread"] = self.task_stack.get()

        t = threading.Thread(target=thread_fn)
        t.start()
        t.join()

        results["in_parent"] = self.task_stack.get()
        self.assertEqual(results["in_thread"], ("thread_name",))
        self.assertEqual(results["in_parent"], ())

    def test_full_stack_with_single_entry(self):
        with self.task_stack.push("only"):
            self.assertEqual(self.task_stack.full_stack(), "only")


class TestCurrentFuture(unittest.TestCase):
    """Tests for the current_future() ambient accessor and context tracking."""

    def test_current_future_is_none_by_default(self):
        from acq4.util.future import current_future
        self.assertIsNone(current_future())

    def test_current_future_set_while_future_runs(self):
        from acq4.util.future import Future, current_future
        captured = {}

        def task():
            captured["during"] = current_future()

        fut = Future(task, name="cf_test")
        fut.wait()
        self.assertIs(captured["during"], fut)

    def test_current_future_is_none_after_future_completes(self):
        from acq4.util.future import Future, current_future
        Future(lambda: None, name="cf_cleanup").wait()
        self.assertIsNone(current_future())

    def test_task_stack_pushed_while_future_runs(self):
        from acq4.util.future import Future, task_stack
        captured = {}

        def task():
            captured["stack"] = task_stack.get()

        Future(task, name="my_task").wait()
        self.assertIn("my_task", captured["stack"])

    def test_task_stack_includes_parent_then_child(self):
        from acq4.util.future import Future, task_stack
        inner_stack = {}

        def inner():
            inner_stack["stack"] = task_stack.get()

        def outer():
            Future(inner, name="inner").wait()

        Future(outer, name="outer").wait()
        self.assertEqual(inner_stack["stack"], ("outer", "inner"))


class TestV2Future(unittest.TestCase):
    """Tests for the v2 Future(fn) API."""

    def test_wait_returns_function_result(self):
        from acq4.util.future import Future
        fut = Future(lambda: 42, name="answer")
        self.assertEqual(fut.wait(), 42)

    def test_is_done_after_wait(self):
        from acq4.util.future import Future
        fut = Future(lambda: None, name="done_check")
        fut.wait()
        self.assertTrue(fut.is_done)

    def test_wait_re_raises_exception(self):
        from acq4.util.future import Future

        def boom():
            raise ValueError("kaboom")

        fut = Future(boom, name="boom")
        with self.assertRaises(ValueError, msg="kaboom"):
            fut.wait()

    def test_stop_interrupts_sleeping_future(self):
        from acq4.util.future import Future, sleep, Stopped
        started = threading.Event()

        def task():
            started.set()
            sleep(60)

        fut = Future(task, name="sleeper")
        started.wait(timeout=2)
        fut.stop()
        with self.assertRaises(Stopped):
            fut.wait()

    def test_is_stopped_after_stop(self):
        from acq4.util.future import Future, sleep
        started = threading.Event()

        def task():
            started.set()
            sleep(60)

        fut = Future(task, name="stop_check")
        started.wait(timeout=2)
        fut.stop()
        fut._done.wait(timeout=2)
        self.assertTrue(fut.is_stopped)

    def test_stop_cascades_to_child(self):
        from acq4.util.future import Future, sleep, Stopped
        child_started = threading.Event()

        def child():
            child_started.set()
            sleep(60)

        def parent():
            child_fut = Future(child, name="child")
            child_started.wait(timeout=2)
            child_fut.wait()

        parent_fut = Future(parent, name="parent")
        child_started.wait(timeout=2)
        parent_fut.stop()
        with self.assertRaises(Stopped):
            parent_fut.wait()

    def test_add_finish_callback_called_on_completion(self):
        from acq4.util.future import Future
        results = []
        fut = Future(lambda: "done", name="cb_test")
        fut.add_finish_callback(lambda result, exc: results.append((result, exc)))
        fut.wait()
        self.assertEqual(results, [("done", None)])

    def test_add_finish_callback_called_immediately_if_already_done(self):
        from acq4.util.future import Future
        fut = Future(lambda: "done", name="cb_immediate")
        fut.wait()
        results = []
        fut.add_finish_callback(lambda result, exc: results.append((result, exc)))
        self.assertEqual(results, [("done", None)])

    def test_wait_timeout_raises(self):
        from acq4.util.future import Future
        fut = Future(lambda: time.sleep(60), name="slow")
        with self.assertRaises(TimeoutError):
            fut.wait(timeout=0.1)
        fut.stop()

    def test_detached_future_not_stopped_by_parent(self):
        from acq4.util.future import Future, sleep
        child_done = threading.Event()

        def child():
            time.sleep(0.2)
            child_done.set()
            return "child_result"

        def parent():
            child_fut = Future(child, name="detached_child", detach=True)
            return child_fut

        parent_fut = Future(parent, name="parent_detach")
        child_fut = parent_fut.wait()
        parent_fut.stop()
        child_done.wait(timeout=2)
        self.assertTrue(child_done.is_set())
        self.assertEqual(child_fut.wait(), "child_result")


class TestSleep(unittest.TestCase):
    def test_sleep_outside_future_behaves_like_time_sleep(self):
        from acq4.util.future import sleep
        t0 = time.monotonic()
        sleep(0.05)
        elapsed = time.monotonic() - t0
        self.assertGreater(elapsed, 0.04)

    def test_sleep_raises_stopped_when_future_is_stopped(self):
        from acq4.util.future import Future, sleep, Stopped
        started = threading.Event()

        def task():
            started.set()
            sleep(60)

        fut = Future(task, name="sleep_stop")
        started.wait(timeout=2)
        fut.stop()
        with self.assertRaises(Stopped):
            fut.wait()

    def test_sleep_completes_normally(self):
        from acq4.util.future import Future, sleep

        def task():
            sleep(0.05)
            return "ok"

        result = Future(task, name="sleep_ok").wait()
        self.assertEqual(result, "ok")


class TestCheckStop(unittest.TestCase):
    def test_check_stop_raises_stopped_when_future_is_stopped(self):
        from acq4.util.future import Future, check_stop, Stopped
        started = threading.Event()
        stopped = threading.Event()

        def task():
            started.set()
            stopped.wait(timeout=2)
            check_stop()

        fut = Future(task, name="check_stop_test")
        started.wait(timeout=2)
        fut.stop()
        stopped.set()
        with self.assertRaises(Stopped):
            fut.wait()

    def test_check_stop_is_noop_outside_future(self):
        from acq4.util.future import check_stop
        check_stop()  # should not raise

    def test_check_stop_is_noop_when_not_stopped(self):
        from acq4.util.future import Future, check_stop

        def task():
            check_stop()
            return "fine"

        self.assertEqual(Future(task, name="cs_noop").wait(), "fine")


class TestQueue(unittest.TestCase):
    def test_get_returns_item(self):
        from acq4.util.future import Future, Queue

        q = Queue()
        q.put("item")

        def task():
            return q.get()

        self.assertEqual(Future(task, name="q_get").wait(), "item")

    def test_get_raises_stopped_when_future_is_stopped(self):
        from acq4.util.future import Future, Queue, Stopped
        q = Queue()
        started = threading.Event()

        def task():
            started.set()
            q.get()

        fut = Future(task, name="q_stop")
        started.wait(timeout=2)
        fut.stop()
        with self.assertRaises(Stopped):
            fut.wait()

    def test_get_outside_future_behaves_normally(self):
        from acq4.util.future import Queue
        q = Queue()
        q.put(99)
        self.assertEqual(q.get(), 99)


class TestEvent(unittest.TestCase):
    def test_wait_returns_when_set(self):
        from acq4.util.future import Future, Event

        ev = Event()
        ev.set()

        def task():
            return ev.wait()

        self.assertTrue(Future(task, name="ev_set").wait())

    def test_wait_raises_stopped_when_future_is_stopped(self):
        from acq4.util.future import Future, Event, Stopped
        ev = Event()
        started = threading.Event()

        def task():
            started.set()
            ev.wait()

        fut = Future(task, name="ev_stop")
        started.wait(timeout=2)
        fut.stop()
        with self.assertRaises(Stopped):
            fut.wait()

    def test_wait_outside_future_behaves_normally(self):
        from acq4.util.future import Event
        ev = Event()
        ev.set()
        self.assertTrue(ev.wait(timeout=0.1))


class TestFutureButton(unittest.TestCase):
    """Tests for the redesigned FutureButton that wraps fn in Future(fn) on click."""

    def _make_button(self, fn, **kwargs):
        from acq4.util.future import FutureButton
        return FutureButton(fn, "Test Button", raiseOnError=False, **kwargs)

    def test_click_runs_fn_in_background(self):
        ran = threading.Event()
        btn = self._make_button(lambda: ran.set())
        btn.click()
        QApplication.processEvents()
        self.assertTrue(ran.wait(timeout=2))

    def test_success_message_shown_on_completion(self):
        btn = self._make_button(lambda: None, success="Done!")
        btn.click()
        QApplication.processEvents()
        import time; time.sleep(0.1)
        QApplication.processEvents()
        self.assertEqual(btn.text(), "Done!")

    def test_failure_message_shown_on_exception(self):
        def boom():
            raise ValueError("oops")
        btn = self._make_button(boom, failure="Oops!")
        btn.click()
        QApplication.processEvents()
        import time; time.sleep(0.1)
        QApplication.processEvents()
        self.assertEqual(btn.text(), "Oops!")

    def test_stop_resets_button(self):
        from acq4.util.future import sleep
        started = threading.Event()
        def task():
            started.set()
            sleep(60)
        btn = self._make_button(task, stoppable=True)
        btn.click()
        QApplication.processEvents()
        started.wait(timeout=2)
        btn.click()  # second click stops it
        QApplication.processEvents()
        import time; time.sleep(0.2)
        QApplication.processEvents()
        self.assertEqual(btn.text(), "Test Button")


if __name__ == "__main__":
    unittest.main()
