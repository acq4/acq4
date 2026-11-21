"""Tests for PSQ_SquarePulse, PSQ_Rheobase, PSQ_Ramp and PSQ_Chirp: synthetic cases and replay."""

import dataclasses
import math
import re

import numpy as np
import pytest

from acq4.util.allen_stimsets.core import (
    AbortSet,
    EarlyStop,
    EpochTable,
    SweepData,
    ZeroCommand,
)
from acq4.util.allen_stimsets.functions.base import RunContext
from acq4.util.allen_stimsets.functions.chirp import (
    BOUNDS_DECREASE,
    BOUNDS_INCREASE,
    BOUNDS_PASS,
    BOUNDS_RERUN,
    INSIDE_BOUNDS,
    MIES_BOUNDS_ACTION,
    SPIKE_PASS,
    Chirp,
    boundsState,
    determineBoundsAction,
    setHasPassed,
)
from acq4.util.allen_stimsets.functions.ramp import Ramp
from acq4.util.allen_stimsets.functions.rheobase import (
    DASCALE_EXCEEDED,
    LIMITED_RESOLUTION,
    Rheobase,
)
from acq4.util.allen_stimsets.functions.square_pulse import SPIKE_WITH_DASCALE_ZERO, SquarePulse
from acq4.util.allen_stimsets.mies_nwb import UNKNOWN_MODE, MiesRecording, userKey
from acq4.util.allen_stimsets.notebook import Keys, Notebook
from acq4.util.allen_stimsets.replay import replayRecording
from acq4.util.allen_stimsets.stimset import EpochDef, StimsetDef, buildSweep

from .test_mies_nwb import HUMAN_CELLS, MOUSE_CELLS, cellFile

DT = 0.02  # ms, SamplingMultiplier 4
COMMAND_LIMIT = 4096.0  # pA
TARGET_V = -70.0  # mV


# --- synthetic helpers ----------------------------------------------------------------------------


def squareStimset(name, pre, pulse, post, numSweeps=10, func='PSQ_SquarePulse', params=None):
    params = {'SamplingMultiplier': 4.0, 'AsyncQCChannels': [3.0], **(params or {})}
    epochs = [EpochDef('square', pre), EpochDef('square', pulse, 1.0), EpochDef('square', post)]
    return StimsetDef(name, epochs, numSweeps, 0.0, func, params)


def context(target=TARGET_V):
    return RunContext(
        autobiasTarget=lambda: target,
        holding=lambda: 0.0,
        commandLimit=COMMAND_LIMIT,
        stimsets=lambda name: None,
    )


def makeFunction(cls, stimset, notebook=None, ctx=None):
    nb = Notebook() if notebook is None else notebook
    fn = cls(stimset, stimset.params, nb, ctx or context())
    fn.setRecord = nb.newSet(stimset.name, cls.analysisType)
    return fn


class SyntheticCell:
    """Drives an analysis function with sweeps built from the stimset and a response model.

    *response(dascale, t, command)* returns the membrane potential (mV) for sweep time *t* (ms).
    """

    def __init__(self, fn, response, chunk=50.0, testPulse=None):
        self.fn, self.response, self.chunk = fn, response, chunk
        self.sweep = fn.notebook.nextSweepNumber()
        self.testPulse = testPulse
        self.log = []  # (dascale, midSweep actions, decision)

    def runSweep(self, i):
        fn = self.fn
        cfgSet = self.setConfig
        built = buildSweep(
            fn.stimset, i, 1.0, cfgSet.sampleInterval, 'IC', None, cfgSet.userOnsetDelay
        )
        cfg = fn.preSweep(i, built.epochs)
        sweep = buildSweep(
            fn.stimset, i, cfg.dascale, cfgSet.sampleInterval, 'IC', None, cfgSet.userOnsetDelay
        )
        epochs = sweep.epochs.copy()
        epochs.add(*cfg.userEpochs)
        dt = sweep.sampleInterval
        t = np.arange(len(sweep.command)) * dt
        full = self.response(cfg.dascale, t, sweep.command)
        data = np.full(len(full), np.nan)
        command = sweep.command.copy()
        actions = []
        zeroedAt = None
        step = int(round(self.chunk / dt))
        n = 0
        stopped = False
        while n < len(full):
            n = min(n + step, len(full))
            data[:n] = full[:n]
            if zeroedAt is not None:
                data[:n] = self.response(cfg.dascale, t, command)[:n]
            sd = SweepData(
                self.sweep, 'IC', dt, data, command, n, epochs, cfg.dascale, False, zeroedAt
            )
            action = fn.midSweep(sd)
            if action is not None:
                actions.append((n * dt, action))
            if isinstance(action, ZeroCommand):
                zeroedAt = n * dt
                command[n:] = 0.0
            if isinstance(action, EarlyStop):
                stopped = True
                break
        sd = SweepData(
            self.sweep, 'IC', dt, data, command, n, epochs, cfg.dascale, stopped, zeroedAt
        )
        fn.notebook.addSweep(self.sweep, fn.setRecord.sci, cfg.dascale)
        decision = fn.postSweep(sd)
        fn.notebook.sweep(self.sweep).values.setdefault(Keys.SWEEP_QC, decision.sweepPassed)
        self.sweep += 1
        self.log.append((cfg.dascale, actions, decision))
        return decision

    def run(self):
        self.setConfig = self.fn.preSet()
        for i in range(self.fn.stimset.numSweeps):
            decision = self.runSweep(i)
            if decision.action != 'continue':
                break
        self.result = self.fn.postSet()
        self.fn.setRecord.values.setdefault(Keys.SET_QC, self.result.passed)
        return self

    @property
    def dascales(self):
        return [d for d, _, _ in self.log]

    @property
    def actions(self):
        return [dec.action for _, _, dec in self.log]


def spikingAbove(threshold, base=TARGET_V, spikeAt=None):
    """Response at *base* mV; one spike 1 ms after pulse onset when DAScale >= *threshold*."""

    def response(dascale, t, command):
        v = np.full(len(t), base)
        on = np.flatnonzero(command > 0)
        if len(on) and dascale >= threshold:
            t0 = t[on[0]] + 1.0 if spikeAt is None else spikeAt
            v[(t >= t0) & (t < t0 + 0.5)] = 20.0
        return v

    return response


# --- SquarePulse ----------------------------------------------------------------------------------


def test_squarePulse_ladder():
    st = squareStimset('X2SP_Search_DA_0', 50, 3, 100, numSweeps=30)
    cell = SyntheticCell(makeFunction(SquarePulse, st), spikingAbove(232)).run()
    assert cell.dascales == [100, 200, 300, 250, 200, 210, 220, 230, 240]
    assert cell.actions[-1] == 'endSetPassed' and cell.result.passed
    assert cell.setConfig.insertTestPulse is False and cell.setConfig.testPulseDuringIti is False
    nb = cell.fn.notebook
    last = nb.sweeps('SP')[-1]
    assert last.values[Keys.FINAL_SCALE] == 240 and last.values[Keys.SWEEP_QC]
    assert nb.lastSweepWith(Keys.FINAL_SCALE, 'SP') is last


def test_squarePulse_spikeAtZeroEndsAfterThree():
    st = squareStimset('X2SP_Search_DA_0', 50, 3, 100, numSweeps=30)

    def alwaysSpikes(dascale, t, command):
        v = np.full(len(t), TARGET_V)
        v[(t > 60) & (t < 60.5)] = 20.0
        return v

    cell = SyntheticCell(makeFunction(SquarePulse, st), alwaysSpikes).run()
    assert cell.dascales == [100, 50, 0, 0, 0]
    assert cell.actions == ['continue'] * 4 + ['abort']
    zero = [r.values.get(SPIKE_WITH_DASCALE_ZERO) for r in cell.fn.notebook.sweeps('SP')]
    assert zero == [None, None, True, True, True]
    assert not cell.result.passed


def test_squarePulse_outOfRangeAborts():
    st = squareStimset('X2SP_Search_DA_0', 50, 3, 100, numSweeps=30)
    ctx = context()
    ctx.commandLimit = 250.0
    cell = SyntheticCell(makeFunction(SquarePulse, st, ctx=ctx), spikingAbove(1000)).run()
    assert cell.dascales == [100, 200] and cell.actions == ['continue', 'abort']


def test_squarePulse_infiniteCommandLimit():
    # clamps without a known DA range (e.g. MockClamp) give an infinite limit: no DAC rounding
    st = squareStimset('X2SP_Search_DA_0', 50, 3, 100, numSweeps=30)
    ctx = context()
    ctx.commandLimit = math.inf
    cell = SyntheticCell(makeFunction(SquarePulse, st, ctx=ctx), spikingAbove(232)).run()
    assert cell.dascales == [100, 200, 300, 250, 200, 210, 220, 230, 240] and cell.result.passed


def test_squarePulse_noSweepLeftAborts():
    st = squareStimset('X2SP_Search_DA_0', 50, 3, 100, numSweeps=3)
    cell = SyntheticCell(makeFunction(SquarePulse, st), spikingAbove(1000)).run()
    assert cell.actions == ['continue', 'continue', 'abort'] and not cell.result.passed


# --- Rheobase -------------------------------------------------------------------------------------


def rheobaseSetup(final, threshold, numSweeps=10):
    nb = Notebook()
    sp = nb.newSet('X2SP_Search_DA_0', 'SP')
    nb.addSweep(0, sp.sci, final, {Keys.FINAL_SCALE: final})
    st = squareStimset('X3SP_Rheo_DA_0', 500, 3, 1100, numSweeps, 'PSQ_Rheobase')
    return SyntheticCell(makeFunction(Rheobase, st, nb), spikingAbove(threshold), chunk=100.0)


def test_rheobase_largeSteps():
    cell = rheobaseSetup(final=120, threshold=95).run()
    assert cell.dascales == [120, 110, 100, 90]
    assert cell.actions[-1] == 'endSetPassed' and cell.result.passed
    rec = cell.fn.setRecord.values
    assert rec[Keys.SET_QC] and rec[Keys.PULSE_DURATION] == pytest.approx(3.0)
    assert [r.values[Keys.SPIKE_DETECT] for r in cell.fn.notebook.sweeps('RB')] == [1, 1, 1, 0]
    # every sweep stops once the first post-pulse chunk passed
    assert all(isinstance(a[-1][1], EarlyStop) for _, a, _ in cell.log)


def test_rheobase_smallStepsAtOrBelow50():
    cell = rheobaseSetup(final=60, threshold=45).run()
    # 10 pA flip at 50 -> 40 switches to 2 pA steps; the 2 pA flip at 44 -> 46 passes
    assert cell.dascales == [60, 50, 40, 42, 44, 46]
    steps = [r.values['StepSize'] for r in cell.fn.notebook.sweeps('RB')]
    assert steps == [10, 10, 10, 2, 2, 2]
    assert cell.result.passed


def test_rheobase_exceedsRange():
    cell = rheobaseSetup(final=100, threshold=1000).run()
    assert cell.dascales == [100, 110, 120, 130, 140, 150]
    assert cell.actions[-1] == 'abort' and not cell.result.passed
    assert cell.fn.setRecord.values[DASCALE_EXCEEDED]


def test_rheobase_zeroDAScale():
    # spiking at 10 pA: 10 -> 0 is replaced by 2 pA steps from 2 pA; spiking at 2 pA ends the set
    cell = rheobaseSetup(final=10, threshold=-1).run()
    assert cell.dascales == [10, 2]
    assert cell.actions == ['continue', 'abort']
    assert cell.fn.setRecord.values[LIMITED_RESOLUTION] and not cell.result.passed


def test_rheobase_needsSquarePulseResult():
    st = squareStimset('X3SP_Rheo_DA_0', 500, 3, 1100, 10, 'PSQ_Rheobase')
    with pytest.raises(AbortSet):
        makeFunction(Rheobase, st).preSet()


def test_rheobase_baselineFailureRepeatsDAScale():
    cell = rheobaseSetup(final=120, threshold=95)
    base = cell.response

    def noisyFirst(dascale, t, command):
        v = base(dascale, t, command)
        if (
            cell.fn.notebook.nextSweepNumber() == 2
        ):  # second RB sweep: pre-pulse baseline off target
            v[t < 500] += 5.0
        return v

    cell.response = noisyFirst
    cell.run()
    assert cell.dascales == [120, 110, 110, 100, 90]
    stop = cell.log[1][1][-1][1]
    assert isinstance(stop, EarlyStop) and stop.extraIti > 10  # REPURP_TIME: 10 s + leftover
    assert Keys.SPIKE_DETECT not in cell.fn.notebook.sweeps('RB')[1].values


# --- Ramp -----------------------------------------------------------------------------------------


def rampStimset(numSweeps=3, params=None):
    params = {
        'SamplingMultiplier': 4.0,
        'AsyncQCChannels': [3.0],
        'NumberOfSpikes': 5.0,
        **(params or {}),
    }
    epochs = [EpochDef('square', 500), EpochDef('ramp', 4000, 400.0), EpochDef('square', 3000)]
    return StimsetDef('X7RAMPN0_DA_0', epochs, numSweeps, 0.0, 'PSQ_Ramp', params)


def rampResponse(spikeEvery=50.0, threshold=100.0):
    """Spikes every *spikeEvery* ms while the command exceeds *threshold* pA."""

    def response(dascale, t, command):
        v = np.full(len(t), TARGET_V)
        above = np.flatnonzero(command > threshold)
        if len(above):
            for t0 in np.arange(t[above[0]], t[above[-1]], spikeEvery):
                v[(t >= t0) & (t < t0 + 0.5)] = 20.0
        return v

    return response


def test_ramp_zeroCommandOnce():
    cell = SyntheticCell(makeFunction(Ramp, rampStimset()), rampResponse(), chunk=20.0).run()
    assert cell.dascales == [1.0, 1.0, 1.0] and cell.result.passed
    for _, actions, decision in cell.log:
        zeros = [(t, a) for t, a in actions if isinstance(a, ZeroCommand)]
        assert len(zeros) == 1
        # the ramp (from 500 ms) passes 100 pA at 1500 ms; the 5th spike is at 1700 ms
        assert 1700 < zeros[0][0] <= 1720.5
        # post-pulse chunk 1 is [zero + 500, zero + 1000] ms
        stopAt = actions[-1][0]
        assert isinstance(actions[-1][1], EarlyStop)
        assert stopAt == pytest.approx(zeros[0][0] + 1000, abs=20.5)
        assert decision.sweepPassed
    rec = cell.fn.notebook.sweeps('RA')[0].values
    assert rec[Keys.SPIKE_DETECT] and len(rec['SpikePositions']) == 5
    # the ramp's first DAC step (0.125 pA at 0.1 pA/ms) starts the pulse ~0.6 ms late
    assert rec[Keys.PULSE_DURATION] == pytest.approx(
        cell.log[0][1][0][0] - 500 - DT - 0.6, abs=0.05
    )


def test_ramp_noSpikes():
    cell = SyntheticCell(makeFunction(Ramp, rampStimset()), rampResponse(threshold=1e6)).run()
    assert all(not any(isinstance(a, ZeroCommand) for _, a in acts) for _, acts, _ in cell.log)
    assert cell.fn.notebook.sweeps('RA')[0].values[Keys.SPIKE_DETECT] is False
    assert cell.result.passed  # spiking does not count for sweep QC


def test_ramp_baselineFailAbortsWhenSetCannotPass():
    def offTarget(dascale, t, command):
        return np.full(len(t), TARGET_V + 5)

    cell = SyntheticCell(makeFunction(Ramp, rampStimset()), offTarget).run()
    assert cell.actions == ['abort'] and not cell.result.passed


# --- Chirp ----------------------------------------------------------------------------------------


def test_boundsStateAndAction():
    assert boundsState(-70, -75, -73, -74)[0] == 'BA'
    assert boundsState(-70, -75, -73, -72)[0] == 'AA'
    state, fac = boundsState(-70, -75, -73, -78)
    assert state == 'BB' and fac == pytest.approx(-4 / -8)
    r = determineBoundsAction(-78, -60, -70, 3, 5, 'Hyperpolarized')
    assert (r.action, r.state) == (BOUNDS_DECREASE, '__BB') and r.factor == pytest.approx(0.5)
    r = determineBoundsAction(-71, -60, -70, 3, 5, 'Hyperpolarized')
    assert (r.action, r.state) == (BOUNDS_INCREASE, '__AA') and r.factor == pytest.approx(4)
    assert determineBoundsAction(-74, -60, -70, 3, 5, 'Hyperpolarized').action == BOUNDS_PASS
    r = determineBoundsAction(-74, -66, -70, 3, 5, 'Symmetric')
    assert (r.action, r.state) == (BOUNDS_PASS, 'BABA')
    r = determineBoundsAction(-71, -69, -70, 3, 5, 'Symmetric')
    assert (r.action, r.state) == (BOUNDS_INCREASE, 'BBAA')
    r = determineBoundsAction(-71, -64, -70, 3, 5, 'Symmetric')
    assert (r.action, r.state) == (BOUNDS_RERUN, 'AAAA')
    r = determineBoundsAction(-72, -60, -70, 3, 5, 'Depolarized')
    assert (r.action, r.state) == (BOUNDS_DECREASE, 'AA__') and r.factor == pytest.approx(0.4)
    # a response at the baseline gives an infinite factor: rerun
    assert determineBoundsAction(-70, -60, -70, 3, 5, 'Hyperpolarized').action == BOUNDS_RERUN


def test_setHasPassed():
    assert setHasPassed([(True, 30), (True, 31), (True, 30.2)]) == (False, 2)
    assert setHasPassed([(True, 30), (False, 30), (True, 30), (True, 29.6)]) == (True, 3)
    assert setHasPassed([(False, 30)]) == (False, 0)


def chirpStimset(numSweeps=11, params=None):
    params = {
        'SamplingMultiplier': 16.0,
        'SamplingFrequency': 12.5,
        'AsyncQCChannels': [3.0],
        'InnerRelativeBound': 3.0,
        'OuterRelativeBound': 5.0,
        'BoundsEvaluationMode': 'Hyperpolarized',
        'NumberOfFailedSweeps': 9.0,
        'NumberOfChirpCycles': 3.0,
        'SpikeCheck': 1.0,
        'FailedLevel': -10.0,
        'DAScaleModifier': 0.9,
        'DAScaleOperator': '*',
        'UserOnsetDelay': 2000.0,
        'AmpBesselFilter': 6000.0,
        'AutobiasTargetVAtSetEnd': -65.0,
        'BaselineRMSShortThreshold': 20.0,
        'BaselineRMSLongThreshold': 20.0,
        **(params or {}),
    }
    sin = EpochDef(
        'sin',
        20000,
        1.0,
        params={'frequency': 0.5, 'endFrequency': 40.0, 'logChirp': 1, 'function': 'sin'},
    )
    epochs = [EpochDef('square', 1000), sin, EpochDef('square', 1000)]
    return StimsetDef('C2CHIRPA180503_DA_0', epochs, numSweeps, 0.0, 'PSQ_Chirp', params)


def chirpNotebook(resistance=100.0, vm=None):
    nb = Notebook()
    da = nb.newSet('X1PS_SubThresh_DA_0', 'DA')
    da.values.update(
        {Keys.SET_QC: True, Keys.OPERATION_MODE: 'Sub', Keys.RESISTANCE_FROM_FIT: resistance}
    )
    if vm is not None:
        rec = nb.newSet('X0NRMP_DA_0', 'VM')
        rec.values.update({Keys.SET_QC: True, Keys.FULL_AVERAGE: vm})
    return nb


def chirpResponse(mvPerPa, spikeSweeps=(), cell=None):
    """Passive response V = target + mvPerPa x command; spike 5 s into the chirp in spikeSweeps."""

    def response(dascale, t, command):
        v = TARGET_V + mvPerPa * command
        if cell is not None and cell[0].fn.notebook.nextSweepNumber() in spikeSweeps:
            on = np.flatnonzero(command != 0)[0]
            v[(t >= t[on] + 5000) & (t < t[on] + 5001)] = 10.0
        return v

    return response


def test_chirp_initialScaleAndAmplifier():
    fn = makeFunction(Chirp, chirpStimset(), chirpNotebook(resistance=88.262952, vm=-61.0))
    cfg = fn.preSet()
    assert fn.nextDascale == 45 and fn.setRecord.values['InitialScale'] == pytest.approx(
        45.319, abs=1e-3
    )
    assert cfg.userOnsetDelay == 2000 and cfg.amplifier.besselFilter == 6000
    assert cfg.runAmplifier.autobiasEnabled and cfg.runAmplifier.autobiasTarget is None
    fn.sweepResults = [(True, 45)] * 3
    result = fn.postSet()
    assert result.passed and result.runAmplifier.autobiasTarget == -61.0  # true RMP wins
    fn.params = dict(
        fn.params, UseTrueRestingMembranePotentialVoltage=0.0, AmpBesselFilterRestore=0.0
    )
    cfg = fn.preSet()
    assert cfg.amplifier.besselFilter is None and cfg.runAmplifier.besselFilter == 6000
    fn.sweepResults = [(True, 45)] * 3
    assert fn.postSet().runAmplifier.autobiasTarget == -65.0


def test_chirp_needsSubthresholdResistance():
    nb = chirpNotebook()
    nb.sets('DA')[0].values[Keys.OPERATION_MODE] = 'Supra'
    with pytest.raises(AbortSet):
        makeFunction(Chirp, chirpStimset(), nb).preSet()


def test_chirp_boundsAdjustAndPass():
    # 4 mV / 100 MOhm = 40 pA; trough of 40 pA x 0.2 mV/pA = 8 mV: decrease by 4/8 -> 20 pA
    fn = makeFunction(Chirp, chirpStimset(), chirpNotebook(resistance=100.0))
    cell = SyntheticCell(fn, chirpResponse(0.2), chunk=200.0).run()
    assert cell.dascales == [40, 20, 20, 20]
    assert cell.actions == ['continue'] * 3 + ['endSetPassed'] and cell.result.passed
    recs = fn.notebook.sweeps('CR')
    assert [r.values[INSIDE_BOUNDS] for r in recs] == [False, True, True, True]
    assert recs[0].values['BoundsState'] == '__BB'
    # out-of-bounds sweeps stop after the 3 cycles; passing ones once post-pulse chunk 1 passed
    stop0 = cell.log[0][1][-1][0]
    assert stop0 == pytest.approx(fn.cycleWindow[1], abs=200.5)
    assert cell.log[1][1][-1][0] > fn.chunks[1].end


def test_chirp_spikeModifierAppliedOnce():
    holder = []
    fn = makeFunction(Chirp, chirpStimset(), chirpNotebook(resistance=200.0))
    # 20 pA x 0.2 mV/pA = 4 mV trough: inside bounds; a spike in sweep 0 scales DAScale by 0.9
    cell = SyntheticCell(fn, chirpResponse(0.2, spikeSweeps=(0,), cell=holder), chunk=100.0)
    holder.append(cell)
    cell.setConfig = fn.preSet()
    decision = cell.runSweep(0)
    assert not decision.sweepPassed and fn.nextDascale == 18  # round(20 x 0.9), once
    # later midSweep calls after the stop request do not apply it again
    actions = cell.log[0][1]
    assert isinstance(actions[-1][1], EarlyStop)
    data = SweepData(0, 'IC', 0.08, np.full(10, TARGET_V), np.zeros(10), 10, EpochTable(), 20)
    assert isinstance(fn.midSweep(data), EarlyStop) and fn.nextDascale == 18
    assert fn.notebook.sweeps('CR')[0].values[SPIKE_PASS] is False


def test_chirp_outOfRangeAborts():
    ctx = context()
    ctx.commandLimit = 30.0
    fn = makeFunction(Chirp, chirpStimset(), chirpNotebook(resistance=200.0), ctx)
    # 20 pA, trough 1 mV: increase x4 = 80 pA exceeds the 30 pA limit
    cell = SyntheticCell(fn, chirpResponse(0.05), chunk=200.0).run()
    assert cell.actions == ['abort'] and fn.notebook.sweeps('CR')[0].values['DAScaleOutOfRange']


# --- replay against recorded cells ----------------------------------------------------------------

FUNCTIONS = {
    'PSQ_SquarePulse': SquarePulse,
    'PSQ_Rheobase': Rheobase,
    'PSQ_Ramp': Ramp,
    'PSQ_Chirp': Chirp,
}
CHUNK = 100.0  # ms per replayed midSweep call


def addMiesPriorResults(notebook: Notebook, rec: MiesRecording) -> None:
    """Add the DAScale and TrueRestingMembranePotential set results MIES recorded to *notebook*.

    Stands in for the DA and VM ports: each recorded set becomes a set record with ``SET_QC``,
    ``OPERATION_MODE`` and ``RESISTANCE_FROM_FIT`` (MOhm) for DA, ``FULL_AVERAGE`` (mV) for VM.
    """
    for m in rec.sets():
        last = m.sweeps[-1]
        if m.analysisFunction not in ('PSQ_DAScale', 'PSQ_TrueRestingMembranePotential'):
            continue

        def get(name):
            return rec.setting(last, userKey(m.analysisFunction, name), m.headstage, UNKNOWN_MODE)

        if m.analysisFunction == 'PSQ_DAScale':
            s = notebook.newSet(m.stimset, 'DA')
            s.values.update(
                {Keys.SET_QC: bool(get('Set QC')), Keys.OPERATION_MODE: get('operation mode')}
            )
            r = rec.setting(last, 'USER_ResistanceFromFit', m.headstage, UNKNOWN_MODE)
            if r is not None:
                s.values[Keys.RESISTANCE_FROM_FIT] = r * 1e-6
        else:
            s = notebook.newSet(m.stimset, 'VM')
            s.values[Keys.SET_QC] = bool(get('Set QC'))
            v = get('Full Average')
            if v is not None:
                s.values[Keys.FULL_AVERAGE] = v * 1e3


def _same(ours, mies, tol=0.0):
    if ours is None or mies is None:
        return ours is None and mies is None
    if isinstance(ours, str) or isinstance(mies, str):
        return ours == mies
    return abs(float(ours) - float(mies)) <= tol


def _mies(rec, sweep, func, name, scale=1.0):
    v = rec.setting(sweep, userKey(func, name), 0, UNKNOWN_MODE)
    if v is None or isinstance(v, str):
        return v
    return None if math.isnan(v) else v * scale


def detailMismatches(rec, cmp, notebook):
    """Compare notebook values of one replayed set with the MIES USER_ labnotebook entries."""
    func = cmp.miesName
    out = []

    def check(sweep, label, ours, mies, tol=0.0):
        if not _same(ours, mies, tol):
            out.append(f"sweep {sweep}: {label} {ours} != MIES {mies}")

    stepSoFar = None
    for s in cmp.sweeps:
        if s.stoppedByUser:
            continue
        v = notebook.sweep(s.sweep).values
        sw = s.sweep
        m = lambda name, scale=1.0: _mies(rec, sw, func, name, scale)  # noqa: E731
        b = lambda x: None if x is None else float(bool(x))  # noqa: E731
        if func == 'PSQ_SquarePulse':
            check(sw, 'spike', b(v.get(Keys.SPIKE_DETECT)), m('spike detected'))
            check(sw, 'final', v.get(Keys.FINAL_SCALE), m('final DAScale', 1e12), 1e-6)
            stepSoFar = m('step size', 1e12) if m('step size') is not None else stepSoFar
            check(sw, 'step', v.get('StepSize'), stepSoFar, 1e-6)
        elif func == 'PSQ_Rheobase':
            check(sw, 'spike', b(v.get(Keys.SPIKE_DETECT)), m('spike detected'))
            check(sw, 'BL', b(v.get(Keys.BASELINE_QC)), m('BL QC'))
            check(sw, 'step', v.get('StepSize'), m('step size', 1e12), 1e-6)
            check(sw, 'pulse', v.get(Keys.PULSE_DURATION), m('Pulse duration'), 1e-6)
        elif func == 'PSQ_Ramp':
            check(sw, 'spike', b(v.get(Keys.SPIKE_DETECT)), m('spike detected'))
            check(sw, 'BL', b(v.get(Keys.BASELINE_QC)), m('BL QC'))
            text = m('spike positions')
            miesPos = [float(x) for x in text.split(';') if x] if text else None
            ours = v.get('SpikePositions')
            if (ours is None) != (miesPos is None) or (
                ours is not None and not np.allclose(ours, miesPos, atol=0.02)
            ):
                out.append(f"sweep {sw}: spike positions {ours} != MIES {miesPos}")
            miesZero = miesZeroTime(rec, sw)
            if (s.zeroCommandAt is None) != (miesZero is None):
                out.append(f"sweep {sw}: zero command at {s.zeroCommandAt}, MIES at {miesZero}")
        elif func == 'PSQ_Chirp':
            check(sw, 'stimset QC', b(v.get('StimsetQC')), m('stimset QC'))
            check(sw, 'spike QC', b(v.get(SPIKE_PASS)), m('spike QC'))
            check(sw, 'BL', b(v.get(Keys.BASELINE_QC)), m('BL QC'))
            check(sw, 'inside bounds', b(v.get(INSIDE_BOUNDS)), m('inside bounds'))
            action = v.get('BoundsAction')
            check(
                sw,
                'bounds action',
                None if action is None else MIES_BOUNDS_ACTION[action],
                m('bounds action'),
            )
            check(sw, 'bounds state', v.get('BoundsState'), m('bounds state'))
            check(sw, 'oor', b(v.get('DAScaleOutOfRange')), m('DAScale out of range'))
            check(sw, 'pulse', v.get(Keys.PULSE_DURATION), m('Pulse duration'), 1e-6)
    first = cmp.mset.sweeps[0]
    sv = cmp.setRecord.values
    if cmp.sweeps and cmp.sweeps[-1].stoppedByUser:
        return [f"{cmp.mset.stimset} (SCI {cmp.mset.sci}): {x}" for x in out]
    if func == 'PSQ_Chirp' and cmp.setConfig is not None:
        check(
            first,
            'initial',
            sv.get('InitialScale'),
            _mies(rec, first, func, 'initial DAScale', 1e12),
            1e-6,
        )
        check(
            first,
            'resistance',
            sv.get('InputResistance'),
            _mies(rec, first, func, 'input resistance', 1e-6),
            1e-6,
        )
    if func == 'PSQ_Rheobase' and cmp.result is not None:
        last = cmp.mset.sweeps[-1]
        check(
            last,
            'exceeded',
            float(sv[DASCALE_EXCEEDED]),
            _mies(rec, last, func, 'DAScale exceeded'),
        )
        check(
            last,
            'limited',
            float(sv[LIMITED_RESOLUTION]),
            _mies(rec, last, func, 'limited resolut.'),
        )
    return [f"{cmp.mset.stimset} (SCI {cmp.mset.sci}): {x}" for x in out]


def miesZeroTime(rec, sweep):
    """Return the start of the MIES 'DA Suppression' epoch (ms), or None when MIES did not zero."""
    ds = [ep for ep in rec.epochs(sweep) if ep.name == 'U_RA_DS']
    return ds[0].start if ds else None


class MiesZeroRamp(Ramp):
    """Ramp that, once it zeroed the command, sees the time MIES zeroed it as ``commandZeroedAt``.

    The recorded AD follows the MIES zeroing time, so baseline chunk placement is compared on it.
    """

    recording: MiesRecording = None

    def _miesZero(self, data):
        if data.commandZeroedAt is None:
            return data
        t = miesZeroTime(self.recording, data.sweep)
        return data if t is None else dataclasses.replace(data, commandZeroedAt=t)

    def midSweep(self, data):
        return super().midSweep(self._miesZero(data))

    def postSweep(self, data):
        return super().postSweep(self._miesZero(data))


def zeroCommandMismatches(rec, result, notebook):
    """Check each ZeroCommand came within CHUNK ms after the last MIES spike position."""
    out = []
    for cmp in result.sets:
        if cmp.miesName != 'PSQ_Ramp':
            continue
        for s in cmp.sweeps:
            text = _mies(rec, s.sweep, 'PSQ_Ramp', 'spike positions')
            if s.zeroCommandAt is None or not text or s.stoppedByUser:
                continue
            last = [float(x) for x in text.split(';') if x][-1]
            if not last <= s.zeroCommandAt <= last + CHUNK:
                out.append(
                    f"{cmp.mset.stimset} (SCI {cmp.mset.sci}): sweep {s.sweep}: zero command at "
                    f"{s.zeroCommandAt:g} ms, last spike {last:g} ms"
                )
    return out


def replayCell(cell):
    """Replay the SP/RB/RA/CR sets of *cell* in one notebook; return result, mismatches, report."""
    with MiesRecording(cellFile(cell)) as rec:
        nb = Notebook()
        addMiesPriorResults(nb, rec)
        functions = dict(FUNCTIONS, PSQ_Ramp=type('Ramp', (MiesZeroRamp,), {'recording': rec}))
        res = replayRecording(
            rec,
            functions,
            notebook=nb,
            include=lambda m: m.analysisFunction in FUNCTIONS,
            chunk=CHUNK,
        )
        mm = res.mismatches() + zeroCommandMismatches(rec, res, nb)
        for cmp in res.sets:
            mm += detailMismatches(rec, cmp, nb)
        return res, mm, res.report()


# Differences from MIES that are expected, by cell: exact mismatch text -> reason.
CHIRPB = "C2CHIRPB180503_DA_0 (SCI 4309349): "
BOUNDS_WINDOW_FIX = (
    "bounds window: MIES evaluated from the spike window start (500 ms of pre-chirp baseline "
    "included, a -72 mV dip there gave __BB); the port uses the chirp cycles only"
)
EXPECTED = {
    '1544261931': {
        "C2CHIRPA180503_DA_0 (SCI 9215): sweep 71: early stop at 23600.0 ms, MIES no": (
            "MIES passed post-pulse chunk 1 (ends 23581.5 ms) but acquired the sweep to its end"
        ),
        "C2CHIRPB180503_DA_0 (SCI 4309349): sweep 72: oor 0.0 != MIES None": (
            "MIES skipped the limit check: its last-sweep test read the previous set's sweep count"
        ),
        CHIRPB + "sweep 81: early stop no, MIES at 7459.1 ms": BOUNDS_WINDOW_FIX,
        CHIRPB + "sweep 81: inside bounds 1.0 != MIES 0.0": BOUNDS_WINDOW_FIX,
        CHIRPB + "sweep 81: bounds action 1 != MIES 2.0": BOUNDS_WINDOW_FIX,
        CHIRPB + "sweep 81: bounds state __BA != MIES __BB": BOUNDS_WINDOW_FIX,
        CHIRPB + "sweep 81: oor None != MIES 0.0": BOUNDS_WINDOW_FIX,
        CHIRPB + "sweep 82: DAScale 30 != MIES 16": BOUNDS_WINDOW_FIX,
        "C2CHIRPB180503_DA_0 (SCI 4309349): sweep 82: pulse 19999.12 != MIES 19998.399999999998": (
            "follows sweep 81: DAC rounding of a different DAScale moves the chirp onset"
        ),
    },
}

# Mismatch patterns expected in every cell -> reason.
EXPECTED_ANY = {
    r": MIES user epoch U_RA_(DS|UD) missing$": (
        "user epochs come only from preSweep; the zeroing time is SweepData.commandZeroedAt"
    ),
    r": user epoch U_CR_SE \S+ != MIES ": (
        "spike window starts at the chirp onset; MIES assumed a 500 ms pre-pulse baseline"
    ),
}


def userStoppedAfterBaselineFailure(rec, result):
    """Return the 'early stop' mismatches of sweeps MIES also stopped on a failed baseline.

    These sweeps carry the DAQ-button stop reason, so the replay counts no MIES early stop.
    """
    out = set()
    for cmp in result.sets:
        for s in cmp.sweeps:
            bl = _mies(rec, s.sweep, cmp.miesName, 'BL QC')
            if s.stoppedByUser and s.earlyStop is not None and bl == 0:
                out.add(
                    f"{cmp.mset.stimset} (SCI {cmp.mset.sci}): sweep {s.sweep}: "
                    f"early stop at {s.earlyStopAt:.1f} ms, MIES no"
                )
    return out


@pytest.mark.parametrize('cell', MOUSE_CELLS + HUMAN_CELLS)
def test_replayRecordedCells(cell):
    res, mm, report = replayCell(cell)
    assert res.sets, f"no SP/RB/RA/CR sets in {cell}"
    assert all(c.aborted is None for c in res.sets), report
    with MiesRecording(cellFile(cell)) as rec:
        userStopped = userStoppedAfterBaselineFailure(rec, res)
    expected = EXPECTED.get(cell, {})
    unexpected = [
        m
        for m in mm
        if m not in expected
        and m not in userStopped
        and not any(re.search(p, m) for p in EXPECTED_ANY)
    ]
    assert unexpected == [], report
    assert set(expected) <= set(mm), "stale expected differences"
