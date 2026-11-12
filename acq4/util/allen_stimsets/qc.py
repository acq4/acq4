"""Shared MIES patch-seq numerics used by the ported analysis functions.

Baseline chunk QC, TP-like epochs and test pulse analysis, pulse duration, spike detection, AP
frequency, sampling QC, set bookkeeping and the DAScale limit check. Everything here is a pure
function of its inputs (``BaselineQC`` keeps per-sweep state only); nothing touches hardware or the
notebook.

Units follow MIES: ms, pA, mV, MOhm; times are on the sweep axis (t=0 is the first DA sample).
Analysis types are the MIES prefixes ``PB SE AR VM DA SP RB RA CR``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Literal, Optional, Sequence

import numpy as np

from .core import (
    AbortSet,
    ClampMode,
    EarlyStop,
    Epoch,
    EpochTable,
    MidSweepAction,
    SetAction,
    SweepData,
)

# MIES return codes (MIES_Constants.ipf)
BL_PASS = 0
BL_FAILED = 1  # PSQ_BL_FAILED
REPURP_TIME = -100  # ANALYSIS_FUNC_RET_REPURP_TIME: stop now, add time to the next ITI
EARLY_STOP = -101  # ANALYSIS_FUNC_RET_EARLY_STOP: stop now

# Per-test QC flag encoding, as stored in the MIES labnotebook
QC_PASSED = 1.0
QC_FAILED = 0.0
QC_NOT_APPLICABLE = -1.0
QC_NOT_REACHED = float('nan')

BL_CHUNK_LENGTH = 500.0  # ms, PSQ_BL_EVAL_RANGE
RMS_SHORT_WINDOW = 1.5  # ms, end of chunk
RMS_SHORT_THRESHOLD = 0.07  # AD units (mV in IC, pA in VC)
RMS_LONG_THRESHOLD = 0.5
TARGETV_THRESHOLD = 1.0  # mV

SPIKE_LEVEL = 0.01  # mV, PSQ_SPIKE_LEVEL (SP, RB, RA)
DA_SPIKE_LEVEL = -20.0  # mV, PSQ_DS_SPIKE_LEVEL (DA Supra)
AP_FREQUENCY_LEVEL = 0.0  # mV, SweepFormula apfrequency default (DA AdaptiveSupra)
CHIRP_MIN_SPIKE_WIDTH = 0.2  # ms, PA_MINIMUM_SPIKE_WIDTH
CHIRP_PEAK_BOX = 5  # PA_PEAK_BOX_AVERAGE
SPIKE_BOX = 3  # FindLevel /B=3

TP_EVAL_OFFSET = 0.025  # ms; TP_EVAL_POINT_OFFSET (5) x ITC minimum sampling interval (0.005 ms)
TP_INST_WINDOW = 0.25  # ms
TP_MAX_EVAL_RANGE = 5.0  # ms

# MIES adds the float32 machine epsilon of the DA wave to its minimum to find pulse edges.
_DA_EPS = float(np.finfo(np.float32).eps)

AnalysisType = Literal['PB', 'SE', 'AR', 'VM', 'DA', 'SP', 'RB', 'RA', 'CR']
ChunkKind = Literal['prePulse', 'postPulse', 'generic']


# --- low-level numerics ---------------------------------------------------------------------------


def igorRound(x: float) -> int:
    """Round half away from zero (Igor ``round``)."""
    return int(math.floor(x + 0.5)) if x >= 0 else -int(math.floor(-x + 0.5))


def truncPoints(t: float, dt: float) -> int:
    """Return ``trunc(t/dt)``, snapping to the nearest integer within 1e-6 points of it."""
    x = t / dt
    r = igorRound(x)
    return r if abs(x - r) < 1e-6 else int(x)


def windowStat(
    trace: np.ndarray, dt: float, start: float, duration: float, method: Literal['avg', 'rms']
) -> float:
    """Return the mean or RMS of *trace* over ``[start, start + duration)`` ms (PSQ_Calculate).

    Window: ``truncPoints(start)`` for ``max(truncPoints(duration), 1)`` points, clipped to the wave
    end. 'rms' is the population standard deviation about the window mean (/N). Raises ValueError
    when the result is not finite (e.g. the window holds unacquired NaN samples).
    """
    n = len(trace)
    startPt = truncPoints(start, dt)
    rangePts = max(truncPoints(duration, dt), 1)
    if startPt + rangePts > n:
        rangePts = max(n - startPt, 1)
    seg = np.asarray(trace[startPt : startPt + rangePts], dtype=float)
    if len(seg) == 0:
        raise ValueError(f"window [{start}, {start + duration}] ms lies outside the trace")
    avg = seg.sum() / len(seg)
    if method == 'avg':
        result = avg
    elif method == 'rms':
        result = math.sqrt(((seg - avg) ** 2).sum() / len(seg))
    else:
        raise ValueError(f"unknown method {method!r}")
    if not math.isfinite(result):
        raise ValueError(f"non-finite {method} over [{start}, {start + duration}] ms")
    return float(result)


def boxSmooth(y: np.ndarray, box: int) -> np.ndarray:
    """Centred sliding average over *box* points, with the window truncated at the ends."""
    y = np.asarray(y, dtype=float)
    if box <= 1 or len(y) == 0:
        return y
    kernel = np.ones(box)
    counts = np.convolve(np.ones(len(y)), kernel, 'same')
    return np.convolve(y, kernel, 'same') / counts


def findLevels(
    y: np.ndarray,
    level: float,
    edge: Literal['both', 'rising', 'falling'] = 'both',
    box: int = 1,
    maxLevels: Optional[float] = None,
) -> np.ndarray:
    """Return fractional indices where *y* crosses *level*, in order (Igor FindLevels).

    A rising crossing reaches the level from below (``y[i] < L <= y[i+1]``) or leaves a sample equal
    to it upwards (``y[i] == L < y[i+1]``); falling likewise. Positions are linearly interpolated,
    and events at the same position (``-, L, +``) count once. *box* > 1 smooths first (Igor /B). NaN
    samples never cross. *maxLevels* caps the count.
    """
    y = boxSmooth(y, box)
    a, b = y[:-1], y[1:]
    rising = ((a < level) & (b >= level)) | ((a == level) & (b > level))
    falling = ((a > level) & (b <= level)) | ((a == level) & (b < level))
    mask = {'both': rising | falling, 'rising': rising, 'falling': falling}[edge]
    idx = np.nonzero(mask)[0]
    with np.errstate(invalid='ignore', divide='ignore'):
        pos = np.where(b[idx] == level, idx + 1.0, idx + (level - a[idx]) / (b[idx] - a[idx]))
    if len(pos) > 1:
        pos = pos[np.concatenate([[True], np.diff(pos) != 0])]
    if maxLevels is not None and math.isfinite(maxLevels):
        pos = pos[: int(maxLevels)]
    return pos


def levelCrossings(
    trace: np.ndarray,
    dt: float,
    start: float,
    end: float,
    level: float,
    edge: Literal['both', 'rising', 'falling'] = 'both',
    box: int = 1,
    maxLevels: Optional[float] = None,
) -> np.ndarray:
    """Return crossing times (ms) of *level* between *start* and *end* ms (Igor ``/R=(x1,x2)``).

    The range is converted to the nearest points, inclusive, and clipped to the trace; *end* may be
    inf.
    """
    p0 = max(0, igorRound(start / dt)) if math.isfinite(start) else 0
    p1 = min(len(trace) - 1, igorRound(end / dt)) if math.isfinite(end) else len(trace) - 1
    if p1 <= p0:
        return np.empty(0)
    idx = findLevels(trace[p0 : p1 + 1], level, edge, box, maxLevels)
    return (p0 + idx) * dt


def acquired(data: SweepData) -> np.ndarray:
    """Return the acquired part of the AD trace, ``data.data[:numValid]``."""
    return data.data[: data.numValid]


def acquiredUntil(data: SweepData, t: float) -> bool:
    """Return True when every sample before sweep time *t* (ms) is acquired."""
    return data.numValid >= truncPoints(t, data.sampleInterval)


def leftoverSweepTime(data: SweepData) -> float:
    """Return the unacquired remainder of the planned sweep in s."""
    return max(0, len(data.data) - data.numValid) * data.sampleInterval * 1e-3


# --- epochs ---------------------------------------------------------------------------------------

_STIMSET_EPOCH_RE = re.compile(r'^E(\d+)$')


def totalOnsetDelay(epochs: EpochTable) -> float:
    """Return the stimset start (ms): start of ``E0``, after the inserted TP and onset delays."""
    return epochs.stimsetEpoch(0).start


def stimsetEpochs(epochs: EpochTable) -> list[Epoch]:
    """Return the stimset epochs ``E<i>`` ordered by index."""
    found = [(int(m.group(1)), ep) for ep in epochs if (m := _STIMSET_EPOCH_RE.match(ep.name))]
    return [ep for _, ep in sorted(found, key=lambda x: x[0])]


def testpulseLikeEpochs(
    baseline: Epoch, pulse: Epoch, postBaseline: Epoch, dascale: float, tpIndex: int
) -> list[Epoch]:
    """Return ``U_TP<i>``, ``U_TP<i>_B0``, ``U_TP<i>_P``, ``U_TP<i>_B1`` for three stimset epochs.

    Stimset epoch amplitudes are at DAScale 1; the ``_P`` amplitude is multiplied by *dascale*.
    Raises AbortSet unless the amplitudes are 0, nonzero, 0 (PSQ_CreateTestpulseLikeEpoch).
    """
    if (
        baseline.amplitude != 0
        or not (pulse.amplitude != 0 and math.isfinite(pulse.amplitude))
        or postBaseline.amplitude != 0
    ):
        raise AbortSet(
            f"TP-like epoch {tpIndex}: stimset epochs "
            f"{baseline.name}/{pulse.name}/{postBaseline.name} "
            f"need amplitudes 0, nonzero, 0; got {baseline.amplitude}, {pulse.amplitude}, "
            f"{postBaseline.amplitude}"
        )
    name = f'U_TP{tpIndex}'
    idx = str(tpIndex)
    amp = pulse.amplitude * dascale
    return [
        Epoch(
            name, baseline.start, postBaseline.end, tags={'Type': 'Testpulse Like', 'Index': idx}
        ),
        Epoch(
            name + '_B0',
            baseline.start,
            baseline.end,
            0.0,
            {'Type': 'Testpulse Like', 'SubType': 'Baseline', 'Index': idx},
        ),
        Epoch(
            name + '_P',
            pulse.start,
            pulse.end,
            amp,
            {'Type': 'Testpulse Like', 'SubType': 'Pulse', 'Amplitude': f'{amp:g}', 'Index': idx},
        ),
        Epoch(
            name + '_B1',
            postBaseline.start,
            postBaseline.end,
            0.0,
            {'Type': 'Testpulse Like', 'SubType': 'Baseline', 'Index': idx},
        ),
    ]


def testpulseEpochs(layout: EpochTable, dascale: float, numTestPulses: int) -> list[Epoch]:
    """Return the TP-like user epochs of a PB/AR stimset (PSQ_CreateTestpulseEpochsImpl).

    TP *i* uses stimset epochs ``1+3i .. 3+3i``. Raises AbortSet when the stimset has fewer than
    ``3·numTestPulses + 2`` epochs or the amplitudes do not match.
    """
    eps = stimsetEpochs(layout)
    required = 3 * numTestPulses + 2
    if len(eps) < required:
        raise AbortSet(
            f"{numTestPulses} test pulses need at least {required} stimset epochs, "
            f"stimset has {len(eps)}"
        )
    out = []
    for i in range(numTestPulses):
        idx = 1 + 3 * i
        out.extend(testpulseLikeEpochs(eps[idx], eps[idx + 1], eps[idx + 2], dascale, i))
    return out


def baselineSelectionEpochs(
    layout: EpochTable, epochIndices: Sequence[int], chunkLength: float = BL_CHUNK_LENGTH
) -> list[Epoch]:
    """Return ``U_BLS<k>`` epochs: the first *chunkLength* ms of each listed stimset epoch.

    Numbered in stimset-epoch order. Raises AbortSet when an index is beyond the stimset, or an
    epoch has nonzero amplitude or is shorter than *chunkLength*
    (PSQ_CreateBaselineChunkSelectionEpochs).
    """
    eps = stimsetEpochs(layout)
    if max(epochIndices) >= len(eps):
        raise AbortSet(
            f"baseline selection epochs {list(epochIndices)} exceed the {len(eps)} stimset epochs"
        )
    out = []
    for i in sorted(set(epochIndices)):
        ep = eps[i]
        if ep.amplitude != 0:
            raise AbortSet(
                f"baseline selection epoch {ep.name} has amplitude {ep.amplitude}, expected 0"
            )
        if ep.duration < chunkLength:
            raise AbortSet(
                f"epoch {ep.name} is {ep.duration} ms, "
                f"shorter than BaselineChunkLength {chunkLength} ms"
            )
        k = len(out)
        out.append(
            Epoch(
                f'U_BLS{k}',
                ep.start,
                ep.start + chunkLength,
                0.0,
                {'Type': 'Baseline Chunk QC Selection', 'Index': str(k)},
            )
        )
    return out


# --- test pulse analysis --------------------------------------------------------------------------

_TP_EPOCH_RE = re.compile(r'^(U_)?TP\d*$')


@dataclass(frozen=True)
class TPResult:
    """Test pulse analysis of one averaged TP (TP_TSAnalysis).

    ``baseline``, ``steadyState``, ``instantaneous`` are AD values (pA in VC, mV in IC); resistances
    are MOhm.
    """

    baseline: float
    steadyState: float
    instantaneous: float
    steadyStateResistance: float
    instantaneousResistance: float
    numAveraged: int = 1


def testPulseEpochsForAnalysis(epochs: EpochTable, ignore: Sequence[int] = ()) -> list[Epoch]:
    """Return the whole-TP epochs (``TP``, ``U_TP<i>``) by start time, without the *ignore* indices.

    Index 0 is normally the inserted TP, so ``ignore=(0,)`` selects the embedded TP-like shapes
    (SweepFormula ``tp(..., [0])``). Raises ValueError for an index out of range.
    """
    tps = sorted((ep for ep in epochs if _TP_EPOCH_RE.match(ep.name)), key=lambda ep: ep.start)
    drop = set(ignore)
    for i in drop:
        if not 0 <= i < len(tps):
            raise ValueError(f"ignored TP index {i} out of range for {len(tps)} TPs")
    return [ep for i, ep in enumerate(tps) if i not in drop]


def averageTestPulse(trace: np.ndarray, dt: float, tps: Sequence[Epoch]) -> np.ndarray:
    """Return the point-wise average of *trace* over the TP epochs *tps* (SFOTP_AverageTPFromSweep).

    Each TP starts at ``truncPoints(start)``; all use the shortest length. Raises ValueError when
    lengths differ by more than one point or a TP is not (fully) acquired.
    """
    starts = [truncPoints(ep.start, dt) for ep in tps]
    lengths = [truncPoints(ep.end, dt) - s for ep, s in zip(tps, starts)]
    if max(lengths) - min(lengths) > 1:
        raise ValueError(f"TP lengths differ by more than one point: {lengths}")
    n = min(lengths)
    segs = np.array([trace[s : s + n] for s in starts], dtype=float)
    if segs.shape[1] != n or not np.all(np.isfinite(segs)):
        raise ValueError("test pulse not fully acquired")
    return segs.mean(axis=0)


def _igorMean(y: np.ndarray, dt: float, x1: float, x2: float) -> float:
    # Igor mean(wave, x1, x2): nearest points, both inclusive
    p1 = max(0, igorRound(x1 / dt))
    p2 = min(len(y) - 1, igorRound(x2 / dt))
    return float(np.mean(y[p1 : p2 + 1]))


def analyzeTestPulse(
    tp: np.ndarray,
    dt: float,
    baselineDuration: float,
    pulseDuration: float,
    postBaselineDuration: float,
    clampAmp: float,
    clampMode: ClampMode,
) -> TPResult:
    """Analyze one (averaged) test pulse trace starting at its pre-baseline (TP_TSAnalysis).

    Durations in ms; *clampAmp* is the pulse amplitude (mV in VC, pA in IC). Baseline and steady
    state are means over ``min(5 ms, 0.2·pulse, 0.2·baseline)`` ending 0.025 ms before pulse onset
    and offset; instantaneous is the extreme sample (sign of *clampAmp*) within 0.25 ms after onset
    + 0.025 ms. Pulse onset/offset scale the epoch geometry to the trace length, so B0 and B1 may
    differ.
    """
    tpLen = len(tp)
    b0Pts, pPts, b1Pts = baselineDuration / dt, pulseDuration / dt, postBaselineDuration / dt
    scale = tpLen / (b0Pts + pPts + b1Pts)
    onsetPt = b0Pts * scale
    offsetPt = tpLen - b1Pts * scale
    evalRange = min(TP_MAX_EVAL_RANGE / dt, pPts * 0.2, onsetPt * 0.2) * dt
    offPts = TP_EVAL_OFFSET / dt

    refTime = (onsetPt - offPts) * dt
    base = _igorMean(tp, dt, refTime - evalRange, refTime)
    refTime = (offsetPt - offPts) * dt
    ss = _igorMean(tp, dt, refTime - evalRange, refTime)

    p0 = igorRound(onsetPt + offPts)
    p1 = min(tpLen - 1, igorRound(onsetPt + offPts + TP_INST_WINDOW / dt))
    seg = tp[p0 : p1 + 1]
    inst = (
        float(np.nanmin(seg) if clampAmp < 0 else np.nanmax(seg))
        if np.any(np.isfinite(seg))
        else float('nan')
    )

    if clampMode == 'IC':
        rss = (ss - base) / clampAmp * 1000
        rinst = (inst - base) / clampAmp * 1000
    else:
        with np.errstate(divide='ignore'):
            rss = clampAmp / (ss - base) * 1000 if ss != base else float('inf')
            rinst = clampAmp / (inst - base) * 1000 if inst != base else float('inf')
    return TPResult(base, ss, inst, float(rss), float(rinst))


def testPulseResistance(data: SweepData, ignore: Sequence[int] = (0,)) -> Optional[TPResult]:
    """Average the sweep's TP epochs except *ignore* and analyze them (SweepFormula ``tp()``).

    Geometry and amplitude come from the first selected TP's ``_B0``/``_P``/``_B1`` epochs. Returns
    None when no TP is selected. Raises ValueError when the TPs are not acquired.
    """
    tps = testPulseEpochsForAnalysis(data.epochs, ignore)
    if not tps:
        return None
    first = tps[0].name
    b0, p, b1 = (data.epochs.get(first + suffix) for suffix in ('_B0', '_P', '_B1'))
    avg = averageTestPulse(acquired(data), data.sampleInterval, tps)
    res = analyzeTestPulse(
        avg, data.sampleInterval, b0.duration, p.duration, b1.duration, p.amplitude, data.clampMode
    )
    return TPResult(
        res.baseline,
        res.steadyState,
        res.instantaneous,
        res.steadyStateResistance,
        res.instantaneousResistance,
        len(tps),
    )


# --- baseline chunk QC ----------------------------------------------------------------------------


@dataclass(frozen=True)
class ChunkSpec:
    """One baseline chunk: ``[start, start + length]`` ms on the sweep axis."""

    index: int
    start: float
    length: float
    kind: ChunkKind

    @property
    def end(self) -> float:
        return self.start + self.length

    def epoch(self) -> Epoch:
        """Return the ``U_BLC<k>`` documentation epoch MIES adds when the chunk is evaluated."""
        return Epoch(
            f'U_BLC{self.index}',
            self.start,
            self.end,
            tags={'Name': 'Baseline Chunk', 'Index': str(self.index)},
        )


def prePulseChunks(onset: float, epoch0Duration: float) -> list[ChunkSpec]:
    """Return the single PB chunk ``[onset, onset + 500]`` ms.

    Raises AbortSet unless ``floor(epoch0Duration / 500) == 1`` (MIES asserts this mid-sweep).
    """
    if math.floor(epoch0Duration / BL_CHUNK_LENGTH) != 1:
        raise AbortSet(
            "stimset epoch 0 must be >= 500 and < 1000 ms for pre-pulse baseline QC, "
            f"is {epoch0Duration} ms"
        )
    return [ChunkSpec(0, onset, BL_CHUNK_LENGTH, 'prePulse')]


def pulseChunks(onset: float, pulseDuration: float, sweepDuration: float) -> list[ChunkSpec]:
    """Return the DA/RB/RA/CR chunks: pre-pulse chunk 0 and post-pulse chunks 1..n-1.

    Chunk 0 is ``[onset, onset+500]``; chunk k starts at ``onset + 500 + pulseDuration + k·500``,
    i.e. the pulse is assumed to start 500 ms after *onset* and the first 500 ms after it are
    skipped. *sweepDuration* is the planned sweep length (ms). Raises ValueError when no chunk fits.
    """
    L = BL_CHUNK_LENGTH
    num = math.floor((sweepDuration - (onset + pulseDuration + L) - L) / L) + 1
    if num < 1:
        raise ValueError(f"sweep of {sweepDuration} ms has no room for baseline chunks")
    out = [ChunkSpec(0, onset, L, 'prePulse')]
    out += [ChunkSpec(k, onset + L + pulseDuration + k * L, L, 'postPulse') for k in range(1, num)]
    return out


_BLS_RE = re.compile(r'^U_BLS\d+$')


def selectionChunks(epochs: EpochTable, numChunks: int) -> list[Optional[ChunkSpec]]:
    """Return *numChunks* generic chunks from the ``U_BLS<k>`` epochs; None where absent."""
    bls = sorted((ep for ep in epochs if _BLS_RE.match(ep.name)), key=lambda ep: ep.start)
    return [
        ChunkSpec(k, bls[k].start, bls[k].duration, 'generic') if k < len(bls) else None
        for k in range(numChunks)
    ]


def baselineChunks(
    analysisType: str, data: SweepData, pulseDuration: Optional[float] = None
) -> list[Optional[ChunkSpec]]:
    """Return the baseline chunks MIES evaluates for *analysisType* in this sweep.

    PB: ``prePulseChunks``; SE: 2 and VM/AR: 1 ``selectionChunks``; DA/RB/RA/CR: ``pulseChunks``,
    which need *pulseDuration* (ms, see ``pulseDuration``).
    """
    if analysisType == 'PB':
        return prePulseChunks(totalOnsetDelay(data.epochs), data.epochs.stimsetEpoch(0).duration)
    if analysisType in ('SE', 'VM', 'AR'):
        return selectionChunks(data.epochs, 2 if analysisType == 'SE' else 1)
    if analysisType in ('DA', 'RB', 'RA', 'CR'):
        if pulseDuration is None:
            raise ValueError(f"{analysisType} baseline chunks need the pulse duration")
        return pulseChunks(
            totalOnsetDelay(data.epochs), pulseDuration, len(data.data) * data.sampleInterval
        )
    raise ValueError(f"no baseline QC for analysis type {analysisType!r}")


@dataclass(frozen=True)
class BaselineTests:
    """Which tests run on a chunk, in order: short RMS, long RMS, target V, leak current."""

    rmsShort: bool = False
    rmsLong: bool = False
    targetV: bool = False
    leak: bool = False


def baselineTests(analysisType: str, kind: ChunkKind) -> BaselineTests:
    """Return the MIES test matrix entry for *analysisType* and chunk *kind*."""
    if analysisType in ('AR', 'PB'):
        wanted = 'generic' if analysisType == 'AR' else 'prePulse'
        return BaselineTests(True, True, False, True) if kind == wanted else BaselineTests()
    if analysisType in ('SE', 'VM'):
        return BaselineTests(True, True) if kind == 'generic' else BaselineTests()
    if analysisType in ('DA', 'RB', 'RA', 'CR'):
        if kind == 'prePulse':
            return BaselineTests(True, True, True, False)
        if kind == 'postPulse':
            return BaselineTests(targetV=True)
        return BaselineTests()
    raise ValueError(f"no baseline QC for analysis type {analysisType!r}")


@dataclass(frozen=True)
class ChunkResult:
    """Outcome of one evaluated chunk.

    Values are in AD units (``rmsShort``/``rmsLong``: pA in VC, mV in IC; ``average``: mV;
    ``leakCurrent``: pA), NaN when not computed. Flags use the labnotebook encoding: 1 pass, 0 fail,
    -1 not applicable, NaN not reached (an earlier test failed). ``code`` is the return code of the
    first evaluation.
    """

    chunk: ChunkSpec
    passed: bool
    code: int
    rmsShort: float = float('nan')
    rmsLong: float = float('nan')
    average: float = float('nan')
    leakCurrent: float = float('nan')
    rmsShortPassed: float = QC_NOT_REACHED
    rmsLongPassed: float = QC_NOT_REACHED
    targetVPassed: float = QC_NOT_REACHED
    leakCurrentPassed: float = QC_NOT_REACHED


@dataclass(frozen=True)
class BaselineStatus:
    """Result of one ``BaselineQC.evaluate`` call (PSQ_EvaluateBaselineChunks).

    ``code`` is None while undecided (MIES NaN), else BL_PASS, BL_FAILED, EARLY_STOP or REPURP_TIME.
    ``chunk`` is the last chunk index looked at (``len(chunks)`` when the loop ran through).
    """

    code: Optional[int]
    chunk: int

    @property
    def decided(self) -> bool:
        return self.code is not None

    @property
    def passed(self) -> bool:
        """The BL QC value MIES writes: True only for BL_PASS (undecided counts as False)."""
        return self.code == BL_PASS

    @property
    def midSweepCode(self) -> Optional[int]:
        """Mid-sweep return: EARLY_STOP on pass, else ``code`` (PSQ_EvaluateBaselinePassed)."""
        return EARLY_STOP if self.passed else self.code


class BaselineQC:
    """Baseline chunk QC of one sweep (PSQ_EvaluateBaselineProperties/-Chunks).

    Create one per sweep and call ``evaluate`` on growing partial data. A chunk is evaluated once,
    as soon as it is fully acquired; later calls return its cached pass/fail as BL_PASS/BL_FAILED,
    so a stop code is returned only once. Results per chunk index are in ``results``.

    Parameters
    ----------
    analysisType : MIES prefix (PB, SE, AR, VM, DA, RB, RA, CR).
    rmsShortThreshold, rmsLongThreshold : strict upper limits in AD units (pA in VC, mV in IC).
    targetVThreshold : mV; ``|average - targetV| <= threshold`` passes (DA, RB, RA, CR).
    maxLeakCurrent : pA; ``|average| <= maxLeakCurrent`` passes (PB, AR).
    targetV : mV, autobias target; required when the target V test runs.
    """

    def __init__(
        self,
        analysisType: str,
        rmsShortThreshold: float = RMS_SHORT_THRESHOLD,
        rmsLongThreshold: float = RMS_LONG_THRESHOLD,
        targetVThreshold: float = TARGETV_THRESHOLD,
        maxLeakCurrent: float = float('nan'),
        targetV: Optional[float] = None,
    ):
        self.analysisType = analysisType
        self.rmsShortThreshold = rmsShortThreshold
        self.rmsLongThreshold = rmsLongThreshold
        self.targetVThreshold = targetVThreshold
        self.maxLeakCurrent = maxLeakCurrent
        self.targetV = targetV
        self.results: dict[int, ChunkResult] = {}

    def evaluateChunk(self, data: SweepData, chunk: Optional[ChunkSpec]) -> Optional[int]:
        """Evaluate one chunk; return its code, or None while it is not fully acquired.

        Codes: BL_PASS on pass. Pre-pulse failure: EARLY_STOP (RMS, leak) or REPURP_TIME (target V).
        Post-pulse/generic failure: BL_FAILED (AR: EARLY_STOP). A missing generic chunk (None) is
        BL_FAILED.
        """
        if chunk is None:
            return BL_FAILED
        if not acquiredUntil(data, chunk.end):
            return None
        cached = self.results.get(chunk.index)
        if cached is not None:
            return BL_PASS if cached.passed else BL_FAILED

        tests = baselineTests(self.analysisType, chunk.kind)
        if not (tests.rmsShort or tests.rmsLong or tests.targetV or tests.leak):
            raise ValueError(f"{self.analysisType}: no baseline tests for {chunk.kind} chunk")
        if tests.leak and data.clampMode != 'VC':
            raise ValueError("leak current test needs voltage clamp data (pA)")
        if tests.targetV and self.targetV is None:
            raise ValueError(f"{self.analysisType}: target V test needs targetV")

        trace, dt = data.data, data.sampleInterval
        vals = {}
        flags = {}
        failed = False
        for name, run in (
            ('rmsShort', tests.rmsShort),
            ('rmsLong', tests.rmsLong),
            ('targetV', tests.targetV),
            ('leakCurrent', tests.leak),
        ):
            if failed:
                flags[name] = QC_NOT_REACHED
                continue
            if not run:
                flags[name] = QC_NOT_APPLICABLE
                continue
            if name == 'rmsShort':
                v = windowStat(trace, dt, chunk.end - RMS_SHORT_WINDOW, RMS_SHORT_WINDOW, 'rms')
                ok = v < self.rmsShortThreshold
            elif name == 'rmsLong':
                v = windowStat(trace, dt, chunk.start, chunk.length, 'rms')
                ok = v < self.rmsLongThreshold
            elif name == 'targetV':
                v = windowStat(trace, dt, chunk.start, chunk.length, 'avg')
                ok = abs(v - self.targetV) <= self.targetVThreshold
            else:
                v = windowStat(trace, dt, chunk.start, chunk.length, 'avg')
                ok = abs(v) <= self.maxLeakCurrent
            vals['average' if name == 'targetV' else name] = v
            flags[name] = QC_PASSED if ok else QC_FAILED
            failed = not ok

        passed = not failed
        if passed:
            code = BL_PASS
        elif chunk.kind == 'prePulse':
            code = REPURP_TIME if flags['targetV'] == QC_FAILED else EARLY_STOP
        else:
            code = EARLY_STOP if self.analysisType == 'AR' else BL_FAILED

        self.results[chunk.index] = ChunkResult(
            chunk,
            passed,
            code,
            rmsShortPassed=flags['rmsShort'],
            rmsLongPassed=flags['rmsLong'],
            targetVPassed=flags['targetV'],
            leakCurrentPassed=flags['leakCurrent'],
            **vals,
        )
        return code

    def evaluate(self, data: SweepData, chunks: Sequence[Optional[ChunkSpec]]) -> BaselineStatus:
        """Run the MIES chunk loop over *chunks* (index order) and return the status.

        - SE: every chunk is evaluated and must be decided (raises ValueError otherwise).
        - An undecided chunk ends the loop; it becomes BL_FAILED if it is the last chunk and the
          sweep is complete.
        - VM, AR, and chunk 0 of every type: a failure ends the loop. Later chunks: a failure tries
          the next chunk, a pass ends the loop.
        """
        t = self.analysisType
        n = len(chunks)
        if t == 'CR' and n < 3:
            raise ValueError("Chirp needs at least 3 baseline chunks")
        if t in ('PB', 'VM', 'AR') and n != 1:
            raise ValueError(f"{t} needs exactly 1 baseline chunk, got {n}")

        code: Optional[int] = None
        i = 0
        while i < n:
            code = self.evaluateChunk(data, chunks[i])
            if t == 'SE':
                if code is None:
                    raise ValueError("Seal evaluation chunk not acquired")
                i += 1
                continue
            if code is None:
                if i == n - 1 and data.complete:
                    code = BL_FAILED
                break
            if code != BL_PASS:
                if t in ('VM', 'AR') or i == 0:
                    break
            elif i > 0:
                break
            i += 1
        return BaselineStatus(code, i)


def repurposedTime(analysisType: str, leftover: float) -> float:
    """Return the s MIES adds to the next ITI after a REPURP_TIME stop (pre-pulse target V failure).

    *leftover* is the unacquired sweep time in s (``leftoverSweepTime``); it is included. CR: 6 s in
    total; DA: 5 s + leftover; others: 10 s + leftover.
    """
    if analysisType == 'CR':
        return 6.0
    base = 5.0 if analysisType == 'DA' else 10.0
    return base + leftover


def toMidSweepAction(
    code: Optional[int], analysisType: str, data: SweepData, reason: str = 'baseline QC'
) -> MidSweepAction:
    """Translate a MIES mid-sweep return code into a mid-sweep action (None: continue)."""
    if code == EARLY_STOP:
        return EarlyStop(reason)
    if code == REPURP_TIME:
        return EarlyStop(reason, extraIti=repurposedTime(analysisType, leftoverSweepTime(data)))
    return None


# --- pulse duration -------------------------------------------------------------------------------


def pulseDuration(
    command: np.ndarray, dt: float, onset: float, kind: Literal['square', 'ramp']
) -> float:
    """Return the pulse duration (ms) of DA *command* after *onset* (PSQ_DeterminePulseDuration).

    'square' (DA, RB): edges at ``min + eps`` after *onset*; works for positive and negative pulses.
    'ramp' (RA, CR): first crossing of 0 searching forward from *onset* and backward from the end.
    Raises ValueError when no edge is found or the duration is not positive.
    """
    p0 = igorRound(onset / dt)
    seg = np.asarray(command[p0:], dtype=float)
    if kind == 'ramp':
        fwd = findLevels(seg, 0.0)
        bwd = findLevels(seg[::-1], 0.0)
        if len(fwd) == 0 or len(bwd) == 0:
            raise ValueError("could not find the pulse edges")
        first = (p0 + fwd[0]) * dt
        last = (p0 + len(seg) - 1 - bwd[0]) * dt
        duration = last - first - dt
    else:
        level = float(np.nanmin(seg)) + _DA_EPS
        rise = findLevels(seg, level, 'rising')
        fall = findLevels(seg, level, 'falling')
        if len(rise) == 0 or len(fall) == 0:
            raise ValueError("could not find the pulse edges")
        first, last = (p0 + rise[0]) * dt, (p0 + fall[0]) * dt
        duration = last - first - dt if level > 0 else first - last + dt
    if not duration > 0:
        raise ValueError(f"pulse duration must be positive, got {duration}")
    return float(duration)


# --- spike detection ------------------------------------------------------------------------------


@dataclass(frozen=True)
class SpikeSearchResult:
    """Spike search outcome; ``positions`` (ms, sweep axis); ``window``: the searched span (ms)."""

    detected: bool
    count: int
    positions: np.ndarray = field(default_factory=lambda: np.empty(0))
    window: tuple[float, float] = (float('nan'), float('nan'))


def spikeSearchWindow(
    command: np.ndarray, dt: float, analysisType: str, offset: float, searchEnd: float = math.inf
) -> Optional[tuple[float, float]]:
    """Return the ``(first, last)`` ms span PSQ_SearchForSpikes searches, or None for "no spike".

    CR, VM: ``(offset, searchEnd)``. Others: from the pulse onset in the DA after *offset* (first
    crossing of ``min + eps``) to the pulse end (DA) or *searchEnd* (SP, RB, RA). An all-zero DA
    gives the whole wave for SP and None otherwise. Raises ValueError when the DA has no two edges.
    """
    if analysisType in ('CR', 'VM'):
        return offset, searchEnd
    p0 = igorRound(offset / dt)
    seg = np.asarray(command[p0:], dtype=float)
    lo, hi = float(np.nanmin(seg)), float(np.nanmax(seg))
    if lo == 0 and hi == 0:
        return (0.0, searchEnd) if analysisType == 'SP' else None
    levels = findLevels(seg, lo + _DA_EPS, maxLevels=2)
    if len(levels) != 2:
        raise ValueError("could not find two pulse edges in the DA")
    first, second = (p0 + levels) * dt
    return float(first), float(second if analysisType == 'DA' else searchEnd)


def chirpSpikePositions(
    trace: np.ndarray, dt: float, start: float, end: float, level: float
) -> np.ndarray:
    """Return spike peak times (ms) between *start* and *end* (PA_SpikePositionsForNonVC).

    Crossings of *level* (both edges, at most 2 per ms) are paired rise/fall after dropping an odd
    last one; a pair is a spike when it is at least 0.2 ms wide and holds a peak above *level* (box
    5).
    """
    p0 = max(0, igorRound(start / dt))
    p1 = min(len(trace) - 1, igorRound(end / dt)) if math.isfinite(end) else len(trace) - 1
    chunk = np.asarray(trace[p0 : p1 + 1], dtype=float)
    if len(chunk) < 2:
        return np.empty(0)
    maxLevels = max(1, igorRound(len(chunk) * dt) * 2)
    levels = findLevels(chunk, level, 'both', maxLevels=maxLevels)
    if len(levels) % 2:
        levels = levels[:-1]
    smooth = boxSmooth(chunk, CHIRP_PEAK_BOX)
    peaks = []
    for rise, fall in levels.reshape(-1, 2):
        if (fall - rise) * dt < CHIRP_MIN_SPIKE_WIDTH:
            continue
        i0, i1 = igorRound(rise), igorRound(fall)
        peak = _findPeak(smooth, i0, i1, level)
        if peak is not None:
            peaks.append((p0 + peak) * dt)
    return np.array(peaks)


def _findPeak(s: np.ndarray, i0: int, i1: int, minLevel: float) -> Optional[int]:
    # first interior local maximum above minLevel in s[i0..i1] (Igor FindPeak /M)
    for i in range(max(i0, 1), min(i1, len(s) - 2) + 1):
        if s[i] > minLevel and s[i] >= s[i - 1] and s[i] > s[i + 1]:
            return i
    return None


def searchForSpikes(
    data: SweepData,
    analysisType: str,
    offset: float,
    level: float,
    searchEnd: float = math.inf,
    numberOfSpikesReq: float = 1,
) -> SpikeSearchResult:
    """Search the acquired AD trace (mV) for spikes (PSQ_SearchForSpikes).

    *offset* is usually the stimset start; the window comes from ``spikeSearchWindow``.
    - CR: ``chirpSpikePositions``; *numberOfSpikesReq* must be inf.
    - ``numberOfSpikesReq == 1``: first crossing of *level*, either direction, box 3.
    - otherwise: rising crossings, box 3, at most *numberOfSpikesReq*; detected when that many are
      found (inf: at least one).
    """
    if not numberOfSpikesReq > 0:
        raise ValueError("numberOfSpikesReq must be > 0")
    req = numberOfSpikesReq if math.isinf(numberOfSpikesReq) else math.trunc(numberOfSpikesReq)
    if data.clampMode != 'IC':
        raise ValueError("spike search needs current clamp data (mV)")
    dt = data.sampleInterval
    window = spikeSearchWindow(data.command, dt, analysisType, offset, searchEnd)
    if window is None:
        return SpikeSearchResult(False, 0)
    first, last = window
    trace = acquired(data)

    if analysisType == 'CR':
        if not math.isinf(req):
            raise ValueError("Chirp spike search needs numberOfSpikesReq = inf")
        pos = chirpSpikePositions(trace, dt, first, last, level)
        return SpikeSearchResult(len(pos) > 0, len(pos), pos, window)
    if req == 1:
        pos = levelCrossings(trace, dt, first, last, level, 'both', SPIKE_BOX, maxLevels=1)
        return SpikeSearchResult(len(pos) > 0, len(pos), pos, window)
    pos = levelCrossings(trace, dt, first, last, level, 'rising', SPIKE_BOX, maxLevels=req)
    detected = len(pos) > 0 if math.isinf(req) else len(pos) == req
    return SpikeSearchResult(detected, len(pos), pos if detected else np.empty(0), window)


def apFrequency(
    data: SweepData, start: float, stop: float, level: float = AP_FREQUENCY_LEVEL
) -> float:
    """Return rising crossings of *level* per s in ``[start, stop)`` ms of the acquired AD trace.

    SweepFormula ``apfrequency(data, FULL)``: points ``round(start/dt) .. round(stop/dt)-1``, no
    smoothing, divided by that window's length; the window is clipped to the acquired data.
    """
    dt = data.sampleInterval
    trace = acquired(data)
    p0 = igorRound(start / dt)
    p1 = min(igorRound(stop / dt), len(trace))
    if p1 - p0 < 2:
        raise ValueError(f"AP frequency window [{start}, {stop}] ms holds no acquired data")
    count = len(findLevels(trace[p0:p1], level, 'rising'))
    return count / ((p1 - p0) * dt * 1e-3)


# --- sampling QC ----------------------------------------------------------------------------------


def defaultSamplingFrequency(analysisType: str) -> float:
    """Return the MIES ITC default ``SamplingFrequency`` (kHz): 200 for PB/SE/VM/AR, else 50."""
    return 200.0 if analysisType in ('PB', 'SE', 'VM', 'AR') else 50.0


def samplingQC(sampleInterval: float, expectedFrequency: float, tol: float = 1.0) -> bool:
    """Return the MIES sampling interval QC: actual rate vs *expectedFrequency* (kHz).

    MIES ``CheckIfClose(expected, actual, tol=1)``: *tol* is relative to both rates, so the default
    passes actual rates in ``[expected/2, 2·expected]`` (the factor-2 ends depend on float
    rounding). *sampleInterval* in ms. An expected rate of 0 fails.
    """
    actual = 1.0 / (sampleInterval * 1e-3)
    expected = expectedFrequency * 1e3
    if expected == 0:
        return False
    diff = abs(expected - actual)
    return diff / abs(expected) <= tol and diff / abs(actual) <= tol


# --- set bookkeeping ------------------------------------------------------------------------------


def determineSweepQCResults(
    sweepPassed: bool,
    samplingPassed: bool,
    sweepsInSet: int,
    acquiredSweeps: int,
    passedSweeps: int,
    requiredPasses: int = 1,
    failsAllowed: float = math.inf,
) -> SetAction:
    """Return what follows a sweep (PSQ_DetermineSweepQCResults).

    Counts are over the current set and include this sweep. A failed sweep returns 'abort' (MIES
    skips every remaining sweep, also later indexed sets) when the set can no longer reach
    *requiredPasses*, when ``fails >= failsAllowed``, or when sampling QC failed. A passed sweep
    returns 'endSetPassed' once *requiredPasses* is reached. Otherwise 'continue'.
    """
    fails = acquiredSweeps - passedSweeps
    if not sweepPassed:
        if (sweepsInSet - acquiredSweeps) < (requiredPasses - passedSweeps):
            return 'abort'
        if fails >= failsAllowed:
            return 'abort'
        if not samplingPassed:
            return 'abort'
    elif passedSweeps >= requiredPasses:
        return 'endSetPassed'
    return 'continue'


# --- DAScale limit --------------------------------------------------------------------------------


def dascaleOutOfRange(
    dascale: float, stimsetMin: float, stimsetMax: float, commandLimit: float, holding: float = 0.0
) -> bool:
    """Return True when *dascale* drives the DA to or beyond *commandLimit* (SetDAScale limitCheck).

    *stimsetMin*/*stimsetMax* are the extremes of the next sweep's stimset wave at DAScale 1;
    *holding* is added to every sample when the DA also carries the holding command. Units: pA (IC)
    or mV (VC).
    """
    extremes = (dascale * stimsetMin + holding, dascale * stimsetMax + holding)
    return max(abs(v) for v in extremes) >= commandLimit
