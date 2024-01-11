from typing import Optional

import numpy as np

from acq4.devices.Camera import Frame
from acq4.util import Qt
from acq4.util.future import Future
from pyqtgraph import SRTTransform3D
from teleprox import ProcessSpawner
from teleprox.shmem import SharedNDArray


_remote_process: Optional[ProcessSpawner] = None
_shared_array: Optional[SharedNDArray] = None


def _get_shared_array(data: np.ndarray) -> SharedNDArray:
    global _shared_array
    # TODO what if someone else is using it?!
    if _shared_array is not None and _shared_array.data.shape != data.shape:
        # TODO deallocate?
        _shared_array = None
    if _shared_array is None:
        _shared_array = SharedNDArray.copy(data)
    else:
        _shared_array.data[:] = data
    return _shared_array


def _get_remote_process():
    global _remote_process
    # TODO what if someone else is using it?!
    # TODO how does cleanup happen?
    if _remote_process is None:
        _remote_process = ProcessSpawner(name="acq4_object_detection", start_server=False)
    return _remote_process



@Future.wrap
def detect_neurons(frame: Frame, _future: Future):
    shared_array = _get_shared_array(frame.data())
    remote_process = _get_remote_process()
    transform = frame.globalTransform()
    rmt_array = remote_process.client.transfer(shared_array)
    # rmt_transform = remote_process.client.transfer(transform)
    rmt_this = remote_process.client._import("acq4.util.imaging.object_detection")
    return rmt_this._do_neuron_detection(rmt_array.data, transform)


def _do_neuron_detection(data: np.ndarray, transform: SRTTransform3D) -> list:
    print(f"data ({type(data)}). mean == {np.mean(data)}")
    boxes = [(0, 0, 20, 20), (120, 180, 20, 20)]

    def xywh_to_rect(box: tuple):
        x, y, width, height = box
        start = transform.map((x, y))
        end = transform.map((x + width, y + height))
        return start, end
    return [xywh_to_rect(box) for box in boxes]
