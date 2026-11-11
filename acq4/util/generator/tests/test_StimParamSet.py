import numpy as np
import pytest

from acq4.util.generator.StimGenerator import StimGenerator
from acq4.util.generator.StimParamSet import STIM_TYPES, StimParamSet

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


def _add(gen, cls):
    gen.stimParams.addNew(cls.menuName)
    return gen.stimParams.children()[-1]


@pytest.mark.parametrize('cls', STIM_TYPES, ids=lambda c: c.stimType)
def test_each_type_compiles_and_evaluates(gen, cls):
    _add(gen, cls)
    assert not gen.advancedMode
    assert gen.test(), gen.ui.errorText.toPlainText()
    wave = gen.getSingle(RATE, NPTS)
    assert wave.shape == (NPTS,)


@pytest.mark.parametrize('cls', STIM_TYPES, ids=lambda c: c.stimType)
def test_state_round_trip(gen, cls):
    _add(gen, cls)
    state = gen.saveState()
    other = StimParamSet()
    for axis, meta in gen.stimParams.meta.items():
        other.setMeta(axis, dict(meta))
    other.setState(state['stimuli'])
    assert other.getState() == gen.stimParams.getState()
    assert other.compile() == gen.stimParams.compile()


def test_sine_values(gen):
    p = _add(gen, STIM_TYPES[[c.stimType for c in STIM_TYPES].index('sineWave')])
    p['start'] = 0.01
    p['duration'] = 0.1
    p['period'] = 0.02
    p['amplitude'] = 1e-9
    wave = gen.getSingle(RATE, NPTS)
    assert np.all(wave[:100] == 0)
    assert np.all(wave[1100:] == 0)
    assert np.isclose(wave[100:1100].max(), 1e-9, rtol=1e-3)


def test_sequenced_parameter(gen):
    p = _add(gen, STIM_TYPES[[c.stimType for c in STIM_TYPES].index('squareWave')])
    p['duty'] = 0.25
    p.param('amplitude')['sequence'] = 'list'
    p.param('amplitude')['list'] = '1, 2, 3'
    seqs = gen.listSequences()
    assert list(seqs) == ['Square_amplitude']
    assert len(seqs['Square_amplitude']) == 3
    w = gen.getSingle(RATE, NPTS, params={'Square_amplitude': 2})
    assert w.max() == 3


def test_unknown_type_raises():
    with pytest.raises(ValueError):
        StimParamSet().setState({'X': {'type': 'bogus'}})
