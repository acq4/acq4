"""Tests for MIES stimset decoding, wave generation and sweep assembly.

Recorded-data tests compare against the DA (stimulus) series and the "Epochs" labnotebook entry of
production cells and skip when the share is unreachable. Known, intentional deviations from MIES:
the inserted TP pulse is ``pulseDuration`` long (MIES: one sample longer) and the stimset keeps its
last sample (MIES drops it), so the sweep is one sample longer.
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import pytest

from acq4.util.allen_stimsets import core
from acq4.util.allen_stimsets.stimset import (
    buildSweep,
    frozenNoise,
    linkDependencies,
    loadProductionStimsets,
    loadStimsets,
    stimsetFromWaves,
    insertedTestPulsePoints,
)

HUMAN = Path('//allen/programs/celltypes/production/humancelltypes/prod172')
MOUSE = Path('//allen/programs/celltypes/production/mousecelltypes/prod4159')
RECORDED = {
    'human_03.04': HUMAN / 'Ephys_Roi_Result_1544261931/H26.51.023.11.11.03.04.nwb',
    'human_06.02': HUMAN / 'Ephys_Roi_Result_1544224968/H26.51.023.11.11.06.02.nwb',
    'mouse_03.02.02': MOUSE / 'Ephys_Roi_Result_1539892860/Pvalb-IRES-Cre;Ai14-895872.03.02.02.nwb',
    'mouse_03.02.01': MOUSE / 'Ephys_Roi_Result_1539885953/Pvalb-IRES-Cre;Ai14-895872.03.02.01.nwb',
}
HUMAN_PXP = HUMAN / 'Ephys_Roi_Result_1544261931/H26.51.023.11.11.03.04.pxp'
ITC_COUNTS_PER_VOLT = 3200

PRODUCTION = {
    'EXTPSMOKET180424_DA_0': 'PSQ_AccessResistanceSmoke',
    'EXTPINBATH180424_DA_0': 'PSQ_PipetteInBath',
    'EXTPCllATT180424_DA_0': 'PSQ_SealEvaluation',
    'EXTPBREAKN180424_DA_0': 'PSQ_AccessResistanceSmoke',
    'X0NRMP_DA_0': 'PSQ_TrueRestingMembranePotential',
    'X1PS_SubThresh_DA_0': 'PSQ_DAScale',
    'X2SP_Search_DA_0': 'PSQ_SquarePulse',
    'X3SP_Rheo_DA_0': 'PSQ_Rheobase',
    'X4LP_Search_DA_0': 'PSQ_SquarePulse',
    'X5LP_Rheo_DA_0': 'PSQ_Rheobase',
    'X6PS_SupraThresh_DA_0': 'PSQ_DAScale',
    'X6PS_SupraThresh_DA_1': 'PSQ_DAScale',
    'X7RAMPN0_DA_0': 'PSQ_Ramp',
    'X7RampN1_DA_0': 'PSQ_Ramp',
    'X7RampN2_DA_0': 'PSQ_Ramp',
    'X7RampN3_DA_0': 'PSQ_Ramp',
    'C2CHIRPA180503_DA_0': 'PSQ_Chirp',
    'C2CHIRPB180503_DA_0': 'PSQ_Chirp',
    'EXTPEXPEND180424_DA_0': None,
    'z_rampepoch_da_0': None,
    'z_rampn1_da_0': None,
    'z_rampn2_da_0': None,
    'z_rampn3_da_0': None,
}


# --------------------------------------------------------------------------------------------------
# synthetic WaveBuilder waves


def _waves(epochs, numSweeps=1, iti=0.0, fn='', params=''):
    """Build WP/WPT/SegWvType; *epochs* lists (typeIndex, {wpRow: value}, {wptRow: text})."""
    wp = np.zeros((88, 100, 9))
    wp[39] = 1
    wpt = np.full((51, 100, 9), '', dtype=object)
    seg = np.zeros(102)
    for e, (t, rows, trows) in enumerate(epochs):
        seg[e] = t
        for r, v in rows.items():
            wp[r, e, t] = v
        for r, v in trows.items():
            wpt[r, e, t] = v
    seg[99], seg[100], seg[101] = iti, len(epochs), numSweeps
    wpt[9, 99, 0] = fn
    wpt[29, 99, 0] = params
    return wp, wpt, seg


def _stimset(name, epochs, **kw):
    return stimsetFromWaves(name, *_waves(epochs, **kw))


def test_decode_stimset_waves():
    s = _stimset(
        'T_DA_0',
        [
            (0, {0: 500}, {}),
            (1, {0: 1000, 2: 400, 4: 5}, {}),
            (3, {0: 20, 2: 1, 6: 0.4, 24: 40, 43: 1}, {}),
        ],
        numSweeps=3,
        iti=2.0,
        fn='PSQ_Ramp',
        params='NumberOfSpikes:variable=5',
    )
    assert [ep.type for ep in s.epochs] == ['square', 'ramp', 'sin']
    assert (s.numSweeps, s.iti, s.analysisFunction) == (3, 2.0, 'PSQ_Ramp')
    assert s.params == {'NumberOfSpikes': 5.0}
    assert s.epochs[1].amplitude == 400 and s.epochs[1].offset == 5
    assert s.epochs[2].params == {
        'frequency': 0.4,
        'endFrequency': 40.0,
        'logChirp': True,
        'function': 'sin',
    }
    assert not s.deltas


def test_decode_old_wp_layout_and_noise_params():
    wp, wpt, seg = _waves([(2, {0: 100, 2: 5, 20: 250, 22: 2, 26: 4, 48: 0.5}, {})])
    s = stimsetFromWaves('N_DA_0', wp[:86], wpt, seg)
    assert s.epochs[0].params == {
        'lowPassCutoff': 250.0,
        'highPassCutoff': 2.0,
        'filterOrder': 4.0,
        'noiseType': 'white',
        'buildResolution': 1,
        'seed': 0.5,
        'rng': 2,
        'reseedPerStep': False,
    }


def test_square_ramp_wave_and_decimation():
    s = _stimset('T_DA_0', [(0, {0: 1}, {}), (0, {0: 0.5, 2: 3}, {}), (1, {0: 1, 2: 2, 4: 1}, {})])
    grid = s.gridWave(0)
    assert grid.dtype == np.float32
    assert len(grid) == 200 + 100 + 200
    assert np.all(grid[:200] == 0) and np.all(grid[200:300] == 3)
    expected = (1 + 2 * 0.005 / 1 * np.arange(200)).astype(np.float32)
    assert np.array_equal(grid[300:], expected)
    w = s.wave(0, 0.02)
    assert len(w) == 125
    assert np.array_equal(w, grid[::4])
    # non-integer decimation rounds half away from zero, never past the last sample
    w = s.wave(0, 0.0125)
    idx = np.floor(2.5 * np.arange(len(w)) + 0.5).astype(int)
    assert len(w) == 200 and idx[-1] <= len(grid) - 1
    assert np.array_equal(w, grid[idx])


def test_unsupported_features_raise():
    with pytest.raises(NotImplementedError, match='delta'):
        _stimset('T_DA_0', [(0, {0: 10, 3: 5}, {})], numSweeps=2).wave(0, 0.02)
    with pytest.raises(NotImplementedError, match='Pulse Train'):
        _stimset('T_DA_0', [(5, {0: 10}, {})]).wave(0, 0.02)
    with pytest.raises(NotImplementedError, match='flipping'):
        stimsetFromWaves('T_DA_0', *_flipped()).wave(0, 0.02)
    with pytest.raises(NotImplementedError, match='frozen noise'):
        _stimset('T_DA_0', [(2, {0: 10, 2: 1, 48: 0.123, 86: 3}, {})]).wave(0, 0.02)
    with pytest.raises(NotImplementedError, match='custom epoch'):
        _stimset('T_DA_0', [(7, {}, {0: 'root:wave'})]).wave(0, 0.02)
    with pytest.raises(NotImplementedError, match='combine formula'):
        s = _stimset('T_DA_0', [(8, {}, {6: 'a?*b?', 7: '1'})])
        s.wave(0, 0.02)


def _flipped():
    wp, wpt, seg = _waves([(0, {0: 10}, {})])
    seg[98] = 1
    return wp, wpt, seg


def test_combine_epoch():
    a = _stimset('a_da_0', [(1, {0: 1, 2: 1}, {})], numSweeps=2)
    b = _stimset('b_da_0', [(0, {0: 0.5, 2: 2}, {})], numSweeps=2)
    c = _stimset(
        'C_DA_0', [(0, {0: 0.1}, {}), (8, {}, {6: 'a_da_0?-0.5*b_da_0?', 7: '1'})], numSweeps=2
    )
    linkDependencies({s.name: s for s in (a, b, c)})
    assert set(c.dependencies) == {'a_da_0', 'b_da_0'}
    grid = c.gridWave(1)
    n = len(b.gridWave(0))
    assert len(grid) == 20 + n
    expected = (a.gridWave(0)[:n].astype(np.float64) - 1.0).astype(np.float32)
    assert np.array_equal(grid[20:], expected)


def test_test_pulse_points_match_recorded_onset_delays():
    # (sample interval, LBN baseline fraction) -> LBN "Delay onset auto" (ms)
    for dt, bf, onset in ((0.005, 0.45, 100.0), (0.02, 0.4514, 102.88), (0.08, 0.4394, 82.48)):
        total, start, pulse = insertedTestPulsePoints(
            core.TestPulseSettings(10.0, bf, 10.0, -50.0), dt
        )
        assert total * dt == pytest.approx(onset)
        assert pulse * dt == pytest.approx(10.0)
    assert insertedTestPulsePoints(core.TestPulseSettings(10.0, 0.4514, 10.0, -50.0), 0.02) == (
        5144,
        2322,
        500,
    )
    with pytest.raises(ValueError):
        insertedTestPulsePoints(core.TestPulseSettings(10.0, 0.1, 10.0, -50.0), 0.02)


def test_build_sweep_layout():
    s = _stimset('T_DA_0', [(0, {0: 100}, {}), (0, {0: 50, 2: 1}, {}), (0, {0: 100}, {})])
    tp = core.TestPulseSettings(10.0, 0.25, 10.0, -50.0)
    sc = buildSweep(s, 0, 20.0, 0.02, 'IC', tp, userOnsetDelay=30.0, terminationDelay=10.0)
    dt = 0.02
    names = [e.name for e in sc.epochs]
    assert names == ['TP', 'TP_B0', 'TP_P', 'TP_B1', 'B0_OD', 'ST', 'E0', 'E1', 'E2', 'B0_TD']
    assert sc.epochs.get('TP').end == pytest.approx(20.0)
    assert sc.epochs.get('TP_P').start == pytest.approx(5.0) and sc.epochs.get(
        'TP_P'
    ).end == pytest.approx(15.0)
    assert sc.epochs.get('TP_P').amplitude == -50.0
    assert sc.stimsetStart == pytest.approx(50.0)
    assert (
        sc.epochs.get('E1').start == pytest.approx(150.0) and sc.epochs.get('E1').amplitude == 20.0
    )
    assert sc.epochs.get('B0_TD').end == pytest.approx(310.0)
    assert len(sc.command) == round(310.0 / dt)
    c = sc.command
    assert np.all(c[:250] == 0) and np.all(c[250:750] == -50) and np.all(c[750:7500] == 0)
    assert np.all(c[7500:10000] == 20) and np.all(c[10000:] == 0)
    vc = buildSweep(s, 0, 1.0, dt, 'VC', tp)
    assert vc.epochs.get('TP_P').amplitude == 10.0 and not vc.epochs.has('B0_OD')
    nt = buildSweep(s, 0, 1.0, dt, 'IC', None)
    assert nt.stimsetStart == 0 and not nt.epochs.has('TP') and len(nt.command) == 12500


def test_chirp_cycle_epochs():
    s = _stimset(
        'C_DA_0',
        [(0, {0: 100}, {}), (3, {0: 1000, 2: 1, 6: 2, 24: 20, 43: 1}, {}), (0, {0: 100}, {})],
    )
    table = s.epochTable(0, 0.0, 0.08)
    cycles = table.withPrefix('E1_TG_C')
    full = [e for e in cycles if '_H' not in e.name]
    assert full[0].name == 'E1_TG_C0' and full[0].start == pytest.approx(100.0, abs=0.08)
    assert all(a.end == pytest.approx(b.start) for a, b in zip(full, full[1:]))
    assert len(full) > 5


# --------------------------------------------------------------------------------------------------
# frozen production assets


def test_production_stimsets():
    prod = loadProductionStimsets()
    assert set(prod) == set(PRODUCTION)
    for name, fn in PRODUCTION.items():
        assert prod[name].analysisFunction == fn
    assert prod['X1PS_SubThresh_DA_0'].params['DAScales'] == [-30, -50, -70, -90, -110]
    assert prod['C2CHIRPA180503_DA_0'].params['UserOnsetDelay'] == 2000
    assert prod['EXTPBREAKN180424_DA_0'].params['NextIndexingEndStimSetName'] == 'X7RampN3_DA_0'
    n1 = prod['X7RampN1_DA_0']
    assert [ep.type for ep in n1.epochs] == ['square', 'custom', 'combine', 'square']
    assert set(n1.dependencies) == {'z_rampepoch_da_0', 'z_rampn1_da_0'}
    w = n1.wave(0, 0.02)
    assert len(w) == 4300000 // 4
    # ramp plus noise reaches ~400 pA at the end of the combine epoch
    assert 380 < w[(500 + 2000 + 16000) * 50 - 1] < 420


def test_frozen_noise_assets():
    for name, seconds in (
        ('noise_16000ms_seed0.992569669536755', 16),
        ('noise_2000ms_seed0.955728178360615', 2),
    ):
        r = frozenNoise(name)
        assert len(r) == seconds * 200000
        assert r.max() - r.min() == pytest.approx(1.0, abs=1e-4)


# --------------------------------------------------------------------------------------------------
# recorded data


def _s(x) -> str:
    return x.decode('utf-8', 'replace') if isinstance(x, bytes) else str(x)


class _RecordedCell:
    """Acquisition labnotebook values, Epochs and DA series of a recorded MIES NWB (headstage 0)."""

    def __init__(self, path):
        import h5py

        self.path = path
        with h5py.File(path, 'r') as f:
            g = f['general/labnotebook'][list(f['general/labnotebook'])[0]]
            self.nk = [_s(k) for k in g['numericalKeys'][0]]
            self.nv = g['numericalValues'][()]
            self.tk = [_s(k) for k in g['textualKeys'][0]]
            self.tv = g['textualValues'][()]
            self.series = {
                int(k.split('_')[1]): k for k in f['stimulus/presentation'] if k.endswith('DA0')
            }
        # TP-during-ITI rows (EntrySourceType 1) carry the preceding sweep's number
        daq = self.nv[:, self.nk.index('EntrySourceType'), 8] == 0
        self.numSweep = np.where(daq, self.nv[:, self.nk.index('SweepNum'), 8], np.nan)
        textSweep = [_s(x) for x in self.tv[:, self.tk.index('SweepNum'), 8]]
        self.textSweep = np.array([float(x) if x else np.nan for x in textSweep])

    def num(self, key, sweep):
        col = self.nk.index(key)
        for layer in (0, 8):
            vals = [v for v in self.nv[self.numSweep == sweep, col, layer] if np.isfinite(v)]
            if vals:
                return vals[-1]
        return np.nan

    def text(self, key, sweep):
        col = self.tk.index(key)
        vals = [_s(v) for v in self.tv[self.textSweep == sweep, col, 0] if _s(v)]
        return vals[-1] if vals else ''

    def stimulus(self, sweep):
        import h5py

        with h5py.File(self.path, 'r') as f:
            return f['stimulus/presentation'][self.series[sweep]]['data'][()].astype(np.float64)

    def epochs(self, sweep) -> dict[str, tuple[float, float, float]]:
        """Return {short name: (start ms, end ms, amplitude)} of MIES-made (level >= 0) epochs."""
        out = {}
        for entry in self.text('Epochs', sweep).split(':'):
            if not entry:
                continue
            parts = entry.rstrip(',').split(',')
            tags = dict(kv.split('=', 1) for kv in ','.join(parts[2:-1]).split(';') if '=' in kv)
            if int(parts[-1]) >= 0:
                amp = float(tags['Amplitude']) if 'Amplitude' in tags else np.nan
                out[tags['ShortName']] = (float(parts[0]) * 1000, float(parts[1]) * 1000, amp)
        return out

    def build(self, sweep, stimsets):
        tp = None
        if self.num('TP Insert Checkbox', sweep):
            keys = (
                'TP Pulse Duration',
                'TP Baseline Fraction',
                'TP Amplitude VC',
                'TP Amplitude IC',
            )
            tp = core.TestPulseSettings(*(self.num(k, sweep) for k in keys))
        return buildSweep(
            stimsets[self.text('Stim Wave Name', sweep)],
            int(self.num('Set Sweep Count', sweep)),
            self.num('Stim Scale Factor', sweep),
            self.num('Sampling interval DA', sweep),
            'VC' if self.num('Clamp Mode', sweep) == 0 else 'IC',
            tp,
            np.nan_to_num(self.num('Delay onset user', sweep)),
            np.nan_to_num(self.num('Delay termination', sweep)),
        )

    def representativeSweeps(self) -> list[int]:
        """First sweep of each stimset, preferring one that was not stopped early."""
        bySet: dict[str, list[int]] = {}
        for sw in sorted(self.series):
            bySet.setdefault(self.text('Stim Wave Name', sw), []).append(sw)
        out = []
        for sweeps in bySet.values():
            complete = [sw for sw in sweeps if 'ShortName=UA;' not in self.text('Epochs', sweep=sw)]
            out.append((complete or sweeps)[0])
        return out


@lru_cache(maxsize=None)
def _cell(key) -> _RecordedCell:
    path = RECORDED[key]
    if not path.exists():
        pytest.skip(f'recorded data not reachable: {path}')
    return _RecordedCell(path)


@lru_cache(maxsize=None)
def _cellStimsets(key):
    return loadStimsets(_cell(key).path)


def _itcQuantize(x, daGain):
    """ITC DA output: int16 counts rounded half away from zero; the NWB holds counts / gain."""
    g = ITC_COUNTS_PER_VOLT / daGain
    y = x * g
    return (
        (np.where(y >= 0, np.floor(y + 0.5), np.ceil(y - 0.5)) / g)
        .astype(np.float32)
        .astype(np.float64)
    )


def _checkCommand(cell, stimsets, sweep):
    """Assert the built command is within one DAC count of the recorded DA series, and equal to it
    after ITC quantization. Only acquired (finite) samples are compared.
    """
    name = cell.text('Stim Wave Name', sweep)
    sc = cell.build(sweep, stimsets)
    rec = cell.stimulus(sweep)
    ours = _itcQuantize(sc.command, cell.num('DA Gain', sweep))
    assert len(ours) == len(rec) + 1, name
    ours = ours[: len(rec)]
    valid = np.isfinite(rec)
    if sc.epochs.has('TP_P'):
        # MIES's TP pulse is one sample longer
        i = round(sc.epochs.get('TP_P').end / sc.sampleInterval)
        assert ours[i] == 0 and rec[i] == ours[i - 1], name
        valid[i] = False
    if stimsets[name].analysisFunction == 'PSQ_Ramp':
        # PSQ_Ramp zeroes the command after the spikes; compare up to the last nonzero sample
        last = np.flatnonzero(valid & (rec != 0))[-1]
        valid[last + 1 :] = False
    step = cell.num('DA Gain', sweep) / ITC_COUNTS_PER_VOLT  # one DAC count, pA (IC) or mV (VC)
    raw = sc.command[: len(rec)]
    assert np.abs(raw[valid] - rec[valid]).max() <= step * (1 + 1e-6), name
    diff = np.abs(ours[valid] - rec[valid]) / step
    if any(
        ep.type == 'noise'
        for s in [stimsets[name], *stimsets[name].dependencies.values()]
        for ep in s.epochs
    ):
        # frozen noise is within 5.1e-4 pA of MIES (2**-16 of its range): rare one-count differences
        assert diff.max() <= 1.0 + 1e-6 and np.mean(diff > 0) < 5e-3, name
    else:
        assert diff.max() == 0, f'{name} sweep {sweep}: {np.sum(diff > 0)} samples differ'


@pytest.mark.parametrize('cellKey', list(RECORDED))
def test_command_matches_recorded_stimulus(cellKey):
    cell = _cell(cellKey)
    stimsets = _cellStimsets(cellKey)
    for sweep in cell.representativeSweeps():
        _checkCommand(cell, stimsets, sweep)


def test_command_matches_every_recorded_sweep():
    cell = _cell('human_03.04')
    stimsets = _cellStimsets('human_03.04')
    for sweep in sorted(cell.series):
        _checkCommand(cell, stimsets, sweep)


@pytest.mark.parametrize('cellKey', list(RECORDED))
def test_epochs_match_recorded_labnotebook(cellKey):
    cell = _cell(cellKey)
    stimsets = _cellStimsets(cellKey)
    for sweep in cell.representativeSweeps():
        name = cell.text('Stim Wave Name', sweep)
        sc = cell.build(sweep, stimsets)
        dt = sc.sampleInterval
        rec = cell.epochs(sweep)
        acquiredEnd = rec['UA'][0] if 'UA' in rec else math.inf
        stimsetEnd = sc.epochs.get('ST').end
        ours = {e.name: e for e in sc.epochs if e.start < acquiredEnd - 1e-6}
        assert set(rec) - {'UA'} == set(ours), name
        for key, (start, end, amp) in rec.items():
            if key == 'UA':
                continue
            ep = ours[key]
            expStart, expEnd = ep.start, min(ep.end, acquiredEnd)
            if key == 'TP_P':
                expEnd += dt
            elif key == 'TP_B1':
                expStart += dt
            if math.isclose(ep.end, stimsetEnd) and acquiredEnd == math.inf:
                expEnd -= dt
            assert start == pytest.approx(expStart, abs=1e-4), f'{name} {key} start'
            assert end == pytest.approx(expEnd, abs=1e-4), f'{name} {key} end'
            if np.isfinite(amp):
                assert ep.amplitude == pytest.approx(amp, abs=1e-6), f'{name} {key} amplitude'


def test_production_assets_match_recorded_definitions():
    stimsets = _cellStimsets('human_03.04')
    prod = loadProductionStimsets()
    for name, s in prod.items():
        rec = stimsets[name]
        assert (s.numSweeps, s.iti, s.analysisFunction, s.params) == (
            rec.numSweeps,
            rec.iti,
            rec.analysisFunction,
            rec.params,
        )
        for a, b in zip(s.epochs, rec.epochs):
            if b.type == 'noise':
                assert a.type == 'custom' and a.params['source'] == dict(type='noise', **b.params)
            else:
                assert a == b
        if not any(ep.type == 'noise' for ep in rec.epochs):
            assert np.array_equal(s.wave(0, 0.02), rec.wave(0, 0.02)), name


def test_noise_stimsets_match_pxp_waves():
    if not HUMAN_PXP.exists():
        pytest.skip(f'recorded data not reachable: {HUMAN_PXP}')
    from acq4.util.allen_stimsets.tools.extract_assets import readPxpWaves

    names = ['z_rampepoch_da_0', 'X7RampN1_DA_0', 'X7RampN2_DA_0', 'X7RampN3_DA_0']
    waves = readPxpWaves(HUMAN_PXP, names)
    prod = loadProductionStimsets()
    assert np.array_equal(prod['z_rampepoch_da_0'].gridWave(0), waves['z_rampepoch_da_0'][0])
    for name in names[1:]:
        ours = prod[name].gridWave(0).astype(np.float64)
        theirs = waves[name][0].astype(np.float64)
        assert len(ours) == len(theirs)
        assert np.abs(ours - theirs).max() < 1e-3, name
