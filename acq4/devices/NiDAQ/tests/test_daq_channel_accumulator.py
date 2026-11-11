"""DaqChannelAccumulator and NiDAQ.Task.getData against a frozen copy of the original getData pipeline."""
import itertools
import types
from collections import OrderedDict

import numpy as np
import pytest

from acq4.devices.NiDAQ.accumulator import DaqChannelAccumulator, checkCommand
from acq4.devices.NiDAQ.nidaq import Task as NiDAQTask
from acq4.devices.NiDAQ.tests.legacy_getdata import legacyGetData

RATE = 20000.0
START = 12.5
CHAN = '/Dev1/ai3'


# ---- fakes ----

class _FakeSuperTask:
    """getResult(channel) like SuperTask's, over a (nPts, nChans) raw buffer (strided per channel if nChans > 1)."""

    def __init__(self, typ, data, nChans=4):
        self.typ = typ
        self.numPts = len(data)
        self.index = nChans - 1
        self.raw = np.zeros((self.numPts, nChans), dtype=data.dtype)
        self.raw[:, self.index] = data
        self.channelInfo = {CHAN: {'task': ('Dev1', typ), 'index': self.index}}

    def absChanName(self, chan):
        return chan

    def rawChannelData(self, chan):
        return self.raw[:, self.index]

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

    def __init__(self):
        self.partialResultErrors = []


def makeTask(cmd, typ, data, nChans=4):
    st = _FakeSuperTask(typ, data, nChans)
    dev = types.SimpleNamespace(n=types.SimpleNamespace(createSuperTask=lambda: st), logger=_RecordingLogger(),
                                config={})
    parent = _FakeParent()
    task = NiDAQTask(dev, cmd, parent)
    task._testParent = parent  # DeviceTask keeps only a weakref
    return task


# ---- parameters ----

NO_FILTER = {
    'absent': {},
    'None': {'filterMethod': 'None', 'denoiseMethod': 'None'},  # as old saved protocols store it
}
DOWNSAMPLE = [1, 2, 3, 10]
TYPES = ['ai', 'di', 'ao', 'do']
NPTS = [0, 1, 5, 50, 99, 100, 101, 1000, 10007]

GRID = list(itertools.product(NO_FILTER, DOWNSAMPLE, TYPES, NPTS))


def gridId(p):
    return '-'.join(str(x) for x in p)


def makeCmd(ds, nPts, extra=None):
    cmd = {'rate': RATE, 'numPts': nPts, **(extra or {})}
    if ds != 1:
        cmd['downsample'] = ds
    return cmd


def makeSignal(typ, n, seed=None):
    """ai/ao: random float64 with a DC offset; di/do: random uint32 port values."""
    rng = np.random.default_rng(n if seed is None else seed)
    if typ in ('ai', 'ao'):
        return rng.uniform(-3, 3) + rng.uniform(0.01, 10) * rng.standard_normal(n)
    return rng.integers(0, 2 ** 32, n, dtype=np.uint32) * rng.integers(0, 2, n, dtype=np.uint32)


def assertSameResult(new, old):
    assert set(new) == {'data', 'info'}
    assert new['data'].dtype == old['data'].dtype
    assert new['data'].shape == old['data'].shape
    assert np.array_equal(new['data'], old['data'])
    assert list(new['info'].items()) == list(old['info'].items())
    assert type(new['info']) is type(old['info'])


def schedules(nPts, ds, rng):
    """Chunk-end sample counts to feed update(): per sample, ds-unaligned, ds-aligned, large, irregular, none."""
    out = {'none': []}
    for name, chunk in [('one', 1), ('seven', 7), ('ds', ds), ('dsPlusOne', ds + 1), ('big', 4096)]:
        if chunk == 1 and nPts > 2000:
            continue
        out[name] = list(range(chunk, nPts, chunk)) + [nPts]
    ends = np.sort(rng.integers(0, nPts + 1, size=min(nPts, 40))) if nPts else []
    out['irregular'] = [int(n) for n in ends] + [nPts]
    out['partialOnly'] = [n for n in out['irregular'] if n < nPts]  # getData() does the rest
    return out


# ---- tests ----

@pytest.mark.parametrize("params", GRID, ids=gridId)
def test_getData_matches_original(params):
    filt, ds, typ, nPts = params
    cmd = makeCmd(ds, nPts, NO_FILTER[filt])
    data = makeSignal(typ, nPts)
    expected = legacyGetData(makeTask(cmd, typ, data), CHAN)

    task = makeTask(cmd, typ, data)
    result = task.getData(CHAN)
    assertSameResult(result, expected)
    acc = task.channelAccumulator(CHAN)
    assert acc.nSettled == acc.numOutput == len(expected['data'])

    again = task.getData(CHAN)  # repeat calls give the same result
    assertSameResult(again, expected)


@pytest.mark.parametrize("nChans", [1, 4], ids=['contiguous', 'strided'])
@pytest.mark.parametrize("seed", range(4))
@pytest.mark.parametrize("ds", [1, 2, 3, 8, 10, 37])
@pytest.mark.parametrize("typ", ['ai', 'di'])
def test_settled_values_are_final(typ, ds, seed, nChans):
    """For every chunk schedule: values never change once settled, and equal the original getData exactly."""
    rng = np.random.default_rng(seed)
    nPts = int(rng.integers(0, 3000)) if seed else 1234
    data = makeSignal(typ, nPts, seed=seed)
    cmd = makeCmd(ds, nPts)
    expected = legacyGetData(makeTask(cmd, typ, data, nChans), CHAN)

    for name, ends in schedules(nPts, ds, rng).items():
        task = makeTask(cmd, typ, data, nChans)
        acc = task.channelAccumulator(CHAN)
        raw = task.st.rawChannelData(CHAN)
        published = []  # (start, values) of each newly settled run, copied as published
        prefixes = []
        for n in ends:
            prev = acc.nSettled
            acc.update(raw, n)
            assert acc.nSettled >= prev
            published.append((prev, acc.output[prev:acc.nSettled].copy()))
            prefixes.append(acc.output[:acc.nSettled].copy())
        if ends and ends[-1] == nPts:
            assert acc.nSettled == acc.numOutput

        result = task.getData(CHAN)
        assertSameResult(result, expected)
        final = result['data']
        for start, values in published:
            assert np.array_equal(final[start:start + len(values)], values), name
        for prefix in prefixes:
            assert np.array_equal(final[:len(prefix)], prefix), name


@pytest.mark.parametrize("cmd", [
    {'filterMethod': 'Bessel', 'besselCutoff': 1000.0, 'besselOrder': 4},
    {'filterMethod': 'Butterworth', 'butterworthPassband': 1000.0, 'butterworthStopband': 2000.0},
    {'filterMethod': 'gaussian'},
    {'filterMethod': None},
    {'denoiseMethod': 'Pointwise', 'denoiseWidth': 2, 'denoiseThreshold': 4.0},
    {'filterMethod': 'None', 'denoiseMethod': 'median'},
], ids=['bessel', 'butterworth', 'unknownFilter', 'pyNone', 'pointwise', 'unknownDenoise'])
def test_filter_commands_raise(cmd):
    cmd = {'rate': RATE, 'numPts': 1000, **cmd}
    with pytest.raises(ValueError, match="filtering was removed"):
        checkCommand(cmd)
    with pytest.raises(ValueError, match="filtering was removed"):
        DaqChannelAccumulator(CHAN, 'ai', cmd)
    with pytest.raises(ValueError, match="filtering was removed"):
        makeTask(cmd, 'ai', makeSignal('ai', 1000))


def test_non_integer_downsampling_raises():
    cmd = {'rate': RATE, 'numPts': 1000, 'downsample': 2.5}
    with pytest.raises(ValueError, match="whole number"):
        DaqChannelAccumulator(CHAN, 'ai', cmd)
    acc = DaqChannelAccumulator(CHAN, 'ai', {**cmd, 'downsample': 4.0})
    assert acc.numOutput == 250 and acc.settleDepth == 3


def test_settle_specs():
    base = {'rate': RATE, 'numPts': 10000}

    def spec(typ='ai', **cmd):
        return DaqChannelAccumulator(CHAN, typ, {**base, **cmd}).settleSpec

    assert spec().delay == 0 and spec().reason == ''
    assert spec(downsample=10).delay == 9 / RATE  # a mean bin needs all of its inputs
    assert spec(downsample=10).reason == "10x mean downsampling"
    assert spec('di', downsample=10).delay == 0  # subsampling
    assert spec('ao', downsample=10).delay == 0 and spec('ao').reason == "output waveform"
    assert spec('do', downsample=10).delay == 0
    assert all(spec(t, downsample=d).updates for t in ('ai', 'di', 'ao', 'do') for d in (1, 3))


@pytest.mark.parametrize("typ, ds", [('ao', 1), ('ao', 3), ('do', 1), ('do', 4)])
def test_output_waveform_settles_up_front(typ, ds):
    nPts = 1001
    cmd = makeCmd(ds, nPts)
    wave = makeSignal(typ, nPts)
    acc = DaqChannelAccumulator('/Dev1/ao0', typ, cmd)
    acc.setOutputWaveform(wave)
    assert acc.nSettled == acc.numOutput
    settled = acc.output.copy()

    task = makeTask(cmd, typ, wave)
    expected = legacyGetData(makeTask(cmd, typ, wave), CHAN)['data']
    assert np.array_equal(settled, expected) and settled.dtype == expected.dtype
    acc.update(task.st.rawChannelData(CHAN), nPts)  # no-op for outputs
    assert np.array_equal(acc.output, settled)


def test_output_waveform_changed_after_settling_raises():
    nPts = 100
    cmd = makeCmd(1, nPts)
    wave = makeSignal('ao', nPts)
    task = makeTask(cmd, 'ao', wave)
    acc = task.channelAccumulator(CHAN)
    acc.setOutputWaveform(wave + 1)
    with pytest.raises(RuntimeError, match="changed after"):
        task.getData(CHAN)
    assert task.dev.logger.messages


def test_wrong_raw_length_raises():
    acc = DaqChannelAccumulator(CHAN, 'ai', makeCmd(1, 100))
    with pytest.raises(ValueError):
        acc.update(np.zeros(99), 50)
    assert acc.nSettled == 0
