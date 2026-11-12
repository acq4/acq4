"""PB, SE and AR: replay against recorded MIES cells and synthetic edge cases."""

import dataclasses
import math

import numpy as np
import pytest
from scipy.signal import lfilter

from acq4.util.allen_stimsets import core, qc
from acq4.util.allen_stimsets.core import MIN_SAMPLE_INTERVAL, AbortSet, EarlyStop, SweepData
from acq4.util.allen_stimsets.functions import _vc_common as vc
from acq4.util.allen_stimsets.functions.access_resistance_smoke import AccessResistanceSmoke
from acq4.util.allen_stimsets.functions.base import RunContext, functionFor
from acq4.util.allen_stimsets.functions.pipette_in_bath import PipetteInBath
from acq4.util.allen_stimsets.functions.seal_evaluation import SealEvaluation
from acq4.util.allen_stimsets.mies_nwb import UNKNOWN_MODE, MiesRecording, userKey
from acq4.util.allen_stimsets.notebook import ASYNC_QC_SKIPPED, Keys, Notebook
from acq4.util.allen_stimsets.replay import replayRecording
from acq4.util.allen_stimsets.stimset import buildSweep, loadProductionStimsets

from .test_mies_nwb import HUMAN_CELLS, MOUSE_CELLS, cellFile

FUNCTIONS = {c.miesName: c for c in (PipetteInBath, SealEvaluation, AccessResistanceSmoke)}

# ---- replay against the recorded cells

# (notebook key, MIES USER_ key suffix, factor from notebook units to labnotebook units)
_COMMON = [
    ('Chk0RMSShort', 'Chk0 S-RMS', 1e-3),  # pA vs MIES "Volt" (really nA)
    ('Chk0RMSLong', 'Chk0 L-RMS', 1e-3),
    ('Chk0RMSShortQC', 'Chk0 S-RMS QC', 1),
    ('Chk0RMSLongQC', 'Chk0 L-RMS QC', 1),
    ('Chk0QC', 'Chk0 BL QC', 1),
    ('RMSShortThreshold', 'S-RMS Threshold', 1e-3),
    ('RMSLongThreshold', 'L-RMS Threshold', 1e-3),
    (Keys.BASELINE_QC, 'BL QC', 1),
    (Keys.SAMPLING_QC, 'Sampling interval QC', 1),
]
_LEAK = [
    ('Chk0LeakCurrent', 'Chk0 Leak Current BL', 1e-12),  # pA vs A
    ('Chk0LeakCurrentQC', 'Chk0 Leak Current BL QC', 1),
]
COMPARED_VALUES = {
    'PSQ_PipetteInBath': _COMMON
    + _LEAK
    + [
        ('PipetteResistance', 'pipette resistance', 1e6),  # MOhm vs Ohm
        ('PipetteResistanceQC', 'pipette resistance QC', 1),
    ],
    'PSQ_SealEvaluation': _COMMON
    + [
        ('Chk1RMSShort', 'Chk1 S-RMS', 1e-3),
        ('Chk1RMSLong', 'Chk1 L-RMS', 1e-3),
        ('Chk1QC', 'Chk1 BL QC', 1),
        ('SealResistanceA', 'seal resistance A', 1e6),
        ('SealResistanceB', 'seal resistance B', 1e6),
        ('SealResistanceMax', 'seal resistance max', 1e6),
        ('SealResistanceQC', 'seal resistance QC', 1),
    ],
    'PSQ_AccessResistanceSmoke': _COMMON
    + _LEAK
    + [
        ('AccessResistance', 'access resistance', 1e6),
        ('SteadyStateResistance', 'steady state resistance', 1e6),
        ('AccessToSteadyStateRatio', 'access vs steady state ratio', 1),
        ('AccessResistanceQC', 'access resistance QC', 1),
        ('ResistanceRatioQC', 'access vs steady state ratio QC', 1),
    ],
}

# Sweeps whose MIES Sweep QC failed only on the async (bath temperature) alarm, which the port skips:
# the sweep and its single-sweep set pass here and fail in MIES. 1544222282 sweeps 1 and 2 read 32.97
# and 33.0 degC against the alarm window [33, 35] ("v <= min" raises the alarm).
ASYNC_ALARM_SWEEPS = {'1544222282': {1, 2}}


def _asyncFailedSweeps(rec, res):
    out = set()
    for c in res.sets:
        for s in c.sweeps:
            v = rec.setting(
                s.sweep, userKey(c.miesName, 'async QC'), c.mset.headstage, UNKNOWN_MODE
            )
            if v is not None and not v:
                out.add(s.sweep)
    return out


def _expectedMismatches(res, asyncSweeps):
    out = set()
    for c in res.sets:
        failed = [s for s in c.sweeps if s.sweep in asyncSweeps]
        for s in failed:
            out.add(f"{c.mset.stimset} (SCI {c.mset.sci}): sweep {s.sweep}: sweep QC 1 != MIES 0")
        if failed and len(c.sweeps) == 1:
            out.add(f"{c.mset.stimset} (SCI {c.mset.sci}): set QC 1 != MIES 0")
    return out


def _same(ours, mies) -> bool:
    if ours is None:
        return False
    if math.isnan(ours) or math.isnan(mies):
        return math.isnan(ours) and math.isnan(mies)
    return math.isclose(ours, mies, rel_tol=1e-6, abs_tol=1e-15)


@pytest.mark.parametrize('cell', MOUSE_CELLS + HUMAN_CELLS)
def test_replayMatchesMies(cell):
    with MiesRecording(cellFile(cell)) as rec:
        res = replayRecording(rec, FUNCTIONS, stimsets='nwb')
        assert res.sets, "no PB/SE/AR sets in the recording"
        asyncSweeps = _asyncFailedSweeps(rec, res)
        assert asyncSweeps == ASYNC_ALARM_SWEEPS.get(cell, set())
        assert set(res.mismatches()) == _expectedMismatches(res, asyncSweeps), res.report()

        compared = 0
        diffs = []
        for c in res.sets:
            for s in c.sweeps:
                values = res.notebook.sweep(s.sweep).values
                assert values[Keys.ASYNC_QC] == ASYNC_QC_SKIPPED
                for ours, mies, factor in COMPARED_VALUES[c.miesName]:
                    m = rec.setting(
                        s.sweep, userKey(c.miesName, mies), c.mset.headstage, UNKNOWN_MODE
                    )
                    o = values.get(ours)
                    o = None if o is None else float(o) * factor
                    if m is None:
                        continue
                    compared += 1
                    if not _same(o, m):
                        diffs.append(f"sweep {s.sweep} {mies}: ours {o}, MIES {m}")
        assert not diffs
        assert compared > 0


# ---- synthetic


TEST_PULSE = core.TestPulseSettings(10.0, 0.45, 10.0, -50.0)


@pytest.fixture(scope='module')
def prod():
    return loadProductionStimsets()


def _context(stimsets):
    return RunContext(
        autobiasTarget=lambda: None,
        holding=lambda: 0.0,
        commandLimit=1000.0,
        stimsets=stimsets.__getitem__,
    )


def resistor(r, offset=0.0, noise=0.0, seed=0):
    """Return a response: current (pA) through *r* MOhm plus *offset* pA and Gaussian *noise* pA."""
    rng = np.random.default_rng(seed)

    def response(i, command, dt, epochs):
        return (
            command / r * 1000 + offset + rng.normal(0, noise, len(command))
            if noise
            else (command / r * 1000 + offset)
        )

    return response


def cell(ra, rm, cm):
    """Return a response of a cell (*ra*, *rm* MOhm, *cm* nF) in whole-cell VC, pA."""

    def response(i, command, dt, epochs):
        tau = ra * rm / (ra + rm) * cm
        a = math.exp(-dt / tau)
        vm = lfilter([0, (1 - a) * rm / (ra + rm)], [1, -a], command)
        return (command - vm) / ra * 1000

    return response


def piecewise(t, before, after):
    """Return *before* for sweep times < *t* ms and *after* from *t* on."""

    def response(i, command, dt, epochs):
        k = int(round(t / dt))
        return np.concatenate(
            [before(i, command, dt, epochs)[:k], after(i, command, dt, epochs)[k:]]
        )

    return response


@dataclasses.dataclass
class SweepRun:
    data: SweepData
    earlyStop: object
    decision: object
    values: dict


@dataclasses.dataclass
class SetRun:
    fn: object
    setConfig: object
    sweeps: list
    result: object
    notebook: Notebook


def runSet(cls, stimset, params, response, chunk=50.0, stopAfter=None):
    """Play *stimset* through *cls* like the runner: growing midSweep data, then postSweep, postSet.

    *response* gives the AD trace (pA) per sweep; *stopAfter* (ms) truncates acquisition (user stop).
    """
    nb = Notebook()
    fn = cls(stimset, params, nb, _context({stimset.name: stimset}))
    fn.setRecord = nb.newSet(stimset.name, cls.analysisType)
    cfg = fn.preSet()
    dt = cfg.sampleInterval
    sweeps = []
    for i in range(stimset.numSweeps):
        layout = buildSweep(stimset, i, 1.0, dt, 'VC', TEST_PULSE).epochs
        swCfg = fn.preSweep(i, layout)
        built = buildSweep(stimset, i, swCfg.dascale, dt, 'VC', TEST_PULSE)
        epochs = built.epochs.copy()
        epochs.add(*swCfg.userEpochs)
        full = response(i, built.command, dt, epochs)
        n = len(full) if stopAfter is None else int(round(stopAfter / dt))
        buf = np.full(len(full), np.nan)
        sweepNo = nb.nextSweepNumber()
        step = int(round(chunk / dt))
        pos, stop = 0, None
        while pos < n:
            new = min(pos + step, n)
            buf[pos:new] = full[pos:new]
            pos = new
            data = SweepData(sweepNo, 'VC', dt, buf, built.command, pos, epochs, swCfg.dascale)
            action = fn.midSweep(data)
            if isinstance(action, EarlyStop):
                stop = action
                break
        data = SweepData(
            sweepNo,
            'VC',
            dt,
            buf.copy(),
            built.command,
            pos,
            epochs,
            swCfg.dascale,
            pos < len(full),
        )
        rec = nb.addSweep(sweepNo, fn.setRecord.sci, swCfg.dascale)
        decision = fn.postSweep(data)
        sweeps.append(SweepRun(data, stop, decision, rec.values))
        if decision.action != 'continue':
            break
    return SetRun(fn, cfg, sweeps, fn.postSet(), nb)


def _replaceEpoch(stimset, i, **changes):
    eps = list(stimset.epochs)
    eps[i] = dataclasses.replace(eps[i], **changes)
    return dataclasses.replace(stimset, epochs=eps)


@pytest.fixture(scope='module')
def pbStimset(prod):
    return prod['EXTPINBATH180424_DA_0']


@pytest.fixture(scope='module')
def seStimset(prod):
    # the 60 s gap between the groups shortened to 100 ms
    return _replaceEpoch(prod['EXTPCllATT180424_DA_0'], 10, duration=100.0)


@pytest.fixture(scope='module')
def arStimset(prod):
    return prod['EXTPBREAKN180424_DA_0']


def test_registered():
    for name, cls in FUNCTIONS.items():
        assert functionFor(name) is cls
        assert cls.clampMode == 'VC'


# ---- PB


def test_pbPasses(pbStimset):
    run = runSet(PipetteInBath, pbStimset, dict(pbStimset.params), resistor(7.0, noise=1.0))
    assert run.setConfig.clampMode == 'VC'
    assert run.setConfig.sampleInterval == MIN_SAMPLE_INTERVAL
    assert run.setConfig.amplifier.changes() == {'holdingEnabled': False, 'pipetteOffset': 'auto'}
    assert run.setConfig.runAmplifier.changes() == {}
    (s,) = run.sweeps
    assert s.earlyStop is None
    assert s.values['PipetteResistance'] == pytest.approx(7.0, rel=1e-2)
    assert s.values['PipetteResistanceQC'] and s.values[Keys.BASELINE_QC]
    assert s.values[Keys.ASYNC_QC] == ASYNC_QC_SKIPPED
    assert s.decision.sweepPassed and s.decision.action == 'endSetPassed'
    assert run.result.passed and run.result.nextStimset == 'EXTPCllATT180424_DA_0'
    assert run.result.nextIndexingEnd is None
    assert run.result.runAmplifier.changes() == {}
    assert run.notebook.set(0).values[Keys.SET_QC] is True
    assert run.notebook.set(0).values['PipetteResistance'] == s.values['PipetteResistance']


def test_pbResistanceOutOfRange(pbStimset):
    run = runSet(PipetteInBath, pbStimset, dict(pbStimset.params), resistor(15.0))
    (s,) = run.sweeps
    assert s.values[Keys.BASELINE_QC] and not s.values['PipetteResistanceQC']
    assert s.decision.action == 'abort' and not s.decision.sweepPassed
    assert not run.result.passed and run.result.nextStimset is None


def test_pbLeakFailStopsEarlyAndRequestsPipetteOffset(pbStimset):
    run = runSet(PipetteInBath, pbStimset, dict(pbStimset.params), resistor(7.0, offset=150.0))
    (s,) = run.sweeps
    assert isinstance(s.earlyStop, EarlyStop)
    assert s.data.acquiredDuration == pytest.approx(
        600.0
    )  # end of the 500 ms chunk after 100 ms TP
    assert s.values['Chk0LeakCurrent'] == pytest.approx(150.0)
    assert s.values['Chk0LeakCurrentQC'] == qc.QC_FAILED
    assert s.values['Chk0RMSShortQC'] == qc.QC_PASSED
    assert not s.values[Keys.BASELINE_QC] and s.values['AutoPipetteOffset']
    assert math.isnan(s.values['PipetteResistance'])
    assert not run.result.passed
    assert run.result.runAmplifier.changes() == {'pipetteOffset': 'auto'}


def test_pbRmsFailStopsEarly(pbStimset):
    run = runSet(PipetteInBath, pbStimset, dict(pbStimset.params), resistor(7.0, noise=30.0))
    (s,) = run.sweeps
    assert isinstance(s.earlyStop, EarlyStop)
    assert s.values['Chk0RMSShortQC'] == qc.QC_FAILED
    assert math.isnan(s.values['Chk0LeakCurrentQC'])  # not reached
    assert not s.values['AutoPipetteOffset']
    assert run.result.runAmplifier.changes() == {}


def test_pbNumberOfFailedSweeps(pbStimset):
    params = dict(pbStimset.params, NumberOfFailedSweeps=2)
    bad, good = resistor(15.0), resistor(7.0)
    run = runSet(PipetteInBath, pbStimset, params, lambda i, *a: (bad if i == 0 else good)(i, *a))
    assert [s.decision.action for s in run.sweeps] == ['continue', 'endSetPassed']
    assert run.result.passed

    run = runSet(PipetteInBath, pbStimset, params, bad)
    assert [s.decision.action for s in run.sweeps] == ['continue', 'abort']
    assert not run.result.passed


def test_pbSamplingMultiplier(pbStimset):
    params = dict(pbStimset.params, SamplingMultiplier=4, SamplingFrequency=50)
    run = runSet(PipetteInBath, pbStimset, params, resistor(7.0))
    assert run.setConfig.sampleInterval == pytest.approx(0.02)
    assert run.sweeps[0].values[Keys.SAMPLING_QC] and run.result.passed

    # 4x slower than the expected 200 kHz fails sampling QC and ends the set
    params = dict(pbStimset.params, SamplingMultiplier=4, NumberOfFailedSweeps=4)
    run = runSet(PipetteInBath, pbStimset, params, resistor(7.0))
    (s,) = run.sweeps
    assert not s.values[Keys.SAMPLING_QC] and s.decision.action == 'abort'


@pytest.mark.parametrize(
    'change',
    [
        {'MaxLeakCurrent': None},
        {'MinPipetteResistance': None},
        {'NumberOfFailedSweeps': 5},  # stimset has 4 sweeps
        {'NumberOfFailedSweeps': 0},
        {'SamplingMultiplier': 3},
        {'MaxPipetteResistance': 25},
        {'BaselineRMSShortThreshold': 21},
        {'AsyncQCChannels': [8]},
        {'NumberOfTestpulses': None},
    ],
)
def test_pbInvalidParams(pbStimset, change):
    params = dict(pbStimset.params)
    for k, v in change.items():
        if v is None:
            params.pop(k)
        else:
            params[k] = v
    with pytest.raises(AbortSet):
        runSet(PipetteInBath, pbStimset, params, resistor(7.0))


def test_pbStimsetChecks(pbStimset):
    params = dict(pbStimset.params)
    with pytest.raises(AbortSet):  # pre-pulse baseline must be in [500, 1000) ms
        runSet(PipetteInBath, _replaceEpoch(pbStimset, 0, duration=1000.0), params, resistor(7.0))
    with pytest.raises(AbortSet):  # TP pulse epoch with zero amplitude
        runSet(PipetteInBath, _replaceEpoch(pbStimset, 5, amplitude=0.0), params, resistor(7.0))
    with pytest.raises(AbortSet):  # 4 TPs need 14 epochs
        runSet(PipetteInBath, pbStimset, dict(params, NumberOfTestpulses=4), resistor(7.0))


def test_pbTwoTestpulses(pbStimset):
    # MIES uses stimset epochs 1+2i for TP i with 2 TPs; the port uses 1+3i
    run = runSet(
        PipetteInBath, pbStimset, dict(pbStimset.params, NumberOfTestpulses=2), resistor(7.0)
    )
    eps = {ep.name: ep for ep in run.sweeps[0].data.epochs}
    assert eps['U_TP1_P'].start == eps['E5'].start
    assert run.sweeps[0].values['PipetteResistance'] == pytest.approx(7.0, rel=1e-3)


def test_pbStoppedByUserBeforeChunk(pbStimset):
    run = runSet(PipetteInBath, pbStimset, dict(pbStimset.params), resistor(7.0), stopAfter=300.0)
    (s,) = run.sweeps
    assert s.earlyStop is None and not s.values[Keys.BASELINE_QC]
    assert 'Chk0QC' not in s.values


# ---- SE


def test_seBothOneGroupSuffices(seStimset):
    t11 = 100.0 + sum(ep.duration for ep in seStimset.epochs[:11])
    response = piecewise(t11, resistor(2000.0), resistor(500.0))
    run = runSet(SealEvaluation, seStimset, dict(seStimset.params), response)
    (s,) = run.sweeps
    names = [ep.name for ep in s.data.epochs if ep.name.startswith('U_')]
    assert {'U_BLS0', 'U_BLS1', 'U_TP5_B1'} <= set(names) and len(names) == 2 + 6 * 4
    assert s.data.epochs.get('U_BLS1').start == pytest.approx(t11)
    assert s.values['SealResistanceA'] == pytest.approx(2000.0, rel=1e-3)
    assert s.values['SealResistanceB'] == pytest.approx(500.0, rel=1e-3)
    assert s.values['SealResistanceMax'] == s.values['SealResistanceA']
    assert s.values['SealResistanceQC'] and s.values['Chk1QC'] and s.values[Keys.BASELINE_QC]
    assert s.values['TestPulseGroup'] == 'Both'
    assert run.result.passed and run.result.nextStimset == 'EXTPBREAKN180424_DA_0'


def test_seBothNeedsBothBaselines(seStimset):
    t11 = 100.0 + sum(ep.duration for ep in seStimset.epochs[:11])
    response = piecewise(t11, resistor(2000.0), resistor(2000.0, noise=30.0))
    run = runSet(SealEvaluation, seStimset, dict(seStimset.params), response)
    (s,) = run.sweeps
    assert s.earlyStop is None  # no mid-sweep QC
    assert s.values['Chk0QC'] and not s.values['Chk1QC'] and not s.values[Keys.BASELINE_QC]
    assert s.values['SealResistanceQC'] and not s.decision.sweepPassed
    assert not run.result.passed


@pytest.mark.parametrize('group, expected', [('First', 2000.0), ('Second', 500.0)])
def test_seSingleGroup(seStimset, group, expected):
    t11 = 100.0 + sum(ep.duration for ep in seStimset.epochs[:11])
    response = piecewise(t11, resistor(2000.0), resistor(500.0))
    params = dict(seStimset.params, TestPulseGroupSelector=group)
    run = runSet(SealEvaluation, seStimset, params, response)
    (s,) = run.sweeps
    epochs = s.data.epochs
    names = [ep.name for ep in epochs if ep.name.startswith('U_')]
    assert len(names) == 1 + 3 * 4 and 'U_BLS1' not in names and 'U_TP3' not in names
    groupStart = 100.0 if group == 'First' else t11
    assert epochs.get('U_BLS0').start == pytest.approx(groupStart)
    assert epochs.get('U_TP0').start == pytest.approx(groupStart + 500.0)
    own, other = ('A', 'B') if group == 'First' else ('B', 'A')
    assert s.values[f'SealResistance{own}'] == pytest.approx(expected, rel=1e-3)
    assert math.isnan(s.values[f'SealResistance{other}'])
    assert s.values['SealResistanceMax'] == s.values[f'SealResistance{own}']
    assert 'Chk1QC' not in s.values and s.values[Keys.BASELINE_QC]
    assert s.values['SealResistanceQC'] == (expected >= 1000.0)
    assert run.result.passed == (expected >= 1000.0)


def test_seUnacquiredChunkFails(seStimset):
    run = runSet(
        SealEvaluation, seStimset, dict(seStimset.params), resistor(2000.0), stopAfter=800.0
    )
    (s,) = run.sweeps
    assert s.values['Chk0QC'] and 'Chk1QC' not in s.values
    assert not s.values[Keys.BASELINE_QC] and math.isnan(s.values['SealResistanceB'])
    assert not s.decision.sweepPassed


@pytest.mark.parametrize(
    'change',
    [
        {'TestPulseGroupSelector': 'Third'},
        {'SealThreshold': None},
        {'SealThreshold': 0},
        {'BaselineRMSLongThreshold': 101},
        {'BaselineChunkLength': 600.0},  # longer than the 500 ms baseline epochs
    ],
)
def test_seInvalid(seStimset, change):
    params = dict(seStimset.params)
    for k, v in change.items():
        if v is None:
            params.pop(k)
        else:
            params[k] = v
    with pytest.raises(AbortSet):
        runSet(SealEvaluation, seStimset, params, resistor(2000.0))


def test_seRmsThresholdUpTo100(seStimset):
    params = dict(seStimset.params, BaselineRMSLongThreshold=100, BaselineRMSShortThreshold=100)
    assert runSet(SealEvaluation, seStimset, params, resistor(2000.0)).result.passed


def test_seNeeds22Epochs(seStimset):
    short = dataclasses.replace(seStimset, epochs=seStimset.epochs[:21])
    with pytest.raises(AbortSet):
        runSet(SealEvaluation, short, dict(seStimset.params), resistor(2000.0))


# ---- AR


def test_arBreakInPasses(arStimset):
    run = runSet(AccessResistanceSmoke, arStimset, dict(arStimset.params), cell(10.0, 300.0, 0.05))
    (s,) = run.sweeps
    assert s.earlyStop is None
    assert 10.0 < s.values['AccessResistance'] < 14.0
    assert s.values['SteadyStateResistance'] == pytest.approx(310.0, rel=1e-2)
    assert s.values['AccessToSteadyStateRatio'] == pytest.approx(
        s.values['AccessResistance'] / s.values['SteadyStateResistance']
    )
    assert s.values['AccessResistanceQC'] and s.values['ResistanceRatioQC']
    assert {ep.name for ep in s.data.epochs if ep.name.startswith('U_BLS')} == {'U_BLS0'}
    assert run.setConfig.amplifier.changes() == run.setConfig.runAmplifier.changes() == {}
    assert run.result.passed and run.result.nextStimset == 'X0NRMP_DA_0'
    assert run.result.nextIndexingEnd == 'X7RampN3_DA_0'
    assert run.notebook.set(0).values['AccessResistance'] == s.values['AccessResistance']


def test_arHighAccessTriesAllSweeps(arStimset):
    run = runSet(AccessResistanceSmoke, arStimset, dict(arStimset.params), cell(30.0, 300.0, 0.05))
    assert [s.decision.action for s in run.sweeps] == ['continue', 'continue', 'abort']
    assert not run.sweeps[0].values['AccessResistanceQC']
    assert not run.result.passed and run.result.nextStimset is None


def test_arRatioFails(arStimset):
    run = runSet(AccessResistanceSmoke, arStimset, dict(arStimset.params), cell(15.0, 40.0, 0.05))
    s = run.sweeps[0]
    assert s.values['AccessResistanceQC'] and not s.values['ResistanceRatioQC']


def test_arLeakFailStopsEarly(arStimset):
    response = lambda *a: cell(10.0, 300.0, 0.05)(*a) + 250.0  # noqa: E731
    run = runSet(AccessResistanceSmoke, arStimset, dict(arStimset.params), response)
    s = run.sweeps[0]
    assert isinstance(s.earlyStop, EarlyStop)
    assert s.data.acquiredDuration == pytest.approx(600.0)
    assert s.values['Chk0LeakCurrentQC'] == qc.QC_FAILED and not s.values[Keys.BASELINE_QC]
    assert math.isnan(s.values['AccessResistance']) and not s.values['AccessResistanceQC']
    assert len(run.sweeps) == 3 and not run.result.passed


def test_arSmokeTestInfiniteLimits(prod):
    stimset = prod['EXTPSMOKET180424_DA_0']
    noise = resistor(math.inf, noise=2.0)  # open circuit: noise only
    run = runSet(AccessResistanceSmoke, stimset, dict(stimset.params), noise)
    (s,) = run.sweeps
    assert s.values['AccessResistanceQC'] and s.values['ResistanceRatioQC']
    assert run.result.passed and run.result.nextStimset == 'EXTPINBATH180424_DA_0'


def test_arNegativeResistanceFailsFiniteLimit(arStimset):
    # inverted response: negative Ra and Rss; MIES passes "Ra < 20 MOhm" and "ratio < 0.2"
    response = lambda *a: -cell(10.0, 300.0, 0.05)(*a)  # noqa: E731
    run = runSet(AccessResistanceSmoke, arStimset, dict(arStimset.params), response)
    s = run.sweeps[0]
    assert s.values['AccessResistance'] < 0 and s.values['SteadyStateResistance'] < 0
    assert not s.values['AccessResistanceQC'] and not s.decision.sweepPassed


def test_arRatioParam(arStimset):
    params = dict(arStimset.params, MaxAccessToSteadyStateResistanceRatio=150)
    assert runSet(AccessResistanceSmoke, arStimset, params, cell(10.0, 300.0, 0.05)).result.passed
    for bad in (float('nan'), -1):
        params = dict(arStimset.params, MaxAccessToSteadyStateResistanceRatio=bad)
        with pytest.raises(AbortSet):
            runSet(AccessResistanceSmoke, arStimset, params, cell(10.0, 300.0, 0.05))


@pytest.mark.parametrize(
    'change',
    [
        {'MaxAccessResistance': None},
        {'MaxAccessResistance': 0},
        {'MaxLeakCurrent': 1001},
        {'BaselineChunkLength': 0},
        {'AsyncQCChannels': None},
    ],
)
def test_arInvalidParams(arStimset, change):
    params = dict(arStimset.params)
    for k, v in change.items():
        if v is None:
            params.pop(k)
        else:
            params[k] = v
    with pytest.raises(AbortSet):
        runSet(AccessResistanceSmoke, arStimset, params, cell(10.0, 300.0, 0.05))


def test_belowLimit():
    assert vc.belowLimit(5.0, 20.0) and not vc.belowLimit(-5.0, 20.0)
    assert not vc.belowLimit(20.0, 20.0) and not vc.belowLimit(float('nan'), 20.0)
    assert vc.belowLimit(-5.0, math.inf) and not vc.belowLimit(float('nan'), math.inf)
