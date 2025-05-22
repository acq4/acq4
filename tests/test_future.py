import contextlib
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock

from PyQt5.QtWidgets import QApplication

from acq4.util.future import Future, FutureButton, MultiFuture, MultiException
from acq4.util.future import future_wrap

app = QApplication([])


class TestFutureButton(unittest.TestCase):
    def setUp(self):
        self._future = Future.immediate("success")
        self.future_producer = MagicMock(return_value=self._future)
        self.button = FutureButton(
            self.future_producer, "Test Button", stoppable=True, success="Completed", failure="Failed"
        )

    def test_button_initial_state(self):
        self.assertIsNone(self.button._future)
        self.assertEqual(self.button.text(), "Test Button")

    def test_button_click_starts_future(self):
        self.button.click()
        QApplication.processEvents()
        self.assertTrue(self.future_producer.called)
        self.assertTrue(self._future.isDone())
        self.assertEqual("success", self._future.getResult())

    def test_button_success_message(self):
        self.button.click()
        QApplication.processEvents()
        self.assertEqual("Completed", self.button.text())

    def test_erroring_future(self):
        @future_wrap
        def task(_future=None):
            raise ValueError("error")
        self.future_producer.return_value = task()
        self.button.click()
        QApplication.processEvents()
        self.assertEqual("Failed", self.button.text())

    def test_stopped_futures_just_reset(self):
        @future_wrap
        def so_sleepy(_future):
            _future.sleep(1e6, interval=0)

        f = so_sleepy()
        self.future_producer.return_value = f
        self.button.click()
        QApplication.processEvents()
        f.stop("stop")
        time.sleep(0.01)
        self.assertTrue(f.isDone())
        QApplication.processEvents()
        self.assertEqual("Test Button", self.button.text())

    def test_button_stop(self):
        f = Future()
        self.future_producer.return_value = f
        self.button.click()
        QApplication.processEvents()
        self.assertFalse(f._stopRequested)
        self.button.click()  # second click to stop
        QApplication.processEvents()
        self.assertTrue(f._stopRequested)


class TestFuture(unittest.TestCase):
    def test_future_immediate(self):
        result = "test"
        fut = Future.immediate(result)
        self.assertTrue(fut.isDone())
        self.assertEqual(fut.getResult(), result)

    def test_future_executeInThread(self):
        def task(_future):
            return "done"

        fut = Future()
        fut.executeInThread(task, (), {})
        fut.wait()
        self.assertTrue(fut.isDone())
        self.assertEqual(fut.getResult(), "done")

    def test_future_stop(self):
        fut = Future()
        fut.stop("test stop")
        self.assertTrue(fut._stopRequested)
        self.assertEqual(fut.errorMessage(), "test stop")

    def test_future_wait_timeout(self):
        fut = Future()
        with self.assertRaises(Future.Timeout):
            fut.wait(timeout=0.1)

    def test_wrapped_on_error(self):
        @future_wrap
        def boom(_future):
            raise ValueError("error")

        called = False

        def on_error(f):
            nonlocal called
            called = True
        fut = boom(onFutureError=on_error)
        with contextlib.suppress(ValueError):
            fut.wait()
        self.assertTrue(called)

    def test_wrapped_on_no_error(self):
        @future_wrap
        def boom(_future):
            return "success"

        called = False

        def on_error(f):
            nonlocal called
            called = True
        fut = boom(onFutureError=on_error)
        fut.wait()
        self.assertFalse(called)

    def test_future_checkStop(self):
        fut = Future()
        fut.stop()
        with self.assertRaises(Future.StopRequested):
            fut.checkStop()

    def test_future_waitFor(self):
        fut1 = Future.immediate("result1")
        fut2 = Future.immediate("meow")
        fut2.waitFor(fut1)
        self.assertTrue(fut2.isDone())
        self.assertEqual(fut1.getResult(), "result1")

    def test_future_wrap(self):
        @future_wrap
        def task(_future=None):
            return "wrapped"

        fut = task()
        fut.wait()
        self.assertTrue(fut.isDone())
        self.assertEqual(fut.getResult(), "wrapped")

    def test_future_onFinish_immediate(self):
        result = "test"
        called = False

        def on_finish(fut):
            nonlocal called
            self.assertTrue(fut.isDone())
            self.assertEqual(fut.getResult(), result)
            called = True

        fut = Future.immediate(result)
        self.assertFalse(called)
        fut.onFinish(on_finish)
        self.assertTrue(called)

    def test_future_waitFor_nested_exception(self):
        outer_future = Future()
        inner_future = Future()

        def inner_task(_future):
            raise ValueError("inner task failed")

        inner_future.executeInThread(inner_task, (), {})

        with self.assertRaises(ValueError) as cm:
            outer_future.waitFor(inner_future)
        self.assertEqual(str(cm.exception), "inner task failed")
        self.assertFalse(outer_future.isDone()) # waitFor raises, outer_future itself is not "done"

    def test_future_waitFor_outer_stop_requested(self):
        outer_future = Future(name="outer")
        inner_future = Future(name="inner")

        def inner_task_long(_future):
            _future.sleep(15) # sleep long enough to be interrupted

        inner_future.executeInThread(inner_task_long, (), {})

        def stop_outer_then_wait():
            time.sleep(0.05) # give waitFor a chance to start
            outer_future.stop("outer stop")

        wait_thread = threading.Thread(target=lambda: outer_future.waitFor(inner_future))
        stopper_thread = threading.Thread(target=stop_outer_then_wait)

        wait_thread.start()
        stopper_thread.start()
        wait_thread.join()
        stopper_thread.join()
        self.assertTrue(outer_future.wasStopped())
        self.assertTrue(inner_future.wasStopped(), "Inner future should be stopped by parent's StopRequested")
        self.assertEqual(inner_future.errorMessage(), "parent task stop requested")

    def test_future_waitFor_timeout_on_inner(self):
        outer_future = Future()
        inner_future = Future(name="inner")

        def inner_task_slow(_future):
            time.sleep(0.5) # longer than timeout
            return "slow done"

        inner_future.executeInThread(inner_task_slow, (), {})

        with self.assertRaises(Future.Timeout) as cm:
            outer_future.waitFor(inner_future, timeout=0.1)
        self.assertIn("Timed out waiting", str(cm.exception)) # Future name might vary
        self.assertIn(" for <Future inner>", str(cm.exception))
        self.assertFalse(inner_future.isDone()) # inner_future is still running
        inner_future.stop() # clean up
        with contextlib.suppress(Future.Stopped): # wait for it to actually stop
            inner_future.wait(timeout=1)

    def test_future_propagateStopsInto(self):
        parent_future = Future()
        child_future = Future()
        parent_future.propagateStopsInto(child_future)

        self.assertFalse(child_future.wasStopped())
        parent_future.stop("parent stopped")
        self.assertTrue(parent_future.wasStopped())
        self.assertTrue(child_future.wasStopped())
        self.assertEqual(child_future.errorMessage(), "parent stopped")

    def test_future_onFinish_called_after_exception(self):
        fut = Future()
        callback_called = False
        exception_in_callback = None

        def on_finish_handler(f):
            nonlocal callback_called, exception_in_callback
            callback_called = True
            exception_in_callback = f.exceptionRaised()

        fut.onFinish(on_finish_handler)

        test_exception = ValueError("Task failed with exception")
        try:
            raise test_exception
        except ValueError:
            exc_info = sys.exc_info()
            fut._taskDone(interrupted=True, excInfo=exc_info)

        self.assertTrue(callback_called)
        self.assertTrue(fut.isDone())
        self.assertTrue(fut.wasInterrupted())
        self.assertIs(fut.exceptionRaised(), test_exception)
        self.assertIs(exception_in_callback, test_exception)

    def test_future_onFinish_multiple_callbacks(self):
        fut = Future.immediate("done")
        call_count = [0, 0]

        def callback1(f):
            call_count[0] += 1

        def callback2(f):
            call_count[1] += 1

        fut.onFinish(callback1)
        fut.onFinish(callback2)

        self.assertEqual(call_count, [1, 1])

    def test_future_getResult_raises_if_error_with_excInfo(self):
        fut = Future()
        test_exception = TypeError("Specific error")
        try:
            raise test_exception
        except TypeError:
            fut._taskDone(interrupted=True, excInfo=sys.exc_info())

        with self.assertRaises(TypeError) as cm:
            fut.getResult()
        self.assertIs(cm.exception, test_exception)

    def test_future_getResult_raises_runtime_error_if_interrupted_no_excInfo(self):
        fut = Future()
        fut._taskDone(interrupted=True, error="Some interruption")
        with self.assertRaisesRegex(RuntimeError, "Task .* did not complete: Some interruption"):
            fut.getResult()

    def test_future_getResult_raises_if_stopped(self):
        fut = Future()
        fut.stop("user requested stop")
        # Simulate task acknowledging stop
        fut._taskDone(interrupted=True) # error message is already set by stop()

        with self.assertRaises(Future.Stopped) as cm:
            fut.getResult()
        self.assertIn(r"did not complete: user requested stop", str(cm.exception))

    def test_future_double_taskDone_call(self):
        fut = Future()
        fut._taskDone(returnValue="first call")
        self.assertTrue(fut.isDone())
        with self.assertRaises(ValueError) as cm:
            fut._taskDone(returnValue="second call")
        self.assertEqual(str(cm.exception), "_taskDone has already been called.")

    def test_future_state_changes_and_signals(self):
        fut = Future()
        mock_slot = MagicMock()
        fut.sigStateChanged.connect(mock_slot)

        fut.setState("processing")
        mock_slot.assert_called_once_with(fut, "processing")
        self.assertEqual(fut.currentState(), "processing")
        mock_slot.reset_mock()

        fut.setState("processing") # same state
        mock_slot.assert_not_called()
        mock_slot.reset_mock()

        fut.setState("finalizing")
        mock_slot.assert_called_once_with(fut, "finalizing")
        self.assertEqual(fut.currentState(), "finalizing")
        mock_slot.reset_mock()

        fut._taskDone(returnValue="done")
        mock_slot.assert_not_called()
        mock_slot.reset_mock()

        fut2 = Future()
        fut2.sigStateChanged.connect(mock_slot)
        fut2._taskDone(interrupted=True, error="failed")
        mock_slot.assert_not_called()

    def test_future_sleep_interrupt(self):
        fut = Future()

        def task_with_sleep(_future):
            try:
                _future.sleep(5) # Long sleep
                return "slept"
            except Future.StopRequested:
                return "stopped during sleep"

        fut.executeInThread(task_with_sleep, (), {})
        time.sleep(0.1) # let sleep start
        self.assertFalse(fut.isDone())
        fut.stop("interrupt sleep")
        result = fut.getResult() # This will raise Future.Stopped if sleep doesn't handle it
        self.assertEqual(result, "stopped during sleep")
        self.assertTrue(fut.wasStopped())

    def test_future_waitFor_propagates_stop_on_self_stop(self):
        # This test ensures that if self.checkStop() within waitFor raises,
        # the future being waited upon (child) is stopped.
        parent_future = Future(name="parent")
        child_future = Future(name="child_for_waitFor_prop_stop")

        def child_task(_future):
            _future.sleep(10) # Keep child busy

        child_future.executeInThread(child_task, (), {})

        # Start waiting in a thread
        wait_thread_finished_event = threading.Event()
        exception_in_thread = None

        def wait_for_child():
            nonlocal exception_in_thread
            try:
                parent_future.waitFor(child_future, timeout=20)
            except Exception as e:
                exception_in_thread = e
            finally:
                wait_thread_finished_event.set()

        wait_thread = threading.Thread(target=wait_for_child)
        wait_thread.start()

        time.sleep(0.1) # Ensure waitFor has started and child_future is running
        self.assertFalse(child_future.wasStopped())

        parent_future.stop("Parent was stopped externally")
        wait_thread_finished_event.wait(timeout=2) # Wait for waitFor to react

        self.assertTrue(wait_thread_finished_event.is_set(), "Wait thread did not finish")
        self.assertIsInstance(exception_in_thread, Future.StopRequested)
        self.assertTrue(child_future.wasStopped(), "Child future was not stopped when parent was stopped during waitFor")
        self.assertEqual(child_future.errorMessage(), "parent task stop requested")

    def test_future_waitFor_propagates_stop_to_grandchildren(self):
        # This test ensures that if self.checkStop() within waitFor raises,
        # the future being waited upon (child) is stopped.
        parent_future = Future(name="parent")
        child_future = Future(name="child_for_waitFor_prop_stop")
        grandchild_future = Future(name="grandchild_for_waitFor_prop_stop")

        def grandchild_task(_future):
            _future.sleep(1000) # Keep child busy
        grandchild_future.executeInThread(grandchild_task, (), {})
        wait_child_finished_event = threading.Event()
        exception_in_child = None

        def child_task(_future):
            nonlocal exception_in_child
            try:
                _future.waitFor(grandchild_future, timeout=2000)
            except Exception as e:
                exception_in_child = e
            finally:
                wait_child_finished_event.set()

        child_future.executeInThread(child_task, (), {})

        # Start waiting in a thread
        wait_thread_finished_event = threading.Event()
        exception_in_thread = None

        def wait_for_child():
            nonlocal exception_in_thread
            try:
                parent_future.waitFor(child_future, timeout=2000)
            except Exception as e:
                exception_in_thread = e
            finally:
                wait_thread_finished_event.set()

        wait_thread = threading.Thread(target=wait_for_child)
        wait_thread.start()

        time.sleep(0.1) # Ensure waitFor has started and all futures are running
        self.assertFalse(child_future.wasStopped())
        self.assertFalse(grandchild_future.wasStopped())

        parent_future.stop("Parent was stopped externally")
        wait_thread_finished_event.wait(timeout=2) # Wait for waitFor to react
        wait_child_finished_event.wait(timeout=2) # Wait for child to react

        self.assertTrue(wait_thread_finished_event.is_set(), "Wait thread did not finish")
        self.assertIsInstance(exception_in_thread, Future.StopRequested)
        self.assertTrue(wait_child_finished_event.is_set(), "Child wait thread did not finish")
        self.assertIsInstance(exception_in_child, Future.StopRequested)
        self.assertTrue(child_future.wasStopped(), "Child future was not stopped when parent was stopped during waitFor")
        self.assertEqual(child_future.errorMessage(), "parent task stop requested")
        self.assertTrue(grandchild_future.wasStopped(), "Grandchild future was not stopped when parent was stopped during waitFor")
        self.assertEqual(grandchild_future.errorMessage(), "parent task stop requested")


class TestMultiFuture(unittest.TestCase):
    def test_raises_on_one_error(self):
        f1 = Future.immediate("success")
        f2 = Future.immediate(excInfo=[ValueError, ValueError("boom"), None])
        multi = MultiFuture([f1, f2])
        with self.assertRaises(ValueError):
            multi.wait()

    def test_raises_on_multiple_errors(self):
        f1 = Future.immediate("success")
        f2 = Future.immediate(excInfo=[ValueError, ValueError("boom"), None])
        f3 = Future.immediate(excInfo=[ValueError, ValueError("pow"), None])
        multi = MultiFuture([f1, f2, f3])
        with self.assertRaises(RuntimeError) as cm:
            multi.wait()
        self.assertIsInstance(cm.exception.__cause__, MultiException)

    def test_onFinish(self):
        result = "test"
        called = False

        def on_finish(fut):
            nonlocal called
            self.assertTrue(fut.isDone())
            self.assertIn(result, fut.getResult())
            called = True

        fut = MultiFuture([Future.immediate(result)])
        self.assertFalse(called)
        fut.onFinish(on_finish)
        self.assertTrue(called)

    def test_multi_future_stop_propagates(self):
        f1 = Future()
        f2 = Future()
        multi = MultiFuture([f1, f2])
        multi.stop("stop multi")
        self.assertTrue(f1.wasStopped())
        self.assertTrue(f2.wasStopped())
        self.assertEqual(f1.errorMessage(), "stop multi")
        self.assertEqual(f2.errorMessage(), "stop multi")
        self.assertTrue(multi.wasStopped())

    def test_multi_future_percent_done(self):
        class MockPercentFuture(Future):
            def __init__(self, percent):
                super().__init__()
                self._percent = percent
                if percent == 1.0:
                    self._taskDone()

            def percentDone(self):
                return self._percent

        f1 = MockPercentFuture(0.5)
        f2 = MockPercentFuture(0.8)
        multi = MultiFuture([f1, f2])
        self.assertEqual(multi.percentDone(), 0.5)

        f3 = MockPercentFuture(1.0)
        multi_all_done = MultiFuture([f3, MockPercentFuture(1.0)])
        self.assertEqual(multi_all_done.percentDone(), 1.0)
        self.assertTrue(multi_all_done.isDone())

    def test_multi_future_current_state(self):
        f1 = Future.immediate("res1")
        f1.setState("f1_state")
        f2 = Future()
        f2.setState("f2_init_state")
        f2_event = threading.Event()
        def f2_task(_future):
            f2_event.set()
            _future.setState("f2_running")
            time.sleep(0.1)
            _future.setState("f2_done")
            return "res2"
        multi = MultiFuture([f1, f2])
        self.assertIn("f2_init_state", multi.currentState()) # or f2_running depending on timing
        f2.executeInThread(f2_task, (), {})
        f2_event.wait(timeout=1)
        # State can be tricky due to timing, check that it contains individual states
        self.assertIn("f1_state", multi.currentState())
        self.assertIn("f2_running", multi.currentState()) # or f2_running depending on timing
        f2.wait()
        self.assertIn("f1_state", multi.currentState())
        self.assertIn("f2_done", multi.currentState())


if __name__ == "__main__":
    unittest.main()
