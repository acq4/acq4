import glob
import math
import os
import re

import numpy as np
import pytest

from acq4.util.allen_stimsets import qc
from acq4.util.allen_stimsets.core import AbortSet, EarlyStop, Epoch, EpochTable, SweepData

DT = 0.02  # ms


def makeSweep(data, command=None, epochs=(), clampMode='IC', dt=DT, numValid=None, dascale=1.0):
    data = np.asarray(data, dtype=float)
    command = np.zeros_like(data) if command is None else np.asarray(command, dtype=float)
    numValid = len(data) if numValid is None else numValid
    data = data.copy()
    data[numValid:] = np.nan
    return SweepData(0, clampMode, dt, data, command, numValid, EpochTable(epochs), dascale)


def stimsetLayout(durations, amplitudes, onset=0.0):
    """E<i> epochs back to back from *onset*."""
    out, t = [], onset
    for i, (d, a) in enumerate(zip(durations, amplitudes)):
        out.append(Epoch(f'E{i}', t, t + d, a))
        t += d
    return EpochTable(out)


# --- low-level numerics ---------------------------------------------------------------------------


def test_igorRound_halfAwayFromZero():
    assert [qc.igorRound(x) for x in (0.5, 1.5, 2.5, -0.5, -1.5, 0.49)] == [1, 2, 3, -1, -2, 0]


def test_truncPoints_snapsFloatError():
    assert 38.66 / 0.02 < 1933
    assert qc.truncPoints(38.66, 0.02) == 1933
    assert qc.truncPoints(38.6698, 0.02) == 1933
    assert qc.truncPoints(0.019, 0.02) == 0


def test_windowStat_meanAndPopulationRms():
    y = np.arange(100.0)
    assert qc.windowStat(y, 1.0, 10, 4, 'avg') == pytest.approx(11.5)
    assert qc.windowStat(y, 1.0, 10, 4, 'rms') == pytest.approx(np.std([10, 11, 12, 13]))  # ddof=0
    # clipped to the wave end
    assert qc.windowStat(y, 1.0, 95, 10, 'avg') == pytest.approx(np.mean([95, 96, 97, 98, 99]))
    # at least one point
    assert qc.windowStat(y, 1.0, 7, 0.2, 'avg') == 7


def test_windowStat_raisesOnNaN():
    y = np.arange(10.0)
    y[5:] = np.nan
    with pytest.raises(ValueError):
        qc.windowStat(y, 1.0, 3, 4, 'rms')


def test_findLevels_interpolatesEdges():
    y = np.array([0, 0, 10, 10, 0, 0], dtype=float)
    assert qc.findLevels(y, 5) == pytest.approx([1.5, 3.5])
    assert qc.findLevels(y, 5, 'rising') == pytest.approx([1.5])
    assert qc.findLevels(y, 5, 'falling') == pytest.approx([3.5])
    assert qc.findLevels(y, 5, maxLevels=1) == pytest.approx([1.5])


def test_findLevels_samplesAtLevel():
    # reaching the level from below counts, passing through it counts once, leaving it upwards
    # counts
    assert qc.findLevels(np.array([-1, 0, -1.0]), 0, 'rising') == pytest.approx([1])
    assert qc.findLevels(np.array([-1, 0, 1.0]), 0, 'rising') == pytest.approx([1])
    assert qc.findLevels(np.array([1, 0, 1.0]), 0, 'rising') == pytest.approx([1])
    assert qc.findLevels(np.array([0, 0, 1.0]), 0, 'rising') == pytest.approx([1])
    assert len(qc.findLevels(np.array([0, 0, 0.0]), 0)) == 0
    assert len(qc.findLevels(np.array([-1, np.nan, 1.0]), 0)) == 0


def test_findLevels_boxSmoothing():
    y = np.array([0, 0, 0, 3, 0, 0, 0], dtype=float)
    assert len(qc.findLevels(y, 2)) == 2
    assert len(qc.findLevels(y, 2, box=3)) == 0  # smoothed peak is 1


def test_levelCrossings_rangeInMs():
    y = np.zeros(100)
    y[20:30] = 1
    y[60:70] = 1
    t = qc.levelCrossings(y, 0.5, 0, math.inf, 0.5, 'rising')
    assert t == pytest.approx([9.75, 29.75])
    assert qc.levelCrossings(y, 0.5, 20, math.inf, 0.5, 'rising') == pytest.approx([29.75])


def test_acquiredUntil_and_leftover():
    d = makeSweep(np.zeros(1000), numValid=501)
    assert qc.acquiredUntil(d, 10.02)  # samples 0..500
    assert not qc.acquiredUntil(d, 10.04)
    assert qc.leftoverSweepTime(d) == pytest.approx(499 * DT * 1e-3)


# --- epochs ---------------------------------------------------------------------------------------

PB_DURATIONS = [500, 25, 10, 25, 25, 10, 25, 25, 10, 25, 25]
PB_AMPS = [0, 0, 10, 0, 0, 10, 0, 0, 10, 0, 0]


def test_totalOnsetDelay_and_stimsetEpochs():
    layout = stimsetLayout([100, 200, 300], [0, 1, 0], onset=50)
    layout.add(Epoch('TP', 0, 50))
    assert qc.totalOnsetDelay(layout) == 50
    assert [ep.name for ep in qc.stimsetEpochs(layout)] == ['E0', 'E1', 'E2']


def test_testpulseEpochs_layoutAndScaling():
    layout = stimsetLayout(PB_DURATIONS, PB_AMPS, onset=100)
    eps = EpochTable(qc.testpulseEpochs(layout, dascale=2.0, numTestPulses=3))
    assert len(eps) == 12
    assert (eps.get('U_TP0').start, eps.get('U_TP0').end) == (600, 660)
    assert (eps.get('U_TP0_B0').start, eps.get('U_TP0_B0').end) == (600, 625)
    p = eps.get('U_TP2_P')
    assert (p.start, p.end, p.amplitude) == (745, 755, 20)
    assert p.tags['SubType'] == 'Pulse' and p.tags['Index'] == '2'
    assert eps.get('U_TP1_B1').end == eps.get('U_TP2_B0').start


def test_testpulseEpochs_indexFixedForTwoPulses():
    # MIES uses idx = 1 + i*numTestPulses (i=1 -> epoch 3, a baseline followed by a baseline)
    layout = stimsetLayout(PB_DURATIONS[:8], PB_AMPS[:8], onset=100)
    eps = EpochTable(qc.testpulseEpochs(layout, 1.0, 2))
    assert eps.get('U_TP1_P').start == layout.get('E5').start


def test_testpulseEpochs_abortsOnBadStimset():
    with pytest.raises(AbortSet):
        qc.testpulseEpochs(stimsetLayout(PB_DURATIONS[:10], PB_AMPS[:10]), 1.0, 3)
    amps = list(PB_AMPS)
    amps[4] = 5
    with pytest.raises(AbortSet):
        qc.testpulseEpochs(stimsetLayout(PB_DURATIONS, amps), 1.0, 3)


def test_baselineSelectionEpochs():
    layout = stimsetLayout([600, 1000, 800], [0, 50, 0], onset=100)
    eps = qc.baselineSelectionEpochs(layout, [2, 0], 500)
    assert [(e.name, e.start, e.end) for e in eps] == [('U_BLS0', 100, 600), ('U_BLS1', 1700, 2200)]
    assert eps[1].tags == {'Type': 'Baseline Chunk QC Selection', 'Index': '1'}
    with pytest.raises(AbortSet):
        qc.baselineSelectionEpochs(layout, [1])  # nonzero amplitude
    with pytest.raises(AbortSet):
        qc.baselineSelectionEpochs(layout, [3])  # beyond stimset
    with pytest.raises(AbortSet):
        qc.baselineSelectionEpochs(layout, [0], 700)  # too short


# --- test pulse analysis --------------------------------------------------------------------------


def tpTrace(dt, b0, p, b1, base, step, spike=0.0):
    n0, n1, n2 = round(b0 / dt), round(p / dt), round(b1 / dt)
    y = np.concatenate([np.full(n0, base), np.full(n1, base + step), np.full(n2, base)])
    y[n0 + 10] += spike  # inside the instantaneous window at 0.005 and 0.02 ms
    return y


def test_analyzeTestPulse_vc():
    y = tpTrace(0.005, 25, 10, 25, base=-20.0, step=100.0, spike=400)
    r = qc.analyzeTestPulse(y, 0.005, 25, 10, 25, clampAmp=10.0, clampMode='VC')
    assert r.baseline == pytest.approx(-20)
    assert r.steadyState == pytest.approx(80)
    assert r.steadyStateResistance == pytest.approx(100.0)  # 10 mV / 100 pA
    assert r.instantaneous == pytest.approx(480)
    assert r.instantaneousResistance == pytest.approx(10 / 500 * 1000)


def test_analyzeTestPulse_icNegative():
    y = tpTrace(0.02, 50, 100, 50, base=-70.0, step=-10.0, spike=-5)
    r = qc.analyzeTestPulse(y, 0.02, 50, 100, 50, clampAmp=-50.0, clampMode='IC')
    assert r.steadyStateResistance == pytest.approx(200.0)  # -10 mV / -50 pA
    assert r.instantaneous == pytest.approx(-85)


def test_analyzeTestPulse_unequalBaselines():
    # B0 != B1: onset from B0 and offset from B1 (MIES assumes B0 == B1)
    y = tpTrace(0.005, 10, 10, 40, base=0.0, step=50.0)
    r = qc.analyzeTestPulse(y, 0.005, 10, 10, 40, clampAmp=5.0, clampMode='VC')
    assert r.baseline == pytest.approx(0) and r.steadyState == pytest.approx(50)


def tpSweep(insertedStep=7.0, steps=(100.0, 100.0, 100.0), dt=0.005):
    # inserted TP 0-60 ms (amp 5 mV), stimset from 60 ms with E0 baseline then three TP-like shapes
    parts = [tpTrace(dt, 25, 10, 25, 0.0, insertedStep), np.zeros(round(100 / dt))]
    for s in steps:
        parts.append(tpTrace(dt, 25, 10, 25, 0.0, s))
    y = np.concatenate(parts + [np.zeros(round(20 / dt))])
    epochs = [
        Epoch('TP', 0, 60),
        Epoch('TP_B0', 0, 25),
        Epoch('TP_P', 25, 35, 5.0),
        Epoch('TP_B1', 35, 60),
    ]
    layout = stimsetLayout([100] + [25, 10, 25] * 3 + [20], [0] + [0, 10, 0] * 3 + [0], onset=60)
    epochs += list(layout) + qc.testpulseEpochs(layout, 1.0, 3)
    return makeSweep(y, epochs=epochs, clampMode='VC', dt=dt)


def test_testPulseResistance_ignoresInsertedTP():
    d = tpSweep(steps=(90.0, 100.0, 110.0))
    r = qc.testPulseResistance(d, (0,))
    assert r.numAveraged == 3
    assert r.steadyStateResistance == pytest.approx(100.0)
    r = qc.testPulseResistance(d, (1, 2, 3))
    assert r.steadyStateResistance == pytest.approx(5 / 7 * 1000)
    r = qc.testPulseResistance(d, (0, 2, 3))  # U_TP0 only
    assert r.steadyStateResistance == pytest.approx(10 / 90 * 1000)
    assert qc.testPulseResistance(d, (0, 1, 2, 3)) is None
    with pytest.raises(ValueError):
        qc.testPulseResistance(d, (4,))


def test_testPulseEpochsForAnalysis_order():
    d = tpSweep()
    assert [e.name for e in qc.testPulseEpochsForAnalysis(d.epochs)] == [
        'TP',
        'U_TP0',
        'U_TP1',
        'U_TP2',
    ]


def test_averageTestPulse_errors():
    d = tpSweep()
    tps = qc.testPulseEpochsForAnalysis(d.epochs, (0,))
    with pytest.raises(ValueError):
        qc.averageTestPulse(d.data, d.sampleInterval, [tps[0], Epoch('X', 0, 30)])
    partial = makeSweep(
        d.data, epochs=list(d.epochs), clampMode='VC', dt=0.005, numValid=round(200 / 0.005)
    )
    with pytest.raises(ValueError):
        qc.testPulseResistance(partial)


# --- baseline chunk positions ---------------------------------------------------------------------


def test_prePulseChunks():
    assert qc.prePulseChunks(100, 500) == [qc.ChunkSpec(0, 100, 500, 'prePulse')]
    for bad in (499, 1000):
        with pytest.raises(AbortSet):
            qc.prePulseChunks(100, bad)


def test_pulseChunks():
    chunks = qc.pulseChunks(onset=100, pulseDuration=1000, sweepDuration=3600)
    # post-pulse chunks start at onset + 500 + pulse + k*500 and must end inside the sweep
    assert [(c.index, c.start, c.kind) for c in chunks] == [
        (0, 100, 'prePulse'),
        (1, 2100, 'postPulse'),
        (2, 2600, 'postPulse'),
        (3, 3100, 'postPulse'),
    ]
    assert chunks[-1].end <= 3600
    with pytest.raises(ValueError):
        qc.pulseChunks(100, 1000, 1500)


def test_selectionChunks_missingIsNone():
    eps = EpochTable([Epoch('U_BLS0', 100, 600), Epoch('U_BLC0', 100, 600)])
    chunks = qc.selectionChunks(eps, 2)
    assert chunks[0] == qc.ChunkSpec(0, 100, 500, 'generic') and chunks[1] is None
    assert chunks[0].epoch().name == 'U_BLC0'


def test_baselineChunks_dispatch():
    layout = list(stimsetLayout([500, 1000, 2000], [0, 50, 0], onset=100))
    d = makeSweep(np.zeros(round(3600 / DT)), epochs=layout + [Epoch('U_BLS0', 100, 600)])
    assert qc.baselineChunks('PB', d) == qc.prePulseChunks(100, 500)
    assert qc.baselineChunks('AR', d) == qc.selectionChunks(d.epochs, 1)
    assert len(qc.baselineChunks('SE', d)) == 2
    assert qc.baselineChunks('DA', d, 1000) == qc.pulseChunks(100, 1000, 3600)
    with pytest.raises(ValueError):
        qc.baselineChunks('RB', d)


def test_baselineTests_matrix():
    T = qc.BaselineTests
    assert qc.baselineTests('PB', 'prePulse') == T(True, True, False, True)
    assert qc.baselineTests('AR', 'generic') == T(True, True, False, True)
    assert qc.baselineTests('SE', 'generic') == T(True, True)
    assert qc.baselineTests('VM', 'generic') == T(True, True)
    assert qc.baselineTests('DA', 'prePulse') == T(True, True, True, False)
    assert qc.baselineTests('CR', 'postPulse') == T(targetV=True)
    assert qc.baselineTests('PB', 'generic') == T()


# --- baseline QC ----------------------------------------------------------------------------------


def noisy(n, mean, sd, seed=0):
    return mean + sd * np.random.default_rng(seed).standard_normal(n)


def daSweep(pre=-70.0, post=-70.0, postChunks=None, numValid=None, sd=0.01):
    """IC sweep: onset 100 ms, pulse 600-1600 ms, 3600 ms total (post chunks start at 2100, 2600,
    3100)."""
    n = round(3600 / DT)
    y = noisy(n, pre, sd)
    y[round(600 / DT) : round(1600 / DT)] += 10
    y[round(1600 / DT) :] += post - pre
    for k, v in (postChunks or {}).items():
        s = round((1600 + 500 * k) / DT)
        y[s : s + round(500 / DT)] += v
    return makeSweep(y, numValid=numValid)


def test_baselineQC_vcPassAndLeakFail():
    n = round(800 / DT)
    chunk = qc.ChunkSpec(0, 100, 500, 'generic')
    d = makeSweep(noisy(n, 5.0, 1.0), clampMode='VC')
    bl = qc.BaselineQC('AR', 15, 15, maxLeakCurrent=10)
    assert bl.evaluateChunk(d, chunk) == qc.BL_PASS
    r = bl.results[0]
    assert r.passed and r.leakCurrent == pytest.approx(5.0, abs=0.1)
    assert (r.rmsShortPassed, r.rmsLongPassed, r.targetVPassed, r.leakCurrentPassed) == (
        1,
        1,
        -1,
        1,
    )

    bl = qc.BaselineQC('AR', 15, 15, maxLeakCurrent=4)
    assert bl.evaluateChunk(d, chunk) == qc.EARLY_STOP
    assert bl.results[0].leakCurrentPassed == 0

    bl = qc.BaselineQC('SE', 15, 15)
    d = makeSweep(noisy(n, 5.0, 1.0), clampMode='VC')
    assert bl.evaluateChunk(d, chunk) == qc.BL_PASS


def test_baselineQC_failedTestSkipsRest():
    n = round(800 / DT)
    d = makeSweep(noisy(n, 0.0, 30.0), clampMode='VC')
    bl = qc.BaselineQC('PB', 15, 15, maxLeakCurrent=100)
    assert bl.evaluateChunk(d, qc.ChunkSpec(0, 100, 500, 'prePulse')) == qc.EARLY_STOP
    r = bl.results[0]
    assert r.rmsShortPassed == 0
    assert math.isnan(r.rmsLongPassed) and math.isnan(r.leakCurrentPassed)
    assert math.isnan(r.rmsLong)


def test_baselineQC_leakNeedsVC():
    d = makeSweep(np.zeros(round(800 / DT)), clampMode='IC')
    with pytest.raises(ValueError):
        qc.BaselineQC('AR', maxLeakCurrent=10).evaluateChunk(
            d, qc.ChunkSpec(0, 100, 500, 'generic')
        )


def test_baselineQC_prePulseCodes():
    chunks = qc.pulseChunks(100, 1000, 3600)
    assert qc.BaselineQC('DA', targetV=-70).evaluateChunk(daSweep(), chunks[0]) == qc.BL_PASS
    assert qc.BaselineQC('DA', targetV=-75).evaluateChunk(daSweep(), chunks[0]) == qc.REPURP_TIME
    assert (
        qc.BaselineQC('DA', targetV=-70).evaluateChunk(daSweep(sd=1.0), chunks[0]) == qc.EARLY_STOP
    )
    with pytest.raises(ValueError):
        qc.BaselineQC('DA').evaluateChunk(daSweep(), chunks[0])


def test_baselineQC_partialDataAndDecideOnce():
    chunks = qc.pulseChunks(100, 1000, 3600)
    bl = qc.BaselineQC('DA', targetV=-75)
    early = daSweep(
        numValid=round(600 / DT) - 1
    )  # chunk 0 ends at 600 ms: sample at 599.98 missing
    st = bl.evaluate(early, chunks)
    assert st == qc.BaselineStatus(None, 0) and not st.decided and not st.passed
    assert st.midSweepCode is None
    later = daSweep(numValid=round(600 / DT))
    st = bl.evaluate(later, chunks)
    assert st.code == qc.REPURP_TIME and st.midSweepCode == qc.REPURP_TIME
    # evaluated once; the cached failure no longer asks for a stop
    st = bl.evaluate(daSweep(), chunks)
    assert st.code == qc.BL_FAILED and st.chunk == 0


def test_baselineQC_postPulseLoop():
    chunks = qc.pulseChunks(100, 1000, 3600)
    # chunk 1 off target, chunk 2 on target: pass at chunk 2
    bl = qc.BaselineQC('DA', targetV=-70)
    st = bl.evaluate(daSweep(postChunks={1: 5}), chunks)
    assert st == qc.BaselineStatus(qc.BL_PASS, 2) and st.midSweepCode == qc.EARLY_STOP
    assert not bl.results[1].passed and 3 not in bl.results

    # all post-pulse chunks fail: BL_FAILED once complete, no stop
    st = qc.BaselineQC('DA', targetV=-70).evaluate(daSweep(post=-60), chunks)
    assert st == qc.BaselineStatus(qc.BL_FAILED, 4) and st.midSweepCode == qc.BL_FAILED

    # partial: chunk 1 failed, chunk 2 not acquired yet
    bl = qc.BaselineQC('DA', targetV=-70)
    st = bl.evaluate(daSweep(post=-60, numValid=round(2700 / DT)), chunks)
    assert st == qc.BaselineStatus(None, 2)


def test_baselineQC_lastChunkIncompleteOnCompleteSweep():
    # chunk that cannot be acquired (sweep stopped short of it) fails once the sweep is complete
    chunks = [qc.ChunkSpec(0, 100, 500, 'generic')]
    y = noisy(round(550 / DT), 0, 0.01)
    st = qc.BaselineQC('VM').evaluate(makeSweep(y), chunks)
    assert st == qc.BaselineStatus(qc.BL_FAILED, 0)


def test_baselineQC_vmArFailureEnds():
    chunks = [qc.ChunkSpec(0, 100, 500, 'generic')]
    d = makeSweep(noisy(round(800 / DT), 0, 1.0), clampMode='VC')
    st = qc.BaselineQC('AR', 0.5, 0.5, maxLeakCurrent=10).evaluate(d, chunks)
    assert st == qc.BaselineStatus(qc.EARLY_STOP, 0) and not st.passed
    with pytest.raises(ValueError):
        qc.BaselineQC('VM').evaluate(d, chunks * 2)


def test_baselineQC_sealEvaluation():
    n = round(2000 / DT)
    y = noisy(n, 0, 1.0)
    y[round(1000 / DT) :] = noisy(n - round(1000 / DT), 0, 30.0, seed=1)
    d = makeSweep(y, clampMode='VC')
    eps = EpochTable([Epoch('U_BLS0', 100, 600), Epoch('U_BLS1', 1200, 1700)])
    bl = qc.BaselineQC('SE', 15, 15)
    st = bl.evaluate(d, qc.selectionChunks(eps, 2))
    assert st.code == qc.BL_FAILED and bl.results[0].passed and not bl.results[1].passed
    # only one group selected: the missing chunk is BL_FAILED without a result
    bl = qc.BaselineQC('SE', 15, 15)
    st = bl.evaluate(d, qc.selectionChunks(EpochTable([Epoch('U_BLS0', 100, 600)]), 2))
    assert st.code == qc.BL_FAILED and list(bl.results) == [0] and bl.results[0].passed
    with pytest.raises(ValueError):
        qc.BaselineQC('SE').evaluate(
            makeSweep(y, numValid=100, clampMode='VC'), qc.selectionChunks(eps, 2)
        )


def test_baselineQC_chirpNeedsThreeChunks():
    with pytest.raises(ValueError):
        qc.BaselineQC('CR', targetV=-70).evaluate(daSweep(), qc.pulseChunks(100, 1000, 2700))


def test_repurposedTime_and_midSweepAction():
    assert qc.repurposedTime('DA', 2.0) == 7.0
    assert qc.repurposedTime('RB', 2.0) == 12.0
    assert qc.repurposedTime('CR', 2.0) == 6.0
    d = makeSweep(np.zeros(1000), numValid=500)
    assert qc.toMidSweepAction(qc.EARLY_STOP, 'DA', d) == EarlyStop('baseline QC')
    a = qc.toMidSweepAction(qc.REPURP_TIME, 'DA', d)
    assert a.extraIti == pytest.approx(5 + 500 * DT * 1e-3)
    assert qc.toMidSweepAction(qc.BL_FAILED, 'DA', d) is None
    assert qc.toMidSweepAction(None, 'DA', d) is None


# --- pulse duration -------------------------------------------------------------------------------


def test_pulseDuration_square():
    c = np.zeros(1000)
    c[200:300] = 50
    assert qc.pulseDuration(c, DT, 1.0, 'square') == pytest.approx(100 * DT)
    assert qc.pulseDuration(-c, DT, 1.0, 'square') == pytest.approx(100 * DT)
    c[500:] = np.nan  # unacquired tail
    assert qc.pulseDuration(c, DT, 1.0, 'square') == pytest.approx(100 * DT)
    with pytest.raises(ValueError):
        qc.pulseDuration(np.zeros(1000), DT, 1.0, 'square')


def test_pulseDuration_ramp():
    c = np.zeros(1000)
    c[200:701] = np.linspace(0, 100, 501)  # c[200] == 0: ramp starts after it
    assert qc.pulseDuration(c, DT, 1.0, 'ramp') == pytest.approx(500 * DT)


# --- spike detection ------------------------------------------------------------------------------


def spikeSweep(
    spikeTimes, n=round(1000 / DT), pulse=(200, 700), width=1.0, numValid=None, peak=30.0
):
    y = np.full(n, -70.0)
    for t in spikeTimes:
        s = round(t / DT)
        y[s : s + round(width / DT)] = peak
    c = np.zeros(n)
    c[round(pulse[0] / DT) : round(pulse[1] / DT)] = 100
    return makeSweep(y, c, numValid=numValid)


def test_spikeSearchWindow():
    c = np.zeros(1000)
    c[200:300] = 5
    assert qc.spikeSearchWindow(c, DT, 'DA', 1.0) == pytest.approx((199 * DT, 300 * DT), abs=1e-6)
    first, last = qc.spikeSearchWindow(c, DT, 'RB', 1.0, 15.0)
    assert first == pytest.approx(199 * DT, abs=1e-6) and last == 15.0
    assert qc.spikeSearchWindow(c, DT, 'CR', 1.0, 9.0) == (1.0, 9.0)
    assert qc.spikeSearchWindow(np.zeros(1000), DT, 'SP', 1.0) == (0.0, math.inf)
    assert qc.spikeSearchWindow(np.zeros(1000), DT, 'RB', 1.0) is None
    with pytest.raises(ValueError):
        qc.spikeSearchWindow(np.full(1000, 5.0), DT, 'RB', 1.0)


def test_searchForSpikes_first():
    d = spikeSweep([100, 300, 800])
    r = qc.searchForSpikes(d, 'RB', 50, qc.SPIKE_LEVEL)
    assert r.detected and r.count == 1
    assert r.positions[0] == pytest.approx(300, abs=2 * DT)  # spike at 100 ms is before the pulse
    r = qc.searchForSpikes(spikeSweep([100]), 'RB', 50, qc.SPIKE_LEVEL)
    assert not r.detected and r.count == 0 and len(r.positions) == 0


def test_searchForSpikes_counting():
    d = spikeSweep([300, 400, 500, 800])
    r = qc.searchForSpikes(d, 'DA', 50, qc.DA_SPIKE_LEVEL, numberOfSpikesReq=math.inf)
    assert r.detected and r.count == 3  # DA: pulse window only
    r = qc.searchForSpikes(d, 'RA', 50, qc.SPIKE_LEVEL, numberOfSpikesReq=4)
    assert r.detected and r.count == 4 and len(r.positions) == 4
    r = qc.searchForSpikes(d, 'RA', 50, qc.SPIKE_LEVEL, numberOfSpikesReq=5)
    assert not r.detected and r.count == 4 and len(r.positions) == 0


def test_searchForSpikes_partialData():
    d = spikeSweep([300, 400, 500], numValid=round(450 / DT))
    r = qc.searchForSpikes(d, 'RA', 50, qc.SPIKE_LEVEL, numberOfSpikesReq=3)
    assert not r.detected and r.count == 2


def test_searchForSpikes_zeroDA():
    d = spikeSweep([300])
    d.command[:] = 0
    assert qc.searchForSpikes(d, 'SP', 50, qc.SPIKE_LEVEL).detected
    assert not qc.searchForSpikes(d, 'RB', 50, qc.SPIKE_LEVEL).detected


def test_searchForSpikes_needsIC():
    d = spikeSweep([300])
    d.clampMode = 'VC'
    with pytest.raises(ValueError):
        qc.searchForSpikes(d, 'RB', 50, qc.SPIKE_LEVEL)


def test_chirpSpikes():
    d = spikeSweep([300, 400], width=0.1)  # too narrow
    r = qc.searchForSpikes(d, 'CR', 250, -10, searchEnd=600, numberOfSpikesReq=math.inf)
    assert not r.detected
    d = spikeSweep([300, 400, 700], width=1.0)
    r = qc.searchForSpikes(d, 'CR', 250, -10, searchEnd=600, numberOfSpikesReq=math.inf)
    assert r.detected and r.count == 2
    assert r.positions == pytest.approx([300, 400], abs=1.0)
    with pytest.raises(ValueError):
        qc.searchForSpikes(d, 'CR', 250, -10, searchEnd=600)


def test_chirpSpikes_flatTopNeedsPeak():
    y = np.full(5000, -70.0)
    y[1000:1100] = np.linspace(-20, 0, 100)  # rises above -10 and is cut off by the range end
    assert len(qc.chirpSpikePositions(y, DT, 0, 1099 * DT, -10)) == 0
    # an odd crossing (spike still in progress) is dropped
    y = np.full(5000, -70.0)
    y[1000:] = 0
    assert len(qc.chirpSpikePositions(y, DT, 0, 4999 * DT, -10)) == 0


def test_apFrequency():
    d = spikeSweep([300, 350, 400, 450, 900])
    assert qc.apFrequency(d, 200, 700) == pytest.approx(4 / 0.5)
    partial = spikeSweep([300, 350, 400, 450], numValid=round(450 / DT))
    assert qc.apFrequency(partial, 200, 700) == pytest.approx(3 / 0.25)


# --- sampling QC, bookkeeping, DAScale limit ------------------------------------------------------


def test_samplingQC_relativeTolerance():
    assert qc.samplingQC(0.02, 50)
    assert qc.samplingQC(0.03, 50) and qc.samplingQC(0.015, 50)  # within [expected/2, 2*expected]
    assert not qc.samplingQC(0.08, 50) and not qc.samplingQC(0.005, 50)
    assert not qc.samplingQC(0.02, 0)
    assert qc.samplingQC(0.02, 50, tol=1e-6) and not qc.samplingQC(0.03, 50, tol=1e-6)
    assert qc.defaultSamplingFrequency('VM') == 200 and qc.defaultSamplingFrequency('CR') == 50


def test_determineSweepQCResults():
    f = qc.determineSweepQCResults
    assert f(True, True, 3, 1, 1) == 'endSetPassed'
    assert f(True, True, 5, 2, 2, requiredPasses=3) == 'continue'
    assert f(False, True, 3, 1, 0, failsAllowed=3) == 'continue'
    assert f(False, True, 3, 1, 0, failsAllowed=1) == 'abort'  # too many fails
    assert f(False, True, 3, 3, 0, failsAllowed=math.inf) == 'abort'  # no sweeps left
    assert f(False, True, 5, 2, 1, requiredPasses=5) == 'abort'  # 3 left < 4 needed
    assert f(False, False, 5, 1, 0, failsAllowed=3) == 'abort'  # sampling QC
    assert f(True, False, 5, 1, 1, requiredPasses=2) == 'continue'


def test_dascaleOutOfRange():
    assert not qc.dascaleOutOfRange(100, 0, 1, 1000)
    assert qc.dascaleOutOfRange(1000, 0, 1, 1000)  # the border value is invalid
    assert qc.dascaleOutOfRange(-1500, 0, 1, 1000)  # negative DAScale is checked too
    assert qc.dascaleOutOfRange(-600, -2, 1, 1000)
    assert qc.dascaleOutOfRange(900, 0, 1, 1000, holding=150)


# --- recorded MIES data ---------------------------------------------------------------------------

HUMAN_0304 = (
    '//allen/programs/celltypes/production/humancelltypes/prod172/'
    'Ephys_Roi_Result_1544261931/H26.51.023.11.11.03.04.nwb'
)
MOUSE_0402 = (
    '//allen/programs/celltypes/production/mousecelltypes/prod4159/Ephys_Roi_Result_1539834022'
)


def _s(x):
    return x.decode() if isinstance(x, bytes) else str(x)


class Recording:
    """Minimal reader for a MIES NWB: sweeps as SweepData, labnotebook values and epochs."""

    def __init__(self, path):
        h5py = pytest.importorskip('h5py')
        self.f = h5py.File(path, 'r')
        g = self.f['general/labnotebook']
        g = g[list(g)[0]]
        self.nk = [_s(k) for k in g['numericalKeys'][0]]
        self.nv = g['numericalValues'][()]
        self.tk = [_s(k) for k in g['textualKeys'][0]]
        self.tv = g['textualValues'][()]
        self.nsw = self.nv[:, self.nk.index('SweepNum'), 8]
        col = self.tv[:, self.tk.index('SweepNum'), 8]
        self.tsw = np.array([float(_s(x)) if _s(x) else np.nan for x in col])

    def num(self, sweep, key, scale=1.0):
        """Last finite value of *key* for *sweep*, headstage 0 or else the independent layer."""
        if key not in self.nk:
            return np.nan
        rows = self.nv[self.nsw == sweep, self.nk.index(key)]
        for layer in (0, 8):
            v = rows[:, layer]
            v = v[np.isfinite(v)]
            if len(v):
                return v[-1] * scale
        return np.nan

    def text(self, sweep, key):
        rows = [_s(r) for r in self.tv[self.tsw == sweep, self.tk.index(key), 0]]
        rows = [r for r in rows if r]
        return rows[-1] if rows else ''

    def epochs(self, sweep):
        out = []
        for ent in self.text(sweep, 'Epochs').split(':'):
            if not ent:
                continue
            start, end, tags = ent.split(',')[:3]
            tagd = dict(t.split('=', 1) for t in tags.split(';') if '=' in t)
            amp = float(tagd['Amplitude']) if 'Amplitude' in tagd else np.nan
            out.append(
                Epoch(tagd.get('ShortName', ''), float(start) * 1000, float(end) * 1000, amp, tagd)
            )
        return EpochTable(out)

    def attrs(self, sweep):
        return self.f['acquisition'][f'data_{sweep:05d}_AD0'].attrs

    def stimset(self, sweep):
        return _s(self.attrs(sweep)['stimulus_description'])

    def params(self, sweep):
        """Analysis parameters, from the newest sweep up to *sweep* of the same stimset that lists
        them."""
        m = None
        for n in range(sweep, -1, -1):
            if self.stimset(n) == self.stimset(sweep):
                m = re.search(r'Function params \(encoded\): (.*)', _s(self.attrs(n)['comments']))
                if m:
                    break
        out = {}
        for item in (m.group(1).split(',') if m else []):
            if ':' in item and '=' in item:
                name, rest = item.split(':', 1)
                out[name] = rest.split('=', 1)[1]
        return out

    def sampleInterval(self, n):
        return float(
            self.f['acquisition'][f'data_{n:05d}_AD0']['data'].attrs['IGORWaveScaling'][1][0]
        )

    def sweep(self, n):
        ad = self.f['acquisition'][f'data_{n:05d}_AD0']['data']
        da = self.f['stimulus/presentation'][f'data_{n:05d}_DA0']['data']
        dt = self.sampleInterval(n)
        y = ad[()].astype(float)
        mode = 'IC' if _s(ad.attrs['IGORWaveUnits'][0]) == 'mV' else 'VC'
        finite = np.isfinite(y)
        numValid = len(y) if finite.all() else int(np.argmin(finite))
        return SweepData(
            n,
            mode,
            dt,
            y,
            da[()].astype(float),
            numValid,
            self.epochs(n),
            self.num(n, 'Stim Scale Factor'),
        )


def _open(path):
    try:
        if not os.path.exists(path):
            pytest.skip(f"recorded data not reachable: {path}")
    except OSError:
        pytest.skip("recorded data share not reachable")
    return Recording(path)


@pytest.fixture(scope='module')
def human():
    return _open(HUMAN_0304)


@pytest.fixture(scope='module')
def mouse():
    try:
        files = glob.glob(MOUSE_0402 + '/Pvalb*.nwb')
    except OSError:
        files = []
    if not files:
        pytest.skip("recorded data share not reachable")
    return _open(files[0])


PREFIX = {
    'PB': 'Pipette in Bath',
    'SE': 'Seal evaluation',
    'AR': 'Access Res. Smoke',
    'VM': 'True Rest Memb.',
}
PREFIX.update({'DA': 'DA Scale', 'RB': 'Rheobase', 'RA': 'Ramp', 'CR': 'Chirp', 'SP': 'Squ. Pul.'})
TYPE_BY_STIMSET = {
    'X1': 'DA',
    'X6': 'DA',
    'X3': 'RB',
    'X5': 'RB',
    'X7': 'RA',
    'C2': 'CR',
    'X2': 'SP',
    'X4': 'SP',
}


def _thresholds(rec, n, t):
    p = PREFIX[t]
    return dict(
        rmsShortThreshold=rec.num(n, f'USER_{p} S-RMS Threshold', 1e3),
        rmsLongThreshold=rec.num(n, f'USER_{p} L-RMS Threshold', 1e3),
        targetVThreshold=rec.num(n, f'USER_{p} T-V Threshold', 1e3),
    )


def _checkChunk(rec, n, t, res):
    p = PREFIX[t]
    k = res.chunk.index
    for attr, key, scale in (
        ('rmsShort', 'S-RMS', 1e3),
        ('rmsLong', 'L-RMS', 1e3),
        ('average', 'T-V BL', 1e3),
        ('leakCurrent', 'Leak Current BL', 1e12),
    ):
        expected = rec.num(n, f'USER_{p} Chk{k} {key}', scale)
        if np.isfinite(expected):
            assert getattr(res, attr) == pytest.approx(expected, rel=1e-9, abs=1e-9), (n, k, attr)
    assert res.passed == bool(rec.num(n, f'USER_{p} Chk{k} BL QC')), (n, k)


@pytest.mark.parametrize('sweep, t', [(0, 'AR'), (1, 'PB'), (3, 'AR'), (4, 'VM')])
def test_recorded_baselineAndTP(human, sweep, t):
    d = human.sweep(sweep)
    params = human.params(sweep)
    th = _thresholds(human, sweep, t)
    bl = qc.BaselineQC(t, maxLeakCurrent=float(params.get('MaxLeakCurrent', 'nan')), **th)
    if t == 'PB':
        chunks = qc.prePulseChunks(qc.totalOnsetDelay(d.epochs), d.epochs.get('E0').duration)
    else:
        chunks = qc.selectionChunks(d.epochs, 1)
    st = bl.evaluate(d, chunks)
    _checkChunk(human, sweep, t, bl.results[0])
    assert st.passed == bool(human.num(sweep, f'USER_{PREFIX[t]} BL QC'))

    tp = qc.testPulseResistance(d, (0,)) if t != 'VM' else None
    if t == 'AR':
        assert tp.instantaneousResistance == pytest.approx(
            human.num(sweep, 'USER_Access Res. Smoke access resistance', 1e-6)
        )
        assert tp.steadyStateResistance == pytest.approx(
            human.num(sweep, 'USER_Access Res. Smoke steady state resistance', 1e-6)
        )
    elif t == 'PB':
        assert tp.steadyStateResistance == pytest.approx(
            human.num(sweep, 'USER_Pipette in Bath pipette resistance', 1e-6)
        )


def test_recorded_sealEvaluation(human):
    d = human.sweep(2)
    bl = qc.BaselineQC('SE', **_thresholds(human, 2, 'SE'))
    bl.evaluate(d, qc.selectionChunks(d.epochs, 2))
    for k in (0, 1):
        _checkChunk(human, 2, 'SE', bl.results[k])
    a = qc.testPulseResistance(d, (0, 4, 5, 6))
    b = qc.testPulseResistance(d, (0, 1, 2, 3))
    assert a.steadyStateResistance == pytest.approx(
        human.num(2, 'USER_Seal evaluation seal resistance A', 1e-6)
    )
    assert b.steadyStateResistance == pytest.approx(
        human.num(2, 'USER_Seal evaluation seal resistance B', 1e-6)
    )


def _pulseSweeps(rec):
    out = []
    for n in range(84):
        t = TYPE_BY_STIMSET.get(rec.stimset(n)[:2])
        if t in ('DA', 'RB', 'RA', 'CR'):
            out.append((n, t))
    return out


def test_recorded_pulseDurationAndChunks(human):
    checked = 0
    for n, t in _pulseSweeps(human):
        d = human.sweep(n)
        if t == 'CR' and not np.all(np.isfinite(d.command)):
            continue  # DA truncated by an early stop: MIES measured the chirp on the full DA
        onset = qc.totalOnsetDelay(d.epochs)
        dur = qc.pulseDuration(
            d.command, d.sampleInterval, onset, 'ramp' if t in ('RA', 'CR') else 'square'
        )
        assert dur == pytest.approx(human.num(n, f'USER_{PREFIX[t]} Pulse duration'), abs=1e-9), n
        bl = qc.BaselineQC(t, targetV=human.num(n, 'Autobias Vcom'), **_thresholds(human, n, t))
        st = bl.evaluate(d, qc.baselineChunks(t, d, dur))
        for res in bl.results.values():
            _checkChunk(human, n, t, res)
        assert st.passed == bool(human.num(n, f'USER_{PREFIX[t]} BL QC')), n
        checked += 1
    assert checked > 30


def test_recorded_prePulseFailures(mouse):
    # sweep 7: long RMS fail -> EARLY_STOP; sweeps 35, 37: target V fail -> REPURP_TIME
    for n, code in (
        (5, qc.BL_PASS),
        (7, qc.EARLY_STOP),
        (35, qc.REPURP_TIME),
        (37, qc.REPURP_TIME),
    ):
        d = mouse.sweep(n)
        bl = qc.BaselineQC(
            'DA', targetV=mouse.num(n, 'Autobias Vcom'), **_thresholds(mouse, n, 'DA')
        )
        assert (
            bl.evaluateChunk(d, qc.ChunkSpec(0, qc.totalOnsetDelay(d.epochs), 500, 'prePulse'))
            == code
        )
        _checkChunk(mouse, n, 'DA', bl.results[0])


def test_recorded_spikes(human):
    for n in range(10, 63):
        st = human.stimset(n)
        t = TYPE_BY_STIMSET[st[:2]]
        d = human.sweep(n)
        onset = qc.totalOnsetDelay(d.epochs)
        p = PREFIX[t]
        if t in ('SP', 'RB'):
            r = qc.searchForSpikes(d, t, onset, qc.SPIKE_LEVEL)
            assert r.detected == bool(human.num(n, f'USER_{p} spike detected')), n
        elif st.startswith('X6PS_SupraThresh_DA_0'):
            r = qc.searchForSpikes(d, 'DA', onset, qc.DA_SPIKE_LEVEL, numberOfSpikesReq=math.inf)
            assert r.count == human.num(n, 'USER_DA Scale spike count'), n
        elif st.startswith('X6PS_SupraThresh_DA_1'):
            e1 = d.epochs.get('E1')
            expected = human.num(n, 'USER_DA Scale AP frequency')
            if np.isfinite(expected):
                assert qc.apFrequency(d, e1.start, e1.end) == pytest.approx(expected), n
        elif t == 'RA':
            req = float(human.params(n).get('NumberOfSpikes', 'nan'))
            if not math.isfinite(req):
                req = 10 if 'N0' not in st else 5
            r = qc.searchForSpikes(d, 'RA', onset, qc.SPIKE_LEVEL, numberOfSpikesReq=req)
            assert r.detected == bool(human.num(n, 'USER_Ramp spike detected')), n
            expected = [
                float(x) for x in human.text(n, 'USER_Ramp spike positions').split(';') if x
            ]
            assert r.positions == pytest.approx(expected, abs=0.006), n


def test_recorded_samplingQC(human):
    for n in range(84):
        t = TYPE_BY_STIMSET.get(human.stimset(n)[:2]) or {
            'EXTPSMOKET': 'AR',
            'EXTPINBATH': 'PB',
            'EXTPCllATT': 'SE',
            'EXTPBREAKN': 'AR',
            'X0NRMP_DA_': 'VM',
        }.get(human.stimset(n)[:10])
        if t is None:
            continue
        expected = human.num(n, f'USER_{PREFIX[t]} Sampling interval QC')
        if not np.isfinite(expected):
            continue
        freq = float(human.params(n).get('SamplingFrequency', qc.defaultSamplingFrequency(t)))
        assert qc.samplingQC(human.sampleInterval(n), freq) == bool(expected), n
