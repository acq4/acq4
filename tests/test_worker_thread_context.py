# Tests for task_stack context propagation in queue-based worker control threads.
# Verifies that each job carries the caller's task_stack snapshot and restores it during handling.

import sys
import queue
import threading
import unittest
from unittest.mock import MagicMock, patch, Mock

from acq4.util.future import task_stack

# ---------------------------------------------------------------------------
# Stub out hardware-dependent modules before importing control threads.
# - motionsynergy_api requires pythonnet (not available in test env)
# - acq4.drivers.Scientifica.__init__ auto-imports Scientifica which pulls in
#   pyserial; stub the package init while leaving control_thread importable.
# ---------------------------------------------------------------------------
_motionsynergy_stub = MagicMock()
_motionsynergy_stub.MotionSynergyException = type('MotionSynergyException', (Exception,), {})
sys.modules.setdefault('acq4.drivers.dovermotion.motionsynergy_api', _motionsynergy_stub)

# Stub the Scientifica package __init__ so importing the sub-module does not
# trigger the auto-import of Scientifica (which needs pyserial).
import importlib.util as _importlib_util
import os as _os
import types as _types

# Resolve the real filesystem path for the Scientifica sub-package so that
# Python's importer can still find acq4.drivers.Scientifica.control_thread.
_acq4_pkg_dir = _os.path.dirname(_importlib_util.find_spec('acq4').origin)
_sci_pkg_dir = _os.path.join(_acq4_pkg_dir, 'drivers', 'Scientifica')
_sci_pkg_stub = _types.ModuleType('acq4.drivers.Scientifica')
_sci_pkg_stub.__path__ = [_sci_pkg_dir]
_sci_pkg_stub.__package__ = 'acq4.drivers.Scientifica'
sys.modules.setdefault('acq4.drivers.Scientifica', _sci_pkg_stub)


# ---------------------------------------------------------------------------
# Helpers to build lightweight test doubles without touching real hardware
# ---------------------------------------------------------------------------

def _make_mock_axis():
    """Return a mock axis object that satisfies the SmartStageControlThread API."""
    axis = MagicMock()
    axis.GetIsEnabled.return_value = MagicMock(Value=True)
    axis.GetActualPosition.return_value = MagicMock(Value=0.0)
    return axis


def _make_mock_motionsynergy(num_axes=3):
    """Return a mock MotionSynergy API object."""
    ms = MagicMock()
    ms.GetFirstProduct.return_value = MagicMock(ProductType='SmartStage')
    ms.AxisList = [_make_mock_axis() for _ in range(num_axes)]
    return ms


# ---------------------------------------------------------------------------
# SmartStage tests
# ---------------------------------------------------------------------------

class TestSmartStageRequestFutureCallerStack(unittest.TestCase):
    """SmartStageRequestFuture captures task_stack at submission time."""

    def _make_future(self, req='position', kwds=None):
        """Create a SmartStageRequestFuture with a mock control thread."""
        from acq4.drivers.dovermotion.control_thread import SmartStageRequestFuture
        mock_ctrl = MagicMock()
        return SmartStageRequestFuture(mock_ctrl, req, kwds or {})

    def test_caller_stack_captured_on_init(self):
        """caller_stack attribute is set when a future is created."""
        fut = self._make_future()
        self.assertTrue(hasattr(fut, 'caller_stack'))

    def test_caller_stack_is_empty_when_no_task_context(self):
        """caller_stack is an empty tuple when there is no active task scope."""
        fut = self._make_future()
        self.assertEqual(fut.caller_stack, ())

    def test_caller_stack_reflects_active_task_chain(self):
        """caller_stack matches task_stack at the moment of future creation."""
        with task_stack.push("outer"):
            with task_stack.push("inner"):
                fut = self._make_future()
        self.assertEqual(fut.caller_stack, ("outer", "inner"))

    def test_caller_stack_is_snapshot_not_live(self):
        """caller_stack does not change if the active task_stack changes later."""
        with task_stack.push("first"):
            fut = self._make_future()
        # After the 'with' block the outer stack is empty again; snapshot is unchanged.
        self.assertEqual(fut.caller_stack, ("first",))


class TestSmartStageHandleRequestContext(unittest.TestCase):
    """_handle_request restores caller's task_stack while executing, then reverts."""

    def _make_patched_ctrl(self):
        """Build a SmartStageControlThread with all hardware calls mocked out."""
        mock_ms = _make_mock_motionsynergy()
        mock_settings = MagicMock()

        with patch(
            'acq4.drivers.dovermotion.control_thread.get_motionsynergyapi',
            return_value=(mock_ms, mock_settings),
        ), patch(
            'acq4.drivers.dovermotion.control_thread.initialize',
        ):
            from acq4.drivers.dovermotion.control_thread import SmartStageControlThread
            ctrl = SmartStageControlThread(
                pos_callback=None,
                poll_interval=0.05,
                callback_threshold=1.0,
                move_complete_threshold=0.1,
            )
        return ctrl

    def test_handle_request_sees_caller_stack_during_execution(self):
        """While _handle_request runs, task_stack reflects the caller's chain."""
        ctrl = self._make_patched_ctrl()
        captured = {}

        from acq4.drivers.dovermotion.control_thread import SmartStageRequestFuture

        class SpyFuture(SmartStageRequestFuture):
            def set_result(self, result):
                captured['stack_during'] = task_stack.get()
                super().set_result(result)

        caller_chain = ("caller_task", "sub_task")
        spy = SpyFuture(ctrl, 'position', {})
        spy.caller_stack = caller_chain

        ctrl._handle_request(spy)

        self.assertEqual(captured['stack_during'], caller_chain)

    def test_handle_request_restores_worker_stack_after_execution(self):
        """After _handle_request completes, task_stack reverts to what it was before."""
        ctrl = self._make_patched_ctrl()

        from acq4.drivers.dovermotion.control_thread import SmartStageRequestFuture

        fut = SmartStageRequestFuture(ctrl, 'position', {})
        fut.caller_stack = ("caller_task",)

        # The worker thread here has an empty stack (default).
        stack_before = task_stack.get()
        ctrl._handle_request(fut)
        stack_after = task_stack.get()

        self.assertEqual(stack_before, stack_after)

    def test_handle_request_restores_even_when_inside_worker_scope(self):
        """Worker's own push_full context is restored correctly after _handle_request."""
        ctrl = self._make_patched_ctrl()

        from acq4.drivers.dovermotion.control_thread import SmartStageRequestFuture

        fut = SmartStageRequestFuture(ctrl, 'position', {})
        fut.caller_stack = ("caller_only",)

        with task_stack.push("worker_scope"):
            ctrl._handle_request(fut)
            stack_restored = task_stack.get()

        self.assertEqual(stack_restored, ("worker_scope",))


# ---------------------------------------------------------------------------
# Scientifica tests
# ---------------------------------------------------------------------------

def _make_mock_scientifica_dev():
    """Return a mock Scientifica device that satisfies ScientificaControlThread's API."""
    dev = MagicMock()
    dev.getSpeed.return_value = 1000.0
    dev.getPos.return_value = [0.0, 0.0, 0.0]
    dev.isMoving.return_value = False
    return dev


class TestScientificaRequestFutureCallerStack(unittest.TestCase):
    """ScientificaRequestFuture captures task_stack at submission time."""

    def _make_future(self, req='stop', kwds=None):
        from acq4.drivers.Scientifica.control_thread import ScientificaRequestFuture
        mock_ctrl = MagicMock()
        return ScientificaRequestFuture(mock_ctrl, req, kwds or {'reason': None})

    def test_caller_stack_captured_on_init(self):
        """caller_stack attribute is set when a future is created."""
        fut = self._make_future()
        self.assertTrue(hasattr(fut, 'caller_stack'))

    def test_caller_stack_is_empty_when_no_task_context(self):
        """caller_stack is an empty tuple when there is no active task scope."""
        fut = self._make_future()
        self.assertEqual(fut.caller_stack, ())

    def test_caller_stack_reflects_active_task_chain(self):
        """caller_stack matches task_stack at the moment of future creation."""
        with task_stack.push("sci_outer"):
            with task_stack.push("sci_inner"):
                fut = self._make_future()
        self.assertEqual(fut.caller_stack, ("sci_outer", "sci_inner"))

    def test_caller_stack_is_snapshot_not_live(self):
        """caller_stack does not change if the active task_stack changes later."""
        with task_stack.push("sci_first"):
            fut = self._make_future()
        self.assertEqual(fut.caller_stack, ("sci_first",))


class TestScientificaHandleRequestContext(unittest.TestCase):
    """_handle_request restores caller's task_stack while executing, then reverts."""

    def _make_ctrl(self):
        """Build a ScientificaControlThread with a mock device."""
        dev = _make_mock_scientifica_dev()
        from acq4.drivers.Scientifica.control_thread import ScientificaControlThread
        ctrl = ScientificaControlThread(dev)
        return ctrl

    def test_handle_request_sees_caller_stack_during_execution(self):
        """While _handle_request runs, task_stack reflects the caller's chain."""
        ctrl = self._make_ctrl()
        captured = {}

        from acq4.drivers.Scientifica.control_thread import ScientificaRequestFuture

        class SpyFuture(ScientificaRequestFuture):
            def set_result(self, result):
                captured['stack_during'] = task_stack.get()
                super().set_result(result)

        caller_chain = ("sci_caller", "sci_sub")
        spy = SpyFuture(ctrl, 'stop', {'reason': None})
        spy.caller_stack = caller_chain

        # _handle_stop calls dev.serial.send which is already mocked on ctrl.dev
        ctrl._handle_request(spy)

        self.assertEqual(captured['stack_during'], caller_chain)

    def test_handle_request_restores_worker_stack_after_execution(self):
        """After _handle_request completes, task_stack reverts to what it was before."""
        ctrl = self._make_ctrl()

        from acq4.drivers.Scientifica.control_thread import ScientificaRequestFuture

        fut = ScientificaRequestFuture(ctrl, 'stop', {'reason': None})
        fut.caller_stack = ("sci_caller",)

        stack_before = task_stack.get()
        ctrl._handle_request(fut)
        stack_after = task_stack.get()

        self.assertEqual(stack_before, stack_after)

    def test_handle_request_restores_even_when_inside_worker_scope(self):
        """Worker's own push_full context is restored correctly after _handle_request."""
        ctrl = self._make_ctrl()

        from acq4.drivers.Scientifica.control_thread import ScientificaRequestFuture

        fut = ScientificaRequestFuture(ctrl, 'stop', {'reason': None})
        fut.caller_stack = ("sci_caller_only",)

        with task_stack.push("sci_worker_scope"):
            ctrl._handle_request(fut)
            stack_restored = task_stack.get()

        self.assertEqual(stack_restored, ("sci_worker_scope",))


if __name__ == "__main__":
    unittest.main()
