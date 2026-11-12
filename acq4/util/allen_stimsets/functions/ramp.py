"""PSQ_Ramp (RA): current ramp at fixed DAScale, stimulation cut after NumberOfSpikes spikes."""

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
    ZeroCommand,
)
from ..notebook import ASYNC_QC_SKIPPED, Keys
from ._patchseq import (
    PatchSeqIC,
)
from .base import register

DASCALE = 1.0  # pA, PSQ_RA_DASCALE_DEFAULT
NUM_SWEEPS_PASS = 3  # PSQ_RA_NUM_SWEEPS_PASS
PULSE_START = (
    qc.BL_CHUNK_LENGTH
)  # ms after the stimset start; MIES assumes a 500 ms pre-pulse baseline
MIN_STIMSET_LENGTH = 1500.0  # ms


@register
class Ramp(PatchSeqIC):
    """Play the ramp at 1 pA DAScale; zero the command once NumberOfSpikes spikes are found.

    ``midSweep`` returns ``ZeroCommand`` once per sweep; afterwards the pulse ends at
    ``SweepData.commandZeroedAt`` for the post-pulse baseline chunks. Sweep QC is baseline, sampling
    and async QC; spiking does not count. Per sweep it writes ``Keys.SPIKE_DETECT`` (once decided),
    ``Keys.SPIKE_POSITIONS`` (ms), ``Keys.BASELINE_QC``, ``Keys.PULSE_DURATION`` (ms, after zeroing),
    ``Keys.SAMPLING_QC``, ``Keys.ASYNC_QC`` and ``Keys.SWEEP_QC``.
    """

    miesName = 'PSQ_Ramp'
    analysisType = 'RA'

    def preSet(self) -> SetConfig:
        dt = self.sampleInterval()
        self.numberOfSpikes = self.param('NumberOfSpikes')
        if not self.numberOfSpikes > 0:
            raise AbortSet(f"{self.miesName}: NumberOfSpikes must be > 0, is {self.numberOfSpikes}")
        self.required = int(self.param('NumberOfPassingSweeps', NUM_SWEEPS_PASS))
        if not 1 <= self.required <= self.stimset.numSweeps:
            raise AbortSet(
                f"{self.miesName}: NumberOfPassingSweeps {self.required} "
                f"needs 1..{self.stimset.numSweeps}"
            )
        self.checkStimsetLength(MIN_STIMSET_LENGTH)
        self.passes = 0
        self.acquired = 0
        return SetConfig('IC', dt, runAmplifier=AmplifierSettings(autobiasEnabled=True))

    def preSweep(self, setSweepIndex, layout) -> SweepConfig:
        self.requireAutobiasTarget()
        self.sweepIndex = setSweepIndex
        self.dascale = DASCALE
        self.bl = self.baselineQC()
        self.blPassed = False
        self.spikeDetect: Optional[bool] = None
        self.spikePositions: list[float] = []
        self.zeroRequested = False
        self.pulseDur: Optional[tuple] = None  # (commandZeroedAt, duration)
        return SweepConfig(self.dascale)

    def pulseDuration(self, data: SweepData) -> float:
        """Return the ramp duration (ms); it ends at ``commandZeroedAt`` once that is set."""
        if self.pulseDur is None or self.pulseDur[0] != data.commandZeroedAt:
            planned = self.withPlannedCommand(data)
            dur = qc.pulseDuration(
                planned.command, data.sampleInterval, qc.totalOnsetDelay(data.epochs), 'ramp'
            )
            self.pulseDur = (data.commandZeroedAt, dur)
        return self.pulseDur[1]

    def midSweep(self, data: SweepData):
        if self.spikeDetect is not None and self.blPassed:
            return None
        dt = data.sampleInterval
        onset = qc.totalOnsetDelay(data.epochs)
        fifoInStimset = (data.numValid - 1) * dt - onset
        dur = self.pulseDuration(data)
        zero = None
        if self.spikeDetect is None and fifoInStimset >= PULSE_START:
            res = qc.searchForSpikes(
                self.withPlannedCommand(data),
                'RA',
                onset,
                qc.SPIKE_LEVEL,
                numberOfSpikesReq=self.numberOfSpikes,
            )
            if res.detected:
                self.spikeDetect = True
                self.spikePositions = [float(p) for p in res.positions]
                if not self.zeroRequested and data.commandZeroedAt is None:
                    self.zeroRequested = True
                    zero = ZeroCommand(f"{res.count} spikes found")
            elif fifoInStimset > PULSE_START + dur:
                self.spikeDetect = False
        if not self.blPassed:
            self.bl.targetV = self.context.autobiasTarget()
            status = self.bl.evaluate(data, qc.baselineChunks('RA', data, self.pulseDuration(data)))
            if status.decided:
                self.blPassed = status.passed
                action = qc.toMidSweepAction(status.midSweepCode, 'RA', data)
                if action is not None:
                    return action
        return zero

    def postSweep(self, data: SweepData) -> SweepDecision:
        values = self.sweepValues(data)
        sampling = self.samplingPassed(data)
        passed = self.blPassed and sampling
        if self.spikeDetect is not None:
            values[Keys.SPIKE_DETECT] = self.spikeDetect
        if self.spikePositions:
            values[Keys.SPIKE_POSITIONS] = self.spikePositions
        values.update(
            {
                Keys.BASELINE_QC: self.blPassed,
                Keys.PULSE_DURATION: self.pulseDuration(data),
                Keys.SAMPLING_QC: sampling,
                Keys.ASYNC_QC: ASYNC_QC_SKIPPED,
                Keys.SWEEP_QC: passed,
            }
        )
        self.acquired += 1
        self.passes += passed
        action = qc.determineSweepQCResults(
            passed,
            sampling,
            self.stimset.numSweeps,
            self.acquired,
            self.passes,
            self.required,
            math.inf,
        )
        return SweepDecision(passed, action, reason=f"{self.passes}/{self.required} passing sweeps")

    def postSet(self) -> SetResult:
        passed = self.passes >= self.required
        self.setRecord.values[Keys.SET_QC] = passed
        return SetResult(passed)
