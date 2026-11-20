"""Tests that the MultiPatch log viewer opens with its most-used traces already drawn."""
import json

import pytest

from acq4.filetypes.MultiPatchLog import TEST_PULSE_METAARRAY_INFO, MultiPatchLogWidget
from acq4.util import Qt
from acq4.util.DataManager import getFileHandle

RSS = 'steady_state_resistance'
RSS_UNITS = next(m['units'] for m in TEST_PULSE_METAARRAY_INFO if m['name'] == RSS)


def _event(time, device, event, **kwargs):
    return {'event_time': time, 'device': device, 'event': event, **kwargs}


def _testPulse(time, device, rss):
    return _event(
        time, device, 'test_pulse',
        baseline_potential=-0.07, baseline_current=-50e-12,
        input_resistance=rss, access_resistance=10e6, steady_state_resistance=rss,
        fit_amplitude=1e-9, time_constant=1e-3, fit_yoffset=0.0, fit_xoffset=0.0,
        capacitance=5e-12, start_time=time,
    )


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


@pytest.fixture
def logFile(tmp_path):
    dev = 'Pipette1'
    events = [
        _event(100.0, dev, 'state_change', state='bath', info=''),
        _event(100.0, dev, 'pressure_changed', pressure=5000.0, source='regulator'),
        _testPulse(100.5, dev, 5e6),
        _event(101.0, dev, 'state_change', state='seal', info=''),
        _event(101.0, dev, 'pressure_changed', pressure=-2000.0, source='regulator'),
        _testPulse(101.5, dev, 1e9),
        _event(102.0, dev, 'pressure_changed', pressure=0.0, source='atmosphere'),
    ]
    path = tmp_path / 'MultiPatch_000.log'
    path.write_text(''.join(f'{json.dumps(e)},\n' for e in events))
    return getFileHandle(str(path))


@pytest.fixture
def widget(qapp, logFile):
    w = MultiPatchLogWidget()
    try:
        w.addLog(logFile)
        yield w
    finally:
        w.close()


def test_default_checkboxes_are_checked(widget):
    assert widget._displayPressure.isChecked()
    assert widget._display_state_regions.isChecked()
    rss = next(cb for cb in widget._testPulseAnalysisCheckboxes if cb.name == RSS)
    assert rss.isChecked()


def test_pressure_is_plotted_by_default(widget):
    plot = widget._plots_by_units['Pa']
    assert plot.isVisible()
    assert [item.name() for item in plot.listDataItems()] == [
        'Pressure: regulator', 'Pressure: atmosphere']


def test_steady_state_resistance_is_plotted_by_default(widget):
    plot = widget._plots_by_units[RSS_UNITS]
    assert [item.name() for item in plot.listDataItems()] == [RSS]


def test_state_regions_are_drawn_on_the_default_plots(widget):
    for units in ('Pa', RSS_UNITS):
        plot = widget._plots_by_units[units]
        assert widget._regions_by_plot.get(plot), f'expected state regions on the {units} plot'
