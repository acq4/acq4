"""PSQ_Rheobase (RB): find the DAScale where spiking flips, starting from the SquarePulse result."""

from __future__ import annotations

import math
from typing import Optional

from .. import qc
from ..core import (
    AbortSet,
    AmplifierSettings,
    SetConfig,
    SetResult,
    SweepConfig,
    SweepData,
    SweepDecision,
)
from ..notebook import Keys
from ._patchseq import (
    ASYNC_QC,
    ASYNC_QC_SKIPPED,
    DASCALE_OUT_OF_RANGE,
    DASCALE_ZERO_TOL,
    INITIAL_SCALE,
    SAMPLING_QC,
    STEP_SIZE,
    PatchSeqIC,
    isClose,
)
from .base import register
from .dascale import AP_CROSSINGS, apCrossings

DASCALE_EXCEEDED = 'DAScaleExceeded'  # bool, set: DAScale left the +-60 pA band around the start
LIMITED_RESOLUTION = 'LimitedResolution'  # bool, set: the next DAScale would be 0 at 2 pA steps

MAX_DASCALE_DIFF = 60.0  # pA, PSQ_RB_MAX_DASCALE_DIFF
SMALL_BORDER = 50.0  # pA, PSQ_RB_DASCALE_SMALL_BORDER
STEP_LARGE = 10.0  # pA
STEP_SMALL = 2.0  # pA
MIN_STIMSET_LENGTH = 1500.0  # ms


@register
class Rheobase(PatchSeqIC):
    """Step DAScale by 10 pA (2 pA at or below 50 pA) until spiking flips between two sweeps.

    Starts at the newest SquarePulse ``Keys.FINAL_SCALE``. Sweeps failing baseline QC repeat the
    DAScale. Per sweep it writes ``STEP_SIZE``, ``SAMPLING_QC``, ``ASYNC_QC``, ``Keys.BASELINE_QC``,
    ``Keys.PULSE_DURATION`` (ms), ``dascale.AP_CROSSINGS`` and, for sweeps passing baseline QC,
    ``Keys.SPIKE_DETECT`` and ``DASCALE_OUT_OF_RANGE``. Set values: ``INITIAL_SCALE``,
    ``Keys.PULSE_DURATION``, ``Keys.SET_QC``, ``DASCALE_EXCEEDED``, ``LIMITED_RESOLUTION``.
    ``SweepDecision.sweepPassed`` is baseline and sampling QC (MIES writes no Sweep QC).
    """

    miesName = 'PSQ_Rheobase'
    analysisType = 'RB'

    def preSet(self) -> SetConfig:
        dt = self.sampleInterval()
        self.checkStimsetLength(MIN_STIMSET_LENGTH)
        rec = self.notebook.lastSweepWith(Keys.FINAL_SCALE, 'SP')
        final = None if rec is None else rec.values[Keys.FINAL_SCALE]
        if final is None or not math.isfinite(final) or abs(final) < DASCALE_ZERO_TOL:
            raise AbortSet(f"{self.miesName}: no SquarePulse final DAScale (found {final})")
        self.initialScale = final
        self.nextDascale = final
        self.stepFuture = STEP_LARGE
        self.stepSizes: list[float] = []
        self.spikes: list[Optional[bool]] = []
        self.setPassed: Optional[bool] = None
        self.exceeded = False
        self.limitedResolution = False
        self.setRecord.values[INITIAL_SCALE] = final
        return SetConfig('IC', dt, runAmplifier=AmplifierSettings(autobiasEnabled=True))

    def preSweep(self, setSweepIndex, layout) -> SweepConfig:
        self.requireAutobiasTarget()
        self.sweepIndex = setSweepIndex
        self.dascale = self.nextDascale
        self.bl = self.baselineQC()
        self.blPassed = False
        self.pulseDur: Optional[float] = None
        return SweepConfig(self.dascale)

    def pulseDuration(self, data: SweepData) -> float:
        if self.pulseDur is None:
            planned = self.withPlannedCommand(data)
            self.pulseDur = qc.pulseDuration(
                planned.command, data.sampleInterval, qc.totalOnsetDelay(data.epochs), 'square'
            )
        return self.pulseDur

    def midSweep(self, data: SweepData):
        if self.blPassed:
            return None
        self.bl.targetV = self.context.autobiasTarget()
        status = self.bl.evaluate(data, qc.baselineChunks('RB', data, self.pulseDuration(data)))
        self.blPassed = status.passed
        return qc.toMidSweepAction(status.midSweepCode, 'RB', data)

    def postSweep(self, data: SweepData) -> SweepDecision:
        values = self.sweepValues(data)
        step = self.stepFuture
        self.stepSizes.append(step)
        sampling = self.samplingPassed(data)
        dur = self.pulseDuration(data)
        values.update(
            {
                STEP_SIZE: step,
                SAMPLING_QC: sampling,
                ASYNC_QC: ASYNC_QC_SKIPPED,
                Keys.BASELINE_QC: self.blPassed,
                Keys.PULSE_DURATION: dur,
                AP_CROSSINGS: apCrossings(data),
            }
        )
        self.setRecord.values[Keys.PULSE_DURATION] = dur
        usable = self.blPassed and sampling
        if not sampling:
            self.spikes.append(None)
            return self._end(False, False, 'endSetFailed', 'sampling QC failed')
        if not self.blPassed:
            self.spikes.append(None)
            return self._continue(usable, 'baseline QC failed, DAScale repeated')

        onset = qc.totalOnsetDelay(data.epochs)
        spike = qc.searchForSpikes(self.withPlannedCommand(data), 'RB', onset, qc.SPIKE_LEVEL)
        cur = spike.detected
        values[Keys.SPIKE_DETECT] = cur
        self.spikes.append(cur)
        x = self.dascale

        if len(self.spikes) >= 2:
            prev = self.spikes[-2]
            if prev is not None and cur != prev and self.stepSizes[-1] == self.stepSizes[-2]:
                if x <= SMALL_BORDER and self.stepFuture == STEP_LARGE:
                    self.stepFuture = STEP_SMALL
                else:
                    return self._end(usable, True, 'endSetPassed', 'spiking flipped')

        step = self.stepFuture
        x = x - step if cur else x + step
        if abs(x) < DASCALE_ZERO_TOL and cur:
            if step == STEP_SMALL:
                self.limitedResolution = True
                return self._end(usable, False, 'abort', 'next DAScale would be 0 pA')
            self.stepFuture = STEP_SMALL
            x = STEP_SMALL
        diff = abs(x - self.initialScale)
        if diff > MAX_DASCALE_DIFF or isClose(diff, MAX_DASCALE_DIFF):
            self.exceeded = True
            return self._end(usable, False, 'abort', f"DAScale {x:g} pA exceeds the allowed range")
        oor = self.outOfRange(x)
        if oor is not None:
            values[DASCALE_OUT_OF_RANGE] = oor
        if oor:
            return self._end(usable, False, 'abort', f"DAScale {x:g} pA out of range")
        self.nextDascale = x
        return self._continue(usable, f"spike {int(cur)}, next {x:g} pA")

    def _continue(self, usable: bool, reason: str) -> SweepDecision:
        if self.isLastSweep():
            return self._end(usable, False, 'abort', f"{reason}; no sweep left")
        return SweepDecision(usable, 'continue', reason=reason)

    def _end(self, usable: bool, setPassed: bool, action: str, reason: str) -> SweepDecision:
        self.setPassed = setPassed
        return SweepDecision(usable, action, reason=reason)

    def postSet(self) -> SetResult:
        passed = bool(self.setPassed)
        self.setRecord.values.update(
            {
                Keys.SET_QC: passed,
                DASCALE_EXCEEDED: self.exceeded,
                LIMITED_RESOLUTION: self.limitedResolution,
            }
        )
        return SetResult(passed)
