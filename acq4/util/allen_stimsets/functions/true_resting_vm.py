"""PSQ_TrueRestingMembranePotential (MIES prefix VM): resting Vm in current clamp, no holding."""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from .. import qc
from ..core import (
    AbortSet,
    AmplifierSettings,
    Epoch,
    EpochTable,
    MidSweepAction,
    SetConfig,
    SetResult,
    SweepConfig,
    SweepData,
    SweepDecision,
)
from ..notebook import ASYNC_QC_SKIPPED, Keys
from .base import AnalysisFunction, register

# Notebook sweep values (MIES units); Keys.FULL_AVERAGE (mV) is also a set value.
SPIKE_QC = 'SpikeQC'  # bool, no crossing of FailedLevel
CHUNK_AVERAGES = 'ChunkAverages'  # [mV, mV]: mean over U_BLS0, U_BLS1 (NaN when BL QC failed)
FULL_AVERAGE_ABS_DIFF = 'FullAverageAbsoluteDifference'  # mV, avg0 - avg1
FULL_AVERAGE_REL_DIFF = 'FullAverageRelativeDifference'  # (avg0 - avg1) / avg0
FULL_AVERAGE_QC = 'FullAverageQC'  # bool
SPIKE_FAIL_AUTOBIAS_TARGET = 'SpikeFailAutobiasTarget'  # mV, requested after a spike failure

NUM_REQUIRED_EPOCHS = 3  # PSQ_VM_REQUIRED_EPOCHS
REQUIRED_PASSES = 1  # PSQ_VM_NUM_SWEEPS_PASS
BLS_EPOCHS = (0, 2)
DEFAULT_ITI_AFTER_SPIKE = 10.0  # s, InterTrialInterval default


def meanExcludingSpikes(
    trace: np.ndarray, dt: float, onset: float, spikes, ignoredTime: float
) -> float:
    """Return the mean of *trace* without ``[0, onset]`` and ``±ignoredTime/2`` around each spike.

    Times in ms; window ends are rounded to the nearest sample and included. NaN when nothing is
    left.
    """
    n = len(trace)
    keep = np.ones(n, dtype=bool)
    keep[: min(n, qc.igorRound(onset / dt) + 1)] = False
    for t in spikes:
        first = min(max(qc.igorRound((t - ignoredTime / 2) / dt), 0), n - 1)
        last = min(max(qc.igorRound((t + ignoredTime / 2) / dt), 0), n - 1)
        keep[first : last + 1] = False
    return float(np.mean(trace[keep])) if keep.any() else float('nan')


def baselineSelectionEpochs(
    layout: EpochTable, stimset, epochIndices, chunkLength: float
) -> list[Epoch]:
    """Return ``U_BLS<k>``: the first *chunkLength* ms of each listed stimset epoch.

    Amplitude and length are checked against the stimset definition (lengths within 1e-6 ms); the
    start comes from *layout*. Raises AbortSet when an epoch is missing, nonzero or too short.
    """
    eps = qc.stimsetEpochs(layout)
    out = []
    for k, i in enumerate(sorted(set(epochIndices))):
        if i >= len(eps) or i >= len(stimset.epochs):
            raise AbortSet(f"baseline selection epoch E{i} is beyond the stimset")
        d = stimset.epochs[i]
        if d.amplitude != 0:
            raise AbortSet(f"baseline selection epoch E{i} has amplitude {d.amplitude}, expected 0")
        if d.duration < chunkLength - 1e-6:
            raise AbortSet(
                f"epoch E{i} is {d.duration} ms, shorter than BaselineChunkLength {chunkLength} ms"
            )
        start = eps[i].start
        out.append(
            Epoch(
                f'U_BLS{k}',
                start,
                start + chunkLength,
                0.0,
                {'Type': 'Baseline Chunk QC Selection', 'Index': str(k)},
            )
        )
    return out


@register
class TrueRestingMembranePotential(AnalysisFunction):
    """Measure resting Vm with holding off; fail on spikes; leave autobias targeting the result.

    Stimset: three epochs, 0 and 2 baselines of amplitude 0 and at least BaselineChunkLength ms.
    Baseline QC (RMS) runs mid-sweep on ``U_BLS0`` only and never stops the sweep.
    """

    miesName = 'PSQ_TrueRestingMembranePotential'
    analysisType = 'VM'
    clampMode = 'IC'

    def preSet(self) -> SetConfig:
        for name in (
            'AbsoluteVoltageDiff',
            'RelativeVoltageDiff',
            'FailedLevel',
            'NumberOfFailedSweeps',
            'SpikeFailureIgnoredTime',
            'UserOffsetTargetVAutobias',
        ):
            self.param(name)
        if len(self.stimset.epochs) != NUM_REQUIRED_EPOCHS:
            raise AbortSet(
                f"{self.miesName}: stimset has {len(self.stimset.epochs)} epochs, "
                f"needs {NUM_REQUIRED_EPOCHS}"
            )
        self._spikeFailTarget: Optional[float] = None
        self._bl: Optional[qc.BaselineQC] = None
        return SetConfig(
            clampMode='IC',
            sampleInterval=self.sampleInterval(),
            insertTestPulse=True,
            runAmplifier=AmplifierSettings(
                holdingEnabled=False,
                capNeutralizationEnabled=True,
                bridgeBalanceEnabled=True,
                autobiasEnabled=False,
            ),
        )

    def preSweep(self, setSweepIndex: int, layout: EpochTable) -> SweepConfig:
        if len(qc.stimsetEpochs(layout)) != NUM_REQUIRED_EPOCHS:
            raise AbortSet(f"{self.miesName}: stimset must have {NUM_REQUIRED_EPOCHS} epochs")
        bls = baselineSelectionEpochs(
            layout,
            self.stimset,
            BLS_EPOCHS,
            self.param('BaselineChunkLength', qc.BL_CHUNK_LENGTH),
        )
        self._bl = self.baselineQC()
        self._blStatus: Optional[qc.BaselineStatus] = None
        return SweepConfig(dascale=1.0, userEpochs=bls)

    def _evaluateBaseline(self, data: SweepData) -> qc.BaselineStatus:
        if self._blStatus is None or not self._blStatus.passed:
            self._blStatus = self._bl.evaluate(data, qc.baselineChunks('VM', data))
        return self._blStatus

    def midSweep(self, data: SweepData) -> MidSweepAction:
        self._evaluateBaseline(data)
        return None

    def postSweep(self, data: SweepData) -> SweepDecision:
        values = self.notebook.sweep(data.sweep).values
        blPassed = self._evaluateBaseline(data).passed
        onset = qc.totalOnsetDelay(data.epochs)

        spikes = qc.searchForSpikes(
            data, 'VM', onset, self.param('FailedLevel'), numberOfSpikesReq=math.inf
        )
        spikePassed = spikes.count == 0
        avgPassed = self._averageVoltage(data, blPassed, values)
        samplingPassed = self.samplingPassed(data)
        sweepPassed = blPassed and samplingPassed and spikePassed and avgPassed
        values.update(
            {
                Keys.BASELINE_QC: blPassed,
                SPIKE_QC: spikePassed,
                Keys.SPIKE_POSITIONS: [float(t) for t in spikes.positions],
                Keys.SAMPLING_QC: samplingPassed,
                Keys.ASYNC_QC: ASYNC_QC_SKIPPED,
                Keys.SWEEP_QC: sweepPassed,
            }
        )

        iti = None
        if not spikePassed:
            target = meanExcludingSpikes(
                qc.acquired(data),
                data.sampleInterval,
                onset,
                spikes.positions,
                self.param('SpikeFailureIgnoredTime'),
            )
            if math.isfinite(target):
                self._spikeFailTarget = target + self.param('UserOffsetTargetVAutobias')
                values[SPIKE_FAIL_AUTOBIAS_TARGET] = self._spikeFailTarget
            iti = float(self.param('InterTrialInterval', DEFAULT_ITI_AFTER_SPIKE))

        recs = [self.notebook.sweep(sw) for sw in self.setRecord.sweeps]
        action = qc.determineSweepQCResults(
            sweepPassed,
            samplingPassed,
            self.stimset.numSweeps,
            len(recs),
            sum(bool(r.values.get(Keys.SWEEP_QC)) for r in recs),
            REQUIRED_PASSES,
            self.param('NumberOfFailedSweeps'),
        )
        return SweepDecision(sweepPassed, action, iti=iti)

    def _averageVoltage(self, data: SweepData, blPassed: bool, values: dict) -> bool:
        """Write the U_BLS0/U_BLS1 averages and their difference QCs; return the Full Average QC."""
        avgs = [float('nan'), float('nan')]
        if blPassed:
            for k in range(2):
                ep = data.epochs.get(f'U_BLS{k}')
                try:
                    avgs[k] = qc.windowStat(
                        qc.acquired(data), data.sampleInterval, ep.start, ep.duration, 'avg'
                    )
                except ValueError:
                    pass  # not acquired (sweep stopped)
        full = (avgs[0] + avgs[1]) / 2
        absDiff = avgs[0] - avgs[1]
        relDiff = absDiff / avgs[0] if avgs[0] != 0 else float('nan')
        absPassed = abs(absDiff) <= self.param('AbsoluteVoltageDiff')
        relPassed = abs(relDiff) <= self.param('RelativeVoltageDiff') / 100
        passed = bool(absPassed and relPassed)
        values.update(
            {
                CHUNK_AVERAGES: avgs,
                Keys.FULL_AVERAGE: full,
                FULL_AVERAGE_ABS_DIFF: absDiff,
                FULL_AVERAGE_REL_DIFF: relDiff,
                FULL_AVERAGE_QC: passed,
            }
        )
        return passed

    def postSet(self) -> SetResult:
        recs = [self.notebook.sweep(sw) for sw in self.setRecord.sweeps]
        passed = sum(bool(r.values.get(Keys.SWEEP_QC)) for r in recs) >= REQUIRED_PASSES
        values = {Keys.SET_QC: passed}
        amp = AmplifierSettings()
        if passed:
            full = recs[-1].values[Keys.FULL_AVERAGE]
            values[Keys.FULL_AVERAGE] = full
            amp = AmplifierSettings(autobiasEnabled=True, autobiasTarget=full)
        elif self._spikeFailTarget is not None:
            amp = AmplifierSettings(autobiasEnabled=True, autobiasTarget=self._spikeFailTarget)
        self.setRecord.values.update(values)
        return SetResult(
            passed=passed,
            nextStimset=self.stimsetParam('NextStimSetName') if passed else None,
            nextIndexingEnd=self.stimsetParam('NextIndexingEndStimSetName') if passed else None,
            runAmplifier=amp,
            values=values,
        )
