from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from acq4.devices.MicroManagerStage.mmstage import MicroManagerMoveFuture


def make_move(axes, busy=False, position=(0, 0, 0)):
    device = SimpleNamespace(
        name=lambda: 'test-stage',
        getPosition=lambda: position,
        _getPosition=Mock(return_value=position),
        scale=(1e-6, 1e-6, 1e-6),
        lock=nullcontext(),
        _axes=axes,
        _mmDeviceNames={'xy': 'xy-stage', 'z': 'z-stage'},
        mmc=SimpleNamespace(deviceBusy=Mock(return_value=busy)),
    )
    # Status tests do not issue hardware movement commands.
    return MicroManagerMoveFuture(device, (0, 0, 0), 1, 1, moveXY=False, moveZ=False)


@pytest.mark.parametrize('axes', [('xy',), ('z',), ('xy', 'z')])
def test_busy_move_uses_device_axes(axes):
    move = make_move(axes, busy=True)
    assert not move.isDone()
    move.dev.mmc.deviceBusy.assert_called_once_with(move.dev._mmDeviceNames[axes[0]])
    move.dev._getPosition.assert_not_called()
    assert move.errorMessage() is None


def test_completed_move_and_cached_status():
    move = make_move(('xy', 'z'))
    assert move.isDone()
    assert not move.wasInterrupted()
    assert move.errorMessage() is None
    assert move.dev.mmc.deviceBusy.call_count == 2
    move.dev.mmc.deviceBusy.reset_mock()
    assert move.isDone()
    move.dev.mmc.deviceBusy.assert_not_called()


def test_missed_target_has_error_message():
    move = make_move(('z',), position=(0, 0, 1e-3))
    assert move.isDone()
    assert move.wasInterrupted()
    assert 'Move did not complete' in move.errorMessage()
    assert move._getStatus() == -1


def test_error_message_is_initialized_before_status_is_checked():
    assert make_move(('z',)).errorMessage() is None
