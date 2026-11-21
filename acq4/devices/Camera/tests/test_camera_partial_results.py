"""CameraTask partial results over fake frames and a synthetic exposure trace, against the original result."""
import math
import threading
import time
import warnings

import numpy as np
import pytest

from acq4.devices.Camera.Camera import CameraTaskResult
from acq4.devices.Camera.tests.camera_fakes import (
    NORMAL, PRECISE, TRIGGER_PROTOCOL, NPTS, FakeFixedFuture, FakeFuture, SyntheticDaq, makeFrames, makeTask,
    pulseTrace,
)
from acq4.devices.Camera.tests.legacy_camera_result import legacyGetResult
from acq4.devices.DAQGeneric.tests.daq_task_fakes import assertSameValue
from acq4.util.partial_results import SettleSpec

# 12 pulses, 40 samples high, every 150 samples, starting at 60
PULSES = [(60 + 150 * k, 100 + 150 * k) for k in range(12)]


@pytest.fixture(autouse=True)
def _quietMeans():
    # frameTimes() takes means of empty slices for short traces; it always has
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        yield


def completePulses(trace, n, startsHigh):
    """Pulses of trace[:n] that frameTimes() would see as complete, computed from scratch."""
    ex = trace[:n].astype(np.int32)
    if len(ex) == 0:
        return 0
    exd = ex[1:] - ex[:-1]
    on = list(np.argwhere(exd > 0.5)[:, 0] + 1)
    if startsHigh and ex[0] > 0.5:
        on = [0] + on
    off = np.argwhere(exd < -0.5)[:, 0] + 1
    if len(off) == 0:
        return 0
    return sum(1 for i in on if i < off[-1])


def chunkSchedule(seed, npts=NPTS):
    """Increasing settled counts in random chunks, including 1-sample chunks and edge-aligned boundaries."""
    rng = np.random.default_rng(seed)
    edges = sorted({e for p in PULSES for e in p} | {e + 1 for p in PULSES for e in p})
    points = set(rng.integers(1, npts, size=40).tolist()) | set(rng.choice(edges, size=10).tolist())
    points |= set(range(PULSES[2][1] - 3, PULSES[2][1] + 3))
    return sorted(points) + [npts]


def runPartials(task, daq, future, schedule, frameArrivals):
    """Advance DAQ settlement through *schedule*; frameArrivals[i] frames arrive before step i. Returns snapshots."""
    snaps = []
    for i, n in enumerate(schedule):
        future.arrive(frameArrivals.get(i, []))
        daq.settle(n)
        res = task.partialResult()
        snaps.append((n, len(future.peekAtResult()), res.settlement()['frames'], res, res.frames()))
    return snaps


@pytest.mark.parametrize('seed', [0, 1, 2])
@pytest.mark.parametrize('mode', ['precise', 'triggerProtocol'])
def test_settled_frames_follow_complete_pulses_across_chunks(mode, seed):
    startsHigh = mode == 'triggerProtocol'
    pulses = [(0, 30)] + PULSES[1:] if startsHigh else PULSES
    trace = pulseTrace(pulses)
    daq = SyntheticDaq(trace)
    future = FakeFuture()
    task = makeTask(TRIGGER_PROTOCOL if startsHigh else PRECISE, daq, future)
    frames = makeFrames(len(pulses) + 2)  # two frames with no pulse: never settle early
    schedule = chunkSchedule(seed)
    arrivals = {0: frames[:3], len(schedule) // 3: frames[3:9], 2 * len(schedule) // 3: frames[9:]}

    prev = 0
    for n, nArrived, settled, res, resFrames in runPartials(task, daq, future, schedule, arrivals):
        assert settled == min(nArrived, completePulses(trace, n, startsHigh)), n
        assert prev <= settled <= len(frames)
        prev = settled
        assert resFrames == frames[:settled]
        assert not res.isComplete()
    assert prev == len(pulses)  # the two extra frames wait for the final result

    final = task.getResult()
    assert final is res
    assert final.isComplete() and final.settlement() == {'frames': len(frames)}


def test_pulse_straddling_chunk_boundary_settles_on_its_falling_edge():
    trace = pulseTrace(PULSES)
    daq = SyntheticDaq(trace)
    future = FakeFuture(makeFrames(3))
    task = makeTask(PRECISE, daq, future)
    on, off = PULSES[0]
    for n, expected in [(on, 0), (on + 1, 0), (off - 1, 0), (off, 0), (off + 1, 1), (PULSES[1][1], 1),
                        (PULSES[1][1] + 1, 2)]:
        daq.settle(n)
        assert task.partialResult().settlement()['frames'] == expected, n


def test_edge_detection_never_rescans_settled_samples():
    trace = pulseTrace(PULSES)
    daq = SyntheticDaq(trace)
    future = FakeFuture(makeFrames(len(PULSES)))
    task = makeTask(PRECISE, daq, future)
    data = daq.result.asarray()
    expRow = daq.result.listColumns('Channel').index('exposure')
    for n in range(97, NPTS, 97):
        daq.settle(n)
        settled = task.partialResult().settlement()['frames']
        assert settled == completePulses(trace, n, False)
        data[expRow, :n] = 7  # garbage in already-examined samples must not matter


def test_frames_arriving_after_their_pulses_settle_when_they_arrive():
    trace = pulseTrace(PULSES)
    daq = SyntheticDaq(trace)
    future = FakeFuture()
    task = makeTask(PRECISE, daq, future)
    frames = makeFrames(len(PULSES))
    daq.settle(NPTS)
    assert task.partialResult().settlement()['frames'] == 0
    future.arrive(frames[:5])
    assert task.partialResult().settlement()['frames'] == 5
    future.arrive(frames[5:])
    assert task.partialResult().settlement()['frames'] == len(PULSES)


@pytest.mark.parametrize('camCmd,buffered', [
    (NORMAL, ('exposure', 'trigger')),  # exposure recorded but camera free-running
    (PRECISE, ('trigger',)),  # triggered but exposure not recorded
])
def test_camera_timestamp_mode_settles_every_arrived_frame(camCmd, buffered):
    daq = SyntheticDaq(pulseTrace(PULSES))
    future = FakeFuture()
    task = makeTask(camCmd, daq, future, buffered=buffered)
    frames = makeFrames(6)
    for k in range(6):
        future.arrive([frames[k]])
        res = task.partialResult()  # no DAQ data settled at all
        assert res.settlement()['frames'] == k + 1
        assert res.frames() == frames[:k + 1]


def test_no_daq_channels_settles_every_arrived_frame():
    future = FakeFuture(makeFrames(4))
    task = makeTask(NORMAL, None, future)
    res = task.partialResult()
    assert res.settlement() == {'frames': 4} and res.daqResult() is None
    assert task.getResult() is res


def test_no_partial_before_acquisition_exists():
    task = makeTask(NORMAL, SyntheticDaq(pulseTrace(PULSES)), None)
    assert task.partialResult() is None


def test_fixed_frame_count_has_no_partial_frames():
    daq = SyntheticDaq(pulseTrace(PULSES))
    frames = makeFrames(3)
    task = makeTask({**PRECISE, 'minFrames': 3}, daq, FakeFixedFuture(frames))
    daq.settle(NPTS // 2)
    res = task.partialResult()
    assert res.settlement() == {'frames': 0} and res.frames() == []
    assert res.daqResult() is daq.result
    assert task.settleSpecs()['frames'] == SettleSpec(math.inf, task.settleSpecs()['frames'].reason)
    final = task.getResult()
    assert final is res and final.frames() == frames


def test_settle_specs():
    specs = {'exposure': SettleSpec(0.002, 'x'), 'trigger': SettleSpec(0.0)}
    precise = makeTask(PRECISE, SyntheticDaq(pulseTrace(PULSES), specs), FakeFuture()).settleSpecs()
    assert precise['exposure'] == specs['exposure'] and precise['trigger'] == specs['trigger']
    assert precise['frames'].delay == 0.002 and 'exposure' in precise['frames'].reason

    normal = makeTask(NORMAL, SyntheticDaq(pulseTrace(PULSES), specs), FakeFuture()).settleSpecs()
    assert normal['frames'].delay == 0.0

    noExpSpec = makeTask(PRECISE, SyntheticDaq(pulseTrace(PULSES), {}), FakeFuture()).settleSpecs()
    assert set(noExpSpec) == {'frames'} and not noExpSpec['frames'].updates

    assert makeTask(NORMAL, None, FakeFuture()).settleSpecs() == {'frames': SettleSpec(0.0, 'camera timestamps')}


def _checkSameAsLegacy(new, old, callOrder):
    """Compare *new* against the legacy result, calling accessors in *callOrder* on both."""
    for name in callOrder:
        a, b = getattr(new, name)(), getattr(old, name)()
        if name == 'frames':
            assert len(a) == len(b) and all(x is y for x, y in zip(a, b))
        elif name == 'info':
            assert a.pop('validFrames', None) == (len(old.frames()) if b else None)
            assertSameValue(a, b, 'info')
        elif name == 'asMetaArray':
            assert type(a).__name__ == 'MetaArray'
            np.testing.assert_array_equal(a.asarray(), b.asarray())
            assert a.dtype == b.dtype and a.shape == b.shape
            info = [dict(x) for x in a._info]
            assert info[-1].pop('validFrames') == len(old.frames())
            assertSameValue(info, b._info, 'marr._info')
        elif name == 'frameTimes':
            assert a[1] == b[1]
            np.testing.assert_array_equal(a[0], b[0])
        elif name == 'asArray':
            np.testing.assert_array_equal(a, b)
            assert a.dtype == b.dtype
        elif name == 'daqResult':
            assert a is b


ORDERS = [
    ['frames', 'info', 'asArray', 'asMetaArray', 'frameTimes', 'info', 'daqResult'],
    ['frameTimes', 'asMetaArray', 'info', 'asArray', 'frames', 'daqResult'],
]


@pytest.mark.parametrize('order', [0, 1])
@pytest.mark.parametrize('mode', ['precise', 'triggerProtocol', 'normal', 'noDaq'])
@pytest.mark.parametrize('usePartialCaches', [False, True])
def test_final_matches_legacy(mode, order, usePartialCaches):
    startsHigh = mode == 'triggerProtocol'
    pulses = [(0, 30)] + PULSES[1:] if startsHigh else PULSES
    camCmd = {'precise': PRECISE, 'triggerProtocol': TRIGGER_PROTOCOL}.get(mode, NORMAL)
    daq = None if mode == 'noDaq' else SyntheticDaq(pulseTrace(pulses))
    future = FakeFuture()
    task = makeTask(camCmd, daq, future)
    frames = makeFrames(len(pulses) + 2)

    for i, n in enumerate(range(0, NPTS, 230)):
        future.arrive(frames[2 * i:2 * i + 2])
        if daq is not None:
            daq.settle(n)
        res = task.partialResult()
        if usePartialCaches:  # fill every lazy cache on the growing partial
            settled = res.settlement()['frames']
            assert len(res.frames()) == settled
            times, precise = res.frameTimes()
            arr = res.asArray()
            marr = res.asMetaArray()
            if settled == 0:
                assert times is None and arr is None and marr is None and res.info() == {}
            else:
                assert arr.shape[0] == settled and marr.shape[0] == settled and len(times) == settled
                assert res.info()['validFrames'] == settled

    final = task.getResult()
    assert final is res and isinstance(final, CameraTaskResult)
    assert task.partialResult() is final and task.getResult() is final
    legacy = legacyGetResult(future.wait(), None if daq is None else daq.result, task)
    _checkSameAsLegacy(final, legacy, ORDERS[order])
    assert final.settlement() == {'frames': len(frames)} and final.isComplete()


def test_partial_frame_times_are_final_times():
    trace = pulseTrace(PULSES)
    daq = SyntheticDaq(trace)
    frames = makeFrames(len(PULSES))
    future = FakeFuture(frames)
    task = makeTask(PRECISE, daq, future)
    partialTimes = []
    for n in range(0, NPTS, 111):
        daq.settle(n)
        times, precise = task.partialResult().frameTimes()
        if times is not None:
            assert precise
            partialTimes.append(times.copy())
    final = task.getResult()
    finalTimes, precise = final.frameTimes()
    assert precise
    assert len(partialTimes) > 3
    for times in partialTimes:
        np.testing.assert_array_equal(times, finalTimes[:len(times)])


def test_reader_does_not_wait_for_a_busy_result():
    daq = SyntheticDaq(pulseTrace(PULSES))
    future = FakeFuture(makeFrames(2))
    task = makeTask(NORMAL, daq, future)
    res = task.partialResult()
    assert res.settlement()['frames'] == 2

    locked, release = threading.Event(), threading.Event()

    def holdLock():
        res.lock.lock()
        locked.set()
        release.wait(5)
        res.lock.unlock()

    t = threading.Thread(target=holdLock)
    t.start()
    try:
        locked.wait(5)
        future.arrive(makeFrames(5)[2:])
        start = time.perf_counter()
        assert task.partialResult() is res
        assert time.perf_counter() - start < 0.5
        assert res.settlement()['frames'] == 2  # update skipped, not lost
    finally:
        release.set()
        t.join(5)
    assert task.partialResult().settlement()['frames'] == 5


def test_final_frames_that_do_not_extend_the_partial_give_a_new_object(caplog):
    future = FakeFuture(makeFrames(3))
    task = makeTask(NORMAL, None, future)
    partial = task.partialResult()
    future._frames = makeFrames(4)
    final = task.getResult()
    assert final is not partial
    assert final.frames() == future._frames and final.isComplete()
    assert 'do not extend' in caplog.text


def test_get_result_without_partials_matches_legacy():
    daq = SyntheticDaq(pulseTrace(PULSES))
    future = FakeFuture(makeFrames(len(PULSES)))
    task = makeTask(PRECISE, daq, future)
    final = task.getResult()
    assert final.isComplete() and final.settlement() == {'frames': len(PULSES)}
    _checkSameAsLegacy(final, legacyGetResult(future.wait(), daq.result, task), ORDERS[0])


def test_directly_constructed_result_is_complete():
    frames = makeFrames(3)
    res = CameraTaskResult(None, frames, None)
    assert res.isComplete() and res.settlement() == {'frames': 3}
    assert res.info()['validFrames'] == 3
