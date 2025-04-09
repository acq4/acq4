import contextlib
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


if __name__ == "__main__":
    unittest.main()
