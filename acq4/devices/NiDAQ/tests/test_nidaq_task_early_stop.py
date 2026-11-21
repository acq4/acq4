"""NiDAQ.Task.stopEarly() and truncated DaqChannelAccumulator.finalize(), on the mock driver."""

import numpy as np
import pytest

from acq4.devices.NiDAQ.accumulator import DaqChannelAccumulator
from acq4.devices.NiDAQ.tests.legacy_getdata import legacyGetData
from acq4.devices.NiDAQ.tests.test_nidaq_task_partial import (
    AI,
    AI2,
    AO,
    DI,
    NPTS,
    RATE,
    assertSameResult,
    makeTasks,
    readerThreads,
    waitUntil,
)
from acq4.devices.NiDAQ.tests.test_nidaq_task_partial import daq  # noqa: F401  (pytest fixture)
from acq4.util import ptime


@pytest.mark.parametrize(
    "cmd", [{}, {'downsample': 3}, {'downsample': 10}], ids=['plain', 'ds3', 'ds10']
)
def test_stop_early_truncates_accumulated_channels(daq, cmd):
    parent, daqTask, rec, chunkCalls = makeTasks(daq, interval=0.01, **cmd)
    ds = cmd.get('downsample', 1)
    daqTask.configure()
    daqTask.start()
    waitUntil(lambda: len(rec.snapshots) >= 3)
    info = daqTask.stopEarly()
    daqTask.stop()
    assert readerThreads() == []
    n = info['numPtsAcquired']
    assert 0 < n < NPTS and n % ds == 0
    assert daqTask.st.startTime < info['stopTime'] <= ptime.time()

    for ch in (AI, AI2, DI, AO):
        result = daqTask.getData(ch)
        assert result['data'].shape == (n // ds,)
        assert result['info']['numPts'] == n // ds
        assert result['info']['stoppedEarly'] is True
        assert result['info']['numPtsAcquired'] == n and result['info']['numPtsRequested'] == NPTS
        assertSameResult(result, legacyGetData(daqTask, ch))
        assert rec.accs[ch].nSettled == n // ds
        for snap in rec.snapshots:
            part = snap[ch]
            k = min(len(part), n // ds)
            if ch != AO:
                assert len(part) <= n // ds
            assert np.array_equal(part[:k], result['data'][:k])


def test_stop_early_after_completion_returns_none(daq):
    parent, daqTask, rec, chunkCalls = makeTasks(daq, interval=0.01)
    daqTask.configure()
    daqTask.start()
    waitUntil(daqTask.isDone)
    assert daqTask.stopEarly() is None
    assert daqTask.getData(AI)['data'].shape == (NPTS,)
    assert 'stoppedEarly' not in daqTask.getData(AI)['info']


@pytest.mark.parametrize(
    "typ, ds, n, nOut",
    [('ai', 1, 37, 37), ('ai', 4, 37, 9), ('di', 4, 37, 10), ('ao', 4, 37, 9), ('do', 1, 0, 0)],
)
def test_accumulator_finalize_truncated(typ, ds, n, nOut):
    nPts = 100
    acc = DaqChannelAccumulator('/Dev1/x0', typ, {'rate': RATE, 'numPts': nPts, 'downsample': ds})
    dtype = np.uint32 if typ[0] == 'd' else np.float64
    raw = (np.arange(nPts) % 7).astype(dtype)
    if typ in ('ao', 'do'):
        acc.setOutputWaveform(raw)
    else:
        acc.reset(dtype)
        acc.update(raw, (n // 8) * 8)  # a partial update before the stop
    settled = acc.output[: acc.nSettled].copy()
    res = acc.finalize({'data': raw[:n], 'info': {'rate': RATE, 'numPts': n, 'stoppedEarly': True}})
    assert res['data'].shape == (nOut,) and res['info']['numPts'] == nOut
    assert acc.nSettled == nOut
    k = min(len(settled), nOut)
    assert np.array_equal(res['data'][:k], settled[:k])


def test_accumulator_finalize_refuses_short_data_without_early_stop():
    acc = DaqChannelAccumulator('/Dev1/ai0', 'ai', {'rate': RATE, 'numPts': 100})
    with pytest.raises(ValueError):
        acc.finalize({'data': np.zeros(50), 'info': {'rate': RATE, 'numPts': 50}})
    with pytest.raises(ValueError):
        acc.finalize(
            {'data': np.zeros(101), 'info': {'rate': RATE, 'numPts': 101, 'stoppedEarly': True}}
        )
