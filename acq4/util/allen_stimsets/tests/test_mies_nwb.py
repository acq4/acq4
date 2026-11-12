import glob
import os

import numpy as np
import pytest

from acq4.util.allen_stimsets.mies_nwb import (
    DATA_ACQUISITION_MODE,
    TEST_PULSE_MODE,
    UNKNOWN_MODE,
    Labnotebook,
    MiesRecording,
    decodeParams,
    parseEpochs,
    parseStimWaveNote,
    userKey,
)

MOUSE = '//allen/programs/celltypes/production/mousecelltypes/prod4159/Ephys_Roi_Result_{}'
HUMAN = '//allen/programs/celltypes/production/humancelltypes/prod172/Ephys_Roi_Result_{}'
MOUSE_CELLS = ['1539885953', '1539892860', '1539818700', '1539834022', '1539846766']
HUMAN_CELLS = [
    '1544268913',
    '1544231474',
    '1544241552',
    '1544222282',
    '1544261931',
    '1544240966',
    '1544221355',
    '1544224968',
]


def cellFile(cell: str) -> str:
    """Return the recorded NWB of *cell*; skip the test when the share is unreachable."""
    if cell in MOUSE_CELLS:
        files = [
            f
            for f in glob.glob(os.path.join(MOUSE.format(cell), '*.nwb'))
            if not f.endswith('_spikes.nwb')
        ]
    else:
        files = glob.glob(os.path.join(HUMAN.format(cell), 'H26*.nwb'))
    if len(files) != 1:
        pytest.skip(f"recorded cell {cell} not reachable")
    return files[0]


@pytest.fixture(scope='module')
def rec0601():
    with MiesRecording(cellFile('1544221355')) as rec:  # H26.51.023.11.11.06.01
        yield rec


# ---- labnotebook semantics (synthetic)


def _numericNotebook(rows, keys):
    """Build a numerical Labnotebook from dicts {key: scalar (layer 0) or 9-list}."""
    names = ['SweepNum', 'EntrySourceType'] + keys
    k = np.array([names] + [[''] * len(names)] * 5, dtype=object)
    v = np.full((len(rows), len(names), 9), np.nan)
    for i, r in enumerate(rows):
        for name, val in r.items():
            col = names.index(name)
            if np.ndim(val) or name in ('SweepNum', 'EntrySourceType'):
                v[i, col, :] = val
            else:
                v[i, col, 0] = val
    return Labnotebook(k, v)


def test_lastSettingReturnsNewestRowNotNewestPerLayer():
    indepOnly = [np.nan] * 8 + [2.0]
    nb = _numericNotebook(
        [
            {'SweepNum': 0, 'EntrySourceType': 0, 'A': 1.0},
            {'SweepNum': 0, 'EntrySourceType': 0, 'A': indepOnly},
        ],
        ['A'],
    )
    row = nb.lastSetting(0, 'a')  # case-insensitive
    assert np.isnan(row[0]) and row[8] == 2.0
    assert nb.lastSetting(1, 'A') is None
    assert nb.lastSetting(0, 'missing') is None


def test_lastSettingSourceTypeFiltering():
    nb = _numericNotebook(
        [
            {'SweepNum': 0, 'U': 1.0},  # user entry before the DAQ rows (no source type)
            {'SweepNum': 0, 'EntrySourceType': 0, 'A': 10.0},
            {'SweepNum': 0, 'U': 2.0},  # post-sweep user entry
            {'SweepNum': 0, 'EntrySourceType': 1, 'A': 99.0},  # TP during ITI
        ],
        ['A', 'U'],
    )
    assert nb.lastSetting(0, 'A', DATA_ACQUISITION_MODE)[0] == 10.0
    assert nb.lastSetting(0, 'A', TEST_PULSE_MODE)[0] == 99.0
    assert nb.lastSetting(0, 'A', UNKNOWN_MODE)[0] == 99.0
    assert nb.lastSetting(0, 'U', UNKNOWN_MODE)[0] == 2.0
    # MIES restricts DAQ queries to the DAQ rows, so user entries outside them are invisible
    assert nb.lastSetting(0, 'U', DATA_ACQUISITION_MODE) is None


def test_lastSettingUsesNewestBlockOfSweep():
    nb = _numericNotebook(
        [
            {'SweepNum': 0, 'EntrySourceType': 0, 'A': 1.0},
            {'SweepNum': 1, 'EntrySourceType': 0, 'A': 5.0},
            {'SweepNum': 0, 'EntrySourceType': 0, 'B': 3.0},
        ],
        ['A', 'B'],
    )
    # rows of sweep 0 separated by a sourced row of another sweep: only the newest block counts
    assert nb.lastSetting(0, 'A', UNKNOWN_MODE) is None
    assert nb.lastSetting(0, 'B', UNKNOWN_MODE)[0] == 3.0


def test_decodeParams():
    p = decodeParams(
        'SamplingMultiplier:variable=4,MaxAccessResistance:variable=inf,AsyncQCChannels:wave=3|,'
        'NextStimSetName:string=X1PS%2CSub_DA_0,Names:textwave=a%7Cb|c|,'
    )
    assert p == {
        'SamplingMultiplier': 4.0,
        'MaxAccessResistance': float('inf'),
        'AsyncQCChannels': [3.0],
        'NextStimSetName': 'X1PS,Sub_DA_0',
        'Names': ['a|b', 'c'],
    }


def test_parseEpochs():
    s = (
        '0.0000000,0.1000000,Type=Inserted Testpulse;ShortName=TP;,0,:'
        '0.0450000,0.0550050,Type=Inserted Testpulse;SubType=Pulse;Amplitude=10;ShortName=TP_P;,1,:'
        '0.1000000,0.6000000,Type=Baseline Chunk QC Selection;Index=0;ShortName=U_BLS0;,-1,:'
    )
    t = parseEpochs(s)
    assert [ep.name for ep in t] == ['TP', 'TP_P', 'U_BLS0']
    tp = t.get('TP_P')
    assert (tp.start, tp.end, tp.amplitude) == (45.0, 55.005, 10.0)
    assert tp.tags == {
        'Type': 'Inserted Testpulse',
        'SubType': 'Pulse',
        'Amplitude': '10',
        'TreeLevel': '1',
    }
    assert np.isnan(t.get('TP').amplitude)
    assert t.get('U_BLS0').tags['TreeLevel'] == '-1'


def test_parseStimWaveNote():
    note = (
        'Version = 12;\nSweep = 0;Epoch = nan;ITI = 5;\n'
        'Sweep = 0;Epoch = 0;Type = Square pulse;Duration = 500;Amplitude = 0;\n'
        'Sweep = 0;Epoch = 1;Type = Ramp;Duration = 16000;Amplitude = 400;\n'
        'Sweep = 1;Epoch = nan;ITI = 5;\nSweep = 1;Epoch = 0;Type = Square pulse;Duration = 300;\n'
    )
    n = parseStimWaveNote(note)
    assert n['version'] == 12 and n['numSweeps'] == 2
    assert [e['Duration'] for e in n['sweeps'][0]] == ['500', '16000']
    assert n['sweepInfo'][1]['ITI'] == '5'


# ---- recorded cells


# (sweep, stimset, clamp mode, DAScale, Stimset Acq Cycle ID, {QC key suffix: value}) for
# H26.51.023.11.11.06.01. Sweeps 3, 95, 96: the clamp mode was switched in the TP after the sweep; the
# DAQ rows (and the NWB series type) give the mode the sweep was acquired in.
EXPECTED_0601 = [
    (
        0,
        'EXTPSMOKET180424_DA_0',
        'VC',
        1.0,
        1151721,
        {'Access Res. Smoke Sweep QC': 1, 'Access Res. Smoke Set QC': 1},
    ),
    (
        1,
        'EXTPINBATH180424_DA_0',
        'VC',
        1.0,
        6500624,
        {'Pipette in Bath Sweep QC': 1, 'Pipette in Bath Set QC': 1},
    ),
    (
        2,
        'EXTPCllATT180424_DA_0',
        'VC',
        1.0,
        7511793,
        {'Seal evaluation Sweep QC': 1, 'Seal evaluation Set QC': 1},
    ),
    (
        3,
        'EXTPBREAKN180424_DA_0',
        'VC',
        1.0,
        3727951,
        {'Access Res. Smoke Sweep QC': 1, 'Access Res. Smoke Set QC': 1},
    ),
    (
        4,
        'X0NRMP_DA_0',
        'IC',
        1.0,
        4976994,
        {'True Rest Memb. Sweep QC': 1, 'True Rest Memb. Set QC': 1},
    ),
    (5, 'X1PS_SubThresh_DA_0', 'IC', -30.0, 656186, {'DA Scale Sweep QC': 1}),
    (
        9,
        'X1PS_SubThresh_DA_0',
        'IC',
        -110.0,
        656186,
        {'DA Scale Sweep QC': 1, 'DA Scale Set QC': 1},
    ),
    (19, 'X2SP_Search_DA_0', 'IC', 1000.0, 3305096, {'Squ. Pul. Sweep QC': 0}),
    (20, 'X2SP_Search_DA_0', 'IC', 950.0, 3305096, {'Squ. Pul. Sweep QC': 0}),
    (
        27,
        'X2SP_Search_DA_0',
        'IC',
        900.0,
        3305096,
        {'Squ. Pul. Sweep QC': 1, 'Squ. Pul. Set QC': 1},
    ),
    (28, 'X3SP_Rheo_DA_0', 'IC', 900.0, 2444385, {}),
    (29, 'X3SP_Rheo_DA_0', 'IC', 890.0, 2444385, {'Rheobase Set QC': 1}),
    (51, 'X5LP_Rheo_DA_0', 'IC', 230.0, 111450, {'Rheobase Set QC': 0}),
    (95, 'Y6PS_SupraThresh_DA_1', 'IC', 2884.0, 5997555, {'DA Scale Sweep QC': 0}),
    (96, 'EXTPEXPEND180424_DA_0', 'VC', 1.0, 4285257, {}),
    (103, 'Y7RAMPN0_DA_0', 'IC', 1.0, 4097979, {'Ramp Sweep QC': 0}),
]


def test_sweepsMatchLabnotebookSummary(rec0601):
    assert len(rec0601.sweeps()) == 104
    assert len(rec0601.sets()) == 21
    qcKeys = [
        n for n in rec0601.numerical.names if n.endswith(' Sweep QC') or n.endswith(' Set QC')
    ]
    for sweep, stimset, mode, dascale, sci, qc in EXPECTED_0601:
        s = rec0601.sweep(sweep)
        assert (s.stimset, s.sci, s.headstage) == (stimset, sci, 0)
        assert s.dascale == pytest.approx(dascale)
        assert s.clampMode == mode
        found = {
            k[5:]: rec0601.setting(sweep, k)
            for k in qcKeys
            if rec0601.setting(sweep, k) is not None
        }
        assert found == qc, sweep
    for s in rec0601.sweeps():
        series = rec0601._file[f'acquisition/data_{s.sweep:05d}_AD{s.adChannel}'].attrs[
            'neurodata_type'
        ]
        assert series == {'VC': 'VoltageClampSeries', 'IC': 'CurrentClampSeries'}[s.clampMode]


def test_sweepMetadata(rec0601):
    s = rec0601.sweep(5)
    assert s.analysisFunction == 'PSQ_DAScale'
    assert s.params['OperationMode'] == 'Sub'
    assert s.params['DAScales'] == [-30.0, -50.0, -70.0, -90.0, -110.0]
    assert s.sampleInterval == pytest.approx(0.02)  # SamplingMultiplier 4
    assert rec0601.sweep(0).sampleInterval == pytest.approx(0.005)
    assert rec0601.sciSweeps(7) == [5, 6, 7, 8, 9]
    assert rec0601.commandLimit(5) == pytest.approx(32767 / 3200 * 400)  # ITC, 400 pA/V
    assert rec0601.commandLimit(0) == pytest.approx(32767 / 3200 * 20)  # 20 mV/V
    assert rec0601.setting(9, 'Skip Sweeps') == 20  # post-sweep entry without source type
    vm = rec0601.setting(4, userKey('PSQ_TrueRestingMembranePotential', 'Full Average'))
    assert vm == pytest.approx(-0.0621114, abs=1e-6)  # USER_ values are SI (V)
    assert rec0601.setting(5, 'Autobias Vcom') == pytest.approx(-62.11136, abs=1e-4)  # mV


def test_commandExcludesHoldingIncludesDAScaleAndTP(rec0601):
    s = rec0601.sweep(103)
    assert s.holding == pytest.approx(-183.88, abs=0.01)
    assert s.command[0] == 0.0
    s = rec0601.sweep(42)
    ep = s.epochs()
    tp = ep.get('TP_P')
    e1 = ep.get('E1')
    assert s.command[int((tp.start + tp.end) / 2 / s.sampleInterval)] == pytest.approx(
        tp.amplitude, abs=0.125
    )
    assert s.command[int((e1.start + 1) / s.sampleInterval)] == pytest.approx(s.dascale)


def test_epochs(rec0601):
    ep = rec0601.epochs(2)
    tp = ep.get('TP')
    assert (tp.start, tp.end) == (0.0, 100.0)
    assert ep.get('TP_P').amplitude == 10.0
    assert ep.get('TP_P').duration == pytest.approx(10.005)
    stim = ep.withPrefix('E')
    assert [e.name for e in stim][:3] == ['E0', 'E1', 'E2']
    assert stim[0].start == 100.0 and stim[0].duration == pytest.approx(500.0)
    assert ep.get('U_TP0_P').tags['TreeLevel'] == '-1'
    ep = rec0601.epochs(4)
    assert [round(e.duration, 2) for e in ep.withPrefix('E')] == [500.0, 5000.0, 499.98]


def test_earlyStoppedSweep(rec0601):
    s = rec0601.sweep(42)
    assert s.stoppedEarly and not s.stoppedByUser
    assert (s.numPoints, s.numValid) == (277370, 30244)
    assert np.isnan(s.data[s.numValid :]).all() and not np.isnan(s.data[: s.numValid]).any()
    assert np.isnan(s.command[s.numValid :]).all()
    recorded = s.epochs()
    assert recorded.get('UA').start == pytest.approx(s.numValid * s.sampleInterval)
    assert recorded.get('E1').end == pytest.approx(604.88)
    assert not recorded.has('E2')
    planned = s.plannedEpochs()
    assert not planned.has('UA') and not planned.has('U_BLC0')
    assert (planned.get('E1').start, planned.get('E1').end) == (547.42, 1547.42)
    assert planned.get('E1').amplitude == pytest.approx(210.0)
    assert (planned.get('E2').start, planned.get('E2').end) == (1547.42, 5547.4)
    assert planned.get('ST').end == 5547.4
    assert planned.get('E0').tags.get('Reconstructed') is None
    assert planned.get('E2').tags['Reconstructed'] == 'True'
    assert rec0601.sweep(95).stoppedByUser and rec0601.sweep(103).stoppedByUser


def test_plannedEpochReconstructionMatchesCompleteSweeps(rec0601):
    checked = 0
    for s in rec0601.sweeps():
        if s.stoppedEarly:
            continue
        recorded = {
            e.name: e
            for e in s.epochs()
            if e.name == 'ST' or (e.name[0] == 'E' and '_' not in e.name)
        }
        for e in rec0601._stimsetEpochs(s):
            r = recorded[e.name]
            assert (r.start, r.end) == pytest.approx((e.start, e.end), abs=1e-3), (s.sweep, e.name)
            assert r.amplitude == pytest.approx(e.amplitude, nan_ok=True)
            checked += 1
    assert checked > 200


def test_chirpSets():
    with MiesRecording(cellFile('1544261931')) as rec:  # H26.51.023.11.11.03.04
        sets = {m.stimset: m for m in rec.sets() if m.analysisFunction == 'PSQ_Chirp'}
        a, b = sets['C2CHIRPA180503_DA_0'], sets['C2CHIRPB180503_DA_0']
        key = userKey('PSQ_Chirp', 'Set QC')
        assert rec.setting(a.sweeps[-1], key) == 1 and rec.setting(b.sweeps[-1], key) == 0
        assert [rec.sweep(sw).dascale for sw in a.sweeps[:6]] == [45, 31, 31, 31, 11, 8]


@pytest.mark.parametrize('cell', MOUSE_CELLS + HUMAN_CELLS)
def test_allCellsEarlyStopMatchesUnacquiredEpoch(cell):
    with MiesRecording(cellFile(cell)) as rec:
        sweeps = rec.sweeps()
        assert len(sweeps) > 40
        for s in sweeps:
            assert s.stoppedEarly == rec.epochs(s.sweep).has('UA'), s.sweep
        assert all(m.sweeps == sorted(m.sweeps) for m in rec.sets())
