import copy
import json

import numpy as np
import pytest
from neuroanalysis import stimuli

from acq4.util.generator.StimGenerator import StimGenerator
from acq4.util.generator.StimParamSet import (
    STIM_TYPES, STIM_TYPES_BY_MENU, SeqParameter, StimParamSet, formatValue, stimuliFromState,
)

RATE = 10e3
NPTS = 2000


@pytest.fixture
def gen(qtbot):
    g = StimGenerator()
    qtbot.addWidget(g)
    g.setMeta('x', units='s', siPrefix=True)
    g.setMeta('y', units='A', siPrefix=True)
    g.setMeta('xy', units='C', siPrefix=True)
    return g


def _add(container, menuName):
    container.addNew(menuName)
    return container.children()[-1]


def _setAmplitudes(item, value=1e-9):
    for path, p in item.iterSeqParams():
        if p.opts.get('axis') == 'y' and p.writable():
            p.setValue(value)


def _seqPoints(gen):
    """Yield every params dict of the generator's sequence space."""
    seqs = gen.listSequences()
    names = list(seqs)
    for idx in np.ndindex(*[len(seqs[n]) for n in names]):
        yield dict(zip(names, idx))


def _advancedWaves(gen, points):
    """Evaluate the compiled function string in advanced mode at each point."""
    gen.forceAdvancedClicked()
    assert gen.advancedMode
    waves = [gen.getSingle(RATE, NPTS, p) for p in points]
    gen.forceSimpleClicked()
    assert not gen.advancedMode
    return waves


def _assertParity(gen, exact=True):
    points = list(_seqPoints(gen))
    simple = [gen.getSingle(RATE, NPTS, p) for p in points]
    for p, w in zip(points, simple):
        expected = gen.getStimulus(p).eval(n_pts=NPTS, sample_rate=RATE).data
        np.testing.assert_array_equal(w, expected)
    advanced = _advancedWaves(gen, points)
    for s, a in zip(simple, advanced):
        if exact:
            np.testing.assert_array_equal(s, a)
        else:
            np.testing.assert_allclose(s, a, rtol=1e-12, atol=1e-20)
    return points, simple


def _stimState(item):
    s = item.stimulusState()
    s['schema_version'] = stimuli.STIMULUS_SCHEMA_VERSION
    return s


TYPE_NAMES = [cls.menuName for cls in STIM_TYPES]


def test_removed_types():
    assert TYPE_NAMES == ['Pulse', 'Pulse Train', 'Sine', 'Chirp', 'Ramp', 'Psp', 'Offset', 'Noise', 'Pwm', 'Filter']


@pytest.mark.parametrize('menuName', TYPE_NAMES)
def test_each_type(gen, menuName):
    item = _add(gen.stimParams, menuName)
    _setAmplitudes(item)
    assert not gen.advancedMode
    assert gen.test(), gen.ui.errorText.toPlainText()
    stim = gen.getStimulus()
    assert isinstance(stim, stimuli.Stimulus)
    assert stim.units == 'A'
    assert len(stim.items) == 1
    assert isinstance(stim.items[0], item.stimClass)
    assert stim.items[0].description == item.name()
    wave = gen.getSingle(RATE, NPTS)
    assert wave.shape == (NPTS,)
    if menuName not in ('Pwm', 'Filter'):  # empty inputs give zero output
        assert np.abs(wave).max() > 0
    # manual saved state matches neuroanalysis' own
    assert _stimState(item) == item.buildStimulus({}).save()
    assert gen.functionString().startswith('stim(')
    _assertParity(gen)


@pytest.mark.parametrize('menuName', TYPE_NAMES)
def test_state_round_trip(gen, menuName):
    item = _add(gen.stimParams, menuName)
    _setAmplitudes(item)
    first = next(p for _, p in item.iterSeqParams())
    first['sequence'] = 'list'
    first['list'] = '1, 2'
    state = gen.saveState()
    assert state['stimuli']['format'] == 2
    json.dumps(state['stimuli'])

    other = StimGenerator()
    for axis in ('x', 'y', 'xy'):
        other.setMeta(axis, **gen.meta[axis])
    other.loadState(copy.deepcopy(state))
    assert not other.advancedMode
    assert other.saveState()['stimuli'] == state['stimuli']
    assert other.functionString() == gen.functionString()
    assert other.listSequences() == gen.listSequences()
    for p in _seqPoints(gen):
        np.testing.assert_array_equal(other.getSingle(RATE, NPTS, p), gen.getSingle(RATE, NPTS, p))
    other.close()


def test_axis_meta_and_units(gen):
    sine = _add(gen.stimParams, 'Sine')
    assert sine.param('amplitude').opts['units'] == 'A'
    assert sine.param('offset').opts['units'] == 'A'
    assert sine.param('duration').opts['units'] == 's'
    assert sine.param('frequency').opts['units'] == 'Hz'  # static, not axis meta
    assert sine.param('phase').opts.get('axis') is None
    gen.setMeta('y', units='V')
    assert sine.param('amplitude').opts['units'] == 'V'
    assert gen.getStimulus().units == 'V'


def test_root_units_from_suffix(gen):
    # MultiClamp sets 'suffix' rather than 'units'
    gen.meta['y'] = {}
    gen.setMeta('y', suffix='V', siPrefix=True)
    _add(gen.stimParams, 'Pulse')
    assert gen.getStimulus().units == 'V'


def test_offset(gen):
    pulse = _add(gen.stimParams, 'Pulse')
    pulse['amplitude'] = 1e-9
    gen.setOffset(-60e-3)
    stim = gen.getStimulus()
    assert isinstance(stim.items[0], stimuli.Offset)
    assert stim.items[0].amplitude == -60e-3
    assert isinstance(stim.items[1], stimuli.SquarePulse)
    wave = gen.getSingle(RATE, NPTS)
    assert wave[0] == -60e-3
    _assertParity(gen, exact=False)


def test_no_offset_item_when_zero(gen):
    _add(gen.stimParams, 'Pulse')
    assert [type(i) for i in gen.getStimulus().items] == [stimuli.SquarePulse]


def test_empty_tree(gen):
    assert gen.functionString() == ''
    gen.setOffset(1.0)
    np.testing.assert_array_equal(gen.getSingle(RATE, 10), np.ones(10))


def test_getStimulus_none_in_advanced_mode(gen):
    _add(gen.stimParams, 'Pulse')
    gen.forceAdvancedClicked()
    assert gen.getStimulus() is None
    assert gen.getStimulus({'Pulse_amplitude': 0}) is None


def test_getStimulus_cached(gen):
    pulse = _add(gen.stimParams, 'Pulse')
    s1 = gen.getStimulus()
    assert gen.getStimulus() is s1
    pulse['amplitude'] = 2e-9
    s2 = gen.getStimulus()
    assert s2 is not s1
    assert s2.items[0].amplitude == 2e-9
    gen.setOffset(1e-3)
    assert gen.getStimulus() is not s2


def test_advanced_test_tolerates_low_rate(gen):
    # test() evaluates at rate 1, where Sine would fail the Nyquist check
    sine = _add(gen.stimParams, 'Sine')
    sine['amplitude'] = 1e-9
    gen.forceAdvancedClicked()
    assert gen.test(), gen.ui.errorText.toPlainText()


def test_invalid_parameters_reported(gen):
    pulse = _add(gen.stimParams, 'Pulse')
    pulse['duration'] = -1
    assert not gen.test()
    assert 'duration' in gen.ui.errorText.toPlainText()


def test_sequences(gen):
    pulse = _add(gen.stimParams, 'Pulse')
    pulse['amplitude'] = 1e-9
    amp = pulse.param('amplitude')
    amp['sequence'] = 'range (n)'
    amp['start'] = 1e-9
    amp['stop'] = 3e-9
    amp['steps'] = 3
    train = _add(gen.stimParams, 'Pulse Train')
    train['amplitude'] = 1e-9
    train.param('n_pulses')['sequence'] = 'list'
    train.param('n_pulses')['list'] = '2, 3'
    seqs = gen.listSequences()
    assert list(seqs) == ['Pulse_amplitude', 'PulseTrain_n_pulses']
    np.testing.assert_allclose(seqs['Pulse_amplitude'], [1e-9, 2e-9, 3e-9])
    stim = gen.getStimulus({'Pulse_amplitude': 2, 'PulseTrain_n_pulses': 1})
    assert stim.items[0].amplitude == 3e-9
    assert stim.items[1].n_pulses == 3
    assert isinstance(stim.items[1].n_pulses, int)
    w = gen.getSingle(RATE, NPTS, params={'Pulse_amplitude': 1})
    assert np.isclose(w[150], 2e-9)
    assert 'n_pulses=round(PulseTrain_n_pulses)' in gen.functionString()
    _assertParity(gen)


def test_pwm_with_sequenced_sine_duty(gen):
    pwm = _add(gen.stimParams, 'Pwm')
    pwm['start_time'] = 0
    pwm['duration'] = 0.2
    pwm['period'] = 0.01
    pwm['amplitude'] = 1e-9
    sine = _add(pwm.param('duty'), 'Sine')
    assert sine['start_time'] == 0
    sine['duration'] = 0.2
    sine['frequency'] = 5
    sine['offset'] = 0.5
    sine['amplitude'] = 0.25
    sine.param('amplitude')['sequence'] = 'list'
    sine.param('amplitude')['list'] = '0, 0.4'

    # duty is dimensionless: x meta only
    assert sine.param('amplitude').opts.get('units') is None
    assert sine.param('offset').opts.get('units') is None
    assert sine.param('duration').opts['units'] == 's'

    assert list(gen.listSequences()) == ['Pwm_duty_Sine_amplitude']
    stim = gen.getStimulus({'Pwm_duty_Sine_amplitude': 1})
    assert stim.items[0].duty.items[0].amplitude == 0.4
    assert gen.getStimulus().items[0].duty.items[0].amplitude == 0.25

    # zero sine amplitude -> constant 50% duty
    w0 = gen.getSingle(RATE, NPTS, {'Pwm_duty_Sine_amplitude': 0})
    assert np.isclose((w0 > 0).mean(), 0.5)
    w1 = gen.getSingle(RATE, NPTS, {'Pwm_duty_Sine_amplitude': 1})
    assert not np.array_equal(w0, w1)

    state = gen.saveState()['stimuli']
    assert state['items'][0]['sequences'] == {
        'duty.Sine.amplitude': {'sequence': 'list', 'list': '0, 0.4', 'randomize': False}}
    _assertParity(gen)


def test_filter_with_noise_input(gen):
    filt = _add(gen.stimParams, 'Filter')
    filt['filter_type'] = 'butterworth'
    filt['cutoff'] = 200.0
    noise = _add(filt.param('input'), 'Noise')
    noise['duration'] = 0.2
    noise['sigma'] = 1e-9
    noise.param('seed')['sequence'] = 'list'
    noise.param('seed')['list'] = '1, 2'
    # Filter input has the host's units
    assert noise.param('sigma').opts['units'] == 'A'

    assert list(gen.listSequences()) == ['Filter_input_Noise_seed']
    filtered = gen.getSingle(RATE, NPTS, {'Filter_input_Noise_seed': 0})
    raw = gen.getStimulus({'Filter_input_Noise_seed': 0}).items[0].input.eval(n_pts=NPTS, sample_rate=RATE).data
    assert filtered.std() < 0.5 * raw.std()
    assert gen.getStimulus({'Filter_input_Noise_seed': 1}).items[0].input.items[0].seed == 2
    _assertParity(gen)


def test_two_level_nesting(gen):
    filt = _add(gen.stimParams, 'Filter')
    filt['cutoff'] = 500.0
    pwm = _add(filt.param('input'), 'Pwm')
    pwm['amplitude'] = 1e-9
    pwm['duration'] = 0.15
    pwm['period'] = 0.005
    assert pwm.param('amplitude').opts['units'] == 'A'
    sine = _add(pwm.param('duty'), 'Sine')
    sine['duration'] = 0.15
    sine['offset'] = 0.5
    sine.param('amplitude')['sequence'] = 'range (n)'
    sine.param('amplitude')['start'] = 0.1
    sine.param('amplitude')['stop'] = 0.4
    sine.param('amplitude')['steps'] = 2
    assert sine.param('amplitude').opts.get('units') is None
    assert sine.param('start_time').opts['units'] == 's'

    name = 'Filter_input_Pwm_duty_Sine_amplitude'
    assert list(gen.listSequences()) == [name]
    stim = gen.getStimulus({name: 1})
    assert stim.items[0].input.items[0].duty.items[0].amplitude == 0.4

    state = gen.saveState()
    assert list(state['stimuli']['items'][0]['sequences']) == ['input.Pwm.duty.Sine.amplitude']
    _assertParity(gen)

    other = StimGenerator()
    for axis in ('x', 'y', 'xy'):
        other.setMeta(axis, **gen.meta[axis])
    other.loadState(state)
    assert other.saveState()['stimuli'] == state['stimuli']
    assert list(other.listSequences()) == [name]
    loadedSine = other.stimParams.child('Filter').param('input', 'Pwm', 'duty', 'Sine')
    assert loadedSine.param('amplitude').opts.get('units') is None
    assert loadedSine.param('duration').opts['units'] == 's'
    other.close()


def test_duplicate_sequence_names_rejected():
    sp = StimParamSet()
    pwm = _add(sp, 'Pwm')
    sine = _add(pwm.param('duty'), 'Sine')
    sine.param('amplitude')['sequence'] = 'list'
    sine.param('amplitude')['list'] = '1'
    clash = _add(sp, 'Sine')
    clash.setName('Pwm_duty_Sine')
    clash.param('amplitude')['sequence'] = 'list'
    clash.param('amplitude')['list'] = '1'
    with pytest.raises(ValueError, match='Duplicate'):
        sp.compile()


def test_pulse_sum_affect(gen):
    pulse = _add(gen.stimParams, 'Pulse')
    pulse['amplitude'] = 2e-9
    pulse['duration'] = 0.01
    assert np.isclose(pulse['sum'], 2e-11)
    assert pulse['sum', 'affect'] == 'duration'
    pulse['sum'] = 4e-11
    assert np.isclose(pulse['duration'], 0.02)
    pulse['sum', 'affect'] = 'amplitude'
    pulse['sum'] = 2e-11
    assert np.isclose(pulse['amplitude'], 1e-9)


@pytest.mark.parametrize('menuName,durAttr', [('Pulse', 'duration'), ('Pulse Train', 'pulse_duration')])
def test_sequence_over_sum(gen, menuName, durAttr):
    pulse = _add(gen.stimParams, menuName)
    pulse['amplitude'] = 1e-9
    pulse[durAttr] = 0.002
    s = pulse.param('sum')
    s['sequence'] = 'list'
    s['list'] = '1e-12, 3e-12'
    name = f'{pulse.name()}_sum'
    assert list(gen.listSequences()) == [name]
    assert f'{durAttr}={name} / (1*nA)' in gen.functionString()
    durs = [getattr(gen.getStimulus({name: i}).items[0], durAttr) for i in range(2)]
    np.testing.assert_allclose(durs, [1e-3, 3e-3])
    _assertParity(gen)

    s['sequence'] = 'off'
    pulse['sum', 'affect'] = 'amplitude'
    s['sequence'] = 'list'
    amps = [gen.getStimulus({name: i}).items[0].amplitude for i in range(2)]
    np.testing.assert_allclose(amps, [0.5e-9, 1.5e-9])
    assert gen.saveState()['stimuli']['items'][0]['ui']['affect'] == 'amplitude'


def test_sum_and_target_both_sequenced_rejected():
    sp = StimParamSet()
    pulse = _add(sp, 'Pulse')
    pulse['amplitude'] = 1e-9
    pulse.param('sum')['sequence'] = 'list'
    pulse.param('duration')['sequence'] = 'list'
    with pytest.raises(ValueError, match='simultaneously'):
        sp.compile()


def test_laser_readonly_meta(gen):
    pulse = _add(gen.stimParams, 'Pulse')
    pulse['amplitude'] = 1e-3
    pulse['duration'] = 0.01
    energy = pulse['sum']
    gen.setMeta('y', value=2e-3, readonly=True)
    assert pulse['amplitude'] == 2e-3
    assert not pulse.param('amplitude').writable()
    pulse['sum'] = energy  # as LaserTaskGui does to preserve energy
    assert np.isclose(pulse['duration'], 0.005)
    # new items pick up the stored readonly meta
    sine = _add(gen.stimParams, 'Sine')
    assert sine['amplitude'] == 2e-3
    assert not sine.param('amplitude').writable()
    # dimensionless duty items are unaffected
    pwm = _add(gen.stimParams, 'Pwm')
    duty = _add(pwm.param('duty'), 'Sine')
    assert duty.param('amplitude').writable()
    assert duty['amplitude'] == 0


def test_noise_seed_random_and_deterministic(gen):
    a = _add(gen.stimParams, 'Noise')
    b = _add(gen.stimParams, 'Noise')
    assert a['seed'] != b['seed']
    a['sigma'] = 1e-9
    w1 = gen.getSingle(RATE, NPTS).copy()
    gen.clearCache()
    np.testing.assert_array_equal(gen.getSingle(RATE, NPTS), w1)


def test_unknown_type_raises():
    with pytest.raises(ValueError):
        StimParamSet().setState({'X': {'type': 'bogus'}})
    with pytest.raises(ValueError):
        StimParamSet().setState({'format': 2, 'items': [
            {'name': 'X', 'stimulus': {'type': 'Bogus', 'args': {}}, 'sequences': {}, 'ui': {}}]})
    with pytest.raises(ValueError):
        StimParamSet().setState({'format': 3, 'items': []})


def test_formatValue_exact():
    rng = np.random.default_rng(0)
    for v in list(rng.uniform(-1, 1, 200) * 10.0 ** rng.integers(-12, 3, 200)) + [0.0, 0.01, 1e-9, 2.5e-3]:
        for units in (None, 's', 'A', 'V*s'):
            s = formatValue(float(v), units)
            import pyqtgraph.units as u
            assert eval(s, {}, u.allUnits) == float(v), (v, units, s)
    assert formatValue(0.01, 's') == '10*ms'
    assert formatValue(12345678901) == '12345678901'
    assert formatValue(1.5, 'furlongs') == '1.5'


# ---- legacy state ----
# Built in the format written by the pre-neuroanalysis StimParamSet.getState().

LEGACY_PULSE = {
    'type': 'pulse',
    'start': {'sequence': 'off', 'value': 0.01},
    'length': {'sequence': 'off', 'value': 0.02},
    'amplitude': {'sequence': 'off', 'value': -5e-11},
    'sum': {'affect': 'length', 'sequence': 'off', 'value': 1e-12},
}

LEGACY_PULSE_SEQ = {
    'type': 'pulse',
    'start': {'sequence': 'off', 'value': 0.005},
    'length': {'sequence': 'off', 'value': 0.01},
    'amplitude': {'sequence': 'range', 'start': -1e-10, 'stop': 1e-10, 'steps': 5, 'value': 0.0},
    'sum': {'affect': 'length', 'sequence': 'off', 'value': 0.0},
}

LEGACY_TRAIN_INTERPULSE = {
    'type': 'pulseTrain',
    'start': {'sequence': 'off', 'value': 0.0},
    'length': {'sequence': 'off', 'value': 0.002},
    'amplitude': {'sequence': 'off', 'value': 0.1},
    'sum': {'affect': 'length', 'sequence': 'off', 'value': 0.0002},
    'interpulse_length': {'sequence': 'off', 'value': 0.01},
    'pulse_number': {'sequence': 'range', 'start': 3, 'stop': 8, 'steps': 6, 'value': 3},
}

LEGACY_TRAIN = {
    'type': 'pulseTrain',
    'start': {'sequence': 'off', 'value': 0.05},
    'length': {'sequence': 'list', 'list': '1*ms, 2*ms', 'randomize': True, 'value': 0.001},
    'amplitude': {'sequence': 'off', 'value': 1e-9},
    'sum': {'affect': 'amplitude', 'sequence': 'off', 'value': 1e-12},
    'period': {'sequence': 'range (step)', 'start': 0.01, 'stop': 0.03, 'step size': 0.01, 'value': 0.02},
    'pulse_number': {'sequence': 'off', 'value': 4},
}


def _legacy():
    return copy.deepcopy({
        'Pulse': LEGACY_PULSE,
        'Pulse2': LEGACY_PULSE_SEQ,
        'PulseTrain': LEGACY_TRAIN_INTERPULSE,
        'PulseTrain2': LEGACY_TRAIN,
    })


def test_legacy_load(gen):
    legacy = _legacy()
    gen.loadState({'advancedMode': False, 'stimuli': legacy})
    assert legacy == _legacy()  # not mutated
    assert not gen.advancedMode
    assert list(gen.listSequences()) == [
        'Pulse2_amplitude', 'PulseTrain_n_pulses', 'PulseTrain2_pulse_duration', 'PulseTrain2_interval']
    seqs = gen.listSequences()
    np.testing.assert_allclose(seqs['Pulse2_amplitude'], np.linspace(-1e-10, 1e-10, 5))
    assert list(seqs['PulseTrain_n_pulses']) == [3, 4, 5, 6, 7, 8]
    np.testing.assert_allclose(seqs['PulseTrain2_interval'], [0.01, 0.02])

    items = gen.getStimulus().items
    p, p2, t, t2 = items
    assert (type(p), p.start_time, p.duration, p.amplitude) == (stimuli.SquarePulse, 0.01, 0.02, -5e-11)
    assert (p2.start_time, p2.duration) == (0.005, 0.01)
    assert type(t) is stimuli.SquarePulseTrain
    assert (t.start_time, t.pulse_duration, t.amplitude, t.interval, t.n_pulses) == (0.0, 0.002, 0.1, 0.01, 3)
    assert (t2.start_time, t2.pulse_duration, t2.amplitude, t2.interval, t2.n_pulses) == (0.05, 0.001, 1e-9, 0.02, 4)

    train = gen.stimParams.child('PulseTrain2')
    assert train['sum', 'affect'] == 'amplitude'
    assert train.param('pulse_duration')['randomize'] is True
    assert gen.stimParams.child('Pulse')['sum', 'affect'] == 'duration'

    assert gen.getStimulus({'PulseTrain_n_pulses': 5}).items[2].n_pulses == 8
    assert gen.getStimulus({'Pulse2_amplitude': 4}).items[1].amplitude == pytest.approx(1e-10)

    # matches the legacy waveform function for a pulse train
    from acq4.util.generator import waveforms
    w = gen.getStimulus({'PulseTrain_n_pulses': 0}).items[2].eval(n_pts=NPTS, sample_rate=RATE).data
    old = waveforms.pulse({'rate': RATE, 'nPts': NPTS}, times=0.0 + np.linspace(0, 0.01 * 2, 3), widths=0.002, values=0.1)
    np.testing.assert_array_equal(w, old)

    _assertParity(gen)


def test_legacy_round_trip_to_new_format(gen):
    gen.loadState({'stimuli': _legacy()})
    state = gen.saveState()['stimuli']
    assert state['format'] == 2
    by_name = {i['name']: i for i in state['items']}
    assert by_name['PulseTrain']['sequences'] == {
        'n_pulses': {'sequence': 'range (n)', 'start': 3.0, 'stop': 8.0, 'steps': 6, 'log spacing': False,
                     'randomize': False}}
    assert by_name['Pulse']['ui'] == {'sum': pytest.approx(1e-12), 'affect': 'duration'}
    other = StimParamSet()
    other.setState(state)
    assert other.getState() == state


def test_stimuliFromState_legacy():
    stims = stimuliFromState(_legacy())
    assert list(stims) == ['Pulse', 'Pulse2', 'PulseTrain', 'PulseTrain2']
    assert stims['Pulse'] == stimuli.SquarePulse(start_time=0.01, duration=0.02, amplitude=-5e-11, description='Pulse')
    assert stims['PulseTrain'] == stimuli.SquarePulseTrain(
        start_time=0.0, n_pulses=3, pulse_duration=0.002, amplitude=0.1, interval=0.01, description='PulseTrain')
    assert stims['PulseTrain2'].interval == 0.02


def test_stimuliFromState_new(gen):
    pwm = _add(gen.stimParams, 'Pwm')
    pwm['amplitude'] = 1e-9
    sine = _add(pwm.param('duty'), 'Sine')
    sine['amplitude'] = 0.3
    sine.param('amplitude')['sequence'] = 'list'
    sine.param('amplitude')['list'] = '0.1, 0.2'
    _add(gen.stimParams, 'Pulse')
    stims = stimuliFromState(gen.saveState()['stimuli'])
    assert list(stims) == ['Pwm', 'Pulse']
    assert stims['Pwm'] == gen.getStimulus().items[0].__class__.load(gen.getStimulus().items[0].save())
    assert stims['Pwm'].duty.items[0].amplitude == 0.3  # default, not sequenced
    assert stims['Pulse'] == gen.stimParams.child('Pulse').buildStimulus({})


def test_legacy_advanced_range_sequence(gen):
    gen.loadState({
        'advancedMode': True,
        'function': 'pulse(30*ms, 15*ms, amp)',
        'params': {'amp': {'default': '10*mV', 'sequence': 'range', 'start': '20*mV', 'stop': '30*mV', 'steps': 5}},
    })
    np.testing.assert_allclose(gen.listSequences()['amp'], np.linspace(20e-3, 30e-3, 5))
    assert gen.getStimulus() is None


def test_seqparameter_standalone_compile():
    # OdorDelivery uses SeqParameter outside a stimulus tree
    from pyqtgraph.parametertree.parameterTypes import GroupParameter

    class Parent(GroupParameter):
        def varName(self):
            return 'ev'

    parent = Parent(name='ev')
    p = parent.addChild(SeqParameter(name='Start', type='float', value=0.5, units='s'))
    assert p.compile() == ('500*ms', None)
    p['sequence'] = 'list'
    p['list'] = '1, 2'
    assert p.compile()[0] == 'ev_Start'
