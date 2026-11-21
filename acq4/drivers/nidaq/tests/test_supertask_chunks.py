"""SuperTask chunked reads, driven through the mock NI-DAQ driver."""
import logging
import threading
import time

import numpy as np
import pytest

from acq4.drivers.nidaq.mock import MockNIDAQ

RATE = 100_000.0
AI_CHANS = ["/Dev1/ai0", "/Dev1/ai1"]
DI_CHANS = ["/Dev1/port0/line0", "/Dev1/port0/line1"]
AO_CHAN = "/Dev1/ao0"
AI_KEY = ("Dev1", "ai")
DI_KEY = ("Dev1", "di")
AO_KEY = ("Dev1", "ao")


def aiWave(chan, n):
    i = AI_CHANS.index(chan)
    return np.sin(np.arange(n) * 0.001 * (i + 1)) + i


def diWave(chan, n):
    period = (7, 13)[DI_CHANS.index(chan)]
    return (np.arange(n) // period) % 2


def aoWave(n):
    return np.linspace(-12.0, 12.0, n)


def readerThreads():
    return [t for t in threading.enumerate() if t.name.startswith("NI-DAQ chunk reader")]


def makeSuperTask(nPts, daq=None):
    daq = MockNIDAQ() if daq is None else daq
    st = daq.createSuperTask()
    for ch in AI_CHANS:
        st.addChannel(ch, "ai", mockFunc=lambda n, rate, ch=ch: aiWave(ch, n))
    for ch in DI_CHANS:
        st.addChannel(ch, "di", mockFunc=lambda n, rate, ch=ch: diWave(ch, n))
    st.addChannel(AO_CHAN, "ao")
    st.setWaveform(AO_CHAN, aoWave(nPts))
    st.configureClocks(rate=RATE, nPts=nPts)
    return st


def waitUntil(condition, timeout=5.0):
    deadline = time.time() + timeout
    while not condition():
        assert time.time() < deadline, "timed out waiting"
        time.sleep(1e-3)


def runToCompletion(st, chunkSize=None, handler=None):
    if handler is not None:
        st.setChunkHandler(chunkSize, handler)
    st.start()
    waitUntil(st.isDone)
    st.stop()
    return st.getResult()


def recordTaskStops(st, reader=None):
    """Wrap each NI task's stop(); return a list of (time, readerAlive) appended per call."""
    events = []
    for task in st.tasks.values():
        def stop(orig=task.stop):
            events.append((time.time(), reader is not None and reader.is_alive()))
            orig()
        task.stop = stop
    return events


@pytest.fixture
def superTaskLog():
    records = []
    handler = logging.Handler(logging.ERROR)
    handler.emit = records.append
    logger = logging.getLogger("acq4.drivers.nidaq.SuperTask")
    logger.addHandler(handler)
    yield records
    logger.removeHandler(handler)


def assertMatchesMockData(result, nPts):
    ai = result[AI_KEY]["data"]
    assert ai.shape == (2, nPts) and ai.dtype == np.float64
    np.testing.assert_array_equal(ai, np.array([aiWave(ch, nPts) for ch in AI_CHANS]))
    di = result[DI_KEY]["data"]
    assert di.shape == (2, nPts) and di.dtype == np.uint32
    np.testing.assert_array_equal(di, np.array([diWave(ch, nPts) for ch in DI_CHANS]))
    ao = result[AO_KEY]["data"]
    assert ao.shape == (1, nPts)
    np.testing.assert_array_equal(ao[0], np.clip(aoWave(nPts), -10, 10))


def test_no_chunk_handler_no_reader_and_legacy_result():
    nPts = 1003
    st = makeSuperTask(nPts)
    for key in (AI_KEY, DI_KEY):
        def readInto(*args):
            raise AssertionError("readInto used without a chunk handler")
        st.tasks[key].readInto = readInto
    assert st.samplesAcquired() == 0
    st.start()
    assert readerThreads() == []
    waitUntil(st.isDone)
    st.stop()
    result = st.getResult()

    assertMatchesMockData(result, nPts)
    assert set(result) == {AI_KEY, DI_KEY, AO_KEY}
    chan = st.getResult(AI_CHANS[1])
    np.testing.assert_array_equal(chan["data"], aiWave(AI_CHANS[1], nPts))
    assert list(chan["info"]) == ["startTime", "numPts", "rate", "type"]
    assert (chan["info"]["numPts"], chan["info"]["rate"], chan["info"]["type"]) == (nPts, RATE, "ai")
    assert st.samplesAcquired() == nPts


def test_chunked_run_matches_unchunked_run():
    nPts, chunk = 5003, 700
    plain = makeSuperTask(nPts)
    plainResult = runToCompletion(plain)

    st = makeSuperTask(nPts)
    calls = []
    prefixes = []

    def onChunk(nAcquired):
        calls.append((nAcquired, st.samplesAcquired()))
        prefixes.append((nAcquired, {ch: st.rawChannelData(ch)[:nAcquired].copy() for ch in AI_CHANS + DI_CHANS}))

    result = runToCompletion(st, chunk, onChunk)

    counts = [n for n, _ in calls]
    assert counts == sorted(set(counts)), "nAcquired must strictly increase"
    assert counts[-1] == nPts
    assert all(n % chunk == 0 or n == nPts for n in counts)
    assert all(n == acquired for n, acquired in calls)
    assert st.samplesAcquired() == nPts

    for n, data in prefixes:
        for ch in AI_CHANS:
            np.testing.assert_array_equal(data[ch], aiWave(ch, nPts)[:n])
        for ch in DI_CHANS:
            np.testing.assert_array_equal(data[ch], diWave(ch, nPts)[:n])

    assertMatchesMockData(result, nPts)
    assert set(result) == set(plainResult)
    for key in result:
        assert result[key]["data"].dtype == plainResult[key]["data"].dtype
        np.testing.assert_array_equal(result[key]["data"], plainResult[key]["data"])
    for ch in AI_CHANS + DI_CHANS + [AO_CHAN]:
        a, b = st.getResult(ch), plain.getResult(ch)
        assert a["data"].dtype == b["data"].dtype
        np.testing.assert_array_equal(a["data"], b["data"])
        assert {k: v for k, v in a["info"].items() if k != "startTime"} == {
            k: v for k, v in b["info"].items() if k != "startTime"
        }
    for ch in AI_CHANS + DI_CHANS:
        np.testing.assert_array_equal(st.rawChannelData(ch), plain.getResult(ch)["data"])
        assert np.shares_memory(st.rawChannelData(ch), st.getResult(ch)["data"])
    assert readerThreads() == []


def test_failing_handler_is_logged_once_and_reading_continues(superTaskLog):
    nPts, chunk = 5000, 500
    st = makeSuperTask(nPts)
    calls = []

    def onChunk(nAcquired):
        calls.append(nAcquired)
        raise RuntimeError("handler broke")

    st.setChunkHandler(chunk, onChunk)
    st.start()
    waitUntil(lambda: st.samplesAcquired() == nPts)
    waitUntil(st.isDone)
    st.stop()

    assert calls == [chunk]
    assert len(superTaskLog) == 1 and "handler" in superTaskLog[0].getMessage()
    assertMatchesMockData(st.getResult(), nPts)


def test_slow_handler_loses_no_data():
    nPts, chunk = 5000, 500
    st = makeSuperTask(nPts)
    calls = []

    def onChunk(nAcquired):
        calls.append(nAcquired)
        time.sleep(0.02)

    result = runToCompletion(st, chunk, onChunk)
    assert calls == sorted(set(calls)) and calls[-1] == nPts
    assertMatchesMockData(result, nPts)


def test_abort_mid_run_joins_reader_before_stopping_tasks():
    nPts = 60_000  # 0.6 s
    st = makeSuperTask(nPts)
    firstChunk = threading.Event()
    calls = []

    def onChunk(nAcquired):
        calls.append(nAcquired)
        firstChunk.set()

    st.setChunkHandler(1000, onChunk)
    st.start()
    (reader,) = readerThreads()
    stops = recordTaskStops(st, reader)
    assert firstChunk.wait(2.0)

    t0 = time.time()
    st.stop(abort=True)
    assert stops, "NI tasks were not stopped"
    assert stops[0][0] - t0 < 0.5, "reader join was not prompt"
    assert not any(alive for _, alive in stops), "an NI task was stopped while the reader ran"
    assert not reader.is_alive() and readerThreads() == []
    nCalls = len(calls)
    assert calls[-1] < nPts

    st.stop(abort=True)
    st.stop()
    time.sleep(0.02)
    assert len(calls) == nCalls
    assert len(stops) == 3 * len(st.tasks)


def test_reader_waits_on_unstarted_clock_and_stops_promptly():
    daq = MockNIDAQ()
    daq.startClock = lambda clock, duration: None  # clock never runs, as for a task awaiting its trigger
    st = makeSuperTask(5000, daq)
    attempts = []
    for key in (AI_KEY, DI_KEY):
        def readInto(out, offset, timeout, orig=st.tasks[key].readInto, key=key):
            attempts.append(key)
            return orig(out, offset, timeout)
        st.tasks[key].readInto = readInto
    calls = []
    st.setChunkHandler(500, calls.append)
    st.start()
    (reader,) = readerThreads()

    time.sleep(0.35)
    assert reader.is_alive()
    assert len(attempts) >= 2, "reader should keep retrying after read timeouts"
    assert calls == [] and st.samplesAcquired() == 0

    t0 = time.time()
    st.stop(abort=True)
    assert time.time() - t0 < 0.5
    assert not reader.is_alive()


def test_read_error_ends_reader_and_is_reported_by_final_read(superTaskLog):
    nPts = 5000
    st = makeSuperTask(nPts)
    task = st.tasks[DI_KEY]
    reads = []

    def readInto(out, offset, timeout, orig=task.readInto):
        reads.append(offset)
        if len(reads) > 1:
            raise RuntimeError("boom")
        orig(out, offset, timeout)

    task.readInto = readInto
    stops = recordTaskStops(st)
    st.setChunkHandler(500, lambda n: None)
    st.start()
    waitUntil(lambda: readerThreads() == [])
    assert any("chunk" in r.getMessage() for r in superTaskLog)
    nReads = len(reads)

    waitUntil(st.isDone)
    with pytest.raises(RuntimeError, match="boom"):
        st.stop()
    assert len(reads) == nReads + 1, "final read should retry only the unread remainder"
    assert len(stops) == len(st.tasks), "NI tasks must be stopped even when the final read fails"


def test_output_channel_data_and_channel_errors():
    nPts = 1000
    st = makeSuperTask(nPts)
    out = st.outputChannelData(AO_CHAN)
    np.testing.assert_array_equal(out, np.clip(aoWave(nPts), -10, 10))
    assert st.outputChannelData("ao0") is out
    with pytest.raises(ValueError):
        st.outputChannelData(AI_CHANS[0])
    with pytest.raises(ValueError):
        st.rawChannelData(AO_CHAN)
    assert st.rawChannelData(AI_CHANS[0]).shape == (nPts,)

    result = runToCompletion(st)
    np.testing.assert_array_equal(st.getResult(AO_CHAN)["data"], out)
    np.testing.assert_array_equal(result[AO_KEY]["data"][0], out)


def test_rerun_keeps_previous_result():
    nPts = 1000
    st = makeSuperTask(nPts)
    first = runToCompletion(st, 300, lambda n: None)[AI_KEY]["data"]
    firstCopy = first.copy()
    second = runToCompletion(st, 300, lambda n: None)[AI_KEY]["data"]
    assert not np.shares_memory(first, second)
    np.testing.assert_array_equal(first, firstCopy)
    np.testing.assert_array_equal(second, firstCopy)


def test_chunk_size_validation():
    st = makeSuperTask(100)
    with pytest.raises(ValueError):
        st.setChunkHandler(0, lambda n: None)
    st.setChunkHandler(0, None)  # disabling needs no chunk size
    st.start()
    assert readerThreads() == []
    waitUntil(st.isDone)
    st.stop()
