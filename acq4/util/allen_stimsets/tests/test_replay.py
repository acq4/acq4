import numpy as np
import pytest

from acq4.util.allen_stimsets.core import (
    MIN_SAMPLE_INTERVAL,
    AbortSet,
    EarlyStop,
    Epoch,
    SetConfig,
    SetResult,
    SweepConfig,
    SweepDecision,
    ZeroCommand,
)
from acq4.util.allen_stimsets.functions.base import AnalysisFunction
from acq4.util.allen_stimsets.mies_nwb import MiesRecording
from acq4.util.allen_stimsets.notebook import Keys, Notebook
from acq4.util.allen_stimsets.replay import replayRecording, replaySet, unscaledLayout

from .test_mies_nwb import cellFile


@pytest.fixture(scope='module')
def rec():
    with MiesRecording(cellFile('1544221355')) as r:  # H26.51.023.11.11.06.01
        yield r


def setOf(rec, stimset, n=0):
    return [m for m in rec.sets() if m.stimset == stimset][n]


class DummyDA(AnalysisFunction):
    """Plays the DAScales parameter; optional early stop / zero command after *stopAt* ms of data."""

    miesName = 'PSQ_DAScale'
    analysisType = 'DA'
    clampMode = 'IC'
    stopAt = None
    zeroAt = None
    passSweeps = True
    endAfter = None  # end the set (passed) after this many sweeps

    def preSet(self):
        self.calls, self.layouts, self.posts = [], [], []
        return SetConfig('IC', MIN_SAMPLE_INTERVAL * self.param('SamplingMultiplier'))

    def preSweep(self, i, layout):
        self.layouts.append(layout)
        scales = self.param('DAScales')
        e0 = layout.get('E0')
        return SweepConfig(
            scales[min(i, len(scales) - 1)], userEpochs=[Epoch('U_X0', e0.start, e0.end)]
        )

    def midSweep(self, data):
        self.calls.append((data.numValid, data.data[: data.numValid].copy(), data.commandZeroedAt))
        assert np.isnan(data.data[data.numValid :]).all()
        t = data.acquiredDuration
        if self.stopAt is not None and t >= self.stopAt:
            return EarlyStop('done')
        if self.zeroAt is not None and t >= self.zeroAt:
            return ZeroCommand('zero')
        return None

    def postSweep(self, data):
        self.posts.append(data)
        self.notebook.sweep(data.sweep).values[Keys.SPIKE_COUNT] = 0
        n = len(self.posts)
        if self.endAfter is not None and n >= self.endAfter:
            return SweepDecision(self.passSweeps, 'endSetPassed')
        return SweepDecision(self.passSweeps, 'continue')

    def postSet(self):
        return SetResult(passed=True, values={'n': len(self.posts)})


def test_midSweepGetsGrowingPartialData(rec):
    mset = setOf(rec, 'X1PS_SubThresh_DA_0')
    cmp = replaySet(rec, mset, DummyDA, stimsets='labnotebook', chunk=100.0)
    fn = cmp.function
    first = rec.sweep(mset.sweeps[0])
    step = int(round(100.0 / first.sampleInterval))
    counts = [c[0] for c in fn.calls[: cmp.sweeps[0].midSweepCalls]]
    assert counts[:3] == [step, 2 * step, 3 * step]
    assert (
        counts[-1] == first.numValid
    )  # MIES stopped this sweep early: last call has every recorded sample
    np.testing.assert_array_equal(fn.calls[2][1], first.data[: 3 * step])
    assert len(fn.posts) == 5
    post = fn.posts[0]
    assert (
        post.numValid == first.numValid and post.stoppedEarly and len(post.data) == first.numPoints
    )
    assert post.epochs.has('U_X0') and post.epochs.has('TP_P') and not post.epochs.has('UA')
    assert post.dascale == -30.0
    # layout passed to preSweep is DAScale 1; recorded stimset epoch amplitudes carry DAScale
    pulse = [e for e in rec.epochs(mset.sweeps[0]).withPrefix('E') if e.amplitude != 0][0]
    assert fn.layouts[0].get(pulse.name).amplitude == pytest.approx(pulse.amplitude / -30.0)


def test_comparisonAgainstLabnotebook(rec):
    mset = setOf(rec, 'X1PS_SubThresh_DA_0')

    class StopsLikeMies(DummyDA):
        stopAt = 2500.0
        endAfter = 5

    cmp = replaySet(rec, mset, StopsLikeMies, stimsets='labnotebook')
    assert [s.dascale for s in cmp.sweeps] == [-30, -50, -70, -90, -110]
    assert all(s.earlyStopAt == pytest.approx(2500.0, abs=100) for s in cmp.sweeps)
    assert cmp.miesSetPassed is True and cmp.result.passed
    # U_X0 is not a MIES epoch; everything else matches
    assert all(m.endswith('user epoch U_X0 not in MIES') for m in cmp.mismatches())

    class NeverStops(DummyDA):
        passSweeps = False

    cmp = replaySet(rec, mset, NeverStops, stimsets='labnotebook')
    mm = '\n'.join(cmp.sweeps[0].mismatches())
    assert 'early stop no, MIES at 2559.8 ms' in mm
    assert 'sweep QC 0 != MIES 1' in mm
    assert 'action continue, MIES ended the set' in '\n'.join(cmp.sweeps[-1].mismatches())


def test_dascaleAndActionMismatches(rec):
    mset = setOf(rec, 'X1PS_SubThresh_DA_0')

    class WrongScale(DummyDA):
        endAfter = 2

        def preSweep(self, i, layout):
            cfg = super().preSweep(i, layout)
            cfg.dascale *= 2
            return cfg

    cmp = replaySet(rec, mset, WrongScale, stimsets='labnotebook')
    assert len(cmp.sweeps) == 2 and cmp.unreplayed == mset.sweeps[2:]
    mm = cmp.mismatches()
    assert any('DAScale -60 != MIES -30' in m for m in mm)
    assert any('action endSetPassed, MIES continued' in m for m in mm)
    report = replayRecording(
        rec,
        {'PSQ_DAScale': WrongScale},
        stimsets='labnotebook',
        include=lambda m: m.sci == mset.sci,
    ).report()
    assert 'X1PS_SubThresh_DA_0' in report and '!! DAScale -60 != MIES -30' in report
    assert 'not replayed (function ended the set)' in report


def test_zeroCommandRecorded(rec):
    mset = setOf(rec, 'X1PS_SubThresh_DA_0')

    class Zeroes(DummyDA):
        zeroAt = 1000.0

    cmp = replaySet(rec, mset, Zeroes, stimsets='labnotebook')
    s = cmp.sweeps[0]
    assert isinstance(s.zeroCommand, ZeroCommand) and s.zeroCommandAt == pytest.approx(1000.0)
    calls = cmp.function.calls[: s.midSweepCalls]
    assert calls[9][2] is None and calls[10][2] == pytest.approx(1000.0)
    assert cmp.function.posts[0].commandZeroedAt == pytest.approx(1000.0)


def test_abortInPreSet(rec):
    class Aborts(DummyDA):
        def preSet(self):
            raise AbortSet('wrong clamp mode')

        def postSet(self):
            raise AssertionError('postSet must not run after AbortSet')

    cmp = replaySet(rec, setOf(rec, 'X1PS_SubThresh_DA_0'), Aborts, stimsets='labnotebook')
    assert cmp.aborted == 'preSet: wrong clamp mode' and not cmp.sweeps
    assert cmp.mismatches()[0].startswith('aborted')


def test_replayRecordingFillsNotebookInOrder(rec):
    seen = {}

    class Reader(DummyDA):
        miesName = 'PSQ_SquarePulse'
        analysisType = 'SP'
        endAfter = 1

        def preSet(self):
            seen.setdefault(self.setRecord.sci, [s.sci for s in self.notebook.sets('DA')])
            return super().preSet()

        def preSweep(self, i, layout):
            return SweepConfig(1.0)

    nb = Notebook()
    res = replayRecording(
        rec,
        {'PSQ_DAScale': DummyDA, 'PSQ_SquarePulse': Reader},
        notebook=nb,
        stimsets='labnotebook',
    )
    order = [(c.mset.stimset, c.setRecord.sci) for c in res.sets]
    assert order[0] == ('X1PS_SubThresh_DA_0', 0)
    assert [st for st, _ in order[:3]] == [
        'X1PS_SubThresh_DA_0',
        'X2SP_Search_DA_0',
        'X4LP_Search_DA_0',
    ]
    assert seen[1] == [0]  # the first SP set saw the earlier DA set
    first = nb.set(0)
    assert first.values[Keys.SET_QC] is True and first.sweeps == [5, 6, 7, 8, 9]
    rec5 = nb.sweep(5)
    assert rec5.values == {Keys.SWEEP_QC: True, Keys.SPIKE_COUNT: 0} and rec5.dascale == -30.0
    skipped = {m.stimset: reason for m, reason in res.skipped}
    assert skipped['X0NRMP_DA_0'] == 'PSQ_TrueRestingMembranePotential not ported'
    assert skipped['EXTPEXPEND180424_DA_0'] == 'no analysis function'
    # sweep 95: MIES DAQ was stopped by the user, so its early stop is not a mismatch
    user = [s for c in res.sets for s in c.sweeps if s.sweep == 95][0]
    assert user.stoppedByUser and not any('early stop' in m for m in user.mismatches())


def test_runContextFromLabnotebook(rec):
    ctx = {}

    class Ctx(DummyDA):
        def preSweep(self, i, layout):
            ctx[i] = (
                self.context.autobiasTarget(),
                self.context.holding(),
                self.context.commandLimit,
            )
            return super().preSweep(i, layout)

    replaySet(rec, setOf(rec, 'X1PS_SubThresh_DA_0'), Ctx, stimsets='labnotebook')
    target, holding, limit = ctx[0]
    assert target == pytest.approx(-62.111, abs=1e-3) and holding == 0.0
    assert limit == pytest.approx(32767 / 3200 * 400)


def test_unscaledLayout():
    from acq4.util.allen_stimsets.core import EpochTable

    t = EpochTable([Epoch('TP_P', 0, 1, 10.0), Epoch('E1', 1, 2, 50.0), Epoch('E0', 0, 1)])
    out = unscaledLayout(t, 25.0)
    assert [e.amplitude for e in out][:2] == [10.0, 2.0] and np.isnan(out[2].amplitude)
