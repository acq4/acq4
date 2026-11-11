"""DaqChannelAccumulator and NiDAQ.Task.getData against a frozen copy of the original getData pipeline."""
import itertools
import math
import types
from collections import OrderedDict

import numpy as np
import pytest

from acq4.devices.NiDAQ.accumulator import DaqChannelAccumulator
from acq4.devices.NiDAQ.nidaq import NiDAQ, Task as NiDAQTask
from acq4.devices.NiDAQ.tests.legacy_getdata import LegacyNiDAQ, legacyGetData

RATE = 20000.0
START = 12.5
CHAN = '/Dev1/ai3'


# ---- fakes ----

class _FakeSuperTask:
    """getResult(channel) like SuperTask's, over a strided (nPts, nChans) raw buffer."""

    def __init__(self, typ, data):
        self.typ = typ
        self.numPts = len(data)
        self.raw = np.zeros((self.numPts, 4), dtype=data.dtype)
        self.raw[:, 3] = data
        self.channelInfo = {CHAN: {'task': ('Dev1', typ), 'index': 3}}

    def absChanName(self, chan):
        return chan

    def rawChannelData(self, chan):
        return self.raw[:, 3]

    def getResult(self, channel):
        return {
            'data': self.raw.T[self.channelInfo[channel]['index']],
            'info': OrderedDict([('startTime', START), ('numPts', self.numPts), ('rate', RATE), ('type', self.typ)]),
        }


class _RecordingLogger:
    def __init__(self):
        self.messages = []

    def exception(self, msg, *args, **kwargs):
        self.messages.append(msg)

    warning = info = error = exception


class _FakeParent:
    tasks = {}


def makeTask(cmd, typ, data):
    st = _FakeSuperTask(typ, data)
    dev = types.SimpleNamespace(n=types.SimpleNamespace(createSuperTask=lambda: st), logger=_RecordingLogger(),
                                config={})
    parent = _FakeParent()
    task = NiDAQTask(dev, cmd, parent)
    task._testParent = parent  # DeviceTask keeps only a weakref
    return task


# ---- parameter grid ----

FILTERS = {
    'absent': {},
    'None': {'filterMethod': 'None'},
    'besselBidir': {'filterMethod': 'Bessel', 'besselCutoff': 1000.0, 'besselOrder': 4, 'besselBidirectional': True},
    'besselCausal': {'filterMethod': 'Bessel', 'besselCutoff': 1000.0, 'besselOrder': 4,
                     'besselBidirectional': False},
    'butterBidir': {'filterMethod': 'Butterworth', 'butterworthPassband': 1000.0, 'butterworthStopband': 2000.0,
                    'butterworthPassDB': 2.0, 'butterworthStopDB': 20.0, 'butterworthBidirectional': True},
    'butterCausal': {'filterMethod': 'Butterworth', 'butterworthPassband': 1000.0, 'butterworthStopband': 2000.0,
                     'butterworthPassDB': 2.0, 'butterworthStopDB': 20.0, 'butterworthBidirectional': False},
}
DENOISE = {
    'noDenoise': {},
    'pointwise': {'denoiseMethod': 'Pointwise', 'denoiseWidth': 2, 'denoiseThreshold': 4.0},
}
DOWNSAMPLE = [1, 3, 10]
TYPES = ['ai', 'di']
NPTS = [50, 99, 100, 101, 1000, 10007]

GRID = list(itertools.product(FILTERS, DOWNSAMPLE, DENOISE, TYPES, NPTS))


def gridId(p):
    return '-'.join(str(x) for x in p)


def makeCmd(filt, ds, denoise, nPts):
    cmd = {'rate': RATE, 'numPts': nPts, **FILTERS[filt], **DENOISE[denoise]}
    if ds != 1:
        cmd['downsample'] = ds
    return cmd


def makeSignal(typ, n):
    """ai: DC offset plus slow sine, noise and spikes; di: uint32 port values from two toggling lines."""
    i = np.arange(n)
    if typ == 'ai':
        rng = np.random.default_rng(n)
        x = -0.81 + 0.5 * np.sin(2 * np.pi * i / 700.0) + 0.05 * rng.standard_normal(n)
        x[5::97] += 0.8
        return x
    return (((i // 13) % 2) * 4 + (i // 5) % 2).astype(np.uint32)


def assertSameResult(new, old):
    assert set(new) == {'data', 'info'}
    assert new['data'].dtype == old['data'].dtype
    assert new['data'].shape == old['data'].shape
    assert np.array_equal(new['data'], old['data'])
    assert list(new['info'].items()) == list(old['info'].items())
    assert type(new['info']) is type(old['info'])


def tolerance(final):
    final = np.asarray(final, dtype=np.float64)
    return 1e-5 * max(1.0, np.abs(final).max() if final.size else 0.0)


# ---- tests ----

@pytest.mark.filterwarnings("ignore::RuntimeWarning")  # the original denoise warns on empty input
@pytest.mark.parametrize("params", GRID, ids=gridId)
def test_getData_matches_original(params):
    filt, ds, denoise, typ, nPts = params
    cmd = makeCmd(filt, ds, denoise, nPts)
    data = makeSignal(typ, nPts)
    expected = legacyGetData(makeTask(cmd, typ, data), CHAN)

    task = makeTask(cmd, typ, data)
    result = task.getData(CHAN)
    assertSameResult(result, expected)
    acc = task.channelAccumulator(CHAN)
    assert acc.nSettled == acc.numOutput == len(expected['data'])

    again = task.getData(CHAN)  # repeat calls give the same result
    assertSameResult(again, expected)


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
@pytest.mark.parametrize("params", GRID, ids=gridId)
def test_partial_prefix_settles_toward_final(params):
    filt, ds, denoise, typ, nPts = params
    cmd = makeCmd(filt, ds, denoise, nPts)
    data = makeSignal(typ, nPts)
    final = legacyGetData(makeTask(cmd, typ, data), CHAN)['data']
    tol = tolerance(final)

    chunkSizes = [7, 4096] + ([1] if nPts <= 1000 else [])
    for chunk in chunkSizes:
        task = makeTask(cmd, typ, data)
        acc = DaqChannelAccumulator(CHAN, typ, cmd)
        assert acc.numOutput == len(final)
        raw = task.st.rawChannelData(CHAN)
        prev = 0
        for n in list(range(chunk, nPts, chunk)) + [nPts]:
            acc.update(raw, n)
            k = acc.nSettled
            assert k >= prev
            prev = k
            assert acc.output.shape == (acc.numOutput,)
            if k:
                err = np.abs(acc.output[:k].astype(np.float64) - final[:k].astype(np.float64)).max()
                assert err <= tol, (chunk, n, k, err)

        if denoise == 'pointwise':
            assert not acc.settleSpec.updates
            assert acc.nSettled == 0
        if acc.settleSpec.updates:
            assert acc.nSettled == acc.numOutput  # the last chunk settles everything
            assert acc.output.dtype == final.dtype
        else:
            assert acc.nSettled == 0

        result = acc.finalize(task.st.getResult(CHAN))
        assert np.array_equal(result['data'], final) and result['data'].dtype == final.dtype
        assert acc.nSettled == acc.numOutput == len(final)


@pytest.mark.parametrize("cutoff, rate, depth", [(10e3, 100e3, 35), (1e3, 20e3, 68), (100.0, 20e3, 670)])
def test_bidirectional_bessel_settle_depth(cutoff, rate, depth):
    cmd = {'rate': rate, 'numPts': 100000, 'filterMethod': 'Bessel', 'besselCutoff': cutoff, 'besselOrder': 4}
    acc = DaqChannelAccumulator(CHAN, 'ai', cmd)
    assert acc.settleDepth == depth
    assert acc.settleSpec.delay == pytest.approx(depth / rate)
    assert acc.settleSpec.reason.startswith("bidirectional Bessel")


def test_settle_spec_per_stage():
    base = {'rate': RATE, 'numPts': 10000}

    def spec(typ='ai', **cmd):
        return DaqChannelAccumulator(CHAN, typ, {**base, **cmd})

    assert spec().settleDepth == 0
    assert spec(**FILTERS['besselCausal']).settleDepth == 0
    assert spec(**FILTERS['besselCausal']).settleSpec.reason == "causal Bessel, 1 kHz cutoff"
    assert spec(**FILTERS['besselBidir']).settleSpec.reason == "bidirectional Bessel, 1 kHz cutoff"
    assert spec(downsample=10).settleDepth == 9  # a mean bin needs all of its inputs
    assert spec(**FILTERS['besselBidir'], downsample=10).settleDepth == 68 + 9
    assert spec('di', downsample=10).settleDepth == 0  # subsampling
    assert spec('ao', **DENOISE['pointwise']).settleDepth == 0  # outputs are known up front

    for s in [spec(**DENOISE['pointwise']), spec('di', **FILTERS['besselBidir']),
              spec(numPts=100, **FILTERS['besselCausal']),
              spec(filterMethod='Bessel', besselCutoff=20000.0, besselOrder=4)]:  # cutoff above Nyquist
        assert s.settleDepth == math.inf and not s.settleSpec.updates and s.settleSpec.reason
    assert spec(**DENOISE['pointwise']).settleSpec.reason == "denoise needs the whole record"


@pytest.mark.parametrize("cmd", [
    # tf-form filters whose edge-started reverse pass cannot match the final one to tolerance
    {'filterMethod': 'Butterworth', 'butterworthPassband': 100.0, 'butterworthStopband': 200.0,
     'butterworthPassDB': 3.0, 'butterworthStopDB': 40.0},
    {'filterMethod': 'Bessel', 'besselCutoff': 100.0, 'besselOrder': 8},
    {'filterMethod': 'Bessel', 'besselCutoff': 100.0, 'besselOrder': 12},  # tf form is unstable
], ids=['butterworth7', 'bessel8', 'bessel12'])
def test_ill_conditioned_filter_does_not_update(cmd):
    nPts = 40000
    cmd = {'rate': RATE, 'numPts': nPts, **cmd}
    acc = DaqChannelAccumulator(CHAN, 'ai', cmd)
    assert not acc.settleSpec.updates
    assert "ill-conditioned" in acc.settleSpec.reason
    task = makeTask(cmd, 'ai', makeSignal('ai', nPts))
    raw = task.st.rawChannelData(CHAN)
    for n in range(1000, nPts + 1, 1000):
        acc.update(raw, n)
    assert acc.nSettled == 0


def test_reverse_pass_work_is_linear():
    nPts, chunk = 200000, 1000
    cmd = {'rate': RATE, 'numPts': nPts, 'filterMethod': 'Bessel', 'besselCutoff': 100.0, 'besselOrder': 4}
    t = np.arange(nPts) / RATE
    data = -0.81 + 3.67 * np.sin(2 * np.pi * 7 * t) + 0.5 * np.random.default_rng(0).standard_normal(nPts)
    task = makeTask(cmd, 'ai', data)
    final = legacyGetData(makeTask(cmd, 'ai', data), CHAN)['data']
    acc = DaqChannelAccumulator(CHAN, 'ai', cmd)
    raw = task.st.rawChannelData(CHAN)
    maxErr = 0.0
    for n in range(chunk, nPts + 1, chunk):
        acc.update(raw, n)
        if n < nPts:
            assert acc.nSettled == n - acc.settleDepth
        maxErr = max(maxErr, np.abs(acc.output[:acc.nSettled] - final[:acc.nSettled]).max())
    assert acc.nSettled == nPts
    assert maxErr <= tolerance(final)
    assert acc._nReversed < 3 * nPts


def test_output_waveform_settles_up_front():
    nPts = 1001
    cmd = {'rate': RATE, 'numPts': nPts, 'downsample': 3, **FILTERS['besselBidir'], **DENOISE['pointwise']}
    wave = makeSignal('ai', nPts) * 3
    acc = DaqChannelAccumulator('/Dev1/ao0', 'ao', cmd)
    assert acc.settleSpec.delay == 0
    acc.setOutputWaveform(wave)
    assert acc.nSettled == acc.numOutput == nPts // 3

    st = _FakeSuperTask('ao', wave)
    st.channelInfo = {'/Dev1/ao0': st.channelInfo[CHAN]}
    fake = types.SimpleNamespace(st=st, cmd=cmd, dev=types.SimpleNamespace(logger=_RecordingLogger()))
    expected = legacyGetData(fake, '/Dev1/ao0')['data']
    assert np.array_equal(acc.output, expected)
    acc.update(st.rawChannelData('/Dev1/ao0'), nPts)  # no-op for outputs
    assert acc.nSettled == nPts // 3


def test_unknown_methods_match_original():
    nPts = 1000
    cmd = {'rate': RATE, 'numPts': nPts, 'filterMethod': 'gaussian', 'denoiseMethod': 'median'}
    data = makeSignal('ai', nPts)
    legacyTask = makeTask(cmd, 'ai', data)
    expected = legacyGetData(legacyTask, CHAN)
    task = makeTask(cmd, 'ai', data)
    acc = task.channelAccumulator(CHAN)
    acc.update(task.st.rawChannelData(CHAN), nPts)
    assert acc.nSettled == nPts and np.array_equal(acc.output, expected['data'])
    assertSameResult(task.getData(CHAN), expected)
    assert task.dev.logger.messages == legacyTask.dev.logger.messages
    assert len(task.dev.logger.messages) == 2


def test_lowpass_unchanged():
    data = makeSignal('ai', 5000)
    for kwargs in [dict(filter='bessel', cutoff=1000.0, order=4, samplerate=RATE),
                   dict(filter='bessel', cutoff=0.05, order=6, bidir=False),
                   dict(filter='butterworth', cutoff=1000.0, stopCutoff=2000.0, gpass=3.0, gstop=40.0,
                        samplerate=RATE)]:
        assert np.array_equal(NiDAQ.lowpass(data, **kwargs), LegacyNiDAQ.lowpass(data, **kwargs))
