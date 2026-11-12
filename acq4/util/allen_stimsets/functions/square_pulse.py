"""PSQ_SquarePulse (SP): coarse-to-fine search for the smallest spiking DAScale."""

from __future__ import annotations

from .. import qc
from ..core import SetConfig, SetResult, SweepConfig, SweepData, SweepDecision
from ..notebook import ASYNC_QC_SKIPPED, Keys
from ._patchseq import (
    DASCALE_ZERO_TOL,
    STEP_SIZE,
    PatchSeqIC,
)
from .base import register

SPIKE_WITH_DASCALE_ZERO = 'SpikeWithDAScaleZero'  # bool, sweep spiked at DAScale 0

STEP_UP_LARGE = 100.0  # pA, PSQ_SP_INIT_AMP_p100
STEP_DOWN = -50.0  # pA, PSQ_SP_INIT_AMP_m50
STEP_UP_SMALL = 10.0  # pA, PSQ_SP_INIT_AMP_p10
MAX_DASCALE_ZERO = 3  # PSQ_SP_MAX_DASCALE_ZERO


@register
class SquarePulse(PatchSeqIC):
    """Step DAScale +100 pA until a spike, -50 pA until none, then +10 pA until a spike.

    Per sweep it writes ``Keys.SPIKE_DETECT``, ``STEP_SIZE``, ``Keys.SAMPLING_QC``, ``Keys.ASYNC_QC``,
    ``Keys.DASCALE_OUT_OF_RANGE``, ``Keys.SWEEP_QC`` and, on the first spike of the +10 pA ladder,
    ``Keys.FINAL_SCALE`` (pA, read by Rheobase). A failed set aborts the chain.
    """

    miesName = 'PSQ_SquarePulse'
    analysisType = 'SP'

    def preSet(self) -> SetConfig:
        dt = self.sampleInterval()
        self.step = STEP_UP_LARGE
        self.nextDascale = STEP_UP_LARGE
        self.zeroSpikes = 0
        self.passes = 0
        return SetConfig('IC', dt, insertTestPulse=False, testPulseDuringIti=False)

    def preSweep(self, setSweepIndex, layout) -> SweepConfig:
        self.sweepIndex = setSweepIndex
        self.dascale = self.nextDascale
        return SweepConfig(self.dascale)

    def postSweep(self, data: SweepData) -> SweepDecision:
        values = self.sweepValues(data)
        onset = qc.totalOnsetDelay(data.epochs)
        spike = qc.searchForSpikes(self.withPlannedCommand(data), 'SP', onset, qc.SPIKE_LEVEL)
        sampling = self.samplingPassed(data)
        values.update(
            {
                Keys.SPIKE_DETECT: spike.detected,
                Keys.SAMPLING_QC: sampling,
                Keys.ASYNC_QC: ASYNC_QC_SKIPPED,
            }
        )

        x = self.dascale
        passed = False
        newScale = None
        action = 'continue'
        if spike.detected:
            if abs(x) < DASCALE_ZERO_TOL:
                values[SPIKE_WITH_DASCALE_ZERO] = True
                self.zeroSpikes += 1
                if self.zeroSpikes == MAX_DASCALE_ZERO:
                    action = 'abort'
            elif self.step == STEP_DOWN:
                newScale = x + self.step
            elif self.step == STEP_UP_SMALL:
                values[Keys.FINAL_SCALE] = x
                passed = sampling
                if passed:
                    action = 'endSetPassed'
            else:
                self.step = STEP_DOWN
                newScale = x + self.step
        else:
            if self.step == STEP_DOWN:
                self.step = STEP_UP_SMALL
            newScale = x + self.step

        oor = None if newScale is None else self.outOfRange(newScale)
        if newScale is not None and not oor:
            self.nextDascale = newScale
        if oor:
            passed = False
            action = 'abort'
        if not sampling:
            action = 'abort'
        if action == 'continue' and self.isLastSweep():
            action = 'abort'  # no sweep left: the set fails, which aborts the chain
        values.update({STEP_SIZE: self.step, Keys.SWEEP_QC: passed})
        if oor is not None:
            values[Keys.DASCALE_OUT_OF_RANGE] = oor
        self.passes += passed
        return SweepDecision(
            passed, action, reason=f"spike {int(spike.detected)}, step {self.step:g} pA"
        )

    def postSet(self) -> SetResult:
        passed = self.passes >= 1
        self.setRecord.values[Keys.SET_QC] = passed
        return SetResult(passed)
