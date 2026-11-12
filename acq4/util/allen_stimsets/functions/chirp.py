"""PSQ_Chirp (CR): sine chirp whose DAScale is tuned until the response stays within bounds."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .. import qc
from ..core import (
    AbortSet,
    AmplifierSettings,
    Epoch,
    EarlyStop,
    SetConfig,
    SetResult,
    SweepConfig,
    SweepData,
    SweepDecision,
)
from ..notebook import ASYNC_QC_SKIPPED, Keys
from ._patchseq import (
    INITIAL_SCALE,
    PatchSeqIC,
    lastSetValue,
    rampEdges,
)
from .base import register

# notebook values
RESISTANCE = 'InputResistance'  # MOhm, set: DA Sub resistance the initial DAScale comes from
SPIKE_CHECK = 'SpikeCheck'  # bool, set
STIMSET_QC = 'StimsetQC'  # bool: the stimset has the requested chirp cycles
SPIKE_PASS = 'SpikeQC'  # bool: no spike during the chirp
INSIDE_BOUNDS = 'InsideBounds'  # bool
BOUNDS_ACTION = 'BoundsAction'  # str: one of the BOUNDS_* actions
BOUNDS_STATE = 'BoundsState'  # str: upper + lower state, e.g. '__BA'
BOUNDS_LOWER = 'BoundsLower'  # mV, minimum over the cycle window
BOUNDS_UPPER = 'BoundsUpper'  # mV, maximum over the cycle window

BOUNDS_PASS = 'pass'
BOUNDS_INCREASE = 'increase'
BOUNDS_DECREASE = 'decrease'
BOUNDS_RERUN = 'rerun'

# MIES PSQ_CR_* bounds action codes, for comparison with the labnotebook
MIES_BOUNDS_ACTION = {BOUNDS_PASS: 1, BOUNDS_DECREASE: 2, BOUNDS_INCREASE: 4, BOUNDS_RERUN: 8}

MODES = ('Symmetric', 'Depolarized', 'Hyperpolarized')
NUM_SWEEPS_PASS = 3  # PSQ_CR_NUM_SWEEPS_PASS
DEFAULT_LPF = 10e3  # Hz, PSQ_CR_DEFAULT_LPF
MIN_STIMSET_LENGTH = 1500.0  # ms
BOUND_RANGE = (1.0, 100.0)  # mV, PSQ_CR_LIMIT_BAND_LOW/HIGH
CYCLE_EPOCH = 'E1_TG_C{}'
MIN_CHUNKS = 3  # baseline chunks MIES requires (pre-pulse + 2 post-pulse)

_ACTIONS = {
    'BABA': BOUNDS_PASS,
    'AABA': BOUNDS_DECREASE,
    'BABB': BOUNDS_DECREASE,
    'AABB': BOUNDS_DECREASE,
    'BBBA': BOUNDS_INCREASE,
    'BAAA': BOUNDS_INCREASE,
    'BBAA': BOUNDS_INCREASE,
    'AAAA': BOUNDS_RERUN,
    'BBBB': BOUNDS_RERUN,
    '__BA': BOUNDS_PASS,
    '__AA': BOUNDS_INCREASE,
    '__BB': BOUNDS_DECREASE,
    'BA__': BOUNDS_PASS,
    'AA__': BOUNDS_DECREASE,
    'BB__': BOUNDS_INCREASE,
}


def boundsState(baseline: float, minimum: float, maximum: float, value: float) -> tuple[str, float]:
    """Return (state, centerFactor) of *value* (PSQ_CR_DetermineBoundsState).

    State: 'AA' at or above *maximum*, 'BB' at or below *minimum*, else 'BA'.

    All values in mV; the factor scales ``value - baseline`` onto the band centre (inf/nan when
    *value* equals *baseline*).
    """
    if not minimum < maximum:
        raise ValueError(f"bounds {minimum} .. {maximum} out of order")
    lo, hi, v = minimum - baseline, maximum - baseline, value - baseline
    center = lo + (hi - lo) / 2
    with np.errstate(divide='ignore', invalid='ignore'):
        fac = float(np.float64(center) / np.float64(v))
    if v >= hi:
        return 'AA', fac
    if v <= lo:
        return 'BB', fac
    return 'BA', fac


@dataclass(frozen=True)
class BoundsResult:
    """Outcome of one bounds evaluation; ``factor`` (DAScale multiplier) is NaN unless rescaling."""

    action: str
    factor: float
    state: str
    lower: float  # mV
    upper: float  # mV


def determineBoundsAction(
    lower: float, upper: float, baseline: float, inner: float, outer: float, mode: str
) -> BoundsResult:
    """Classify the response extremes (mV) against the bands (PSQ_CR_DetermineBoundsAction).

    Bands are ``baseline +- [inner, outer]`` mV; *mode* is one of ``MODES``. A non-finite or zero
    factor turns increase/decrease into rerun.
    """
    upperState, upperFac = boundsState(baseline, baseline + inner, baseline + outer, upper)
    lowerState, lowerFac = boundsState(baseline, baseline - outer, baseline - inner, lower)
    if mode == 'Hyperpolarized':
        upperState = '__'
    elif mode == 'Depolarized':
        lowerState = '__'
    state = upperState + lowerState
    action = _ACTIONS[state]
    factor = math.nan
    if action in (BOUNDS_INCREASE, BOUNDS_DECREASE):
        factor = {
            'Symmetric': (lowerFac + upperFac) / 2,
            'Hyperpolarized': lowerFac,
            'Depolarized': upperFac,
        }[mode]
        if not math.isfinite(factor) or factor == 0:
            action, factor = BOUNDS_RERUN, math.nan
    return BoundsResult(action, factor, state, lower, upper)


def setHasPassed(passedAndScales: list[tuple[bool, float]]) -> tuple[bool, int]:
    """Return (3 passing sweeps share a DAScale, largest count at one DAScale).

    MIES PSQ_CR_SetHasPassed.

    *passedAndScales*: (sweep passed, DAScale pA) per sweep of the set; DAScales compare rounded.
    """
    counts: dict[int, int] = {}
    for passed, scale in passedAndScales:
        if passed:
            key = qc.igorRound(scale)
            counts[key] = counts.get(key, 0) + 1
            if counts[key] == NUM_SWEEPS_PASS:
                return True, NUM_SWEEPS_PASS
    return False, max(counts.values(), default=0)


@register
class Chirp(PatchSeqIC):
    """Play the chirp; after NumberOfChirpCycles cycles rescale DAScale for the next sweep.

    The set passes once 3 passing sweeps share a DAScale. A spike in the chirp (SpikeCheck) applies
    DAScaleModifier once and stops the sweep. Set values: ``RESISTANCE``, ``INITIAL_SCALE`` (pA),
    ``SPIKE_CHECK``, ``Keys.SET_QC``. Per sweep: ``STIMSET_QC``, ``SPIKE_PASS``, ``INSIDE_BOUNDS``,
    ``BOUNDS_ACTION``, ``BOUNDS_STATE``, ``BOUNDS_LOWER``, ``BOUNDS_UPPER``, ``Keys.BASELINE_QC``,
    ``Keys.DASCALE_OUT_OF_RANGE``, ``Keys.PULSE_DURATION``, ``Keys.SAMPLING_QC``, ``Keys.ASYNC_QC``,
    ``Keys.SWEEP_QC`` (entries stay absent where MIES leaves them unset).
    """

    miesName = 'PSQ_Chirp'
    analysisType = 'CR'

    def preSet(self) -> SetConfig:
        dt = self.sampleInterval()
        p = self.param
        self.inner = self.param('InnerRelativeBound')
        self.outer = self.param('OuterRelativeBound')
        for name, v in (('InnerRelativeBound', self.inner), ('OuterRelativeBound', self.outer)):
            if not BOUND_RANGE[0] <= v <= BOUND_RANGE[1]:
                raise AbortSet(f"{self.miesName}: {name} {v} mV outside {BOUND_RANGE}")
        if not self.inner < self.outer:
            raise AbortSet(f"{self.miesName}: InnerRelativeBound must be below OuterRelativeBound")
        self.mode = self.param('BoundsEvaluationMode')
        if self.mode not in MODES:
            raise AbortSet(f"{self.miesName}: BoundsEvaluationMode {self.mode!r} not in {MODES}")
        self.failsAllowed = self.param('NumberOfFailedSweeps')
        if not self.failsAllowed <= self.stimset.numSweeps:
            raise AbortSet(f"{self.miesName}: NumberOfFailedSweeps exceeds the stimset's sweeps")
        self.cycles = int(p('NumberOfChirpCycles', 1))
        if self.cycles < 1:
            raise AbortSet(f"{self.miesName}: NumberOfChirpCycles must be > 0")
        if self.stimset.numSweeps < NUM_SWEEPS_PASS:
            raise AbortSet(f"{self.miesName}: stimset needs at least {NUM_SWEEPS_PASS} sweeps")
        self.checkStimsetLength(MIN_STIMSET_LENGTH)

        self.spikeCheck = bool(p('SpikeCheck', 1))
        if self.spikeCheck:
            self.failedLevel = self.param('FailedLevel')
            self.modifier = self.param('DAScaleModifier')
            self.operator = self.param('DAScaleOperator')
            if self.operator not in ('+', '*'):
                raise AbortSet(f"{self.miesName}: DAScaleOperator {self.operator!r} not '+' or '*'")

        sub = self.lastPassingSet(
            'DA', where=lambda s: lastSetValue(s, self.notebook, Keys.OPERATION_MODE) == 'Sub'
        )
        resistance = (
            None if sub is None else lastSetValue(sub, self.notebook, Keys.RESISTANCE_FROM_FIT)
        )
        if resistance is None or not math.isfinite(resistance) or resistance <= 0:
            raise AbortSet(f"{self.miesName}: no passing DAScale Sub set with a fitted resistance")
        initial = (self.outer + self.inner) / 2 / resistance * 1e3  # mV / MOhm -> pA
        self.nextDascale = float(qc.igorRound(initial))
        self.setRecord.values.update(
            {RESISTANCE: resistance, INITIAL_SCALE: initial, SPIKE_CHECK: self.spikeCheck}
        )

        self.sweepResults: list[tuple[bool, float]] = []
        self.abortSet = False

        lpf = p('AmpBesselFilter', DEFAULT_LPF)
        setAmp = AmplifierSettings(besselFilter=lpf)
        runAmp = AmplifierSettings(autobiasEnabled=True, autobiasTarget=p('AutobiasTargetV', None))
        if not p('AmpBesselFilterRestore', 1):
            setAmp, runAmp.besselFilter = AmplifierSettings(), lpf
        return SetConfig(
            'IC',
            dt,
            userOnsetDelay=p('UserOnsetDelay', 0.0),
            amplifier=setAmp,
            runAmplifier=runAmp,
        )

    def preSweep(self, setSweepIndex, layout) -> SweepConfig:
        self.requireAutobiasTarget()
        self.sweepIndex = setSweepIndex
        self.dascale = self.nextDascale
        dt = self.sampleInterval()
        onset = qc.totalOnsetDelay(layout)

        cycles = layout
        if not cycles.has(CYCLE_EPOCH.format(0)):
            # layouts rebuilt from early-stopped recordings lack the cycle sub-epochs
            cycles = self.stimset.epochTable(setSweepIndex, onset, dt)
        first, last = CYCLE_EPOCH.format(0), CYCLE_EPOCH.format(self.cycles - 1)
        self.stimsetQC = cycles.has(first) and cycles.has(last)
        epochs = []
        if self.stimsetQC:
            self.cycleWindow = (cycles.get(first).start, cycles.get(last).end)
            epochs.append(
                Epoch('U_CR_CE', *self.cycleWindow, tags={'Type': 'Chirp cycles evaluation'})
            )

        length = qc.truncPoints(onset, dt) + len(self.stimset.wave(setSweepIndex, dt))
        start, end = rampEdges(self.plannedCommand(layout, length, dt), dt, onset)
        self.spikeWindow = (start, end)
        self.pulseDur = end - start - dt
        self.chunks = None
        if self.spikeCheck:
            epochs.append(Epoch('U_CR_SE', start, end, tags={'Type': 'Chirp spike evaluation'}))

        self.bl = self.baselineQC()
        self.blPassed: Optional[bool] = None
        self.spikePass: Optional[bool] = None
        self.insideBounds: Optional[bool] = None
        self.bounds: Optional[BoundsResult] = None
        self.oor: Optional[bool] = None
        self.modifierApplied = False
        return SweepConfig(self.dascale, userEpochs=epochs)

    def _setNext(self, dascale: float) -> bool:
        """Make *dascale* (pA, rounded) the next sweep's DAScale unless it fails the limit check."""
        new = float(qc.igorRound(dascale))
        self.oor = self.outOfRange(new)
        if not self.oor:
            self.nextDascale = new
        return not self.oor

    def midSweep(self, data: SweepData):
        dt = data.sampleInterval
        fifo = (data.numValid - 1) * dt
        if (
            self.insideBounds is not None
            and self.blPassed is not None
            and (not self.spikeCheck or self.spikePass)
        ):
            return None
        if not self.stimsetQC:
            self.abortSet = True
            return EarlyStop('stimset lacks the requested chirp cycles')
        if self.chunks is None:
            self.chunks = qc.baselineChunks('CR', data, self.pulseDur)
        if len(self.chunks) < MIN_CHUNKS:
            self.abortSet = True
            return EarlyStop(f"{len(self.chunks)} baseline chunks fit, needs {MIN_CHUNKS}")

        if self.spikeCheck and self.spikePass is None:
            start, end = self.spikeWindow
            if fifo > start:
                res = qc.searchForSpikes(data, 'CR', start, self.failedLevel, end, math.inf)
                if res.count > 0:
                    self.spikePass = False
                elif fifo > end:
                    self.spikePass = True

        code = None
        if self.blPassed is None:
            self.bl.targetV = self.context.autobiasTarget()
            status = self.bl.evaluate(data, self.chunks)
            if status.decided:
                self.blPassed = status.passed
                code = status.code

        if self.spikeCheck and self.spikePass is False:
            if not self.modifierApplied:
                self.modifierApplied = True
                op = (
                    self.nextDascale * self.modifier
                    if self.operator == '*'
                    else self.nextDascale + self.modifier
                )
                if not self._setNext(op):
                    self.abortSet = True
            return EarlyStop('spike during the chirp')

        cycleStart, cycleEnd = self.cycleWindow
        if self.blPassed is not False and self.insideBounds is None and fifo >= cycleEnd:
            trace = qc.acquired(data)
            p0, p1 = qc.igorRound(cycleStart / dt), qc.igorRound(cycleEnd / dt)
            seg = trace[p0 : p1 + 1]
            baseline = self.bl.results[0].average
            self.bounds = determineBoundsAction(
                float(np.min(seg)), float(np.max(seg)), baseline, self.inner, self.outer, self.mode
            )
            self.insideBounds = self.bounds.action == BOUNDS_PASS
            if self.bounds.action in (BOUNDS_INCREASE, BOUNDS_DECREASE):
                if not self._setNext(self.nextDascale * self.bounds.factor):
                    self.abortSet = True
                    return EarlyStop('DAScale out of range')

        if self.blPassed:
            return EarlyStop('baseline QC passed')
        if self.blPassed is False:
            return qc.toMidSweepAction(code, 'CR', data)
        if self.insideBounds is False:
            return EarlyStop(f"bounds: {self.bounds.action}")
        return None

    def postSweep(self, data: SweepData) -> SweepDecision:
        values = self.sweepValues(data)
        sampling = self.samplingPassed(data)
        passed = (
            self.blPassed is True
            and self.insideBounds is True
            and sampling
            and self.stimsetQC
            and not self.oor
            and (self.spikePass is True or not self.spikeCheck)
        )
        values.update(
            {
                STIMSET_QC: self.stimsetQC,
                Keys.PULSE_DURATION: self.pulseDur,
                Keys.SAMPLING_QC: sampling,
                Keys.ASYNC_QC: ASYNC_QC_SKIPPED,
                Keys.SWEEP_QC: passed,
            }
        )
        optional = {
            SPIKE_PASS: self.spikePass,
            Keys.BASELINE_QC: self.blPassed,
            INSIDE_BOUNDS: self.insideBounds,
            Keys.DASCALE_OUT_OF_RANGE: self.oor,
        }
        values.update({k: v for k, v in optional.items() if v is not None})
        if self.bounds is not None:
            values.update(
                {
                    BOUNDS_ACTION: self.bounds.action,
                    BOUNDS_STATE: self.bounds.state,
                    BOUNDS_LOWER: self.bounds.lower,
                    BOUNDS_UPPER: self.bounds.upper,
                }
            )

        self.sweepResults.append((passed, self.dascale))
        setPassed, maxOcc = setHasPassed(self.sweepResults)
        acquired = len(self.sweepResults)
        fails = acquired - sum(p for p, _ in self.sweepResults)
        left = self.stimset.numSweeps - acquired
        if setPassed:
            action = 'endSetPassed'
        elif (
            maxOcc + left < NUM_SWEEPS_PASS
            or fails >= self.failsAllowed
            or not sampling
            or self.abortSet
        ):
            action = 'abort'
        else:
            action = 'continue'
        return SweepDecision(passed, action, reason=f"max {maxOcc} passing sweeps at one DAScale")

    def postSet(self) -> SetResult:
        passed, _ = setHasPassed(self.sweepResults)
        self.setRecord.values[Keys.SET_QC] = passed
        result = SetResult(passed)
        if passed:
            target = None
            if self.param('UseTrueRestingMembranePotentialVoltage', 1):
                vm = self.lastPassingSet('VM')
                if vm is not None:
                    target = lastSetValue(vm, self.notebook, Keys.FULL_AVERAGE)
            if target is None:
                target = self.param('AutobiasTargetVAtSetEnd', None)
            if target is not None:
                result.runAmplifier = AmplifierSettings(autobiasEnabled=True, autobiasTarget=target)
        return result
