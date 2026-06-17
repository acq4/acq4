# Regression tests for Manager.move() under an existing device reservation.
# Reproduces the nested-move deadlock (acq4/acq4#543): a thread that holds a device
# reservation issues a move; the planner must re-enter that reservation inline rather
# than block on a worker thread.
from __future__ import annotations

import threading

import numpy as np
import pytest

from acq4.Manager import Manager
from acq4.devices.Device import Device
from acq4.motion.plan import AtomicMove, SequentialGroup
from acq4.motion.planner import MotionPlanner
from acq4.motion.spec import MoveSpec
from acq4.util.gentle import ManualGuiTask


class _FakeDM:
    """Minimal device-manager stub: Device.__init__ only needs declareInterface."""

    def declareInterface(self, name, interfaces, obj):
        pass


class _ReservableDevice(Device):
    """A real Device (real recursive-mutex reservation machinery) that records the
    thread each move runs on instead of touching hardware."""

    def __init__(self, dm, name, pos=(0.0, 0.0, 0.0)):
        Device.__init__(self, dm, {}, name)
        self._pos = np.asarray(pos, dtype=float)
        self.move_threads = []

    def globalPosition(self):
        return self._pos.copy()

    def mapToGlobal(self, local_pos):
        return np.asarray(local_pos, dtype=float) + self._pos

    def mapFromGlobal(self, global_pos):
        return np.asarray(global_pos, dtype=float) - self._pos

    def moveToGlobalNoPlanning(self, pos, speed, name=None, **kwargs):
        self.move_threads.append(threading.current_thread())
        move = ManualGuiTask(name="move")
        move.resolve()
        return move


class _TrivialPlanner(MotionPlanner):
    """Plans each spec as a single AtomicMove to its global target (no geometry)."""

    def plan(self, specs, name=""):
        steps = [
            AtomicMove(device=s.device, position=s.position, speed=s.speed, explanation=name or "move")
            for s in specs
        ]
        return steps[0] if len(steps) == 1 else SequentialGroup(steps=steps)


class _FakeManager:
    """Stands in for the real Manager: exposes the real reserveDevices/move and a trivial planner.

    reserveDevices uses a short timeout so that a (buggy) cross-thread reservation
    attempt fails fast instead of hanging the test for the default 10s.
    """

    RESERVE_TIMEOUT = 1.0

    def __init__(self, planner, devices):
        self._planner = planner
        self._devices = {d.name(): d for d in devices}

    def getDevice(self, name):
        return self._devices[name]

    def reserveDevices(self, devices, timeout=10.0, reserver=None):
        # Reuse the real Manager.reserveDevices behaviour but with a short timeout.
        return Manager.reserveDevices(self, devices, timeout=self.RESERVE_TIMEOUT, reserver=reserver)

    @property
    def motionPlanner(self):
        return self._planner

    # The method under test, bound to this stand-in manager.
    move = Manager.move


@pytest.fixture
def reservation_setup(qtbot, monkeypatch):
    """A device, a fake manager wired to a trivial planner, with getManager patched."""
    (qtbot,)  # noqa: F841 -- ensures a QApplication exists for Device's Qt mutex
    dm = _FakeDM()
    dev = _ReservableDevice(dm, "stage1")
    mgr = _FakeManager(_TrivialPlanner(), [dev])
    # The planner resolves the manager via getManager(); point it at our stand-in.
    monkeypatch.setattr("acq4.motion.planner.getManager", lambda: mgr)
    return mgr, dev


def test_move_under_held_reservation_runs_inline(reservation_setup):
    """Regression for #543: moving a device whose reservation this thread already holds
    must execute inline (re-entering the recursive mutex), not deadlock on a worker thread."""
    mgr, dev = reservation_setup
    target = np.array([1.0, 2.0, 3.0])
    caller_thread = threading.current_thread()

    with mgr.reserveDevices([dev], reserver="run_image_sequence"):
        fut = mgr.move(MoveSpec(dev, target, speed="fast"))
        # Already resolved when run inline; would raise TimeoutError before the fix.
        fut.wait(timeout=5.0)

    assert len(dev.move_threads) == 1
    assert dev.move_threads[0] is caller_thread, "move should run inline on the reserving thread"


def test_move_without_reservation_runs_on_worker_thread(reservation_setup):
    """When no reservation is held, the move is dispatched to a worker thread as before."""
    mgr, dev = reservation_setup
    target = np.array([4.0, 5.0, 6.0])
    caller_thread = threading.current_thread()

    fut = mgr.move(MoveSpec(dev, target, speed="fast"))
    fut.wait(timeout=5.0)

    assert len(dev.move_threads) == 1
    assert dev.move_threads[0] is not caller_thread, "move should run on a worker thread"
