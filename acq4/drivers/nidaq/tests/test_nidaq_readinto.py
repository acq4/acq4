"""DAQmx call sequence of the real driver's Task.read()/readInto(), against a recording fake (no DAQmx calls)."""
import numpy as np
import pytest

PyDAQmx = pytest.importorskip("PyDAQmx")

from acq4.drivers.nidaq.base import DAQReadTimeout
from acq4.drivers.nidaq.nidaq import DAQMX_ERROR_SAMPLES_NOT_YET_AVAILABLE, Task


class _RecordingDriver:
    """Stands in for _NIDAQ: records each call; *responses* maps a function name to a value or callable."""

    def __init__(self, responses):
        self.calls = []
        self.responses = responses

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def fn(*args):
            self.calls.append((name,) + args)
            r = self.responses.get(name)
            return r(*args) if callable(r) else r

        return fn

    def names(self):
        return [c[0] for c in self.calls if c[0] != "ClearTask"]


def _task(chanType=PyDAQmx.Val_AI, numChans=2, read=None, sampsPerChan=None):
    drv = _RecordingDriver({
        "GetTaskNumChans": numChans,
        "GetTaskChannels": ", ".join(f"Dev1/ai{i}" for i in range(numChans)),
        "GetTaskDevices": "Dev1",
        "GetChanType": chanType,
        "GetSampQuantSampPerChan": sampsPerChan,
        "ReadAnalogF64": read,
        "ReadDigitalU32": read,
    })
    task = Task.__new__(Task)  # skip CreateTask
    task.nidaq = drv
    task.handle = "H"
    return task, drv


def _fill(handle, n, timeout, fillMode, arr, size, sampsRead):
    arr[...] = np.arange(arr.size).reshape(arr.shape)


def test_readInto_reads_by_scan_at_offset_into_caller_buffer():
    task, drv = _task(read=_fill)
    raw = np.zeros((100, 2))
    out = raw[10:14]
    task.readInto(out, 10, 0.1)

    assert drv.names() == [
        "GetTaskNumChans", "GetTaskChannels", "GetTaskDevices", "GetChanType",
        "SetReadRelativeTo", "SetReadOffset", "ReadAnalogF64",
    ]
    calls = {c[0]: c[1:] for c in drv.calls}
    assert calls["SetReadRelativeTo"] == ("H", PyDAQmx.Val_FirstSample)
    assert calls["SetReadOffset"] == ("H", 10)
    h, n, timeout, fillMode, arr, size, sampsRead = calls["ReadAnalogF64"]
    assert (h, n, timeout, fillMode, size, sampsRead) == ("H", 4, 0.1, PyDAQmx.Val_GroupByScanNumber, 8, None)
    assert arr is out
    np.testing.assert_array_equal(raw[10:14], np.arange(8).reshape(4, 2))


def test_readInto_uses_digital_read_for_uint32():
    task, drv = _task(chanType=PyDAQmx.Val_DI, numChans=1, read=_fill)
    task.readInto(np.zeros((5, 1), dtype=np.uint32), 0, 0.1)
    assert drv.names()[-1] == "ReadDigitalU32"


def test_readInto_maps_samples_not_available_to_DAQReadTimeout():
    timeoutError = PyDAQmx.DAQmxFunctions.error_by_number[DAQMX_ERROR_SAMPLES_NOT_YET_AVAILABLE]

    def read(*args):
        raise timeoutError("not yet", "DAQmxReadAnalogF64")

    task, drv = _task(read=read)
    with pytest.raises(DAQReadTimeout):
        task.readInto(np.zeros((4, 2)), 0, 0.1)


def test_readInto_passes_other_DAQ_errors_through():
    otherError = PyDAQmx.DAQmxFunctions.error_by_number[-200279]

    def read(*args):
        raise otherError("overflow", "DAQmxReadAnalogF64")

    task, drv = _task(read=read)
    with pytest.raises(otherError):
        task.readInto(np.zeros((4, 2)), 0, 0.1)


@pytest.mark.parametrize("out", [np.zeros((2, 8))[:, ::2], np.zeros((4, 3)), np.zeros(8)])
def test_readInto_rejects_bad_buffers_before_reading(out):
    task, drv = _task(read=_fill)
    with pytest.raises(ValueError):
        task.readInto(out, 0, 0.1)
    assert not any(name.startswith(("Read", "SetRead")) for name in drv.names())


def test_read_call_sequence_unchanged():
    task, drv = _task(read=_fill, sampsPerChan=6)
    buf, _ = task.read()
    assert buf.shape == (2, 6)
    assert drv.names() == [
        "GetSampQuantSampPerChan", "GetTaskNumChans", "GetTaskChannels", "GetTaskDevices", "GetChanType",
        "SetReadRelativeTo", "SetReadOffset", "ReadAnalogF64",
    ]
    calls = {c[0]: c[1:] for c in drv.calls}
    assert calls["SetReadOffset"] == ("H", 0)
    h, n, timeout, fillMode, arr, size, sampsRead = calls["ReadAnalogF64"]
    assert (n, timeout, fillMode, size, sampsRead) == (6, 10.0, PyDAQmx.Val_GroupByChannel, 12, None)
    assert arr is buf
