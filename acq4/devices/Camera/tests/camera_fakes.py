"""Fakes for CameraTask partial-result tests: frames, frame futures, a synthetic DAQ result, a task builder."""
import copy
import logging

import numpy as np

from MetaArray import axis
from acq4.devices.Camera.Camera import CameraTask
from acq4.util.partial_results import SettleSpec, TaskResultArray

RATE = 10_000.0
NPTS = 2000


class FakeFrame:
    def __init__(self, index, time, shape=(4, 3)):
        self._data = np.full(shape, index, dtype=np.uint16)
        self._info = {'time': time, 'id': index, 'exposure': 1e-3}

    def data(self):
        return self._data

    def info(self):
        return self._info


def makeFrames(n, t0=100.0, period=0.011, jitter=0.0013):
    """*n* FakeFrames with camera timestamps t0 + k*period plus a fixed pseudo-random jitter."""
    rng = np.random.default_rng(n)
    return [FakeFrame(k, t0 + k * period + jitter * rng.uniform()) for k in range(n)]


class FakeFuture:
    """FrameAcquisitionFuture stand-in: frames arrive when the test says so."""

    def __init__(self, frames=()):
        self._frames = list(frames)
        self.is_done = False

    def arrive(self, frames):
        self._frames.extend(frames)

    def peekAtResult(self):
        return self._frames[:]

    def stop(self):
        self.is_done = True

    def wait(self, timeout=None):
        return self._frames


class FakeFixedFuture:
    """The future of a fixed-count acquisition: no peekAtResult(), frames only at the end."""

    def __init__(self, frames):
        self._frames = list(frames)
        self.is_done = False

    def stop(self):
        self.is_done = True

    def wait(self, timeout=None):
        return self._frames


def pulseTrace(pulses, npts=NPTS, startHigh=False):
    """Exposure trace that is 1 on [on, off) for each (on, off) in *pulses*, else 0."""
    trace = np.zeros(npts)
    for on, off in pulses:
        trace[on:off] = 1
    if startHigh:
        trace[0] = 1
    return trace


class SyntheticDaq:
    """A DAQ TaskResultArray with 'trigger' and 'exposure' rows whose settled prefix the test advances.

    Unsettled samples are 0, as in DAQ partial results.
    """

    def __init__(self, exposure, specs=None):
        self.full = np.vstack([np.zeros_like(exposure), exposure])
        n = exposure.shape[0]
        info = [
            axis(name='Channel', cols=[('trigger', None), ('exposure', None)]),
            axis(name='Time', units='s', values=np.linspace(0, float(n - 1) / RATE, n)),
            {'DAQ': {'exposure': {}, 'trigger': {}}},
        ]
        self.result = TaskResultArray(np.zeros_like(self.full), info=info)
        self.result._initSettlement(['trigger', 'exposure'])
        self.specs = specs if specs is not None else {'exposure': SettleSpec(0.0), 'trigger': SettleSpec(0.0)}

    def settle(self, n):
        prev = self.result.settlement()['exposure']
        n = min(n, self.full.shape[1])
        if n > prev:
            self.result.asarray()[:, prev:n] = self.full[:, prev:n]
            self.result._setSettled('exposure', n)
            self.result._setSettled('trigger', n)

    def settled(self):
        return self.result.settlement()['exposure']

    # ResultAccumulator interface used by DAQGenericTask
    def partialResult(self):
        return self.result

    def getResult(self):
        self.settle(self.full.shape[1])
        self.result._setComplete()
        return self.result

    def settleSpecs(self):
        return dict(self.specs)


class NoDaq:
    def partialResult(self):
        return None

    def getResult(self):
        return None

    def settleSpecs(self):
        return {}


class FakeCameraDev:
    logger = logging.getLogger('acq4.tests.fakeCamera')

    def __init__(self):
        self.calls = []

    def stop(self, block=False):
        self.calls.append('stop')

    def start(self, block=False):
        self.calls.append('start')


PRECISE = {'params': {'triggerMode': 'TriggerStart'}}
TRIGGER_PROTOCOL = {'params': {'triggerMode': 'Normal'}, 'triggerProtocol': True}
NORMAL = {'params': {'triggerMode': 'Normal'}}


def makeTask(camCmd, daq=None, future=None, buffered=('exposure', 'trigger')):
    """A configured-and-started CameraTask over fakes; *daq* is a SyntheticDaq or None."""
    camCmd = copy.deepcopy(camCmd)
    camCmd.setdefault('channels', {ch: {'record': True} for ch in buffered})
    task = CameraTask(FakeCameraDev(), camCmd, None)
    task.bufferedChannels = list(buffered) if daq is not None else []
    task._resultAcc = daq if daq is not None else NoDaq()
    task._future = future
    task._dev_was_running = True  # getResult() leaves the fake camera alone
    return task
