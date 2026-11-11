"""MockCamera tasks through a real Manager.Task and NiDAQ on the mock driver."""
import warnings

import numpy as np
import pytest

from acq4.devices.Camera.Camera import Camera, CameraTaskResult
from acq4.devices.Camera.tests.legacy_camera_result import legacyGetResult
from acq4.devices.Camera.tests.test_camera_partial_results import ORDERS, _checkSameAsLegacy
from acq4.devices.DAQGeneric.tests.daq_task_fakes import FakeManager, WaveDAQ, runTask

RATE = 10_000.0
NPTS = 4000  # 0.4 s
EXPOSE = '/Dev1/port0/line3'


@pytest.fixture
def rig(qtbot):
    from acq4.devices.MockCamera import MockCamera

    dm = FakeManager()
    WaveDAQ(dm)
    cam = MockCamera(dm, {'exposeChannel': {'device': 'DAQ', 'channel': EXPOSE, 'type': 'di'}}, 'Camera')
    yield dm, cam
    Camera.quit(cam)


def cameraCommand(interval=None, triggerMode='Normal'):
    protocol = {'duration': NPTS / RATE}
    if interval is not None:
        protocol['updateInterval'] = interval
    return {
        'protocol': protocol,
        'DAQ': {'rate': RATE, 'numPts': NPTS},
        'Camera': {
            'record': True,
            'triggerProtocol': False,
            'params': {'triggerMode': triggerMode},
            'channels': {'exposure': {'record': True}},
        },
    }


@pytest.fixture(autouse=True)
def _quietMeans():
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        yield


@pytest.mark.parametrize('triggerMode', ['Normal', 'TriggerStart'])
def test_no_update_interval_matches_original(rig, triggerMode):
    dm, cam = rig
    task, result = runTask(dm, cameraCommand(triggerMode=triggerMode))
    final = result['Camera']
    assert isinstance(final, CameraTaskResult)
    assert final.isComplete() and final.settlement() == {'frames': len(final.frames())}
    assert len(final.frames()) > 0
    assert final.daqResult().hasColumn('Channel', 'exposure')
    camTask = task.tasks['Camera']
    legacy = legacyGetResult(final.frames(), final.daqResult(), camTask)
    _checkSameAsLegacy(final, legacy, ORDERS[0])


@pytest.mark.parametrize('triggerMode', ['Normal', 'TriggerStart'])
def test_partials_are_settled_prefixes_of_the_final_result(rig, triggerMode):
    # the mock's exposure trace is fixed at the first chunk, so TriggerStart partials see no pulses
    dm, cam = rig
    snaps = []

    def handler(payload):
        res = payload['Camera']
        snaps.append((res, res.settlement()['frames'], res.frames(), res.isComplete()))

    task, result = runTask(dm, cameraCommand(interval=0.05, triggerMode=triggerMode), handler)
    final = result['Camera']
    assert task.partialResultErrors == []
    assert len(snaps) >= 2
    prev = 0
    finalFrames = final.frames()
    for res, settled, frames, complete in snaps:
        assert res is final and not complete
        assert len(frames) == settled >= prev
        assert all(a is b for a, b in zip(frames, finalFrames))
        prev = settled
    if triggerMode == 'Normal':
        assert prev > 0  # free-running camera: frames settle as they arrive
    assert prev <= len(finalFrames)
    assert final.isComplete() and final.settlement() == {'frames': len(finalFrames)}
    _checkSameAsLegacy(final, legacyGetResult(finalFrames, final.daqResult(), task.tasks['Camera']), ORDERS[1])
