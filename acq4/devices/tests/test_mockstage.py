from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pyqtgraph as pg
import pytest

import acq4.devices.MockStage as mockstage
from acq4.devices.MockStage import MockStage, MockStageThread


@pytest.fixture
def stage(monkeypatch):
    pg.mkQApp()
    monkeypatch.setattr(MockStageThread, 'start', lambda self: None)
    manager = MagicMock()
    manager.readConfigFile.return_value = {}
    stage = MockStage(manager, {}, 'test stage')
    thread = stage.stageThread
    # A zero-distance move arrives in one iteration, without timing or scheduling.
    timestamps = iter([0, 1, 1, 1])
    monkeypatch.setattr(mockstage, 'ptime', SimpleNamespace(time=lambda: next(timestamps)))
    monkeypatch.setattr(mockstage, 'time', SimpleNamespace(sleep=lambda _: thread.quit()))
    yield stage
    stage.quit()


@pytest.mark.parametrize('replacement', ['move', 'velocity', 'stop'])
def test_arrival_does_not_finish_or_clear_replacement(stage, monkeypatch, replacement):
    thread = stage.stageThread
    first = stage._lastMove  # zero-distance priming move created by MockStage
    next_target = np.array([1e-4, 0, 0])
    next_moves = []
    set_position = thread._setPosition

    def replace_after_snapshot(position):
        set_position(position)
        # Simulate a command arriving after the monitor snapshots the old move.
        if replacement == 'move':
            next_moves.append(stage._move(next_target, 1e-3, False))
        elif replacement == 'velocity':
            stage.startMoving(next_target)
        else:
            stage.abort()

    monkeypatch.setattr(thread, '_setPosition', replace_after_snapshot)
    thread.run()

    assert first.isDone()
    assert first.wasInterrupted()
    if replacement == 'move':
        assert not next_moves[0].isDone()
        assert thread.currentMove is next_moves[0]
        np.testing.assert_array_equal(thread.target, next_target)
        assert thread.speed == 1e-3
    elif replacement == 'velocity':
        assert thread.currentMove is None
        np.testing.assert_array_equal(thread.velocity, next_target)
    else:
        assert thread.target is None
        assert thread.velocity is None


@pytest.mark.parametrize('target', [np.zeros(3), np.array([1e-4, 0, 0])])
def test_arrival_completes_move(stage, target):
    thread = stage.stageThread
    move = stage._move(target, 1e-3, False)

    thread.run()

    assert move.isDone()
    assert not move.wasInterrupted()
    assert thread.target is None
    np.testing.assert_array_equal(thread.getPosition(), move.targetPos)


def test_completion_callback_can_start_move(stage):
    thread = stage.stageThread
    move = stage._lastMove
    next_target = np.array([1e-4, 0, 0])
    next_moves = []
    move.onFinish(lambda _: next_moves.append(stage._move(next_target, 1e-3, False)))

    thread.run()

    assert move.isDone()
    assert len(next_moves) == 1
    assert not next_moves[0].isDone()
    np.testing.assert_array_equal(thread.target, next_target)
