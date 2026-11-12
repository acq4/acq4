"""PSQ_DAScale (MIES prefix DA): Sub, Supra and AdaptiveSupra DAScale series in current clamp."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from .. import qc
from ..core import (
    AbortSet,
    AmplifierSettings,
    EpochTable,
    MidSweepAction,
    MIN_SAMPLE_INTERVAL,
    SetConfig,
    SetResult,
    SweepConfig,
    SweepData,
    SweepDecision,
)
from ..notebook import ASYNC_QC_SKIPPED, Keys, Notebook, SetRecord, SweepRecord
from .base import AnalysisFunction, register

# --- notebook keys (MIES units) -------------------------------------------------------------------
# Sweep values written by DA; RB sweeps must provide Keys.BASELINE_QC, Keys.SPIKE_DETECT and
# Keys.AP_CROSSINGS, RB sets Keys.SET_QC and Keys.PULSE_DURATION.
CHUNK0_QC = 'BaselineChunk0QC'  # bool, pre-pulse chunk
PULSE_EPOCH = 'PulseEpoch'  # [start, end] ms of stimset epoch E1 (sweep axis)
AUTOBIAS_TARGET = 'AutobiasTarget'  # mV at the sweep
DELTA_V = 'DeltaV'  # mV, Sub
DELTA_I = 'DeltaI'  # pA, Sub
RESISTANCE_FROM_FIT_ERR = 'ResistanceFromFitError'  # MOhm, Sub
FI_SLOPE = 'FISlope'  # % of Hz/pA
FI_SLOPE_REACHED_QC = 'FISlopeReachedQC'  # bool
FI_OFFSET = 'FIOffset'  # Hz, AdaptiveSupra
FI_NEG_SLOPE_QC = 'FINegSlopeQC'  # bool, AdaptiveSupra
FILLIN_QC = 'FillinQC'  # bool, AdaptiveSupra: an earlier point had a larger DAScale
MAX_SLOPE = 'FIMaxSlope'  # % of Hz/pA, AdaptiveSupra
ENOUGH_FI_POINTS_QC = 'EnoughFIPointsQC'  # bool, AdaptiveSupra
SWEEP_EXCEPT_BL_PP_QC = 'SweepExceptBaselinePostPulseQC'  # bool, AdaptiveSupra
FUTURE_DASCALES = 'FutureDAScales'  # list of 'type:pA', AdaptiveSupra (also a set value)
FUTURE_DASCALES_QC = 'FutureDAScalesMeasuredQC'  # bool, AdaptiveSupra
# Set values
PARAMS = 'Params'  # analysis parameters of the set
RSA_SWEEPS = 'RhSuAdSweeps'  # AdaptiveSupra pool, ordered by DAScale (stable)
RSA_DASCALE = 'RhSuAdDAScale'  # pA
RSA_FREQ = 'RhSuAdAPFrequency'  # Hz
RSA_FI_OFFSETS = 'RhSuAdFIOffsets'  # Hz, pairwise
RSA_FI_SLOPES = 'RhSuAdFISlopes'  # % of Hz/pA, pairwise
RSA_FILLIN_QC = 'RhSuAdFillinQC'
RSA_FI_SLOPES_REACHED_QC = 'RhSuAdFISlopesReachedQC'
RSA_FI_NEG_SLOPES_QC = 'RhSuAdFINegSlopesQC'
MIN_DASCALE_NORM = 'MinNormDAScaleStep'  # pA/Hz
MAX_DASCALE_NORM = 'MaxNormDAScaleStep'  # pA/Hz
NEG_SLOPE_FILLIN = 'NegSlopeFillin'  # bool

SUB, SUPRA, ADAPTIVE = 'Sub', 'Supra', 'AdaptiveSupra'
RHEOBASE_MIN_PULSE = 500.0  # ms, PSQ_RHEOBASE_DURATION
MIN_STIMSET_LENGTH = 3 * qc.BL_CHUNK_LENGTH  # ms
MAX_FREQ_OFFSET = 2.0  # %, PSQ_DS_MAX_FREQ_OFFSET
FAILSWEEP_NEGSLOPE_OFFSET = 1.0  # pA
SMALL = 1e-8  # CheckIfSmall
ADAPTIVE_DEFAULTS = {
    'SlopePercentage': 10.0,
    'NumSweepsWithSaturation': 2.0,
    'MaxFrequencyChangePercent': 20.0,
    'DaScaleStepWidthMinMaxRatio': 3.0,
    'AbsFrequencyMinDistance': 15.0,
    'DAScaleRangeFactor': 1.5,
    'DAScaleNegativeSlopePercent': 10.0,
    'MinimumSpikeCountForMaxSlope': 4.0,
    'FailingAdaptiveSCIRange': 1.0,
}


# --- helpers --------------------------------------------------------------------------------------


def lineFit(x: Sequence[float], y: Sequence[float]) -> tuple[float, float, float]:
    """Return least-squares ``(offset, slope, slopeError)`` of y vs x, ignoring non-finite pairs.

    NaN when fewer than 2 points remain or x is constant; slopeError is NaN for 2 points.
    """
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < 2:
        return math.nan, math.nan, math.nan
    sxx = float(np.sum((x - x.mean()) ** 2))
    if sxx == 0:
        return math.nan, math.nan, math.nan
    slope = float(np.sum((x - x.mean()) * (y - y.mean())) / sxx)
    offset = float(y.mean() - slope * x.mean())
    if len(x) > 2:
        resid = y - (offset + slope * x)
        err = math.sqrt(float(np.sum(resid**2)) / (len(x) - 2) / sxx)
    else:
        err = math.nan
    return offset, slope, err


def minSigDigits(v: float, digits: int = 2) -> float:
    """Return *v* printed with at least *digits* significant digits and read back (MIES helper)."""
    if not math.isfinite(v):
        return v
    mag = math.ceil(math.log10(abs(v))) if v != 0 else -math.inf
    return float(format(v, f'.{int(max(mag, digits))}g'))


def tpLikeDeltas(data: SweepData) -> tuple[float, float]:
    """Return ``(deltaV mV, deltaI pA)`` of the stimset pulse (CalculateTPLikePropsFromSweep).

    Edges: first two crossings of 10 % of the DA range after the stimset start. Baseline and
    elevated levels are means over the last 10 % before each edge, ending one sample before it.
    Raises ValueError when the DA has fewer than two edges.
    """
    dt = data.sampleInterval
    onset = qc.totalOnsetDelay(data.epochs)
    p0 = qc.igorRound(onset / dt)
    da = np.asarray(data.command, dtype=float)
    seg = da[p0:]
    lo, hi = float(np.nanmin(seg)), float(np.nanmax(seg))
    levels = qc.findLevels(seg, lo + 0.1 * (hi - lo), maxLevels=2)
    if len(levels) < 2:
        raise ValueError("could not find two pulse edges in the DA")
    first, second = int(p0 + levels[0]), int(p0 + levels[1])
    onsetPt = onset / dt

    def level(trace, edge, start):
        high = edge - 1
        low = high - (edge - start) * 0.1
        return float(np.mean(trace[qc.igorRound(low) : qc.igorRound(high) + 1]))

    ad = np.asarray(data.data, dtype=float)
    deltaV = level(ad, second, first) - level(ad, first, onsetPt)
    deltaI = level(da, second, first) - level(da, first, onsetPt)
    return deltaV, deltaI


def lastPassingLongRheobaseSweep(
    notebook: Notebook, minDuration: float = RHEOBASE_MIN_PULSE
) -> Optional[SweepRecord]:
    """Return the last spiking sweep of the newest passing RB set with pulse >= *minDuration* ms.

    Older passing long-pulse sets are searched when a set has no spiking sweep. None if none.
    """
    for s in reversed(notebook.sets('RB')):
        if not s.values.get(Keys.SET_QC):
            continue
        dur = s.values.get(Keys.PULSE_DURATION)
        if dur is None or dur < minDuration:
            continue
        for sw in reversed(s.sweeps):
            rec = notebook.sweep(sw)
            if rec.values.get(Keys.SPIKE_DETECT):
                return rec
    return None


def lastPassingDAScaleSet(notebook: Notebook, mode: str) -> Optional[SetRecord]:
    """Return the newest DA set in operation *mode* with a passing set QC, or None."""
    return notebook.lastSet(
        'DA',
        lambda s: bool(s.values.get(Keys.SET_QC)) and s.values.get(Keys.OPERATION_MODE) == mode,
    )


def g15(v: float) -> float:
    """Return *v* rounded to 15 significant digits (MIES stores the RhSuAd lists as text)."""
    return float(f'{v:.15g}')


def parseFuture(entry: str) -> tuple[str, int]:
    """Split a future DAScale entry ``'type:value'``."""
    typ, _, value = entry.partition(':')
    return typ, int(value)


def consecutivePasses(ref: Sequence, check: Sequence, numRef: int, numCheck: int) -> bool:
    """Return True for a run of *numCheck* passing ``check[i]`` with *numRef* passing ``ref[i+1]``.

    ``check`` is pairwise (one element shorter than ``ref``); a failing ``check[i]`` resets the run.
    """
    if len(ref) != len(check) + 1:
        raise ValueError("ref must be one element longer than check")
    nc = nr = 0
    for i, c in enumerate(check):
        if not c:
            nc = nr = 0
            continue
        nc += 1
        nr += ref[i + 1] == 1
        if nc >= numCheck and nr >= numRef:
            return True
    return False


def hasRequiredQCOrder(firstQC, checkFirst, lastQC, checkLast) -> bool:
    """Return True for a passing ``checkFirst`` on a ``firstQC`` point followed by a passing
    ``checkLast`` on a ``lastQC`` point, only failing points between (PSQ_DS_HasRequiredQCOrder).
    """
    prevFirst = currentLast = False
    for i in range(len(checkFirst)):
        if lastQC[i + 1]:
            currentLast = bool(checkLast[i])
            if not currentLast:
                prevFirst = False
        if prevFirst and currentLast:
            return True
        if firstQC[i + 1]:
            prevFirst = bool(checkFirst[i])
            currentLast = False
    return False


def fillinQC(x: Sequence[float], idx: int) -> bool:
    """Return True when a point before *idx* has a DAScale larger than ``x[idx]``."""
    return idx > 0 and max(x[:idx]) > x[idx]


def maxSlope(slopes: Sequence[float], freqs: Sequence[float], minFrequency: float) -> float:
    """Return the largest pairwise slope whose right point has AP frequency >= *minFrequency* Hz."""
    vals = [
        s
        for i, s in enumerate(slopes)
        if freqs[i + 1] >= minFrequency and not math.isnan(s)  # NaN frequency compares False
    ]
    return max(vals) if vals else math.nan


# --- adaptive point pool --------------------------------------------------------------------------


@dataclass
class _Point:
    """One f-I point of the AdaptiveSupra pool; the slope belongs to the pair ending here."""

    sweep: int
    x: float  # pA
    y: float = math.nan  # Hz
    rsa: bool = False
    rank: int = 0  # acquisition order
    sweepPass: bool = True
    sweepExcept: bool = True
    bl: bool = True
    fillin: bool = False
    slope: float = math.nan  # % of Hz/pA
    offset: float = math.nan  # Hz
    slopeSource: Optional[int] = None  # pool index of the point whose fit gave ``slope``
    slopeReached: bool = False
    negSlope: bool = False
    enough: Optional[bool] = True  # None: not evaluated (no current-set point to fit)


@dataclass
class _Pool:
    points: list[_Point] = field(default_factory=list)
    rsaQCDone: bool = False  # RhSuAd slope QCs computed; they filter later fits
    current: Optional[int] = None  # index of the sweep being evaluated

    def gather(
        self,
        attr: str,
        filterPassing: bool = False,
        filterNeg: bool = False,
        beforeSweepQC: bool = False,
        rsaOnly: bool = False,
    ) -> tuple[list, list[int], bool]:
        """Return ``(values, pool indices, emptySCI)``: RhSuAd points then current-set points.

        *filterPassing* keeps passing set points (the current one by its BL QC when
        *beforeSweepQC*); *filterNeg* also drops points whose slope is negative-QC or NaN (RhSuAd
        point 0 is always kept).
        """
        rsa = [i for i, p in enumerate(self.points) if p.rsa]
        sci = [] if rsaOnly else [i for i, p in enumerate(self.points) if not p.rsa]
        if filterPassing:
            if filterNeg and self.rsaQCDone:
                rsa = [
                    i
                    for k, i in enumerate(rsa)
                    if k == 0
                    or (not self.points[i].negSlope and not math.isnan(self.points[i].slope))
                ]
            kept = []
            for i in sci:
                p = self.points[i]
                isCurrent = beforeSweepQC and i == self.current
                passed = p.bl if isCurrent else p.sweepPass
                if filterNeg and not isCurrent:
                    passed = passed and not p.negSlope and not math.isnan(p.slope)
                if passed:
                    kept.append(i)
            sci = kept
        idx = rsa + sci
        return [getattr(self.points[i], attr) for i in idx], idx, len(sci) == 0

    def pairwise(self, attr: str, rsaOnly: bool = False) -> list:
        """Return *attr* of every point but the first (slope-aligned)."""
        vals, _, _ = self.gather(attr, rsaOnly=rsaOnly)
        return vals[1:]


@register
class DAScale(AnalysisFunction):
    """Play a DAScale series and evaluate it: resistance (Sub), f-I slope (Supra) or the f-I curve
    until saturation (AdaptiveSupra).

    Supra DAScales are offsets (``OffsetOperator`` '+') or factors ('*') of the rheobase found by
    the newest passing long-pulse Rheobase set; Sub DAScales are absolute; AdaptiveSupra computes
    absolute DAScales from the rheobase, Supra and failed adaptive sweeps (RhSuAd) and its own.
    """

    miesName = 'PSQ_DAScale'
    analysisType = 'DA'
    clampMode = 'IC'

    # --- set -------------------------------------------------------------------------------------

    def preSet(self) -> SetConfig:
        self.mode = self.param('OperationMode')
        if self.mode not in (SUB, SUPRA, ADAPTIVE):
            raise AbortSet(f"{self.miesName}: invalid OperationMode {self.mode!r}")
        multiplier = self.param('SamplingMultiplier')
        if sum(e.duration for e in self.stimset.epochs) < MIN_STIMSET_LENGTH:
            raise AbortSet(f"{self.miesName}: stimset must be at least {MIN_STIMSET_LENGTH} ms")
        target = self.context.autobiasTarget()
        if target is None or not math.isfinite(target) or abs(target) < 1e-12:
            raise AbortSet(f"{self.miesName}: autobias target is zero, non-finite or unknown")

        self.setRecord.values[Keys.OPERATION_MODE] = self.mode
        self.setRecord.values[PARAMS] = dict(self.params)
        self._index = 0
        self._offset = 0.0
        self._modifier = 0.0
        self._operator = '+'
        self._oor = False
        self._dascale: Optional[float] = None
        self._sciX: list[float] = []
        self._resistance: Optional[tuple[float, float]] = None
        if self.mode == SUPRA:
            self._operator = self.param('OffsetOperator', '+')
            rb = lastPassingLongRheobaseSweep(self.notebook)
            if rb is None:
                raise AbortSet(f"{self.miesName}: no passing long-pulse rheobase set")
            self._offset = rb.dascale
        if self.mode == ADAPTIVE:
            self._adaptivePreSet()
        else:
            self._values = [float(v) for v in self.param('DAScales')]
        self._setDAScale(limitCheck=False)
        return SetConfig(
            clampMode='IC',
            sampleInterval=MIN_SAMPLE_INTERVAL * multiplier,
            insertTestPulse=True,
            runAmplifier=AmplifierSettings(autobiasEnabled=True),
        )

    def postSet(self) -> SetResult:
        recs = [self.notebook.sweep(sw) for sw in self.setRecord.sweeps]
        passes = sum(bool(r.values.get(Keys.SWEEP_QC)) for r in recs)
        if self.mode == ADAPTIVE:
            passed = self._isFinished(rsaOnly=False, oor=self._oor)
        else:
            passed = passes >= len(self._values) and not self._oor
            finalSlope = (
                self.param('FinalSlopePercent', math.nan) if self.mode == SUPRA else math.nan
            )
            if math.isfinite(finalSlope):
                passed = passed and any(r.values.get(FI_SLOPE_REACHED_QC) for r in recs)
        values = {Keys.SET_QC: passed, Keys.OPERATION_MODE: self.mode}
        if self.mode == SUB and self._resistance is not None:
            values[Keys.RESISTANCE_FROM_FIT] = self._resistance[0]
            values[RESISTANCE_FROM_FIT_ERR] = self._resistance[1]
        if self.mode == ADAPTIVE:
            values[FUTURE_DASCALES] = list(self._future)
            values[NEG_SLOPE_FILLIN] = self._negSlopeFillin
        self.setRecord.values.update(values)
        return SetResult(passed=passed, values=values)

    # --- sweep -----------------------------------------------------------------------------------

    def preSweep(self, setSweepIndex: int, layout: EpochTable) -> SweepConfig:
        pulse = next((ep for ep in qc.stimsetEpochs(layout) if ep.amplitude != 0), None)
        if pulse is None:
            raise AbortSet(f"{self.miesName}: stimset has no pulse epoch")
        self._pulseDuration = pulse.duration
        self._bl = qc.BaselineQC(
            'DA',
            rmsShortThreshold=self.param('BaselineRMSShortThreshold', qc.RMS_SHORT_THRESHOLD),
            rmsLongThreshold=self.param('BaselineRMSLongThreshold', qc.RMS_LONG_THRESHOLD),
            targetVThreshold=self.param('BaselineTargetVThreshold', qc.TARGETV_THRESHOLD),
        )
        self._blStatus: Optional[qc.BaselineStatus] = None
        self._setSweepIndex = setSweepIndex
        return SweepConfig(dascale=self._dascale)

    def _evaluateBaseline(self, data: SweepData) -> qc.BaselineStatus:
        if self._blStatus is None or not self._blStatus.passed:
            self._bl.targetV = self.context.autobiasTarget()
            chunks = qc.baselineChunks('DA', data, self._pulseDuration)
            self._blStatus = self._bl.evaluate(data, chunks)
        return self._blStatus

    def midSweep(self, data: SweepData) -> MidSweepAction:
        if self._blStatus is not None and self._blStatus.passed:
            return None
        status = self._evaluateBaseline(data)
        return qc.toMidSweepAction(status.midSweepCode, 'DA', data)

    def postSweep(self, data: SweepData) -> SweepDecision:
        values = self.notebook.sweep(data.sweep).values
        self._sciX.append(data.dascale)
        blPassed = self._evaluateBaseline(data).passed
        chunk0 = self._bl.results.get(0)
        samplingPassed = qc.samplingQC(
            data.sampleInterval,
            self.param('SamplingFrequency', qc.defaultSamplingFrequency('DA')),
        )
        e1 = data.epochs.stimsetEpoch(1)
        values.update(
            {
                Keys.OPERATION_MODE: self.mode,
                Keys.BASELINE_QC: blPassed,
                CHUNK0_QC: chunk0 is not None and chunk0.passed,
                Keys.SAMPLING_QC: samplingPassed,
                Keys.ASYNC_QC: ASYNC_QC_SKIPPED,
                Keys.PULSE_DURATION: self._pulseDuration,
                PULSE_EPOCH: [e1.start, e1.end],
                Keys.AP_CROSSINGS: qc.apCrossings(data),
                AUTOBIAS_TARGET: self.context.autobiasTarget(),
            }
        )
        if self.mode == ADAPTIVE:
            sweepPassed, action = self._adaptivePostSweep(data, values, samplingPassed)
        else:
            sweepPassed, action = self._subSupraPostSweep(data, values, blPassed, samplingPassed)

        lastInSet = self._setSweepIndex >= self.stimset.numSweeps - 1
        self._setDAScale(limitCheck=not lastInSet)
        values[Keys.DASCALE_OUT_OF_RANGE] = self._oor
        if self.mode == ADAPTIVE and self._endAtPreSet and action == 'continue':
            action = 'endSetPassed'
        if self._oor:
            action = 'abort'
        return SweepDecision(
            sweepPassed, action, reason='DAScale out of range' if self._oor else ''
        )

    def _setDAScale(self, limitCheck: bool) -> None:
        """Set the next sweep's DAScale from the list entry at the current index."""
        if self.mode == ADAPTIVE:
            values = [parseFuture(e)[1] for e in self._future]
        else:
            values = self._values
        if self._index >= len(values):
            return
        v = values[self._index] * (1 + self._modifier)
        dascale = v + self._offset if self._operator == '+' else v * self._offset
        if limitCheck:
            lo, hi = self.stimset.extremes(self._setSweepIndex + 1)
            if qc.dascaleOutOfRange(dascale, lo, hi, self.context.commandLimit):
                self._oor = True
                return
        self._dascale = float(dascale)

    def _subSupraPostSweep(
        self, data: SweepData, values: dict, blPassed: bool, samplingPassed: bool
    ) -> tuple[bool, str]:
        sweepPassed = blPassed and samplingPassed
        values[Keys.SWEEP_QC] = sweepPassed
        self._modifier = 0.0
        fiSlope = math.nan
        if sweepPassed and self.mode == SUB:
            dV, dI = tpLikeDeltas(data)
            values[DELTA_V], values[DELTA_I] = dV, dI
            self._fitResistance(values)
        elif sweepPassed and self.mode == SUPRA:
            fiSlope = self._supraAnalysis(data, values)
        values[FI_SLOPE] = fiSlope
        finalSlope = self.param('FinalSlopePercent', math.nan) if self.mode == SUPRA else math.nan
        values[FI_SLOPE_REACHED_QC] = bool(math.isfinite(finalSlope) and fiSlope >= finalSlope)

        recs = [self.notebook.sweep(sw) for sw in self.setRecord.sweeps]
        action = qc.determineSweepQCResults(
            sweepPassed,
            samplingPassed,
            self.stimset.numSweeps,
            len(recs),
            sum(bool(r.values.get(Keys.SWEEP_QC)) for r in recs),
            len(self._values),
            math.inf,
        )
        if sweepPassed and action == 'continue':
            self._index += 1
        return sweepPassed, action

    def _fitResistance(self, values: dict) -> None:
        """Fit deltaV vs deltaI of the passing set sweeps; write Keys.RESISTANCE_FROM_FIT (MOhm)."""
        recs = [self.notebook.sweep(sw).values for sw in self.setRecord.sweeps]
        pts = [(r[DELTA_I], r[DELTA_V]) for r in recs if DELTA_V in r]
        if len(pts) < 2:
            r, err = pts[-1][1] / pts[-1][0] * 1e3, math.nan
        else:
            _, slope, slopeErr = lineFit([p[0] for p in pts], [p[1] for p in pts])
            r, err = slope * 1e3, slopeErr * 1e3  # mV/pA -> MOhm
        values[Keys.RESISTANCE_FROM_FIT] = r
        values[RESISTANCE_FROM_FIT_ERR] = err
        self._resistance = (r, err)

    def _supraAnalysis(self, data: SweepData, values: dict) -> float:
        """Count spikes in the pulse, set the next sweep's modifier; return the set's f-I slope."""
        onset = qc.totalOnsetDelay(data.epochs)
        spikes = qc.searchForSpikes(
            data, 'DA', onset, qc.DA_SPIKE_LEVEL, numberOfSpikesReq=math.inf
        )
        values[Keys.SPIKE_DETECT] = spikes.detected
        values[Keys.SPIKE_COUNT] = spikes.count
        mod = self.param('DAScaleModifier', math.nan)
        if math.isfinite(mod):
            if spikes.count < self.param('MinimumSpikeCount'):
                self._modifier = mod / 100
            elif spikes.count > self.param('MaximumSpikeCount'):
                self._modifier = -mod / 100

        freqs = []
        for sw in self.setRecord.sweeps:
            r = self.notebook.sweep(sw).values
            count = r.get(Keys.SPIKE_COUNT, math.nan)
            freqs.append(minSigDigits(count / (r[Keys.PULSE_DURATION] * 1e-3)))
        _, slope, _ = lineFit(self._sciX, freqs)
        return slope * 100  # Hz/pA -> % of Hz/pA

    # --- AdaptiveSupra ---------------------------------------------------------------------------

    def _ap(self, name: str) -> float:
        return float(self.param(name, ADAPTIVE_DEFAULTS[name]))

    def _adaptivePreSet(self) -> None:
        self._values = []
        self._mfcp = self._ap('MaxFrequencyChangePercent')
        self._absMinDist = self._ap('AbsFrequencyMinDistance')
        self._slopePct = self._ap('SlopePercentage')
        self._negPct = self._ap('DAScaleNegativeSlopePercent')
        self._minCountMaxSlope = self._ap('MinimumSpikeCountForMaxSlope')
        self._nsws = int(self._ap('NumSweepsWithSaturation'))
        self._negSlopeFillin = False
        self._measuredAll = True
        self._future: list[str] = []
        self.pool = _Pool()

        supraSet, rsaRecs, historic = self._rhSuAdSweeps()
        start, stop = self._rhSuAdWindow(supraSet)
        chrono = []
        for rec in rsaRecs:
            cr = rec.values.get(Keys.AP_CROSSINGS)
            if cr is None:
                raise AbortSet(f"{self.miesName}: sweep {rec.sweep} has no {Keys.AP_CROSSINGS}")
            y = qc.apFrequencyFromCrossings(cr, start, stop)
            chrono.append(_Point(rec.sweep, g15(rec.dascale), g15(y), rsa=True, rank=len(chrono)))
        xs = [p.x for p in chrono]
        for i, p in enumerate(chrono):
            p.fillin = fillinQC(xs, i)
        # pairwise slopes are taken between DAScale neighbours, so the pool is kept in that order
        self.pool.points = sorted(chrono, key=lambda p: p.x)
        pts = self.pool.points

        if len(pts) < 2:
            raise AbortSet(f"{self.miesName}: f-I fit of the RhSuAd data needs 2 points")
        for i in range(1, len(pts)):
            pts[i].offset, pts[i].slope = map(g15, self._twoPointFit(pts[i - 1], pts[i]))
            pts[i].slopeSource = i
        if all(math.isnan(p.slope) and math.isnan(p.offset) for p in pts[1:]):
            raise AbortSet(f"{self.miesName}: all f-I fits of the RhSuAd data failed")

        _, m, _ = lineFit([p.x for p in pts], [p.y for p in pts])
        if abs(m) >= SMALL:
            self._minNorm = (self._mfcp / 100) / abs(m)
        else:
            self._minNorm = self._ap('DAScaleRangeFactor') * (max(xs) - min(xs))
        self._maxNorm = self._minNorm * self._ap('DaScaleStepWidthMinMaxRatio')
        if not self._minNorm < self._maxNorm:
            raise AbortSet(f"{self.miesName}: invalid DAScale step widths {self._minNorm}")

        self._future = self._fillin('FillinRhSuAd', pts, historic)
        self._storeFuture()
        slopes = [p.slope for p in pts[1:]]
        mx = maxSlope(slopes, [p.y for p in pts], self._minCountMaxSlope)
        for i in range(len(slopes)):
            pts[i + 1].slopeReached = self._reachedFinalSlope(i, mx)
            pts[i + 1].negSlope = self._negSlopePass(i)
        self.pool.rsaQCDone = True

        if self._isFinished(rsaOnly=True):
            new = self._calculateDAScale(rsaOnly=True, alreadyDone=True)
            self._endAtPreSet = True
        else:
            new = self._calculateDAScale(rsaOnly=True)
            self._endAtPreSet = False
        self._future.append(new)
        self._storeFuture()

        sv = self.setRecord.values
        sv.update(
            {
                RSA_SWEEPS: [p.sweep for p in pts],
                RSA_DASCALE: [p.x for p in pts],
                RSA_FREQ: [p.y for p in pts],
                RSA_FI_OFFSETS: [p.offset for p in pts[1:]],
                RSA_FI_SLOPES: slopes,
                RSA_FILLIN_QC: [p.fillin for p in pts],
                RSA_FI_SLOPES_REACHED_QC: [p.slopeReached for p in pts[1:]],
                RSA_FI_NEG_SLOPES_QC: [p.negSlope for p in pts[1:]],
                MAX_SLOPE: mx,
                MIN_DASCALE_NORM: self._minNorm,
                MAX_DASCALE_NORM: self._maxNorm,
            }
        )

    def _rhSuAdSweeps(self) -> tuple[SetRecord, list[SweepRecord], list[str]]:
        """Return the newest passing Supra set, the RhSuAd sweeps, and the carried-over future list.

        RhSuAd: passing-baseline sweeps of the newest passing long-pulse RB set, passing sweeps of
        the newest passing Supra set, and passing sweeps of qualifying failed adaptive sets.
        """
        supraSet = lastPassingDAScaleSet(self.notebook, SUPRA)
        if supraSet is None:
            raise AbortSet(f"{self.miesName}: no passing Supra DAScale set")
        rb = lastPassingLongRheobaseSweep(self.notebook)
        if rb is None:
            raise AbortSet(f"{self.miesName}: no passing long-pulse rheobase set")
        nb = self.notebook
        rbSweeps = [
            nb.sweep(sw)
            for sw in nb.setOf(rb.sweep).sweeps
            if nb.sweep(sw).values.get(Keys.BASELINE_QC)
        ]
        supraSweeps = [
            nb.sweep(sw) for sw in supraSet.sweeps if nb.sweep(sw).values.get(Keys.SWEEP_QC)
        ]
        if not rbSweeps or not supraSweeps:
            raise AbortSet(f"{self.miesName}: no passing rheobase or Supra sweeps")
        adSweeps = sorted(
            (
                nb.sweep(sw)
                for s in self._failedAdaptiveSets()
                for sw in s.sweeps
                if nb.sweep(sw).values.get(Keys.SWEEP_QC)
            ),
            key=lambda r: r.sweep,
        )
        recs = rbSweeps + supraSweeps + adSweeps
        lastSet = nb.setOf(recs[-1].sweep)
        acquired = {nb.sweep(sw).dascale for sw in lastSet.sweeps}
        historic = [
            e for e in lastSet.values.get(FUTURE_DASCALES, []) if parseFuture(e)[1] not in acquired
        ]
        return supraSet, recs, historic

    def _failedAdaptiveSets(self) -> list[SetRecord]:
        """Return the failed adaptive sets among the FailingAdaptiveSCIRange sets before this one
        that used the same parameters and autobias target (within 0.01 mV)."""
        rng = self._ap('FailingAdaptiveSCIRange')
        target = self.context.autobiasTarget()
        earlier = [s for s in self.notebook.sets() if s.sweeps and s.sci != self.setRecord.sci]
        out = []
        for s in reversed(earlier):
            if rng <= 0:
                break
            rng -= 1
            if (
                s.analysisType == 'DA'
                and s.values.get(Keys.OPERATION_MODE) == ADAPTIVE
                and not s.values.get(Keys.SET_QC, False)
                and s.values.get(PARAMS) == dict(self.params)
            ):
                t0 = self.notebook.sweep(s.sweeps[0]).values.get(AUTOBIAS_TARGET)
                if t0 is not None and target is not None and abs(t0 - target) <= 0.01:
                    out.append(s)
        return out

    def _rhSuAdWindow(self, supraSet: SetRecord) -> tuple[float, float]:
        """Return the AP frequency window (ms) for RhSuAd sweeps: supra E1 start + adaptive E1."""
        e1 = self.notebook.sweep(supraSet.sweeps[-1]).values.get(PULSE_EPOCH)
        if e1 is None:
            raise AbortSet(
                f"{self.miesName}: Supra sweep {supraSet.sweeps[-1]} has no {PULSE_EPOCH}"
            )
        adaptiveLength = self.stimset.epochs[1].duration
        if adaptiveLength > (e1[1] - e1[0]) + 1e-6:
            raise AbortSet(f"{self.miesName}: adaptive epoch 1 is longer than the Supra pulse")
        return e1[0], e1[0] + adaptiveLength

    @staticmethod
    def _twoPointFit(a: _Point, b: _Point) -> tuple[float, float]:
        """Return (offset Hz, slope % of Hz/pA) of the line through two points; NaN for equal x."""
        if b.x == a.x or not (math.isfinite(a.y) and math.isfinite(b.y)):
            return math.nan, math.nan
        slope = (b.y - a.y) / (b.x - a.x)
        return a.y - slope * a.x, slope * 100

    def _storeFuture(self) -> None:
        n = len(self._future)
        self._measuredAll = n == 0 or n == self._index + 1

    def _fillin(self, typ: str, points: list[_Point], historic: list[str]) -> list[str]:
        """Return *historic* plus midpoints where neighbouring frequencies jump too much.

        Points are ordered by frequency, ties in acquisition order; a midpoint is added when the
        relative jump exceeds MaxFrequencyChangePercent, the absolute one AbsFrequencyMinDistance,
        the half step the minimum step, and it was neither proposed nor measured before.
        """
        if len(points) < 2:
            raise ValueError("fill-in needs at least two points")
        ordered = sorted(points, key=lambda p: (p.y, p.rank))
        y = [p.y for p in ordered]
        x = [p.x for p in ordered]
        known = {parseFuture(e)[1] for e in historic}
        new = []
        for i in range(len(y) - 1):
            xs_ = (x[i + 1] - x[i]) / 2
            xm = qc.igorRound(x[i] + xs_)
            if y[i] == 0:
                frac = math.inf if y[i + 1] > 0 else math.nan
            else:
                frac = y[i + 1] / y[i] - 1
            if (
                frac > self._mfcp / 100
                and abs(y[i + 1] - y[i]) > self._absMinDist
                and xs_ > self._minNorm * y[i]
                and xm not in known
                and not any(abs(v - xm) <= 1e-12 for v in x)
            ):
                new.append(f'{typ}:{xm}')
        return historic + new

    def _slopeSourcePoint(self, slopeIdx: int) -> _Point:
        p = self.pool.points[slopeIdx + 1]
        return self.pool.points[p.slopeSource if p.slopeSource is not None else slopeIdx + 1]

    def _reachedFinalSlope(self, slopeIdx: int, mx: float) -> bool:
        """f-I slope QC: below (1 - SlopePercentage) * *mx*, right of *mx*'s point, not fill-in."""
        slopes = self.pool.pairwise('slope')
        s = slopes[slopeIdx]
        if not (math.isfinite(s) and math.isfinite(mx)):
            return False
        maxIdx = max(i for i, v in enumerate(slopes) if v == mx)
        src = self._slopeSourcePoint(slopeIdx)
        return (
            s < mx * (1 - self._slopePct / 100)
            and src.x > self._slopeSourcePoint(maxIdx).x
            and not src.fillin
        )

    def _negSlopePass(self, slopeIdx: int) -> bool:
        s = self.pool.pairwise('slope')[slopeIdx]
        return math.isfinite(s) and s <= 0 and not self._slopeSourcePoint(slopeIdx).fillin

    def _fit(self) -> tuple[float, float, Optional[int], bool]:
        """Fit the current point and its DAScale predecessor (passing, non-negative-slope points).

        Returns ``(offset Hz, slope % of Hz/pA, source pool index, enough points)``; NaN on failure,
        enough None when no current-set point qualifies.
        """
        xs, idx, emptySCI = self.pool.gather('x', True, True, True)
        if not idx or emptySCI:
            return math.nan, math.nan, None, None
        enough = len(idx) >= 2
        if not enough:
            return math.nan, math.nan, None, False
        ref = idx[-1]
        order = sorted(range(len(idx)), key=lambda k: xs[k])
        k = order.index(len(idx) - 1)
        if k == 0:
            return math.nan, math.nan, ref, True
        a, b = self.pool.points[idx[order[k - 1]]], self.pool.points[ref]
        offset, slope = self._twoPointFit(a, b)
        return offset, slope, ref, True

    def _adaptivePostSweep(
        self, data: SweepData, values: dict, samplingPassed: bool
    ) -> tuple[bool, str]:
        pool = self.pool
        bl = self._blStatus.passed
        p = _Point(data.sweep, data.dascale, bl=bl, rank=len(pool.points))
        pool.points.append(p)
        pool.current = len(pool.points) - 1
        if bl:
            e1 = data.epochs.stimsetEpoch(1)
            p.y = qc.apFrequency(data, e1.start, e1.end)
            values[Keys.AP_FREQUENCY] = p.y

        _, idx, emptySCI = pool.gather('x', filterPassing=True, beforeSweepQC=True)
        future = list(self._future)
        if not emptySCI:
            future = self._fillin('Fillin', [pool.points[i] for i in idx], future)

        p.offset, p.slope, p.slopeSource, p.enough = self._fit()
        if p.enough is None and pool.current == len(pool.gather('x', rsaOnly=True)[0]):
            p.enough = True  # first sweep keeps the preSet result (MIES writes it to that sweep)
        slopes = pool.pairwise('slope')
        mx = (
            maxSlope(slopes, pool.gather('y')[0], self._minCountMaxSlope)
            if math.isfinite(p.slope)
            else math.nan
        )
        p.fillin = fillinQC(pool.gather('x')[0], pool.current)
        p.slopeReached = self._reachedFinalSlope(len(slopes) - 1, mx)
        p.negSlope = self._negSlopePass(len(slopes) - 1)

        chunk0 = self._bl.results.get(0)
        p.sweepExcept = bool(
            chunk0 is not None and chunk0.passed and samplingPassed and p.enough is not False
        )
        p.sweepPass = p.sweepExcept and bl
        pool.current = None
        values.update(
            {
                FI_OFFSET: p.offset,
                FI_SLOPE: p.slope,
                MAX_SLOPE: mx,
                FILLIN_QC: p.fillin,
                FI_SLOPE_REACHED_QC: p.slopeReached,
                FI_NEG_SLOPE_QC: p.negSlope,
                ENOUGH_FI_POINTS_QC: p.enough,
                SWEEP_EXCEPT_BL_PP_QC: p.sweepExcept,
                Keys.SWEEP_QC: p.sweepPass,
            }
        )

        self._future = future
        self._storeFuture()
        sciPoints = [q for q in pool.points if not q.rsa]
        if not samplingPassed or any(q.enough is False for q in sciPoints):
            action = 'endSetFailed'
        elif self._isFinished(rsaOnly=False):
            action = 'endSetPassed'
        else:
            action = 'continue'
            if p.sweepPass:
                if not self._negSlopeFillin and self._measuredAll:
                    self._future.append(self._calculateDAScale())
                    self._storeFuture()
                self._index += 1
            else:
                new = self._calculateDAScale(onlyFailingNegSlope=True)
                if new is not None:
                    self._future.append(new)
                    self._storeFuture()
                    self._index += 1
        values[FUTURE_DASCALES] = list(self._future)
        values[FUTURE_DASCALES_QC] = self._measuredAll
        return p.sweepPass, action

    def _isFinished(self, rsaOnly: bool, oor: bool = False) -> bool:
        """Return True when the f-I curve saturated or turned negative (PSQ_DS_AdaptiveIsFinished).

        May append a fill-in between the last positive and negative slope and return False.
        """
        if oor or not self._measuredAll:
            return False
        pool = self.pool
        if self._negativeSlopeCriteria(rsaOnly):
            if self._negSlopeFillin:
                return True
            if self._addFillinBeforeNegSlope(rsaOnly):
                return True
            self._negSlopeFillin = True
            return False
        sp, _, _ = pool.gather('sweepPass', rsaOnly=rsaOnly)
        if len(sp) < self._nsws:
            return False
        fillin, _, _ = pool.gather('fillin', rsaOnly=rsaOnly)
        sp = [s and not f for s, f in zip(sp, fillin)]
        return consecutivePasses(sp, pool.pairwise('slopeReached', rsaOnly), self._nsws, self._nsws)

    def _negativeSlopeCriteria(self, rsaOnly: bool) -> bool:
        pool = self.pool
        neg = pool.pairwise('negSlope', rsaOnly)
        if not any(neg):
            return False
        fillin, _, _ = pool.gather('fillin', rsaOnly=rsaOnly)
        sp, _, _ = pool.gather('sweepPass', rsaOnly=rsaOnly)
        se, _, _ = pool.gather('sweepExcept', rsaOnly=rsaOnly)
        sp = [s and not f for s, f in zip(sp, fillin)]
        se = [s and not f for s, f in zip(se, fillin)]
        if consecutivePasses(se, neg, 1, 2):
            return True
        return hasRequiredQCOrder(sp, pool.pairwise('slopeReached', rsaOnly), se, neg)

    def _addFillinBeforeNegSlope(self, rsaOnly: bool) -> bool:
        """Append the midpoint before the last negative slope; True when none can be added."""
        neg = [math.nan] + self.pool.pairwise('negSlope', rsaOnly)
        xs, _, _ = self.pool.gather('x', rsaOnly=rsaOnly)
        idx = next(
            (i for i in range(len(neg) - 2, -1, -1) if neg[i] == 0 and neg[i + 1] == 1), None
        )
        if idx is None:
            return True
        c = qc.igorRound((xs[idx] + xs[idx + 1]) / 2)
        if any(abs(v - c) <= 1e-12 for v in xs):
            return True
        typ = 'FillinPosNegSlopeRhSuAd' if rsaOnly else 'FillinPosNegSlope'
        self._future.append(f'{typ}:{c}')
        self._storeFuture()
        return False

    def _largest(self, rsaOnly: bool) -> tuple[float, float, bool, float, float, float]:
        """Return (offset, slope, negSlope, x, y, xPrev) at the largest passing DAScale.

        After a failing last sweep with a negative slope: x, y of that sweep and xPrev of the latest
        passing point with a positive slope, everything else NaN.
        """
        pool = self.pool
        xs, _, _ = pool.gather('x', rsaOnly=rsaOnly)
        ys, _, _ = pool.gather('y', rsaOnly=rsaOnly)
        sp, _, _ = pool.gather('sweepPass', rsaOnly=rsaOnly)
        neg = pool.pairwise('negSlope', rsaOnly)
        sl = pool.pairwise('slope', rsaOnly)
        off = pool.pairwise('offset', rsaOnly)
        last = len(xs) - 1
        if not sp[last] and neg[last - 1]:
            for i in range(last, 0, -1):
                if sp[i] and sl[i - 1] > 0:
                    return math.nan, math.nan, False, xs[last], ys[last], xs[i]
            return math.nan, math.nan, False, xs[last], ys[last], xs[last - 1]
        maxLoc, maxValue = None, -math.inf
        for i in range(last, -1, -1):
            if sp[i] and xs[i] > maxValue:
                maxValue, maxLoc = xs[i], i
        if maxLoc is None:
            raise ValueError("no passing point")
        x, y = xs[maxLoc], ys[maxLoc]
        if maxLoc == 0:
            return math.nan, math.nan, False, x, y, math.nan
        negS = bool(neg[maxLoc - 1])
        if negS:
            return math.nan, math.nan, True, x, y, math.nan
        return off[maxLoc - 1], sl[maxLoc - 1], False, x, y, math.nan

    def _calculateDAScale(
        self, rsaOnly: bool = False, alreadyDone: bool = False, onlyFailingNegSlope: bool = False
    ) -> Optional[str]:
        """Return the next proposal ``'type:pA'`` (PSQ_DS_CalculateDAScale); None when
        *onlyFailingNegSlope* and the last sweep was not a failing one after a negative slope."""
        suffix = 'RhSuAd' if rsaOnly else ''
        a, m, negS, x, y, xPrev = self._largest(rsaOnly)
        if onlyFailingNegSlope:
            if not (math.isfinite(x) and math.isfinite(xPrev)):
                return None
            typ, xp = 'FailSweepNegSlope', qc.igorRound(x + FAILSWEEP_NEGSLOPE_OFFSET)
        elif alreadyDone:
            typ, xp = 'Finished', self._negSlopeStep(x, y)
        elif negS:
            typ, xp = 'RegPosNegSlope', self._negSlopeStep(x, y)
        elif math.isnan(a) and math.isnan(m):
            typ, xp = 'Fallback', self._fallbackStep(x, y)
        else:
            typ, xp = 'Reg', self._plainStep(a, m, x, y)
        xAll, _, _ = self.pool.gather('x', rsaOnly=rsaOnly)
        if any(abs(v - xp) <= 1e-12 for v in xAll):
            typ, xp = 'Fallback', self._fallbackStep(xAll[-1], y)
        return f'{typ}{suffix}:{int(xp)}'

    def _negSlopeStep(self, x: float, y: float) -> int:
        return qc.igorRound(x + self._maxNorm * y * self._negPct / 100)

    def _fallbackStep(self, x: float, y: float) -> int:
        if math.isnan(y):
            y = self.notebook.nextSweepNumber()  # MIES: sweep number + 1, unique per call
        xp = qc.igorRound(x + self._minNorm * y)
        return xp + 1 if xp == x else xp

    def _plainStep(self, a: float, m: float, x: float, y: float) -> int:
        """Extrapolate along the fit to MaxFrequencyChangePercent - 2 % more frequency, bounded by
        the step widths."""
        m = m / 100
        yp = y * (1 + (self._mfcp - MAX_FREQ_OFFSET) / 100)
        maxStep = self._maxNorm * y
        if abs(m) < SMALL:
            return math.ceil(x + maxStep)
        xp = qc.igorRound((yp - a) / m)
        if abs(x - xp) > maxStep:
            return math.ceil(x + maxStep)
        if abs(y - yp) < self._absMinDist:
            return math.ceil(x + self._minNorm * y)
        return xp
