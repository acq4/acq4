"""Regression tests for cooperative-stop completion of Sensapex moves.

A paused/stopped Sensapex move must complete its future with a cooperative
``Stopped``, not a ``RuntimeError`` built from the interrupt reason, so callers
that suppress ``Stopped`` (e.g. PatchPipette approach's pause loop) are not
knocked over by a spurious error.
"""

from __future__ import annotations

import pytest

from acq4.util.task import Stopped


@pytest.fixture
def sensapex_move_future(qapp, monkeypatch):
    """A SensapexMoveFuture with its task machinery initialized but no hardware.

    The sensapex driver calls ``getManager()`` at import time, so a stub manager
    is patched in before importing the device module. The future is built by
    running only the ``MoveFuture`` base initializer (skipping the hardware move
    request and monitor thread that ``SensapexMoveFuture.__init__`` would start).
    """

    # The sensapex SDK is only present where sensapex hardware is used; skip
    # elsewhere rather than erroring on a missing dependency.
    pytest.importorskip("sensapex")

    class _StubManager:
        config = {}

    monkeypatch.setattr("acq4.getManager", lambda: _StubManager())

    from acq4.devices.Stage.Stage import MoveFuture
    from acq4.devices.Sensapex import SensapexMoveFuture

    class _FakeDev:
        def name(self):
            return "FakeSensapex"

        def getPosition(self):
            return [0.0, 0.0, 0.0]

    fut = SensapexMoveFuture.__new__(SensapexMoveFuture)
    MoveFuture.__init__(
        fut, _FakeDev(), pos=[1e-6, 0.0, 0.0], speed=10e-6, name="test move"
    )
    return fut


class _InterruptedMoveReq:
    """Stand-in for a sensapex MoveRequest that was interrupted by our own stop."""

    interrupted = True
    interrupt_reason = "Paused"


class _CleanMoveReq:
    """Stand-in for a sensapex MoveRequest that reached its target cleanly."""

    interrupted = False


def test_completeFromMoveReq_yields_stopped_when_stopped(sensapex_move_future):
    """When a move is interrupted by a cooperative stop, the monitor thread's
    completion must not overwrite the pending ``Stopped`` with a ``RuntimeError``.
    """
    fut = sensapex_move_future
    fut._moveReq = _InterruptedMoveReq()

    # Simulate the window inside ManualTask.stop(): the stop has been requested
    # (is_stopped True, reason recorded) but the cooperative Stopped has not yet
    # been injected. This is exactly when the monitor thread runs its completion.
    fut._stop_requested.set()
    fut._stop_reason = "Paused"

    # The monitor thread completes from the interrupted move request.
    fut._completeFromMoveReq()

    # stop() now injects its Stopped; _finish is idempotent, so this is a no-op if
    # the producer already completed the future (the bug) and wins otherwise.
    fut._finish(exc=Stopped("Paused"))

    assert fut.is_done
    with pytest.raises(Stopped):
        fut.wait()


def test_completeFromMoveReq_fails_on_genuine_interruption(sensapex_move_future):
    """An interruption that is NOT a cooperative stop is still a genuine failure."""
    fut = sensapex_move_future
    fut._moveReq = _InterruptedMoveReq()

    fut._completeFromMoveReq()

    assert fut.is_done
    with pytest.raises(RuntimeError):
        fut.wait()


def test_completeFromMoveReq_resolves_on_clean_finish(sensapex_move_future):
    """A move that reaches its target completes successfully."""
    fut = sensapex_move_future
    fut._moveReq = _CleanMoveReq()

    fut._completeFromMoveReq()

    assert fut.is_done
    assert fut.wait() is None
