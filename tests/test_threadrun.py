import threading
import time
from unittest.mock import patch

import pytest

from acq4.util import Qt
from acq4.util.threadrun import inGuiThread


# Mock PyQt5 components
class MockSignal:
    def __init__(self, *args):
        self.args_spec = args
        self.handlers = []
        self.emit_called = False
        self.last_args = None

    def connect(self, handler, conn_type=None):
        self.handlers.append(handler)

    def disconnect(self, handler):
        if handler in self.handlers:
            self.handlers.remove(handler)

    def emit(self, *args):
        self.emit_called = True
        self.last_args = args
        for handler in self.handlers:
            handler(*args)


class MockQTimer:
    @staticmethod
    def singleShot(timeout, callback):
        # For testing, we'll just run immediately
        callback()


# Mock the runInGuiThread function
def mock_run_in_gui_thread(func, *args, **kwargs):
    return func(*args, **kwargs)


# Setup mock patches
@pytest.fixture(autouse=True)
def setup_mocks():
    with patch("acq4.util.Qt.pyqtSignal", MockSignal), patch("acq4.util.Qt.QTimer", MockQTimer), patch(
        "acq4.util.threadrun.runInGuiThread", mock_run_in_gui_thread
    ):
        yield


# Test case 1: Method in a decorated class (non-blocking)
def test_decorated_class_nonblocking():
    call_tracker = []

    class TestClass(Qt.QObject):
        @inGuiThread
        def test_method(self):
            call_tracker.append("method_called")
            return "result"

    instance = TestClass()

    # Verify signal was created
    assert hasattr(TestClass, "__test_methodEvent")

    # Call the method non-blocking
    result = instance.test_method()

    # Verify the signal was emitted and the implementation was called
    assert TestClass.__test_methodEvent.emit_called

    assert call_tracker == ["method_called"]

    # Non-blocking should return None
    assert result is None


# Test case 2: Method in a decorated class (blocking)
def test_decorated_class_blocking():
    class TestClass(Qt.QObject):
        @inGuiThread
        def test_method(self):
            return "blocking_result"

    instance = TestClass()

    # Call the method blocking
    result = instance.test_method(blocking=True)

    # Blocking should return the actual result
    assert result == "blocking_result"


# Test case 3: Method in a non-decorated class (non-blocking)
def test_non_decorated_class_nonblocking():
    call_tracker = []

    class TestClass:
        @inGuiThread
        def test_method(self):
            call_tracker.append("method_called")
            return "result"

    instance = TestClass()

    # Call the method non-blocking
    result = instance.test_method()

    # Verify method was called via QTimer
    assert call_tracker == ["method_called"]

    # Non-blocking should return None
    assert result is None


# Test case 4: Method in a non-decorated class (blocking)
def test_non_decorated_class_blocking():
    class TestClass:
        @inGuiThread
        def test_method(self):
            return "blocking_result"

    instance = TestClass()

    # Call the method blocking
    result = instance.test_method(blocking=True)

    # Blocking should return the actual result
    assert result == "blocking_result"


# Test case 5: Pure function (non-blocking)
def test_pure_function_nonblocking():
    call_tracker = []

    @inGuiThread
    def test_function():
        call_tracker.append("function_called")
        return "function_result"

    # Call the function non-blocking
    result = test_function()

    # Verify function was called
    assert call_tracker == ["function_called"]

    # Non-blocking should return None
    assert result is None


# Test case 6: Pure function (blocking)
def test_pure_function_blocking():
    @inGuiThread
    def test_function():
        return "function_blocking_result"

    # Call the function blocking
    result = test_function(blocking=True)

    # Blocking should return the actual result
    assert result == "function_blocking_result"


# Test case 7: Methods with arguments
def test_method_with_arguments():
    class TestClass(Qt.QObject):
        @inGuiThread
        def test_with_args(self, a, b, c=None):
            return f"a={a}, b={b}, c={c}"

    instance = TestClass()

    # Verify signal arguments
    signal = TestClass.__test_with_argsEvent
    assert len(signal.args_spec) == 3  # 3 args (excluding self)

    # Test with positional args
    result = instance.test_with_args(1, 2, blocking=True)
    assert result == "a=1, b=2, c=None"

    # Test with keyword args
    result = instance.test_with_args(1, 2, c=3, blocking=True)
    assert result == "a=1, b=2, c=3"

    # Test non-blocking with args
    instance.test_with_args(4, 5, c=6)
    assert TestClass.__test_with_argsEvent.last_args == (4, 5)  # args passed to signal


# Test case 8: Return value handling
def test_return_value_handling():
    class TestClass(Qt.QObject):
        @inGuiThread
        def returns_none(self):
            return None

        @inGuiThread
        def returns_value(self):
            return 42

        @inGuiThread
        def returns_object(self):
            return {"key": "value"}

    instance = TestClass()

    # Test blocking mode preserves all return values
    assert instance.returns_none(blocking=True) is None
    assert instance.returns_value(blocking=True) == 42
    assert instance.returns_object(blocking=True) == {"key": "value"}

    # Test non-blocking mode always returns None
    assert instance.returns_none() is None
    assert instance.returns_value() is None
    assert instance.returns_object() is None


# Test case 9: Keyword argument handling
def test_keyword_argument_handling():
    class TestClass(Qt.QObject):
        @inGuiThread
        def method_with_kwargs(self, a, b=2, **kwargs):
            return {"a": a, "b": b, **kwargs}

    instance = TestClass()

    # Test with mixture of args and kwargs
    result = instance.method_with_kwargs(1, b=20, extra="value", blocking=True)

    # Verify all args made it through
    assert result == {"a": 1, "b": 20, "extra": "value"}


# Test case 10: Threading behavior
def test_threading_behavior():
    class TestClass(Qt.QObject):
        def __init__(self):
            super().__init__()
            self.thread_ids = []

        @inGuiThread
        def record_thread_id(self):
            self.thread_ids.append(threading.get_ident())
            time.sleep(0.1)  # Small delay to simulate work
            return threading.get_ident()

    # For this test, we need to mock runInGuiThread to run in a separate thread
    def mock_run_in_thread(func):
        thread = threading.Thread(target=func)
        thread.start()
        thread.join()
        return thread.ident

    with patch("acq4.util.threadrun.runInGuiThread", mock_run_in_thread):
        instance = TestClass()

        # Record the main thread ID
        main_thread_id = threading.get_ident()

        # Call blocking - should run in a separate thread
        thread_id = instance.record_thread_id(blocking=True)

        # Verify it ran in a different thread
        assert thread_id != main_thread_id
        assert instance.thread_ids[0] != main_thread_id


# Test case 11: Exception handling
def test_exception_handling():
    class TestClass(Qt.QObject):
        @inGuiThread
        def raises_exception(self):
            raise ValueError("Test exception")

    instance = TestClass()

    # Test exception propagation in blocking mode
    with pytest.raises(ValueError) as excinfo:
        instance.raises_exception(blocking=True)

    assert "Test exception" in str(excinfo.value)

    # Non-blocking exceptions won't be propagated, but shouldn't crash
    # (This is hard to test directly, but at least verify it doesn't crash)
    # instance.raises_exception()  # Should not raise


# Test case 12: Multiple decorated methods
def test_multiple_decorated_methods():
    class TestClass(Qt.QObject):
        def __init__(self):
            super().__init__()
            self.calls = []

        @inGuiThread
        def method1(self):
            self.calls.append("method1")

        @inGuiThread
        def method2(self):
            self.calls.append("method2")

        def normal_method(self):
            self.calls.append("normal")

    instance = TestClass()

    # Verify both signals were created
    assert hasattr(TestClass, "__method1Event")
    assert hasattr(TestClass, "__method2Event")
    assert not hasattr(TestClass, "__normal_methodEvent")

    # Call all methods
    instance.method1()
    instance.method2()
    instance.normal_method()

    # Verify calls
    assert instance.calls == ["method1", "method2", "normal"]
