"""Extract the production stimset definitions and frozen noise assets from a recorded MIES cell.

Usage::

    python -m acq4.util.allen_stimsets.tools.extract_assets <cell.nwb> <cell.pxp> [outdir]

Stimset definitions come from the NWB's ``/general/stimsets``. Noise epochs (not reproducible
outside Igor: xoshiro seeding and FilterIIR) are taken from the float32 stimset waves saved in the
``.pxp``, stored once per noise shape normalized to unit peak-to-peak, and referenced as custom
epochs.
"""

from __future__ import annotations

import json
import lzma
import struct
import sys
from pathlib import Path
from typing import Iterable

import numpy as np

from ..stimset import ASSET_DIR, StimsetDef, _segmentLength, loadStimsets, noiseAssetKey

PRODUCTION_STIMSETS = (
    'EXTPSMOKET180424_DA_0',
    'EXTPINBATH180424_DA_0',
    'EXTPCllATT180424_DA_0',
    'EXTPBREAKN180424_DA_0',
    'X0NRMP_DA_0',
    'X1PS_SubThresh_DA_0',
    'X2SP_Search_DA_0',
    'X3SP_Rheo_DA_0',
    'X4LP_Search_DA_0',
    'X5LP_Rheo_DA_0',
    'X6PS_SupraThresh_DA_0',
    'X6PS_SupraThresh_DA_1',
    'X7RAMPN0_DA_0',
    'X7RampN1_DA_0',
    'X7RampN2_DA_0',
    'X7RampN3_DA_0',
    'C2CHIRPA180503_DA_0',
    'C2CHIRPB180503_DA_0',
    'EXTPEXPEND180424_DA_0',
)

STIMSET_FOLDER = 'MIES:WaveBuilder:SavedStimulusSets:DA'
NOISE_SCALE_BITS = 16  # quantization step 2**-16 of the peak-to-peak amplitude

_WAVE_RECORD, _FOLDER_START, _FOLDER_END = 3, 9, 10
_NUMPY_TYPES = {2: '<f4', 4: '<f8'}


def readPxpWaves(
    path: Path | str, names: Iterable[str], folder: str = STIMSET_FOLDER
) -> dict[str, np.ndarray]:
    """Read Igor version-5 binary waves *names* in data folder *folder* from a packed experiment.

    Returns ``{name: array}`` shaped (columns, rows), i.e. one row per stimset sweep. Name matching
    is case-insensitive; missing waves are absent from the result.
    """
    wanted = {n.lower(): n for n in names}
    out: dict[str, np.ndarray] = {}
    path_: list[str] = []
    with open(path, 'rb') as f:
        pos = 0
        while len(out) < len(wanted):
            f.seek(pos)
            header = f.read(8)
            if len(header) < 8:
                break
            recordType, _, numBytes = struct.unpack('<HhI', header)
            recordType &= 0x7FFF
            if recordType == _FOLDER_START:
                path_.append(f.read(32).split(b'\0')[0].decode('latin1'))
            elif recordType == _FOLDER_END:
                path_.pop()
            elif recordType == _WAVE_RECORD and ':'.join(path_) == folder:
                binHeader, waveHeader = f.read(64), f.read(320)
                if struct.unpack('<h', binHeader[:2])[0] == 5:
                    name = waveHeader[28:60].split(b'\0')[0].decode('latin1')
                    if name.lower() in wanted:
                        npnts = struct.unpack('<i', waveHeader[12:16])[0]
                        waveType = struct.unpack('<h', waveHeader[16:18])[0]
                        dims = [d for d in struct.unpack('<4i', waveHeader[68:84]) if d > 0]
                        dtype = np.dtype(_NUMPY_TYPES[waveType])
                        data = np.frombuffer(f.read(npnts * dtype.itemsize), dtype=dtype)
                        out[wanted[name.lower()]] = data.reshape(
                            dims[::-1] if len(dims) > 1 else (1, -1)
                        )
            pos += 8 + numBytes
    return out


def encodeNoise(r: np.ndarray, scaleBits: int = NOISE_SCALE_BITS) -> tuple[bytes, str]:
    """Return lzma-compressed second differences of round(r * 2**scaleBits) and their dtype."""
    q = np.round(r * 2.0**scaleBits).astype(np.int64)
    d2 = np.diff(np.concatenate([[0, 0], q]), 2)
    span = np.abs(d2).max()
    dtype = '<i1' if span < 2**7 else '<i2' if span < 2**15 else '<i4'
    return lzma.compress(d2.astype(dtype).tobytes(), preset=9 | lzma.PRESET_EXTREME), dtype


def _noiseName(key: dict) -> str:
    return f"noise_{key['duration']:g}ms_seed{key['seed']:.15g}"


def extract(nwbPath: Path | str, pxpPath: Path | str, outDir: Path | str = ASSET_DIR) -> dict:
    """Write production_stimsets.json, frozen_noise.json and frozen_noise.npz into *outDir*.

    Returns, per noise asset, its size and the largest error (pA) of the reproduced epochs.
    """
    outDir = Path(outDir)
    outDir.mkdir(parents=True, exist_ok=True)
    allStimsets = loadStimsets(nwbPath)
    selected: dict[str, StimsetDef] = {}
    queue = list(PRODUCTION_STIMSETS)
    while queue:
        s = allStimsets[queue.pop()]
        if s.name not in selected:
            selected[s.name] = s
            queue.extend(dep.name for dep in s.dependencies.values())

    groups: dict[str, list[tuple[StimsetDef, int]]] = {}
    for s in selected.values():
        for i, ep in enumerate(s.epochs):
            if ep.type == 'noise':
                groups.setdefault(_noiseName(noiseAssetKey(ep)), []).append((s, i))
    waves = readPxpWaves(pxpPath, {s.name for members in groups.values() for s, _ in members})

    def epochSamples(s: StimsetDef, i: int) -> np.ndarray:
        start = sum(_segmentLength(s, ep) for ep in s.epochs[:i])
        n = _segmentLength(s, s.epochs[i])
        sweeps = waves[s.name]
        if not all(np.array_equal(sweeps[0], col) for col in sweeps[1:]):
            raise ValueError(f"{s.name}: stimset sweeps differ")
        return sweeps[0][start : start + n].astype(np.float64)

    index, blobs, summary = {}, {}, {}
    for name, members in groups.items():
        ref, refIdx = max(members, key=lambda m: abs(m[0].epochs[m[1]].amplitude))
        refEp = ref.epochs[refIdx]
        r = (epochSamples(ref, refIdx) - refEp.offset) / refEp.amplitude
        blob, dtype = encodeNoise(r)
        q = np.round(r * 2.0**NOISE_SCALE_BITS) / 2.0**NOISE_SCALE_BITS
        maxErr = 0.0
        for s, i in members:
            ep = s.epochs[i]
            rebuilt = (ep.amplitude * q + ep.offset).astype(np.float32).astype(np.float64)
            maxErr = max(maxErr, float(np.abs(rebuilt - epochSamples(s, i)).max()))
        blobs[name] = np.frombuffer(blob, dtype=np.uint8)
        index[name] = {
            'length': len(r),
            'scaleBits': NOISE_SCALE_BITS,
            'dtype': dtype,
            'source': noiseAssetKey(refEp),
            'extractedFrom': f'{Path(pxpPath).name}:{ref.name} epoch {refIdx}',
        }
        summary[name] = {
            'maxErrorPA': maxErr,
            'bytes': len(blob),
            'members': [f'{s.name} E{i}' for s, i in members],
        }

    stimsets = {}
    for s in sorted(selected.values(), key=lambda s: s.name):
        d = s.toDict()
        for i, ep in enumerate(s.epochs):
            if ep.type == 'noise':
                d['epochs'][i] = {
                    'type': 'custom',
                    'duration': ep.duration,
                    'amplitude': ep.amplitude,
                    'offset': ep.offset,
                    'params': {
                        'asset': _noiseName(noiseAssetKey(ep)),
                        'source': dict(type='noise', **ep.params),
                    },
                }
        stimsets[s.name] = d

    with open(outDir / 'production_stimsets.json', 'w') as fh:
        json.dump({'source': Path(nwbPath).name, 'stimsets': stimsets}, fh, indent=1)
    with open(outDir / 'frozen_noise.json', 'w') as fh:
        json.dump(index, fh, indent=1)
    np.savez(outDir / 'frozen_noise.npz', **blobs)
    return summary


if __name__ == '__main__':
    result = extract(*sys.argv[1:])
    print(json.dumps(result, indent=1))
