"""Shared parts of the voltage-clamp patch-seq QC functions (PB, SE, AR).

Units follow MIES: ms, pA, mV, MOhm. Notebook keys written by every function here:

- ``Keys.BASELINE_QC``, ``Keys.SWEEP_QC`` (sweep), ``Keys.SET_QC`` (set): bool.
- ``Chk<k>RMSShort``, ``Chk<k>RMSLong``, ``Chk<k>LeakCurrent``: pA, NaN when not computed.
- ``Chk<k>RMSShortQC``, ``Chk<k>RMSLongQC``, ``Chk<k>LeakCurrentQC``: labnotebook encoding
  (1 pass, 0 fail, -1 not applicable, NaN not reached); ``Chk<k>QC``: bool.
- ``RMSShortThreshold``, ``RMSLongThreshold``: pA.
- ``SamplingQC``: bool. ``AsyncQC``: ``'skipped'`` (async alarm QC is not run and counts as passed).
"""

from __future__ import annotations

import math
from typing import Any, Optional, Sequence

from .. import qc
from ..core import AbortSet, AmplifierSettings, SetConfig, SetResult, SweepData, SweepDecision
from ..notebook import ASYNC_QC_SKIPPED, Keys
from .base import NO_STIMSET, AnalysisFunction

NUM_ASYNC_CHANNELS = 8
DASCALE = 1.0  # MIES uses the panel DAScale; the production VC stimsets run at 1

RMS_SHORT_THRESHOLD = 'RMSShortThreshold'
RMS_LONG_THRESHOLD = 'RMSLongThreshold'


def chunkKey(k: int, name: str) -> str:
    """Return the notebook key ``Chk<k><name>``."""
    return f'Chk{k}{name}'


def belowLimit(value: float, limit: float) -> bool:
    """Return ``0 < value < limit``; with an infinite *limit* any value below it passes, NaN fails."""
    if not value < limit:
        return False
    return math.isinf(limit) or value > 0


class VCQCFunction(AnalysisFunction):
    """Base of PB, SE and AR: parameter checks, set config, baseline records, bookkeeping, postSet.

    Subclasses set ``rmsThresholdMax`` and ``setValueKeys`` (sweep keys copied into the set values).
    """

    clampMode = 'VC'
    rmsThresholdMax = 20.0
    setValueKeys: Sequence[str] = ()

    # ---- parameters

    def checkParams(self, extra: Sequence[str] = ()) -> None:
        """Validate the parameters common to PB/SE/AR (PSQ_CheckParamCommon); raise AbortSet.

        *extra* names the optional common parameters this function also has: 'BaselineChunkLength',
        'MaxLeakCurrent', 'NumberOfTestpulses' (the latter two are required when listed). Next stimset
        names are not looked up; the chain runner resolves them.
        """
        channels = self.param('AsyncQCChannels')
        if not channels or any(
            not (float(c).is_integer() and 0 <= c < NUM_ASYNC_CHANNELS) for c in channels
        ):
            raise AbortSet(f"{self.miesName}: invalid AsyncQCChannels {channels!r}")
        for name in ('BaselineRMSShortThreshold', 'BaselineRMSLongThreshold'):
            v = self.param(name, None)
            if v is not None and not (0 < v <= self.rmsThresholdMax):
                raise AbortSet(f"{self.miesName}: invalid {name} {v}")
        if 'BaselineChunkLength' in extra:
            v = self.param('BaselineChunkLength', None)
            if v is not None and not v > 0:
                raise AbortSet(f"{self.miesName}: invalid BaselineChunkLength {v}")
        if 'MaxLeakCurrent' in extra:
            v = self.param('MaxLeakCurrent')
            if not (0 < v <= 1000):
                raise AbortSet(f"{self.miesName}: invalid MaxLeakCurrent {v}")
        if 'NumberOfTestpulses' in extra:
            v = self.param('NumberOfTestpulses')
            if not (0 < v <= 100 and float(v).is_integer()):
                raise AbortSet(f"{self.miesName}: invalid NumberOfTestpulses {v}")
        v = self.param('NumberOfFailedSweeps')
        if not (math.isfinite(v) and float(v).is_integer() and 0 < v <= self.stimset.numSweeps):
            raise AbortSet(
                f"{self.miesName}: NumberOfFailedSweeps {v} must be an integer in "
                f"[1, {self.stimset.numSweeps}] (sweeps in the stimset)"
            )
        v = self.param('SamplingFrequency', None)
        if v is not None and not (0 <= v <= 1000):
            raise AbortSet(f"{self.miesName}: invalid SamplingFrequency {v}")
        self.sampleInterval()
        for name in ('NextStimSetName', 'NextIndexingEndStimSetName'):
            v = self.param(name, NO_STIMSET)
            if not (isinstance(v, str) and v):
                raise AbortSet(f"{self.miesName}: invalid {name} {v!r}")

    def baselineQC(self) -> qc.BaselineQC:
        """Return a fresh ``BaselineQC`` with this function's thresholds."""
        return super().baselineQC(maxLeakCurrent=self.param('MaxLeakCurrent', float('nan')))

    def setConfig(self, amplifier: Optional[AmplifierSettings] = None) -> SetConfig:
        """Return the VC set config: sample interval = MIN_SAMPLE_INTERVAL x SamplingMultiplier.

        *amplifier* changes are restored at set end (auto calibrations are kept).
        """
        return SetConfig(
            clampMode='VC',
            sampleInterval=self.sampleInterval(),
            amplifier=amplifier or AmplifierSettings(),
        )

    # ---- sweep

    def recordBaseline(self, values: dict[str, Any], bl: qc.BaselineQC, passed: bool) -> None:
        """Write the chunk results of *bl*, the thresholds and ``BaselineQC`` into *values*."""
        values[RMS_SHORT_THRESHOLD] = bl.rmsShortThreshold
        values[RMS_LONG_THRESHOLD] = bl.rmsLongThreshold
        for k, r in sorted(bl.results.items()):
            values[chunkKey(k, 'RMSShort')] = r.rmsShort
            values[chunkKey(k, 'RMSLong')] = r.rmsLong
            values[chunkKey(k, 'LeakCurrent')] = r.leakCurrent
            values[chunkKey(k, 'RMSShortQC')] = r.rmsShortPassed
            values[chunkKey(k, 'RMSLongQC')] = r.rmsLongPassed
            values[chunkKey(k, 'LeakCurrentQC')] = r.leakCurrentPassed
            values[chunkKey(k, 'QC')] = r.passed
        values[Keys.BASELINE_QC] = passed

    def finishSweep(self, data: SweepData, values: dict[str, Any], *checks: bool) -> SweepDecision:
        """Run sampling QC, write ``SweepQC`` and return the bookkeeping decision.

        *checks* are the function's own QC results (baseline, resistance); the sweep passes when all of
        them and sampling QC pass.
        """
        sampling = self.samplingPassed(data)
        values[Keys.SAMPLING_QC] = sampling
        values[Keys.ASYNC_QC] = ASYNC_QC_SKIPPED
        passed = bool(sampling and all(checks))
        values[Keys.SWEEP_QC] = passed

        records = self.notebook.sweeps(sci=self.setRecord.sci)
        numPassed = sum(bool(r.values[Keys.SWEEP_QC]) for r in records)
        action = qc.determineSweepQCResults(
            passed,
            sampling,
            sweepsInSet=self.stimset.numSweeps,
            acquiredSweeps=len(records),
            passedSweeps=numPassed,
            requiredPasses=1,
            failsAllowed=self.param('NumberOfFailedSweeps'),
        )
        return SweepDecision(passed, action)

    # ---- set

    def postSet(self) -> SetResult:
        """Set QC = at least one passing sweep; on pass, return NextStimSetName / -IndexingEnd."""
        records = self.notebook.sweeps(sci=self.setRecord.sci)
        passed = sum(bool(r.values[Keys.SWEEP_QC]) for r in records) >= 1
        values: dict[str, Any] = {Keys.SET_QC: passed}
        if records:
            last = records[-1].values
            values.update({k: last[k] for k in self.setValueKeys if k in last})
        self.setRecord.values.update(values)
        return SetResult(
            passed=passed,
            nextStimset=self.stimsetParam('NextStimSetName') if passed else None,
            nextIndexingEnd=self.stimsetParam('NextIndexingEndStimSetName') if passed else None,
            runAmplifier=self.postSetAmplifier(),
            values=values,
        )

    def postSetAmplifier(self) -> AmplifierSettings:
        """Return amplifier changes to apply after the set (run scope); none by default."""
        return AmplifierSettings()


def tpResistance(data: SweepData, names: Sequence[str]) -> Optional[qc.TPResult]:
    """Analyze the average of the TP epochs *names* (SweepFormula ``tp()``); None if not acquired."""
    tps = qc.testPulseEpochsForAnalysis(data.epochs)
    ignore = [i for i, ep in enumerate(tps) if ep.name not in names]
    selected = [ep for ep in tps if ep.name in names]
    if not selected or not all(qc.acquiredUntil(data, ep.end) for ep in selected):
        return None
    return qc.testPulseResistance(data, ignore)
