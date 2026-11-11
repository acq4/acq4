import pytest
from neuroanalysis import stimuli

from acq4.analysis.dataModels.PatchEPhys import getPulseTiming, getStimulusItem

LEGACY = {
    'Pulse': {
        'type': 'pulse',
        'start': {'sequence': 'off', 'value': 0.01},
        'length': {'sequence': 'off', 'value': 0.02},
        'amplitude': {'sequence': 'off', 'value': -5e-11},
        'sum': {'affect': 'length', 'sequence': 'off', 'value': 1e-12},
    },
    'PulseTrain': {
        'type': 'pulseTrain',
        'start': {'sequence': 'off', 'value': 0.05},
        'length': {'sequence': 'off', 'value': 0.002},
        'amplitude': {'sequence': 'off', 'value': 1.0},
        'interpulse_length': {'sequence': 'off', 'value': 0.01},
        'pulse_number': {'sequence': 'range', 'start': 3, 'stop': 8, 'steps': 6, 'value': 4},
    },
}


def _item(name, stim):
    return {'name': name, 'stimulus': stim.save(), 'sequences': {}, 'ui': {}}


NEW = {'format': 2, 'items': [
    _item('Pulse', stimuli.SquarePulse(start_time=0.01, duration=0.02, amplitude=-5e-11, description='Pulse')),
    _item('PulseTrain', stimuli.SquarePulseTrain(
        start_time=0.05, n_pulses=4, pulse_duration=0.002, amplitude=1.0, interval=0.01, description='PulseTrain')),
    _item('Sine', stimuli.Sine(start_time=0, duration=0.1, frequency=10, amplitude=1.0, description='Sine')),
]}


@pytest.mark.parametrize('state', [LEGACY, NEW], ids=['legacy', 'new'])
def test_pulse_timing(state):
    assert getPulseTiming(state) == (0.01, 0.02)
    assert getPulseTiming(state, 'PulseTrain') == (0.05, 0.002)


@pytest.mark.parametrize('state', [LEGACY, NEW], ids=['legacy', 'new'])
def test_pulse_train_item(state):
    train = getStimulusItem(state, 'PulseTrain')
    assert isinstance(train, stimuli.SquarePulseTrain)
    assert (train.start_time, train.pulse_duration, train.interval, train.n_pulses) == (0.05, 0.002, 0.01, 4)


@pytest.mark.parametrize('state', [LEGACY, NEW, {}], ids=['legacy', 'new', 'empty'])
def test_missing_item_raises_keyerror(state):
    with pytest.raises(KeyError):
        getPulseTiming(state, 'Nope')


def test_non_square_item_raises_keyerror():
    with pytest.raises(KeyError):
        getPulseTiming(NEW, 'Sine')


def test_unknown_format_raises_valueerror():
    with pytest.raises(ValueError):
        getPulseTiming({'format': 99, 'items': []})
