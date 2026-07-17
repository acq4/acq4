"""Regression tests for cooperative-stop completion of mock stage moves.

A move interrupted while a cooperative stop is in flight must complete with a
``Stopped``, not a ``RuntimeError``, so callers that suppress ``Stopped`` are not
knocked over by a spurious error.
"""

from __future__ import annotations

import pytest

from acq4.util.task import Stopped


@pytest.fixture
def mock_move_future(qapp):
    """A MockMoveFuture with its task machinery initialized but no stage thread.

    Built by running only the ``MoveFuture`` base initializer, skipping the
    ``setTarget`` on the mock hardware thread that ``MockMoveFuture.__init__``
    would do.
    """
    from acq4.devices.Stage.Stage import MoveFuture
    from acq4.devices.MockStage import MockMoveFuture

    class _FakeDev:
        def name(self):
            return "FakeMockStage"

        def getPosition(self):
            return [0.0, 0.0, 0.0]

    fut = MockMoveFuture.__new__(MockMoveFuture)
    MoveFuture.__init__(
        fut, _FakeDev(), pos=[1e-6, 0.0, 0.0], speed=10e-6, name="test move"
    )
    return fut


def test_mockInterrupt_yields_stopped_when_stopped(mock_move_future):
    """An interrupt that lands during a cooperative stop must not overwrite the
    pending ``Stopped`` with a ``RuntimeError``.
    """
    fut = mock_move_future

    # Simulate the window inside ManualTask.stop(): the stop has been requested
    # (is_stopped True, reason recorded) but the cooperative Stopped has not yet
    # been injected.
    fut._stop_requested.set()
    fut._stop_reason = "Paused"

    fut.mockInterrupt()

    # stop() now injects its Stopped; _finish is idempotent, so this is a no-op if
    # mockInterrupt already completed the future (the bug) and wins otherwise.
    fut._finish(exc=Stopped("Paused"))

    assert fut.is_done
    with pytest.raises(Stopped):
        fut.wait()


def test_mockInterrupt_fails_when_not_stopped(mock_move_future):
    """An interrupt that is NOT a cooperative stop is still a genuine failure."""
    fut = mock_move_future

    fut.mockInterrupt()

    assert fut.is_done
    with pytest.raises(RuntimeError):
        fut.wait()
