import pytest

from acq4.analysis.scripts.chr2analysis import ledPulseDurKey


@pytest.mark.parametrize('name', ['Command.PulseTrain_length', 'Command.PulseTrain_pulse_duration'])
def test_led_pulse_dur_key(name):
    info = {('LED-Blue', name): 2, ('protocol', 'repetitions'): 0}
    assert ledPulseDurKey(info) == ('LED-Blue', name)


def test_led_pulse_dur_key_missing():
    with pytest.raises(KeyError):
        ledPulseDurKey({('LED-Blue', 'Command.PulseTrain_amplitude'): 0})
