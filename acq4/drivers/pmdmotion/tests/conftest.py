import pytest

from acq4.drivers.pmdmotion import backend as backend_module
from acq4.drivers.pmdmotion import commutation
from acq4.drivers.pmdmotion.tests.fake_bus import ManualClock
from acq4.drivers.pmdmotion.tests.sim import FakeTime


@pytest.fixture
def clock(monkeypatch):
    """ManualClock that also drives ``time`` in the backend and commutation modules."""
    clock = ManualClock()
    fake = FakeTime(clock)
    monkeypatch.setattr(backend_module, 'time', fake)
    monkeypatch.setattr(commutation, 'time', fake)
    return clock
