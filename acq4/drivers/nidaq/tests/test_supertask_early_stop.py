"""SuperTask.stop(early=True), driven through the mock NI-DAQ driver."""

import threading
import time

import numpy as np
import pytest

from acq4.drivers.nidaq.mock import MockNIDAQ
from acq4.drivers.nidaq.tests.test_supertask_chunks import (
    AI_CHANS,
    AI_KEY,
    AO_CHAN,
    AO_KEY,
    DI_CHANS,
    DI_KEY,
    RATE,
    aiWave,
    aoWave,
    diWave,
    makeSuperTask,
    readerThreads,
    waitUntil,
)
from acq4.util import ptime

NPTS = 60_000  # 0.6 s


def assertTruncated(st, n):
    result = st.getResult()
    ai, di, ao = (result[k]["data"] for k in (AI_KEY, DI_KEY, AO_KEY))
    assert ai.shape == (2, n) and di.shape == (2, n) and ao.shape == (1, n)
    np.testing.assert_array_equal(ai, np.array([aiWave(ch, NPTS)[:n] for ch in AI_CHANS]))
    np.testing.assert_array_equal(di, np.array([diWave(ch, NPTS)[:n] for ch in DI_CHANS]))
    np.testing.assert_array_equal(ao[0], np.clip(aoWave(NPTS), -10, 10)[:n])
    for ch in AI_CHANS + DI_CHANS + [AO_CHAN]:
        chan = st.getResult(ch)
        assert chan["data"].shape == (n,)
        info = chan["info"]
        assert info["numPts"] == info["numPtsAcquired"] == n
        assert info["stoppedEarly"] is True and info["numPtsRequested"] == NPTS
        assert st.startTime < info["stopTime"] <= ptime.time()


@pytest.mark.parametrize("chunked", [True, False], ids=["chunked", "unchunked"])
def test_early_stop_mid_run_keeps_acquired_samples(chunked):
    st = makeSuperTask(NPTS)
    calls = []
    if chunked:
        st.setChunkHandler(1000, calls.append)
    st.start()
    time.sleep(0.2)
    t0 = time.time()
    st.stop(early=True)
    assert time.time() - t0 < 0.5
    assert st.isDone() and readerThreads() == []
    n = st.earlyStop["numPtsAcquired"]
    assert 0.15 * RATE < n < 0.45 * RATE
    if chunked:
        assert calls and calls[-1] <= n
    assertTruncated(st, n)
    st.stop()  # later stops only stop again
    assertTruncated(st, n)


def test_early_stop_after_completion_is_a_normal_stop():
    st = makeSuperTask(5000)
    st.setChunkHandler(1000, lambda n: None)
    st.start()
    waitUntil(lambda: st.samplesAcquired() == 5000)
    waitUntil(st.isDone)
    st.stop(early=True)
    assert st.earlyStop is None
    result = st.getResult()
    assert result[AI_KEY]["data"].shape == (2, 5000) and result[AO_KEY]["data"].shape == (1, 5000)
    assert "stoppedEarly" not in st.getResult(AI_CHANS[0])["info"]


def test_early_stop_while_awaiting_trigger_gives_empty_result():
    daq = MockNIDAQ()
    daq.startClock = lambda clock, duration: None  # clock never runs
    st = makeSuperTask(NPTS, daq)
    st.setChunkHandler(1000, lambda n: None)
    st.start()
    time.sleep(0.05)
    st.stop(early=True)
    assert st.earlyStop["numPtsAcquired"] == 0
    result = st.getResult()
    assert result[AI_KEY]["data"].shape == (2, 0) and result[AO_KEY]["data"].shape == (1, 0)


def test_unread_stop_mid_run_raises_on_get_result():
    st = makeSuperTask(NPTS)
    st.start()
    time.sleep(0.05)
    st.stop()
    assert st.isDone()
    with pytest.raises(RuntimeError, match="stopped before acquisition finished"):
        st.getResult()


def test_early_stop_from_another_thread_while_reader_runs():
    st = makeSuperTask(NPTS)
    started = threading.Event()
    st.setChunkHandler(500, lambda n: started.set())
    st.start()
    assert started.wait(2.0)
    errors = []

    def stopper():
        try:
            st.stop(early=True)
        except Exception as exc:
            errors.append(exc)

    t = threading.Thread(target=stopper)
    t.start()
    t.join(2.0)
    assert not t.is_alive() and errors == []
    assertTruncated(st, st.earlyStop["numPtsAcquired"])


def test_rerun_after_early_stop_is_full_length():
    st = makeSuperTask(5000)
    st.start()
    st.stop(early=True)
    first = st.getResult()[AI_KEY]["data"]
    assert st.earlyStop is not None and first.shape[1] < 5000
    st.start()
    assert st.earlyStop is None
    waitUntil(st.isDone)
    st.stop()
    assert st.getResult()[AI_KEY]["data"].shape == (2, 5000)
