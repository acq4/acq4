"""Helpers shared by the current-clamp patch-seq functions SP, RB, RA and CR.

Notebook value names below are written in MIES units (ms, pA, mV, MOhm); names other functions
read are in ``notebook.Keys``.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any, Optional

import numpy as np

from .. import qc
from ..core import MIN_SAMPLE_INTERVAL, AbortSet, EpochTable, SweepData
from ..notebook import Keys, SetRecord
from .base import AnalysisFunction

STEP_SIZE = 'StepSize'  # pA; SP: step after this sweep's update, RB: this sweep's step
INITIAL_SCALE = 'InitialScale'  # pA, set value (RB, CR)
SAMPLING_QC = 'SamplingQC'  # bool
ASYNC_QC = 'AsyncQC'  # ASYNC_QC_SKIPPED: async alarm QC is not ported and always passes
DASCALE_OUT_OF_RANGE = 'DAScaleOutOfRange'  # bool, the next DAScale failed the limit check
SPIKE_POSITIONS = 'SpikePositions'  # list of ms on the sweep axis (RA)

ASYNC_QC_SKIPPED = 'skipped'
SAMPLING_MULTIPLIERS = (1, 2, 4, 8, 16, 32, 64)
DAC_STEPS = 32768  # 16-bit DAC: steps from 0 to full scale
DASCALE_ZERO_TOL = 1e-2  # pA; MIES CheckIfSmall(DAScale, tol=1e-14 A)


def isClose(a: float, b: float, tol: float = 1e-8) -> bool:
    """MIES ``CheckIfClose`` (relative tolerance against both values; 0 only equals 0)."""
    if a == b:
        return True
    diff = abs(a - b)
    return (b != 0 and diff / abs(b) <= tol) and (a != 0 and diff / abs(a) <= tol)


def lastSetValue(setRecord: SetRecord, notebook, key: str) -> Any:
    """Return *key* from the set's values, else from its newest sweep with it; None if absent."""
    if key in setRecord.values:
        return setRecord.values[key]
    for sweep in reversed(setRecord.sweeps):
        values = notebook.sweep(sweep).values
        if key in values:
            return values[key]
    return None


class PatchSeqIC(AnalysisFunction):
    """Base for SP, RB, RA, CR: sampling, DAScale limit check, planned command, notebook access.

    Subclasses set ``self.sweepIndex`` and ``self.dascale`` (pA) in ``preSweep``.
    """

    clampMode = 'IC'
    defaultSamplingFrequency = 50.0  # kHz

    sweepIndex: int = 0
    dascale: float = 0.0

    def requiredParam(self, name: str) -> Any:
        """Return parameter *name*; raises AbortSet when absent."""
        try:
            return self.param(name)
        except KeyError as exc:
            raise AbortSet(str(exc)) from None

    def sampleInterval(self) -> float:
        """Return ms per sample from ``SamplingMultiplier``; raises AbortSet when invalid."""
        mult = self.requiredParam('SamplingMultiplier')
        if mult not in SAMPLING_MULTIPLIERS:
            raise AbortSet(
                f"{self.miesName}: SamplingMultiplier {mult} not in {SAMPLING_MULTIPLIERS}"
            )
        self.requiredParam('AsyncQCChannels')
        return MIN_SAMPLE_INTERVAL * mult

    def checkStimsetLength(self, minLength: float) -> None:
        """Raise AbortSet when the stimset is shorter than *minLength* ms."""
        length = len(self.stimset.gridWave(0)) * MIN_SAMPLE_INTERVAL
        if length < minLength:
            raise AbortSet(f"{self.stimset.name} is {length:g} ms, needs at least {minLength:g} ms")

    def requireAutobiasTarget(self) -> float:
        """Return the autobias target (mV); raises AbortSet when it is unset or 0."""
        target = self.context.autobiasTarget()
        if target is None or not math.isfinite(target) or abs(target) < 1e-8:
            raise AbortSet(f"{self.miesName}: autobias target is {target}")
        return target

    def samplingPassed(self, data: SweepData) -> bool:
        freq = self.param('SamplingFrequency', self.defaultSamplingFrequency)
        return qc.samplingQC(data.sampleInterval, freq)

    def isLastSweep(self) -> bool:
        return self.sweepIndex >= self.stimset.numSweeps - 1

    def outOfRange(self, dascale: float) -> Optional[bool]:
        """Return whether *dascale* (pA) fails the limit check for the next stimset sweep.

        Returns None (not checked) on the stimset's last sweep, as MIES does.
        """
        if self.isLastSweep():
            return None
        lo, hi = self.stimset.extremes(self.sweepIndex + 1)
        return qc.dascaleOutOfRange(
            dascale, lo, hi, self.context.commandLimit, self.context.holding()
        )

    def plannedCommand(
        self, epochs: EpochTable, length: int, dt: float, zeroedAt=None
    ) -> np.ndarray:
        """Return the stimset part of the command (pA): wave x DAScale from ``E0``, 0 elsewhere.

        Values are rounded to the 16-bit DAC step (``commandLimit / DAC_STEPS``), as the DA output
        that MIES measures pulse edges on. Samples from *zeroedAt* (ms) on are 0. The inserted test
        pulse is not included.
        """
        key = (self.sweepIndex, dt, self.dascale, length, zeroedAt)
        cached = getattr(self, '_plannedCache', None)
        if cached is not None and cached[0] == key:
            return cached[1]
        wave = self.stimset.wave(self.sweepIndex, dt).astype(np.float64) * self.dascale
        out = np.zeros(length)
        start = qc.truncPoints(qc.totalOnsetDelay(epochs), dt)
        stop = min(length, start + len(wave))
        lsb = self.context.commandLimit / DAC_STEPS
        out[start:stop] = np.round(wave[: stop - start] / lsb) * lsb
        if zeroedAt is not None:
            out[min(length, qc.truncPoints(zeroedAt, dt)) :] = 0.0
        self._plannedCache = (key, out)
        return out

    def withPlannedCommand(self, data: SweepData) -> SweepData:
        """Return *data* with ``command`` set to ``plannedCommand``, zeroed from commandZeroedAt."""
        cmd = self.plannedCommand(
            data.epochs, len(data.data), data.sampleInterval, data.commandZeroedAt
        )
        return dataclasses.replace(data, command=cmd)

    def baselineQC(self) -> qc.BaselineQC:
        """Return a BaselineQC for this sweep with the Baseline* parameters (defaults from qc)."""
        return qc.BaselineQC(
            self.analysisType,
            rmsShortThreshold=self.param('BaselineRMSShortThreshold', qc.RMS_SHORT_THRESHOLD),
            rmsLongThreshold=self.param('BaselineRMSLongThreshold', qc.RMS_LONG_THRESHOLD),
            targetVThreshold=self.param('BaselineTargetVThreshold', qc.TARGETV_THRESHOLD),
        )

    def sweepValues(self, data: SweepData) -> dict:
        """Return the notebook values of the sweep being post-processed (added by the runner)."""
        return self.notebook.sweep(data.sweep).values

    def lastPassingSet(self, analysisType: str, where=None) -> Optional[SetRecord]:
        """Return the newest set of *analysisType* with a true ``SET_QC`` that matches *where*."""
        return self.notebook.lastSet(
            analysisType,
            where=lambda s: bool(lastSetValue(s, self.notebook, Keys.SET_QC))
            and (where is None or where(s)),
        )


def rampEdges(command: np.ndarray, dt: float, onset: float) -> tuple[float, float]:
    """Return the first and last crossing of 0 (ms) in *command* after *onset*.

    The span ``last - first - dt`` is ``qc.pulseDuration(..., 'ramp')``. Raises ValueError when no
    crossing exists.
    """
    p0 = qc.igorRound(onset / dt)
    seg = np.asarray(command[p0:], dtype=float)
    fwd = qc.findLevels(seg, 0.0)
    bwd = qc.findLevels(seg[::-1], 0.0)
    if len(fwd) == 0 or len(bwd) == 0:
        raise ValueError("could not find the pulse edges")
    return float((p0 + fwd[0]) * dt), float((p0 + len(seg) - 1 - bwd[0]) * dt)
