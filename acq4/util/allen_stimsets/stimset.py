"""MIES stimset definitions (WaveBuilder WP/WPT/SegWvType) and sweep construction."""

from __future__ import annotations

import dataclasses
import json
import lzma
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .core import MIN_SAMPLE_INTERVAL, ClampMode, Epoch, EpochTable, TestPulseSettings
from .mies_nwb import decodeParams

ASSET_DIR = Path(__file__).parent / 'assets'

# WaveBuilder epoch types in WP/WPT layer order, and the names MIES writes into epoch tags.
EPOCH_TYPES = ('square', 'ramp', 'noise', 'sin', 'saw', 'pulseTrain', 'psc', 'custom', 'combine')
_MIES_TYPE_NAMES = {
    'square': 'Square pulse',
    'ramp': 'Ramp',
    'noise': 'Noise',
    'sin': 'Sin Wave',
    'saw': 'Saw tooth',
    'pulseTrain': 'Pulse Train',
    'psc': 'PSC',
    'custom': 'Custom Wave',
    'combine': 'Combine',
}
_NOISE_TYPES = ('white', 'pink', 'brown')
_NOISE_BUILD_RESOLUTIONS = (1, 5, 10, 20, 40, 60, 80, 100)
_COMBINE_FORMULA_VERSION = '1'
_NOISE_GEN_LINEAR_CONGRUENTIAL, _NOISE_GEN_MERSENNE_TWISTER = 1, 2
_GENERATED_TYPES = ('square', 'ramp', 'noise', 'sin', 'custom', 'combine')
_TP_BASELINE_FRACTION_RANGE = (0.25, 0.49)

# WP rows holding per-sweep deltas, and WPT rows holding explicit delta lists.
_WP_DELTA_ROWS = {
    1: 'Duration delta',
    3: 'Amplitude delta',
    5: 'Offset delta',
    7: 'Frequency delta',
    9: 'Train pulse duration delta',
    11: 'PSC exp rise time delta',
    13: 'PSC exp decay time 1/2 delta',
    15: 'PSC exp decay time 2/2 delta',
    17: 'PSC ratio decay times delta',
    21: 'Low pass filter cut off delta',
    23: 'High pass filter cut off delta',
    25: 'Chirp end frequency delta',
    27: 'Noise filter order delta',
    29: 'PT first mixed frequency delta',
    31: 'PT last mixed frequency delta',
    47: 'Number of pulses delta',
}
_WPT_LDEL_ROWS = range(11, 27)
_SET = 99  # WPT column for set-wide entries


@dataclass
class EpochDef:
    """One WaveBuilder epoch. Times in ms; amplitudes in stimset units (scaled later by DAScale).

    ``params`` by type:

    - noise: lowPassCutoff, highPassCutoff (Hz), filterOrder, noiseType, buildResolution, seed, rng,
      reseedPerStep
    - sin: frequency, endFrequency (Hz), logChirp, function ('sin' | 'cos')
    - custom: ``asset`` (frozen waveform name; segment = amplitude x asset + offset) or ``wave``
      (MIES wave path, not reproducible); ``source`` holds the original epoch definition
    - combine: formula, formulaVersion
    """

    type: str  # one of EPOCH_TYPES
    duration: float
    amplitude: float = 0.0
    offset: float = 0.0
    params: dict[str, Any] = field(default_factory=dict)  # type-specific WP/WPT values, decoded


@dataclass
class StimsetDef:
    """A MIES stimset: epochs, sweep count, ITI, and its analysis function with decoded parameters.

    ``params`` maps analysis parameter names to Python values: float for 'variable', str for
    'string', list[float] for 'wave', list[str] for 'textwave'. ``dependencies`` maps the lower-case
    names of stimsets referenced by combine epochs to their definitions. ``deltas`` lists the
    nonzero WaveBuilder per-sweep delta settings, which are not supported.
    """

    name: str  # MIES name including channel suffix, e.g. 'X1PS_SubThresh_DA_0'
    epochs: list[EpochDef]
    numSweeps: int
    iti: float  # s
    analysisFunction: Optional[str] = None
    params: dict[str, Any] = field(default_factory=dict)
    flipped: bool = False
    deltas: dict[str, Any] = field(default_factory=dict)
    dependencies: dict[str, 'StimsetDef'] = field(default_factory=dict, repr=False, compare=False)
    _gridCache: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    def wave(self, setSweepIndex: int, sampleInterval: float) -> np.ndarray:
        """Return one sweep's stimset wave at *sampleInterval* (ms), DAScale 1, as MIES plays it.

        Float32. DAQ sample p takes WaveBuilder sample round(d * p), d = sampleInterval / 0.005 ms.
        Raises NotImplementedError for WaveBuilder features that are not reproduced.
        """
        return _decimate(self.gridWave(setSweepIndex), sampleInterval)

    def extremes(self, setSweepIndex: int) -> tuple[float, float]:
        """Return (min, max) of one sweep's stimset wave at DAScale 1, for the DAScale limit check."""
        w = self.gridWave(setSweepIndex)
        return (float(w.min()), float(w.max())) if len(w) else (0.0, 0.0)

    def gridWave(self, setSweepIndex: int) -> np.ndarray:
        """Return the float32 stimset wave for one sweep on the 0.005 ms WaveBuilder grid."""
        self._checkSupported(setSweepIndex)
        cached = self._gridCache.get('wave')
        if cached is None:
            segments = [_segment(self, ep) for ep in self.epochs]
            cached = (
                np.concatenate(segments).astype(np.float32) if segments else np.zeros(0, np.float32)
            )
            self._gridCache['wave'] = cached
        return cached

    def epochTable(
        self, setSweepIndex: int, offset: float, sampleInterval: float = MIN_SAMPLE_INTERVAL
    ) -> EpochTable:
        """Return ``E<i>`` epochs (and chirp cycle sub-epochs) for one sweep, DAScale 1.

        Times in ms, shifted to start at *offset*, at the DAQ boundaries for *sampleInterval*.
        """
        self._checkSupported(setSweepIndex)
        gridLength = sum(_segmentLength(self, ep) for ep in self.epochs)
        n = _decimatedLength(gridLength, _decimationFactor(sampleInterval))
        entries = _stimsetEpochs(self, offset, offset + n * sampleInterval, sampleInterval, 1.0)
        return EpochTable(_sortedEpochs(entries))

    def _checkSupported(self, setSweepIndex: int) -> None:
        if not 0 <= setSweepIndex < self.numSweeps:
            raise IndexError(
                f"{self.name}: sweep {setSweepIndex} out of range (0..{self.numSweeps - 1})"
            )
        if self.deltas:
            raise NotImplementedError(
                f"{self.name}: WaveBuilder per-sweep deltas {sorted(self.deltas)}"
            )
        if self.flipped:
            raise NotImplementedError(f"{self.name}: WaveBuilder time-axis flipping")

    def toDict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation; dependencies are stored by name."""
        return {
            'name': self.name,
            'epochs': [dataclasses.asdict(ep) for ep in self.epochs],
            'numSweeps': self.numSweeps,
            'iti': self.iti,
            'analysisFunction': self.analysisFunction,
            'params': self.params,
            'flipped': self.flipped,
            'deltas': self.deltas,
            'dependencies': sorted(self.dependencies),
        }

    @classmethod
    def fromDict(cls, d: dict[str, Any]) -> StimsetDef:
        """Inverse of `toDict`; link ``dependencies`` afterwards with `linkDependencies`."""
        return cls(
            name=d['name'],
            epochs=[EpochDef(**ep) for ep in d['epochs']],
            numSweeps=d['numSweeps'],
            iti=d['iti'],
            analysisFunction=d['analysisFunction'],
            params=d['params'],
            flipped=d['flipped'],
            deltas=d.get('deltas', {}),
        )


def linkDependencies(stimsets: dict[str, StimsetDef]) -> None:
    """Fill ``dependencies`` of each stimset's combine epochs from *stimsets* (case-insensitive).

    Missing references and unsupported formulas are skipped; generating such a stimset raises.
    """
    byLower = {name.lower(): s for name, s in stimsets.items()}
    for s in stimsets.values():
        for ep in s.epochs:
            if ep.type != 'combine':
                continue
            try:
                terms = _parseFormula(ep.params.get('formula', ''), s.name)
            except NotImplementedError:
                continue
            for _, ref in terms:
                if ref in byLower:
                    s.dependencies[ref] = byLower[ref]


# --------------------------------------------------------------------------------------------------
# NWB reading


def _str(x) -> str:
    return x.decode('utf-8', 'replace') if isinstance(x, bytes) else str(x)


def stimsetFromWaves(
    name: str, wp: np.ndarray, wpt: np.ndarray, segWvType: np.ndarray
) -> StimsetDef:
    """Decode one stimset from its WP (88x100x9), WPT (51x100x9, text) and SegWvType (102) arrays.

    An 86-row WP (layout before the noise RNG rows) gets MIES's upgrade defaults (Mersenne Twister).
    """
    wp = np.asarray(wp)
    if wp.shape[0] == 86:
        wp = np.concatenate([wp, np.zeros((2,) + wp.shape[1:], wp.dtype)])
        wp[86], wp[87] = _NOISE_GEN_MERSENNE_TWISTER, _NOISE_GEN_LINEAR_CONGRUENTIAL
    elif wp.shape[0] != 88:
        raise NotImplementedError(f"{name}: WP layout with {wp.shape[0]} rows")
    seg = np.asarray(segWvType).ravel()
    wpt = np.vectorize(_str, otypes=[object])(np.asarray(wpt))
    numEpochs = int(seg[100])
    deltas: dict[str, Any] = {}
    epochs = []
    for e in range(numEpochs):
        t = int(seg[e])
        typ = EPOCH_TYPES[t]
        v = lambda row: float(wp[row, e, t])  # noqa: E731
        params: dict[str, Any] = {}
        if typ == 'noise':
            params = {
                'lowPassCutoff': v(20),
                'highPassCutoff': v(22),
                'filterOrder': v(26),
                'noiseType': _NOISE_TYPES[int(v(54))],
                'buildResolution': _NOISE_BUILD_RESOLUTIONS[int(v(55))],
                'seed': v(48) if v(39) else float(seg[97]),
                'rng': int(v(86)),
                'reseedPerStep': bool(v(49)),
            }
        elif typ in ('sin', 'saw'):
            params = {'frequency': v(6)}
            if typ == 'sin':
                params.update(
                    endFrequency=v(24), logChirp=bool(v(43)), function='cos' if v(53) else 'sin'
                )
        elif typ == 'pulseTrain':
            params = {'frequency': v(6), 'pulseDuration': v(8), 'numberOfPulses': v(45)}
        elif typ == 'psc':
            params = {
                'tauRise': v(10),
                'tauDecay1': v(12),
                'tauDecay2': v(14),
                'tauDecay2Weight': v(16),
            }
        elif typ == 'custom':
            params = {'wave': wpt[0, e, 7]}
        elif typ == 'combine':
            params = {'formula': wpt[6, e, 8], 'formulaVersion': wpt[7, e, 8]}
        for row, label in _WP_DELTA_ROWS.items():
            if wp[row, e, t] != 0:
                deltas[f'E{e} {label}'] = float(wp[row, e, t])
        for row in _WPT_LDEL_ROWS:
            if wpt[row, e, t]:
                deltas[f'E{e} explicit delta row {row}'] = wpt[row, e, t]
        epochs.append(EpochDef(typ, duration=v(0), amplitude=v(2), offset=v(4), params=params))
    if seg[96] != 0:
        deltas['ITI delta'] = float(seg[96])
    if wpt[28, _SET, 0]:
        deltas['ITI explicit delta'] = wpt[28, _SET, 0]
    return StimsetDef(
        name=name,
        epochs=epochs,
        numSweeps=int(seg[101]),
        iti=float(seg[99]),
        analysisFunction=wpt[9, _SET, 0] or None,
        params=decodeParams(wpt[29, _SET, 0]),
        flipped=bool(seg[98]),
        deltas=deltas,
    )


def loadStimsets(path: Path | str) -> dict[str, StimsetDef]:
    """Read every stimset from a MIES NWB (stimset file or recorded experiment), keyed by name.

    Reads ``/general/stimsets/<name>_{WP,WPT,SegWvType}`` and links combine dependencies.
    """
    import h5py

    with h5py.File(path, 'r') as f:
        g = f['general/stimsets']
        names = sorted(k[: -len('_SegWvType')] for k in g if k.endswith('_SegWvType'))
        stimsets = {
            name: stimsetFromWaves(
                name, g[name + '_WP'][()], g[name + '_WPT'][()], g[name + '_SegWvType'][()]
            )
            for name in names
            if name + '_WP' in g and name + '_WPT' in g
        }
    linkDependencies(stimsets)
    return stimsets


def loadProductionStimsets() -> dict[str, StimsetDef]:
    """Return the production patch-seq stimsets frozen in ``assets/production_stimsets.json``.

    Noise epochs are stored as custom epochs backed by frozen noise assets.
    """
    with open(ASSET_DIR / 'production_stimsets.json') as fh:
        data = json.load(fh)
    stimsets = {name: StimsetDef.fromDict(d) for name, d in data['stimsets'].items()}
    linkDependencies(stimsets)
    return stimsets


# --------------------------------------------------------------------------------------------------
# Frozen noise assets


@lru_cache(maxsize=1)
def _frozenNoiseIndex() -> dict[str, dict[str, Any]]:
    path = ASSET_DIR / 'frozen_noise.json'
    if not path.exists():
        return {}
    with open(path) as fh:
        return json.load(fh)


@lru_cache(maxsize=8)
def frozenNoise(name: str) -> np.ndarray:
    """Return frozen noise asset *name*: float64 on the 0.005 ms grid, max - min = 1, no offset.

    Stored as lzma-compressed second differences of round(r * 2**scaleBits).
    """
    meta = _frozenNoiseIndex()[name]
    with np.load(ASSET_DIR / 'frozen_noise.npz') as npz:
        raw = lzma.decompress(npz[name].tobytes())
    d2 = np.frombuffer(raw, dtype=meta['dtype']).astype(np.int64)
    q = np.cumsum(np.cumsum(d2))
    assert len(q) == meta['length']
    return q / 2.0 ** meta['scaleBits']


def noiseAssetKey(ep: EpochDef) -> dict[str, Any]:
    """Return the parameters that fix a noise epoch's shape (all but amplitude and offset)."""
    p = ep.params
    return {
        'duration': ep.duration,
        'lowPassCutoff': p['lowPassCutoff'],
        'highPassCutoff': p['highPassCutoff'],
        'filterOrder': p['filterOrder'],
        'noiseType': p['noiseType'],
        'buildResolution': p['buildResolution'],
        'seed': p['seed'],
        'rng': p['rng'],
    }


def _findFrozenNoise(ep: EpochDef) -> Optional[str]:
    key = noiseAssetKey(ep)
    for name, meta in _frozenNoiseIndex().items():
        if meta['source'] == key:
            return name
    return None


# --------------------------------------------------------------------------------------------------
# Wave generation on the WaveBuilder grid


def _numPoints(duration: float) -> int:
    return int(math.ceil(duration / MIN_SAMPLE_INTERVAL))


def _checkEpochType(stimset: StimsetDef, ep: EpochDef) -> None:
    if ep.type not in _GENERATED_TYPES:
        raise NotImplementedError(
            f"{stimset.name}: WaveBuilder epoch type {_MIES_TYPE_NAMES[ep.type]!r}"
        )


def _segmentLength(stimset: StimsetDef, ep: EpochDef) -> int:
    _checkEpochType(stimset, ep)
    if ep.type == 'combine':
        terms = _parseFormula(ep.params['formula'], stimset.name)
        return min(len(_dependency(stimset, ref).gridWave(0)) for _, ref in terms)
    if ep.type == 'custom':
        return len(_customWave(stimset, ep))
    if ep.duration == 0:
        return 0
    return _numPoints(_checkedDuration(stimset, ep))


def _checkedDuration(stimset: StimsetDef, ep: EpochDef) -> float:
    if ep.duration < 0 or not math.isfinite(ep.duration):
        raise ValueError(f"{stimset.name}: invalid epoch duration {ep.duration}")
    return ep.duration


def _segment(stimset: StimsetDef, ep: EpochDef) -> np.ndarray:
    """Return one epoch's samples (float64 before the stimset's float32 rounding)."""
    _checkEpochType(stimset, ep)
    if ep.type == 'combine':
        return _combineSegment(stimset, ep)
    if ep.type == 'custom':
        seg = _customWave(stimset, ep) * ep.amplitude
    else:
        n = _segmentLength(stimset, ep)
        if n == 0:
            return np.zeros(0)
        p = np.arange(n, dtype=np.float64)
        if ep.type == 'square':
            seg = np.full(n, ep.amplitude)
        elif ep.type == 'ramp':
            seg = (ep.amplitude * MIN_SAMPLE_INTERVAL / ep.duration) * p
        elif ep.type == 'sin':
            seg = _trigSegment(ep, p * MIN_SAMPLE_INTERVAL)
        else:
            seg = _noiseSegment(stimset, ep) * ep.amplitude
    return seg + ep.offset if ep.offset != 0 else seg


def _chirpConstants(ep: EpochDef) -> tuple[float, float, float, float]:
    f0 = ep.params['frequency'] / 1000
    k0 = math.log(f0)
    k1 = (math.log(ep.params['endFrequency'] / 1000) - k0) / ep.duration
    k2 = 2 * math.pi * math.exp(k0) / k1
    k3 = math.fmod(k2, 2 * math.pi)
    return k0, k1, k2, k3


def _trigSegment(ep: EpochDef, x: np.ndarray) -> np.ndarray:
    fn = np.cos if ep.params['function'] == 'cos' else np.sin
    if ep.params['logChirp']:
        _, k1, k2, k3 = _chirpConstants(ep)
        return ep.amplitude * fn(k2 * np.exp(k1 * x) - k3)
    return ep.amplitude * fn(2 * math.pi * (ep.params['frequency'] / 1000) * x)


def _noiseSegment(stimset: StimsetDef, ep: EpochDef) -> np.ndarray:
    if ep.params['reseedPerStep'] and stimset.numSweeps > 1:
        raise NotImplementedError(
            f"{stimset.name}: noise reseeded per sweep (\"Reseed RNG for each step\")"
        )
    name = _findFrozenNoise(ep)
    if name is None:
        raise NotImplementedError(
            f"{stimset.name}: noise epoch generation (MIES WB_NoiseSegment); "
            f"no frozen noise asset for {noiseAssetKey(ep)}"
        )
    wave = frozenNoise(name)
    if len(wave) != _numPoints(ep.duration):
        raise ValueError(f"{stimset.name}: frozen noise {name!r} has {len(wave)} samples")
    return wave


def _customWave(stimset: StimsetDef, ep: EpochDef) -> np.ndarray:
    name = ep.params.get('asset')
    if name is None:
        raise NotImplementedError(
            f"{stimset.name}: custom epoch wave {ep.params.get('wave')!r} "
            "(only frozen assets are available)"
        )
    return frozenNoise(name)


_TERM_RE = re.compile(
    r'\s*([+-]?)\s*(?:(\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)\s*\*\s*)?([A-Za-z_][A-Za-z0-9_]*)\?\s*'
)


def _parseFormula(formula: str, stimsetName: str) -> list[tuple[float, str]]:
    """Parse a combine formula ``[k*]name? (+|-) [k*]name? ...`` into (factor, name) terms."""
    terms = []
    pos = 0
    while pos < len(formula):
        m = _TERM_RE.match(formula, pos)
        if m is None or (terms and not m.group(1)) or m.end() == pos:
            raise NotImplementedError(f"{stimsetName}: combine formula {formula!r}")
        factor = float(m.group(2)) if m.group(2) else 1.0
        terms.append((-factor if m.group(1) == '-' else factor, m.group(3).lower()))
        pos = m.end()
    if not terms:
        raise NotImplementedError(f"{stimsetName}: empty combine formula")
    return terms


def _dependency(stimset: StimsetDef, ref: str) -> StimsetDef:
    try:
        return stimset.dependencies[ref]
    except KeyError:
        raise KeyError(
            f"{stimset.name}: combine formula references unknown stimset {ref!r}"
        ) from None


def _combineSegment(stimset: StimsetDef, ep: EpochDef) -> np.ndarray:
    if ep.params.get('formulaVersion') != _COMBINE_FORMULA_VERSION:
        raise NotImplementedError(
            f"{stimset.name}: combine formula version {ep.params.get('formulaVersion')!r}"
        )
    terms = _parseFormula(ep.params['formula'], stimset.name)
    deps = [(k, _dependency(stimset, ref)) for k, ref in terms]
    if min(dep.numSweeps for _, dep in deps) < stimset.numSweeps:
        raise ValueError(f"{stimset.name}: combine references a stimset with fewer sweeps")
    # sweeps of a stimset without deltas are identical, so sweep 0 stands for every sweep
    waves = [(k, dep.gridWave(0)) for k, dep in deps]
    n = min(len(w) for _, w in waves)
    out = np.zeros(n)
    for k, w in waves:
        out += k * w[:n].astype(np.float64)
    return out


# --------------------------------------------------------------------------------------------------
# DAQ sampling and epochs


def _decimationFactor(sampleInterval: float) -> float:
    d = sampleInterval / MIN_SAMPLE_INTERVAL
    return float(round(d)) if abs(d - round(d)) < 1e-9 else d


def _decimatedLength(n: int, d: float) -> int:
    """Number of DAQ samples p with round(d * p) <= n - 1."""
    return int(math.ceil((n - 0.5) / d)) if n > 0 else 0


def _decimate(grid: np.ndarray, sampleInterval: float) -> np.ndarray:
    d = _decimationFactor(sampleInterval)
    n = _decimatedLength(len(grid), d)
    idx = np.minimum(np.floor(d * np.arange(n) + 0.5).astype(np.int64), len(grid) - 1)
    return grid[idx]


def _indexAfterDecimation(i: float, d: float) -> float:
    """MIES IndexAfterDecimation: last DAQ index p with round(d * p) < i (-1 for i == 0)."""
    return -1 if i == 0 else math.floor((i - 0.5) / d)


@dataclass
class _EpochEntry:
    name: str
    start: float
    end: float
    level: int
    amplitude: float = float('nan')
    tags: dict[str, str] = field(default_factory=dict)


def _sortedEpochs(entries: list[_EpochEntry]) -> list[Epoch]:
    entries = [e for e in entries if e.end - e.start > 1e-9]
    entries.sort(key=lambda e: (e.start, -e.end, e.level))
    return [Epoch(e.name, e.start, e.end, e.amplitude, e.tags) for e in entries]


def _epochAmplitude(ep: EpochDef) -> float:
    if ep.type == 'combine' or (ep.type == 'custom' and 'asset' not in ep.params):
        return float('nan')
    return ep.amplitude


def _stimsetEpochs(
    stimset: StimsetDef, stimsetBegin: float, stimsetEnd: float, dt: float, scale: float
) -> list[_EpochEntry]:
    """Return E<i> epochs and sine cycle sub-epochs (ms) as MIES EP_AddEpochsFromStimSetNote."""
    d = _decimationFactor(dt)
    lengths = [_segmentLength(stimset, ep) for ep in stimset.epochs]
    offsets = np.concatenate([[0], np.cumsum(lengths)[:-1]]) if lengths else []
    offsetTimes = [(_indexAfterDecimation(o, d) + 1) * dt for o in offsets]
    entries = []
    for i, ep in enumerate(stimset.epochs):
        if lengths[i] == 0:
            continue
        endIndex = _indexAfterDecimation(offsets[i] + lengths[i], d) + 1
        begin = stimsetBegin + offsetTimes[i]
        if begin >= stimsetEnd:
            break
        end = min(stimsetBegin + endIndex * dt, stimsetEnd)
        sourceType = ep.params.get('source', {}).get('type', ep.type)
        tags = {'Type': 'Epoch', 'EpochType': _MIES_TYPE_NAMES[sourceType], 'Epoch': str(i)}
        amplitude = scale * _epochAmplitude(ep)
        entries.append(_EpochEntry(f'E{i}', begin, end, 1, amplitude, tags))
        if ep.type == 'sin':
            entries.extend(
                _trigSubEpochs(ep, i, offsets[i], stimsetBegin, begin, end, d, dt, amplitude, tags)
            )
    return entries


def _inflectionIndices(ep: EpochDef) -> list[int]:
    """WaveBuilder sample indices (within the epoch) of the sine/chirp zero crossings."""
    p = ep.params
    if ep.amplitude == 0 or p['frequency'] <= 0:
        return []
    if p['logChirp'] and (p['frequency'] == p['endFrequency'] or p['endFrequency'] <= 0):
        return []
    phase = 0.5 if p['function'] == 'cos' else 0.0
    dur = ep.duration
    if p['logChirp']:
        fs, fe = p['frequency'] / 1000, p['endFrequency'] / 1000
        phi, phii = fs / math.log(fe / fs), fe / math.log(fe / fs)
        lower = 2 * math.trunc(dur * phi) - phase
        upper = 2 * dur * phii - 2 * math.fmod(dur * phi, 1) - phase
        k0, k1, k2, k3 = _chirpConstants(ep)
        xzero = lambda c: 1 / k1 * math.log(((c + phase) * math.pi + k3) / k2)  # noqa: E731
    else:
        lower, upper = -phase, 2 * dur * (p['frequency'] / 1000) - phase
        k0 = 2 * math.pi * (p['frequency'] / 1000)
        xzero = lambda c: (c + phase) * math.pi / k0  # noqa: E731
    return [
        math.trunc(xzero(c) / MIN_SAMPLE_INTERVAL)
        for c in range(math.ceil(lower), math.floor(upper) + 1)
    ]


def _trigSubEpochs(
    ep, i, wbOffset, stimsetBegin, begin, end, d, dt, amplitude, tags
) -> list[_EpochEntry]:
    """Return ``E<i>_TG_C<n>`` cycles, ``_H<k>`` half cycles and ``E<i>_TG_I<n>`` partial cycles."""
    infl = _inflectionIndices(ep)
    ti = [
        min(stimsetBegin + (_indexAfterDecimation(wbOffset + x + 1, d) + 1) * dt, end) - begin
        for x in infl
    ]
    out = []
    prefix = f'E{i}_TG_'
    incomplete = 0

    def add(name, start, stop, level, lo, hi, extra):
        out.append(
            _EpochEntry(name, max(start, lo), min(stop, hi), level, amplitude, dict(tags, **extra))
        )

    n = len(ti)
    for j in range(0, n, 2):
        hasFull = j + 2 < n
        incStart = j == 0 and ti[j] != 0
        incEnd = not hasFull or j + 1 >= n
        if not hasFull or incStart:
            sb = begin if incStart else begin + ti[j]
            se = end if incEnd else begin + ti[j]
            if sb != se:
                add(
                    f'{prefix}I{incomplete}',
                    sb,
                    se,
                    2,
                    begin,
                    end,
                    {'IncompleteCycle': str(incomplete)},
                )
                incomplete += 1
        if hasFull:
            c = j // 2
            cb, ce = begin + ti[j], begin + ti[j + 2]
            add(f'{prefix}C{c}', cb, ce, 2, begin, end, {'Cycle': str(c)})
            for h in range(2):
                add(
                    f'{prefix}C{c}_H{h}',
                    begin + ti[j + h],
                    begin + ti[j + h + 1],
                    3,
                    cb,
                    ce,
                    {'Cycle': str(c), 'HalfCycle': str(h)},
                )
    if not ti:
        add(f'{prefix}I0', begin, end, 2, begin, end, {'IncompleteCycle': '0'})
    return out


@dataclass
class SweepCommand:
    """A built sweep: DA command (stimset x DAScale plus inserted TP, no holding) and its epochs."""

    command: np.ndarray  # mV (VC) or pA (IC)
    sampleInterval: float  # ms
    epochs: EpochTable
    stimsetStart: float  # ms, sweep time at which epoch E0 begins


def insertedTestPulsePoints(
    testPulse: TestPulseSettings, sampleInterval: float
) -> tuple[int, int, int]:
    """Return (total, pulse start, pulse length) of the inserted test pulse in DAQ samples.

    Computed as MIES TP_UpdateTPSettingsCalculatedImpl. Raises ValueError when the baseline fraction
    is outside [0.25, 0.49].
    """
    bf = testPulse.baselineFraction
    if not _TP_BASELINE_FRACTION_RANGE[0] <= bf <= _TP_BASELINE_FRACTION_RANGE[1]:
        raise ValueError(f"TP baseline fraction {bf} outside {_TP_BASELINE_FRACTION_RANGE}")
    pulse = math.trunc(testPulse.pulseDuration / sampleInterval)
    total = math.trunc(pulse / (1 - 2 * bf))
    start = math.trunc(bf * total)
    return total, start, pulse


def _igorRound(x: float) -> int:
    return int(math.floor(x + 0.5)) if x >= 0 else int(math.ceil(x - 0.5))


def buildSweep(
    stimset: StimsetDef,
    setSweepIndex: int,
    dascale: float,
    sampleInterval: float,
    clampMode: ClampMode,
    testPulse: Optional[TestPulseSettings],
    userOnsetDelay: float = 0.0,
    terminationDelay: float = 0.0,
) -> SweepCommand:
    """Assemble a sweep as MIES does: inserted TP (if *testPulse*), onset delay, stimset, end delay.

    Delays in ms, rounded to whole samples. The TP amplitude follows *clampMode* and is not scaled
    by *dascale*. Raises NotImplementedError for unsupported stimset features.
    """
    dt = sampleInterval
    stim = stimset.wave(setSweepIndex, dt)
    entries: list[_EpochEntry] = []
    nTP = 0
    if testPulse is not None:
        nTP, pulseStart, pulseLen = insertedTestPulsePoints(testPulse, dt)
        tpAmp = testPulse.amplitudeVC if clampMode == 'VC' else testPulse.amplitudeIC
        pulseEnd = pulseStart + pulseLen
        tpTags = {'Type': 'Inserted Testpulse'}
        entries += [
            _EpochEntry('TP', 0.0, nTP * dt, 0, tags=tpTags),
            _EpochEntry('TP_B0', 0.0, pulseStart * dt, 1, tags=dict(tpTags, SubType='Baseline')),
            _EpochEntry(
                'TP_P', pulseStart * dt, pulseEnd * dt, 1, tpAmp, dict(tpTags, SubType='Pulse')
            ),
            _EpochEntry('TP_B1', pulseEnd * dt, nTP * dt, 1, tags=dict(tpTags, SubType='Baseline')),
        ]
    nUser = _igorRound(userOnsetDelay / dt)
    nTerm = _igorRound(terminationDelay / dt)
    start = nTP + nUser
    stop = start + len(stim)
    command = np.zeros(stop + nTerm)
    if nTP:
        command[pulseStart:pulseEnd] = tpAmp
    command[start:stop] = dascale * stim.astype(np.float64)

    if nUser:
        entries.append(_EpochEntry('B0_OD', nTP * dt, start * dt, 0, tags={'Type': 'Baseline'}))
    if nTerm:
        entries.append(
            _EpochEntry('B0_TD', stop * dt, (stop + nTerm) * dt, 0, tags={'Type': 'Baseline'})
        )
    entries.append(_EpochEntry('ST', start * dt, stop * dt, 0, tags={'Type': 'Stimset'}))
    entries += _stimsetEpochs(stimset, start * dt, stop * dt, dt, dascale)
    return SweepCommand(command, dt, EpochTable(_sortedEpochs(entries)), stimsetStart=start * dt)
