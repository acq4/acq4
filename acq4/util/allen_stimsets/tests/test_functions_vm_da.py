import math

import numpy as np
import pytest

from acq4.util.allen_stimsets import qc
from acq4.util.allen_stimsets.core import AbortSet, Epoch, EpochTable, SweepData
from acq4.util.allen_stimsets.functions import dascale as da
from acq4.util.allen_stimsets.functions import true_resting_vm as vm
from acq4.util.allen_stimsets.functions.base import RunContext, _registry
from acq4.util.allen_stimsets.functions.dascale import DAScale
from acq4.util.allen_stimsets.functions.true_resting_vm import TrueRestingMembranePotential
from acq4.util.allen_stimsets.mies_nwb import MiesRecording, userKey
from acq4.util.allen_stimsets.notebook import Keys, Notebook
from acq4.util.allen_stimsets.replay import replaySet
from acq4.util.allen_stimsets.stimset import EpochDef, StimsetDef

from .test_mies_nwb import HUMAN_CELLS, MOUSE_CELLS, cellFile

RB = 'PSQ_Rheobase'


# ---- replay support


def addRheobaseSet(notebook: Notebook, rec: MiesRecording, mset) -> None:
    """Record a MIES Rheobase SCI in *notebook* from its labnotebook and traces.

    Writes what DAScale reads: set QC and pulse duration (set), BL QC, spike detection and
    ``Keys.AP_CROSSINGS`` (sweeps). Stands in for the ported PSQ_Rheobase.
    """
    s = notebook.newSet(mset.stimset, 'RB')
    hs = mset.headstage
    for sw in mset.sweeps:
        ms = rec.sweep(sw, hs)
        notebook.addSweep(
            sw,
            s.sci,
            ms.dascale,
            {
                Keys.BASELINE_QC: bool(rec.setting(sw, userKey(RB, 'BL QC'), hs, None) or 0),
                Keys.SPIKE_DETECT: bool(
                    rec.setting(sw, userKey(RB, 'spike detected'), hs, None) or 0
                ),
                Keys.AP_CROSSINGS: qc.apCrossings(ms.sweepData()),
            },
        )
    setQC = None
    for sw in reversed(mset.sweeps):
        setQC = rec.setting(sw, userKey(RB, 'Set QC'), hs, None)
        if setQC is not None:
            break
    durations = [rec.setting(sw, userKey(RB, 'Pulse duration'), hs, None) for sw in mset.sweeps]
    durations = [d for d in durations if d is not None]
    s.values[Keys.SET_QC] = bool(setQC)
    if durations:
        s.values[Keys.PULSE_DURATION] = durations[-1]


def replayCell(rec: MiesRecording, daClass=DAScale):
    """Replay every VM and DA SCI of *rec* in order into one notebook; RB SCIs come from the
    labnotebook (addRheobaseSet)."""
    notebook = Notebook()
    out = []
    for mset in rec.sets():
        if mset.analysisFunction == RB:
            addRheobaseSet(notebook, rec, mset)
        elif mset.analysisFunction == DAScale.miesName:
            out.append(replaySet(rec, mset, daClass, notebook))
        elif mset.analysisFunction == TrueRestingMembranePotential.miesName:
            out.append(replaySet(rec, mset, TrueRestingMembranePotential, notebook))
    return out, notebook


class MiesPreSetDAScale(DAScale):
    """DAScale with MIES's AdaptiveSupra preSet: a negative-slope fill-in added while checking the
    RhSuAd data is discarded (its flag stays set)."""

    def _isFinished(self, rsaOnly, oor=False):
        saved = list(self._future)
        done = super()._isFinished(rsaOnly, oor)
        if rsaOnly:
            self._future = saved
        return done


# AdaptiveSupra SCIs whose RhSuAd data meet the negative-slope criterion at preSet: we measure the
# fill-in MIES drops (MiesPreSetDAScale), so the DAScales and the set end differ.
LOST_FILLIN_SETS = {('1539885953', 4750219), ('1544222282', 7122419), ('1544221355', 5162498)}
# f-I maximum slope differs (decisions do not): RhSuAd slopes are paired with their DAScale-sorted
# right point; MIES pairs them with the chronological one.
MAX_SLOPE_ALIGNMENT_CELLS = {'1539834022', '1544231474'}
DQ_STOP_REASON_FINISHED = 0x4


def _externallyStopped(rec, sweep) -> bool:
    reason = rec.sweep(sweep).daqStopReason
    return reason is not None and reason != DQ_STOP_REASON_FINISHED


def _expected(cell, rec, cmp, sc, msg) -> bool:
    """Return True for a replay mismatch that is an explained difference."""
    if (cell, cmp.mset.sci) in LOST_FILLIN_SETS:
        return True
    if sc is None:
        return False
    if 'MIES no' in msg and sc.stoppedByUser:
        # replay ignores MIES early stops on sweeps after which the DAQ button was pressed
        return True
    if msg.startswith('action continue, MIES ended') and _externallyStopped(rec, sc.sweep):
        return True  # e.g. stop reason 0x80: operator selected another stimset
    if cmp.miesName == TrueRestingMembranePotential.miesName:
        if msg.startswith('DAScale'):
            return True  # all-zero stimset: MIES leaves the panel DAScale, we request 1
        if msg.startswith('user epoch U_BLS'):
            return True  # within one sample, checked in test_vmValues
    return False


@pytest.fixture(scope='module', params=MOUSE_CELLS + HUMAN_CELLS)
def replayed(request):
    with MiesRecording(cellFile(request.param)) as rec:
        sets, nb = replayCell(rec)
        yield request.param, rec, sets, nb


def test_replayDecisions(replayed):
    """DAScale, sweep QC, set QC, early stop and set end against MIES, for every VM/DA SCI."""
    cell, rec, sets, nb = replayed
    assert sets
    unexpected = []
    for c in sets:
        if c.aborted:
            unexpected.append(f"{c.mset.stimset} SCI {c.mset.sci}: aborted {c.aborted}")
        for s in c.sweeps:
            for m in s.mismatches():
                if not _expected(cell, rec, c, s, m):
                    unexpected.append(f"{c.mset.stimset} sweep {s.sweep}: {m}")
        if (
            c.result is not None
            and c.miesSetPassed is not None
            and c.result.passed != c.miesSetPassed
            and not _expected(cell, rec, c, None, 'set QC')
        ):
            unexpected.append(f"{c.mset.stimset} SCI {c.mset.sci}: set QC {c.result.passed}")
    assert not unexpected, '\n'.join(unexpected)


@pytest.mark.parametrize('cell, sci', sorted(LOST_FILLIN_SETS))
def test_lostFillinIsTheOnlyAdaptiveDifference(cell, sci):
    with MiesRecording(cellFile(cell)) as rec:
        ours = next(c for c in replayCell(rec)[0] if c.mset.sci == sci)
        mies = next(c for c in replayCell(rec, MiesPreSetDAScale)[0] if c.mset.sci == sci)
        recorded = rec.setting(
            ours.mset.sweeps[0], userKey(DAScale.miesName, 'DAScale values left'), None, None
        )
    future = ours.setRecord.values[da.FUTURE_DASCALES]
    assert future[0].startswith('FillinPosNegSlopeRhSuAd:')
    assert future[1] + ';' == recorded
    assert ours.setRecord.values[da.NEG_SLOPE_FILLIN]
    assert mies.mismatches() == []


def _num(v):
    return math.nan if v is None else float(v)


def _same(a, b, rtol=1e-9):
    a, b = _num(a), _num(b)
    return (math.isnan(a) and math.isnan(b)) or abs(a - b) <= rtol * max(1.0, abs(b))


def test_daValues(replayed):
    """Per-sweep DA results against the recorded USER_ entries (SI there, MIES units here)."""
    cell, rec, sets, nb = replayed
    bad = []
    for c in sets:
        if c.miesName != DAScale.miesName or (cell, c.mset.sci) in LOST_FILLIN_SETS:
            continue
        mode, hs = c.mset.params['OperationMode'], c.mset.headstage

        def lbn(sw, name, key=None):
            return rec.setting(sw, key or userKey(DAScale.miesName, name), hs, None)

        for s in c.sweeps:
            v, sw = nb.sweep(s.sweep).values, s.sweep
            checks = []
            if mode == 'Sub' and v[Keys.SWEEP_QC]:
                checks += [
                    ('deltaV', v[da.DELTA_V], _num(lbn(sw, '', 'USER_Delta V')) * 1e3, 1e-9),
                    ('deltaI', v[da.DELTA_I], _num(lbn(sw, '', 'USER_Delta I')) * 1e12, 1e-9),
                    # stored as float32 by MIES
                    (
                        'R',
                        v[Keys.RESISTANCE_FROM_FIT],
                        _num(lbn(sw, '', 'USER_ResistanceFromFit')) * 1e-6,
                        1e-6,
                    ),
                ]
            if mode == 'Supra' and v[Keys.SWEEP_QC]:
                checks.append(('spike count', v[Keys.SPIKE_COUNT], lbn(sw, 'spike count'), 0))
                if math.isnan(v[da.FI_SLOPE]) and lbn(sw, 'f-I slope') == 0:
                    pass  # single point: MIES writes the fit's initial coefficient 0, we NaN
                else:
                    checks.append(('f-I slope', v[da.FI_SLOPE], lbn(sw, 'f-I slope'), 1e-9))
            if mode == 'AdaptiveSupra':
                checks += [
                    ('AP frequency', v.get(Keys.AP_FREQUENCY), lbn(sw, 'AP frequency'), 1e-9),
                    ('f-I slope', v[da.FI_SLOPE], lbn(sw, 'f-I slope'), 1e-9),
                    ('f-I offset', v[da.FI_OFFSET], lbn(sw, 'f-I offset'), 1e-9),
                    ('slope QC', v[da.FI_SLOPE_REACHED_QC], lbn(sw, 'f-I slope QC'), 0),
                    ('neg slope QC', v[da.FI_NEG_SLOPE_QC], lbn(sw, 'f-I neg. slope QC'), 0),
                    ('fillin QC', v[da.FILLIN_QC], lbn(sw, 'fillin QC'), 0),
                    (
                        'sweep except BL',
                        v[da.SWEEP_EXCEPT_BL_PP_QC],
                        lbn(sw, 'sweep except baseline QC'),
                        0,
                    ),
                ]
                if not math.isnan(v[da.FI_SLOPE]) and cell not in MAX_SLOPE_ALIGNMENT_CELLS:
                    checks.append(
                        ('max slope', v[da.MAX_SLOPE], lbn(sw, 'f-I maximum slope'), 1e-9)
                    )
                recorded = lbn(sw, 'DAScale values left')
                if recorded is not None and not s.stoppedByUser:
                    checks.append(('future', ';'.join(v[da.FUTURE_DASCALES]) + ';', recorded, None))
            for name, ours, mies, tol in checks:
                if not (ours == mies if tol is None else _same(ours, mies, tol)):
                    bad.append(f"{c.mset.stimset} sweep {sw} {name}: {ours} != MIES {mies}")
        if mode == 'AdaptiveSupra':
            sv, sw0 = c.setRecord.values, c.mset.sweeps[0]
            for key, name in (
                (da.MIN_DASCALE_NORM, 'Min. norm. DAScale step'),
                (da.MAX_DASCALE_NORM, 'Max. norm. DAScale step'),
            ):
                if not _same(sv[key], rec.settingIndep(sw0, userKey(c.miesName, name), None)):
                    bad.append(f"{c.mset.stimset} {name}: {sv[key]}")
            for key, name in (
                (da.RSA_DASCALE, 'DAScale from rheobase, supra, adaptive'),
                (da.RSA_FREQ, 'AP frequency from rheobase, supra, adaptive'),
            ):
                mies = sorted(float(x) for x in lbn(sw0, name).strip(';').split(';'))
                if sorted(sv[key]) != mies:  # ours in DAScale order, MIES chronological
                    bad.append(f"{c.mset.stimset} {name}: {sv[key]} != {mies}")
    assert not bad, '\n'.join(bad)


def test_vmValues(replayed):
    cell, rec, sets, nb = replayed
    for c in sets:
        if c.miesName != TrueRestingMembranePotential.miesName:
            continue
        hs = c.mset.headstage
        for s in c.sweeps:
            if s.stoppedByUser:
                continue
            v = nb.sweep(s.sweep).values

            def lbn(name):
                return rec.setting(s.sweep, userKey(c.miesName, name), hs, None)

            assert v[Keys.FULL_AVERAGE] == pytest.approx(_num(lbn('Full Average')) * 1e3, abs=1e-3)
            assert v[vm.SPIKE_QC] == bool(lbn('spike QC'))
            assert v[Keys.BASELINE_QC] == bool(lbn('BL QC'))
            mies = {ep.name: ep for ep in rec.epochs(s.sweep, hs)}
            dt = rec.sweep(s.sweep, hs).sampleInterval
            # MIES starts at the unrounded onset delay and clips U_BLS1 to the last sample
            for ep in s.sweepConfig.userEpochs:
                assert abs(ep.start - mies[ep.name].start) <= dt + 1e-9
                assert abs(ep.end - mies[ep.name].end) <= dt + 1e-9
        if c.result is not None and c.result.passed:
            assert c.result.runAmplifier.autobiasEnabled
            assert c.result.runAmplifier.autobiasTarget == c.result.values[Keys.FULL_AVERAGE]
            assert c.result.nextStimset == c.mset.params['NextStimSetName']


# ---- synthetic sweeps

DT = 0.16  # ms; SamplingMultiplier 32, SamplingFrequency 6.25 kHz
ONSET = 10.0  # ms, stands in for the inserted TP
TARGET_V = -70.0  # mV, autobias target
DA_EPOCHS = [(500.0, 0.0), (1000.0, 1.0), (2000.0, 0.0)]
PULSE = (ONSET + 500.0, ONSET + 1500.0)
SPIKE_SAMPLES = 5
COMMON = {'SamplingMultiplier': 32.0, 'SamplingFrequency': 6.25, 'AsyncQCChannels': [3.0]}


def makeStimset(name, epochs, numSweeps, fn, params):
    return StimsetDef(
        name=name,
        epochs=[EpochDef('square', d, a) for d, a in epochs],
        numSweeps=numSweeps,
        iti=0.0,
        analysisFunction=fn,
        params=params,
    )


def layoutOf(stimset, dascale=1.0) -> EpochTable:
    eps, t = [Epoch('TP', 0.0, ONSET)], ONSET
    for i, e in enumerate(stimset.epochs):
        eps.append(Epoch(f'E{i}', t, t + e.duration, e.amplitude * dascale))
        t += e.duration
    return EpochTable(eps)


def makeContext(target=TARGET_V, limit=1e6) -> RunContext:
    return RunContext(
        autobiasTarget=lambda: target,
        holding=lambda: 0.0,
        commandLimit=limit,
        stimsets=lambda name: None,
    )


def makeSweep(sweep, stimset, dascale, ad, userEpochs=()) -> SweepData:
    layout = layoutOf(stimset, dascale)
    cmd = np.zeros(len(ad))
    for ep in layout:
        if ep.name.startswith('E') and ep.amplitude:
            cmd[int(round(ep.start / DT)) : int(round(ep.end / DT))] = ep.amplitude
    layout.add(*userEpochs)
    return SweepData(sweep, 'IC', DT, np.asarray(ad, float), cmd, len(ad), layout, dascale)


def trace(stimset, v=TARGET_V, spikesAt=(), pulseDV=0.0):
    """Flat trace at *v* mV, +pulseDV during E1, 1 ms +20 mV spikes starting at *spikesAt* ms."""
    n = int(round((ONSET + sum(e.duration for e in stimset.epochs)) / DT))
    y = np.full(n, float(v))
    y[int(round(PULSE[0] / DT)) : int(round(PULSE[1] / DT))] += pulseDV
    for t in spikesAt:
        i = int(round(t / DT))
        y[i : i + SPIKE_SAMPLES] = 20.0
    return y


def spikeTimes(count, start=PULSE[0], stop=PULSE[1]):
    return [start + (k + 0.5) * (stop - start) / count for k in range(count)]


def runSet(cls, stimset, notebook, context, adFor, firstSweep=None):
    """Drive one set like the runner; *adFor(setSweepIndex, dascale)* returns the AD trace."""
    fn = cls(stimset, stimset.params, notebook, context)
    fn.setRecord = notebook.newSet(stimset.name, cls.analysisType)
    config = fn.preSet()
    sweep = notebook.nextSweepNumber() if firstSweep is None else firstSweep
    decisions, configs = [], []
    for k in range(stimset.numSweeps):
        cfg = fn.preSweep(k, layoutOf(stimset))
        data = makeSweep(sweep, stimset, cfg.dascale, adFor(k, cfg.dascale), cfg.userEpochs)
        fn.midSweep(data)
        rec = notebook.addSweep(sweep, fn.setRecord.sci, cfg.dascale)
        dec = fn.postSweep(data)
        rec.values.setdefault(Keys.SWEEP_QC, dec.sweepPassed)
        decisions.append(dec)
        configs.append(cfg)
        sweep += 1
        if dec.action != 'continue':
            break
    result = fn.postSet()
    fn.setRecord.values.setdefault(Keys.SET_QC, result.passed)
    return fn, config, configs, decisions, result


def test_registered():
    assert _registry['PSQ_DAScale'] is DAScale
    assert _registry['PSQ_TrueRestingMembranePotential'] is TrueRestingMembranePotential


# ---- VM


VM_PARAMS = dict(
    COMMON,
    AbsoluteVoltageDiff=math.inf,
    RelativeVoltageDiff=math.inf,
    FailedLevel=0.0,
    NumberOfFailedSweeps=2.0,
    SpikeFailureIgnoredTime=20.0,
    UserOffsetTargetVAutobias=-2.0,
    NextStimSetName='X1PS_SubThresh_DA_0',
)
VM_EPOCHS = [(500.0, 0.0), (1000.0, 0.0), (500.0, 0.0)]


def test_vmMeanExcludesOnsetAndSpikeWindows():
    dt = 0.2  # ms
    y = np.full(1000, -70.0)
    y[:51] = -10.0  # onset region [0, 10 ms] incl. sample 50
    y[500:520] = 30.0  # spike window around 102 ms
    assert vm.meanExcludingSpikes(y, dt, 10.0, [102.0], 20.0) == pytest.approx(-70.0)
    assert math.isnan(vm.meanExcludingSpikes(y[:40], dt, 10.0, [], 20.0))


def test_vmSpikeFailureThenPass():
    stimset = makeStimset(
        'X0NRMP_DA_0', VM_EPOCHS, 2, 'PSQ_TrueRestingMembranePotential', VM_PARAMS
    )

    def adFor(k, dascale):
        if k == 0:
            y = trace(stimset, spikesAt=[800.0, 900.0])
            y[: int(ONSET / DT)] = -10.0  # excluded from the autobias target
            return y
        return trace(stimset, v=-65.0)

    nb = Notebook()
    fn, config, configs, decisions, result = runSet(
        TrueRestingMembranePotential, stimset, nb, makeContext(), adFor
    )
    amp = config.runAmplifier
    assert (amp.holdingEnabled, amp.capNeutralizationEnabled, amp.bridgeBalanceEnabled) == (
        False,
        True,
        True,
    )
    assert amp.autobiasEnabled is False
    assert [ep.name for ep in configs[0].userEpochs] == ['U_BLS0', 'U_BLS1']
    assert configs[0].userEpochs[1].start == pytest.approx(ONSET + 1500)

    first, second = decisions
    assert not first.sweepPassed and first.action == 'continue' and first.iti == 10.0
    v0 = nb.sweep(0).values
    assert not v0[vm.SPIKE_QC] and v0[Keys.SPIKE_POSITIONS] == pytest.approx([800.0, 900.0], abs=DT)
    assert v0[vm.SPIKE_FAIL_AUTOBIAS_TARGET] == pytest.approx(-72.0)
    assert second.sweepPassed and second.action == 'endSetPassed' and second.iti is None
    assert result.passed and result.nextStimset == 'X1PS_SubThresh_DA_0'
    assert result.values[Keys.FULL_AVERAGE] == pytest.approx(-65.0)
    assert (
        result.runAmplifier.autobiasEnabled
        and result.runAmplifier.autobiasTarget == pytest.approx(-65.0)
    )


def test_vmFailedSetKeepsSpikeFailureTarget():
    params = dict(VM_PARAMS, NumberOfFailedSweeps=1.0)
    stimset = makeStimset('X0NRMP_DA_0', VM_EPOCHS, 3, 'PSQ_TrueRestingMembranePotential', params)
    nb = Notebook()
    _, _, _, decisions, result = runSet(
        TrueRestingMembranePotential,
        stimset,
        nb,
        makeContext(),
        lambda k, d: trace(stimset, spikesAt=[700.0]),
    )
    assert [d.action for d in decisions] == ['abort']
    assert not result.passed and result.nextStimset is None
    assert result.runAmplifier.autobiasTarget == pytest.approx(-72.0)


def test_vmRejectsShortBaseline():
    stimset = makeStimset('X0', [(400.0, 0.0), (10.0, 0.0), (500.0, 0.0)], 1, 'x', VM_PARAMS)
    fn = TrueRestingMembranePotential(stimset, VM_PARAMS, Notebook(), makeContext())
    fn.setRecord = fn.notebook.newSet('X0', 'VM')
    fn.preSet()
    with pytest.raises(AbortSet):
        fn.preSweep(0, layoutOf(stimset))


# ---- DA Sub / Supra


def test_subResistanceAndOutOfRange():
    params = dict(COMMON, OperationMode='Sub', DAScales=[-30.0, -50.0, -70.0, -90.0])
    stimset = makeStimset('X1PS_SubThresh_DA_0', DA_EPOCHS, 6, 'PSQ_DAScale', params)
    nb = Notebook()
    # 0.1 mV/pA = 100 MOhm; the DA range ends at 60 pA so -70 pA is out of range
    fn, config, configs, decisions, result = runSet(
        DAScale, stimset, nb, makeContext(limit=60.0), lambda k, d: trace(stimset, pulseDV=0.1 * d)
    )
    assert config.runAmplifier.autobiasEnabled
    assert [c.dascale for c in configs] == [-30, -50]
    assert [d.action for d in decisions] == ['continue', 'abort']
    assert nb.sweep(1).values[Keys.DASCALE_OUT_OF_RANGE]
    assert nb.sweep(1).values[Keys.RESISTANCE_FROM_FIT] == pytest.approx(100.0)
    assert nb.sweep(0).values[da.DELTA_I] == pytest.approx(-30.0)
    assert not result.passed and result.values[Keys.RESISTANCE_FROM_FIT] == pytest.approx(100.0)


def test_subRepeatsFailedDAScale():
    params = dict(COMMON, OperationMode='Sub', DAScales=[-30.0, -50.0])
    stimset = makeStimset('X1PS_SubThresh_DA_0', DA_EPOCHS, 4, 'PSQ_DAScale', params)

    def adFor(k, dascale):
        return trace(stimset, v=TARGET_V + (5.0 if k == 0 else 0.0))  # target V fails once

    _, _, configs, decisions, result = runSet(DAScale, stimset, Notebook(), makeContext(), adFor)
    assert [c.dascale for c in configs] == [-30, -30, -50]
    assert [d.sweepPassed for d in decisions] == [False, True, True]
    assert result.passed


def addRheobase(nb, sweeps, setQC=True, pulse=1000.0):
    """*sweeps*: (DAScale pA, AP frequency Hz in PULSE, spike detected)."""
    s = nb.newSet('X5LP_Rheo_DA_0', 'RB')
    for x, f, spike in sweeps:
        nb.addSweep(
            nb.nextSweepNumber(),
            s.sci,
            x,
            {
                Keys.BASELINE_QC: True,
                Keys.SPIKE_DETECT: spike,
                Keys.AP_CROSSINGS: crossings(f),
            },
        )
    s.values.update({Keys.SET_QC: setQC, Keys.PULSE_DURATION: pulse})
    return s


def crossings(freq):
    pos = [t / DT for t in spikeTimes(int(round(freq)))] if freq else []
    return {'positions': pos, 'sampleInterval': DT, 'numValid': int(3510 / DT)}


def test_supraOffsetsFromRheobaseAndModifier():
    nb = Notebook()
    addRheobase(nb, [(100.0, 0, False), (110.0, 1, True)], pulse=200.0)  # too short
    addRheobase(nb, [(90.0, 0, False), (100.0, 2, True), (95.0, 0, False)])
    params = dict(
        COMMON,
        OperationMode='Supra',
        DAScales=[30.0, 50.0, 70.0],
        MinimumSpikeCount=5.0,
        MaximumSpikeCount=10.0,
        DAScaleModifier=50.0,
    )
    stimset = makeStimset('X6PS_SupraThresh_DA_0', DA_EPOCHS, 5, 'PSQ_DAScale', params)
    counts = {0: 2, 1: 20, 2: 8}
    _, _, configs, decisions, result = runSet(
        DAScale,
        stimset,
        nb,
        makeContext(),
        lambda k, d: trace(stimset, spikesAt=spikeTimes(counts[k])),
    )
    # rheobase 100 pA; 2 spikes < 5 raise the next DAScale by 50 %, 20 > 10 lower it
    assert [c.dascale for c in configs] == [130.0, 100 + 50 * 1.5, 100 + 70 * 0.5]
    assert result.passed
    last = nb.sweep(nb.setOf(nb.nextSweepNumber() - 1).sweeps[-1]).values
    assert last[Keys.SPIKE_COUNT] == 8
    freqs, xs = [2, 20, 8], [130.0, 175.0, 135.0]
    assert last[da.FI_SLOPE] == pytest.approx(da.lineFit(xs, freqs)[1] * 100)


def test_supraNeedsRheobase():
    nb = Notebook()
    addRheobase(nb, [(100.0, 2, True)], setQC=False)
    params = dict(COMMON, OperationMode='Supra', DAScales=[30.0])
    stimset = makeStimset('X6', DA_EPOCHS, 2, 'PSQ_DAScale', params)
    fn = DAScale(stimset, params, nb, makeContext())
    fn.setRecord = nb.newSet('X6', 'DA')
    with pytest.raises(AbortSet):
        fn.preSet()


def test_daNeedsAutobiasTarget():
    params = dict(COMMON, OperationMode='Sub', DAScales=[-30.0])
    stimset = makeStimset('X1', DA_EPOCHS, 2, 'PSQ_DAScale', params)
    fn = DAScale(stimset, params, Notebook(), makeContext(target=None))
    fn.setRecord = fn.notebook.newSet('X1', 'DA')
    with pytest.raises(AbortSet):
        fn.preSet()


# ---- AdaptiveSupra helpers


def test_consecutivePassesAndQCOrder():
    assert da.consecutivePasses([1, 1, 1, 1], [1, 1, 0], 2, 2)
    assert not da.consecutivePasses([1, 0, 1, 1], [1, 1, 0], 2, 2)
    assert not da.consecutivePasses([1, 1, 1, 1], [1, 0, 1], 2, 2)
    # slope reached on a passing point, then failing points, then a negative slope
    assert da.hasRequiredQCOrder([1, 1, 0, 1], [1, 1, 0], [1, 1, 0, 1], [0, 0, 1])
    assert not da.hasRequiredQCOrder([1, 1, 1, 1], [1, 0, 0], [1, 1, 1, 1], [0, 0, 1])


def test_fillinAndMaxSlopeHelpers():
    assert da.fillinQC([100, 120, 110], 2) and not da.fillinQC([100, 120, 130], 2)
    assert not da.fillinQC([100], 0)
    # slope 2 belongs to a 2 Hz point, below the 4 Hz minimum
    assert da.maxSlope([50.0, 200.0, 30.0], [0.0, 10.0, 2.0, 12.0], 4.0) == 50.0
    assert math.isnan(da.maxSlope([1.0], [0.0, 1.0], 4.0))


def test_apFrequencyFromCrossingsMatchesQC():
    stimset = makeStimset('X', DA_EPOCHS, 1, 'PSQ_DAScale', {})
    data = makeSweep(0, stimset, 100.0, trace(stimset, spikesAt=spikeTimes(17) + [100.0, 2000.0]))
    cr = qc.apCrossings(data)
    assert qc.apFrequencyFromCrossings(cr, *PULSE) == qc.apFrequency(data, *PULSE) == 17.0


def test_lineFitAndSigDigits():
    off, slope, err = da.lineFit([1, 2, 3, math.nan], [2, 4, 6, 1])
    assert (off, slope, err) == pytest.approx((0.0, 2.0, 0.0))
    assert all(math.isnan(v) for v in da.lineFit([1, 1], [2, 3]))
    assert da.minSigDigits(123.456) == 123.0 and da.minSigDigits(0.1234) == 0.12


ADAPTIVE = dict(
    COMMON,
    OperationMode='AdaptiveSupra',
    DAScales=[0.0],
    SlopePercentage=80.0,
    AbsFrequencyMinDistance=10.0,
    MaxFrequencyChangePercent=40.0,
    DaScaleStepWidthMinMaxRatio=2.0,
    NumSweepsWithSaturation=2.0,
    DAScaleNegativeSlopePercent=2.0,
)


def adaptiveNotebook(rheobase, supra):
    """Notebook with a passing long RB set and a passing Supra set; points are (pA, Hz)."""
    nb = Notebook()
    addRheobase(nb, [(x, f, f > 0) for x, f in rheobase])
    s = nb.newSet('X6PS_SupraThresh_DA_0', 'DA')
    for x, f in supra:
        nb.addSweep(
            nb.nextSweepNumber(),
            s.sci,
            x,
            {Keys.SWEEP_QC: True, da.PULSE_EPOCH: list(PULSE), Keys.AP_CROSSINGS: crossings(f)},
        )
    s.values.update({Keys.SET_QC: True, Keys.OPERATION_MODE: 'Supra'})
    return nb


def runAdaptive(nb, curve, numSweeps=20, params=ADAPTIVE, cls=DAScale):
    """Run an AdaptiveSupra set whose cell fires ``round(curve(pA))`` spikes per 1 s pulse."""
    stimset = makeStimset('X6PS_SupraThresh_DA_1', DA_EPOCHS, numSweeps, 'PSQ_DAScale', params)

    def adFor(k, dascale):
        n = int(round(curve(dascale)))
        return trace(stimset, spikesAt=spikeTimes(n) if n else ())

    return runSet(cls, stimset, nb, makeContext(), adFor)


RHEO = [(80.0, 0), (100.0, 2), (90.0, 0)]
SUPRA = [(130.0, 30), (150.0, 40), (170.0, 50), (190.0, 60)]


def test_adaptivePreSetPoolStepsAndFillin():
    nb = adaptiveNotebook(RHEO, SUPRA)
    fn = DAScale(
        makeStimset('A', DA_EPOCHS, 5, 'PSQ_DAScale', ADAPTIVE), ADAPTIVE, nb, makeContext()
    )
    fn.setRecord = nb.newSet('A', 'DA')
    fn.preSet()
    sv = fn.setRecord.values
    assert sv[da.RSA_DASCALE] == [80, 90, 100, 130, 150, 170, 190]  # DAScale order
    assert sv[da.RSA_FREQ] == [0, 0, 2, 30, 40, 50, 60]
    assert sv[da.RSA_FILLIN_QC] == [False, True, False, False, False, False, False]  # 90 after 100
    _, m, _ = da.lineFit(sv[da.RSA_DASCALE], sv[da.RSA_FREQ])
    assert sv[da.MIN_DASCALE_NORM] == pytest.approx(0.4 / m)
    assert sv[da.MAX_DASCALE_NORM] == pytest.approx(0.8 / m)
    # 2 Hz -> 30 Hz jump between 100 and 130 pA: fill-in at 115 pA first, then extrapolation
    future = sv.get(da.FUTURE_DASCALES) or fn._future
    assert future[0] == 'FillinRhSuAd:115'
    assert future[1].startswith('RegRhSuAd:')
    y, a, slope = 60.0, 60.0 - 0.5 * 190, 50.0
    assert da.parseFuture(future[1])[1] == fn._plainStep(a, slope, 190.0, y)


def test_plainStepBranches():
    fn = DAScale.__new__(DAScale)
    fn._mfcp, fn._absMinDist, fn._minNorm, fn._maxNorm = 40.0, 10.0, 1.0, 2.0
    # y=60 Hz, 0.5 Hz/pA through (190, 60): 38 % more frequency is 22.8 Hz, i.e. +45.6 pA
    assert fn._plainStep(60 - 0.5 * 190, 50.0, 190.0, 60.0) == 236
    # steep extrapolation capped at maxNorm * y
    assert fn._plainStep(60 - 0.01 * 190, 1.0, 190.0, 60.0) == math.ceil(190 + 2.0 * 60)
    # zero slope
    assert fn._plainStep(60.0, 0.0, 190.0, 60.0) == math.ceil(190 + 120)
    # frequency gain below AbsFrequencyMinDistance: minimum step
    assert fn._plainStep(20 - 0.5 * 190, 50.0, 190.0, 20.0) == math.ceil(190 + 1.0 * 20)


def test_fillinRequiresAllConditions():
    fn = DAScale.__new__(DAScale)
    fn._mfcp, fn._absMinDist, fn._minNorm = 40.0, 10.0, 0.5
    P = da._Point
    pts = [P(0, 100.0, 20.0, rank=0), P(1, 140.0, 40.0, rank=1), P(2, 150.0, 45.0, rank=2)]
    # 20 -> 40 Hz: +100 %, 20 Hz apart, half step 20 pA > 0.5 * 20
    assert fn._fillin('Fillin', pts, []) == ['Fillin:120']
    assert fn._fillin('Fillin', pts, ['Reg:120']) == ['Reg:120']  # already proposed
    fn._minNorm = 1.0  # half step 20 pA no longer above 1.0 * 20
    assert fn._fillin('Fillin', pts, []) == []
    fn._minNorm, fn._mfcp = 0.5, 150.0  # +100 % below MaxFrequencyChangePercent
    assert fn._fillin('Fillin', pts, []) == []


def test_adaptiveSaturates():
    nb = adaptiveNotebook(RHEO, SUPRA)

    def curve(x):  # 0.5 Hz/pA at the Supra points, flattening above 190 pA
        return 60 + 120 * (1 - math.exp(-(x - 190) / 240)) if x > 190 else 60 - 0.5 * (190 - x)

    fn, _, configs, decisions, result = runAdaptive(nb, curve)
    assert result.passed and decisions[-1].action == 'endSetPassed'
    reached = [nb.sweep(sw).values[da.FI_SLOPE_REACHED_QC] for sw in fn.setRecord.sweeps]
    assert reached[-2:] == [True, True]
    assert not any(nb.sweep(sw).values[da.FI_NEG_SLOPE_QC] for sw in fn.setRecord.sweeps)
    assert configs[0].dascale == 115
    types = [da.parseFuture(e)[0] for e in fn._future]
    assert types[:2] == ['FillinRhSuAd', 'RegRhSuAd'] and 'Reg' in types


def test_adaptiveNegativeSlopeAddsFillinAndPasses():
    nb = adaptiveNotebook(RHEO, SUPRA)

    def curve(x):  # rises to 100 Hz at 270 pA, then drops
        return 60 + 0.5 * (x - 190) if x <= 270 else 100 - 0.5 * (x - 270)

    fn, _, configs, decisions, result = runAdaptive(nb, curve)
    assert result.passed
    types = [da.parseFuture(e)[0] for e in fn._future]
    assert 'FillinPosNegSlope' in types or 'RegPosNegSlope' in types
    assert any(nb.sweep(sw).values[da.FI_NEG_SLOPE_QC] for sw in fn.setRecord.sweeps)
    assert fn.setRecord.values[da.NEG_SLOPE_FILLIN]


def test_adaptiveRunsOutOfSweeps():
    nb = adaptiveNotebook(RHEO, SUPRA)
    fn, _, _, decisions, result = runAdaptive(nb, lambda x: 60 + 0.5 * (x - 130), numSweeps=3)
    assert [d.action for d in decisions] == ['continue'] * 3
    assert not result.passed


def test_adaptiveFailingSweepAfterNegativeSlope():
    fn = DAScale.__new__(DAScale)
    fn.pool = da._Pool()
    P = da._Point
    fn.pool.points = [
        P(0, 100.0, 10.0, rsa=True),
        P(1, 150.0, 40.0, slope=60.0, rsa=True),
        P(2, 200.0, 30.0, slope=-20.0, negSlope=True),
        P(3, 250.0, math.nan, slope=-20.0, negSlope=True, sweepPass=False, bl=False),
    ]
    # last sweep failed after a negative slope: retry 1 pA above it
    assert fn._calculateDAScale(onlyFailingNegSlope=True) == 'FailSweepNegSlope:251'
    fn.pool.points[3].negSlope = False
    assert fn._calculateDAScale(onlyFailingNegSlope=True) is None


def test_adaptiveKeepsNegSlopeFillinAtPreSet():
    # RhSuAd ends in two negative slopes: MIES drops the fill-in it adds at preSet, we measure it
    nb = adaptiveNotebook(RHEO, [(130.0, 30), (150.0, 40), (170.0, 35), (190.0, 30)])
    fn = DAScale(
        makeStimset('A', DA_EPOCHS, 5, 'PSQ_DAScale', ADAPTIVE), ADAPTIVE, nb, makeContext()
    )
    fn.setRecord = nb.newSet('A', 'DA')
    fn.preSet()
    assert fn._future[0] == 'FillinRhSuAd:115'
    assert 'FillinPosNegSlopeRhSuAd:160' in fn._future
    mies = MiesPreSetDAScale(fn.stimset, ADAPTIVE, nb, makeContext())
    mies.setRecord = nb.newSet('A', 'DA')
    mies.preSet()
    assert 'FillinPosNegSlopeRhSuAd:160' not in mies._future and mies._negSlopeFillin


def test_adaptiveOutOfRangeAborts():
    nb = adaptiveNotebook(RHEO, SUPRA)
    stimset = makeStimset('X6PS_SupraThresh_DA_1', DA_EPOCHS, 10, 'PSQ_DAScale', ADAPTIVE)
    _, _, configs, decisions, result = runSet(
        DAScale,
        stimset,
        nb,
        makeContext(limit=200.0),
        lambda k, d: trace(stimset, spikesAt=spikeTimes(int(60 + 0.5 * (d - 190)))),
    )
    assert decisions[-1].action == 'abort' and not result.passed
    assert all(c.dascale < 200 for c in configs)
