"""Sensapex limit capabilities, Sensapex.setLimits, and SensapexInterface's limit checkboxes."""

from __future__ import annotations

import inspect

import pytest


@pytest.fixture
def sensapex(qapp, monkeypatch):
    """Import the Sensapex class with a stub manager."""

    pytest.importorskip("sensapex")

    class _StubManager:
        config = {}

    monkeypatch.setattr("acq4.getManager", lambda: _StubManager())

    from acq4.devices.Sensapex import Sensapex

    return Sensapex


def _stub(sensapex, nAxes=4, config=None):
    """A Sensapex built with __new__, holding only what capabilities() and setLimits() read.

    Constructing a real one needs a uMp on the bus.
    """
    dev = sensapex.__new__(sensapex)
    dev.nAxes = nAxes
    dev.config = config if config is not None else {}
    return dev


def test_capabilities_says_limits_are_enforced(sensapex):
    caps = sensapex.capabilities(_stub(sensapex, nAxes=4))

    assert caps["limits"] == (True,) * 4


def test_capabilities_tracks_the_axis_count(sensapex):
    assert sensapex.capabilities(_stub(sensapex, nAxes=3))["limits"] == (True,) * 3


def test_a_configured_capabilities_block_still_wins(sensapex):
    override = {"getPos": (True,), "setPos": (True,), "limits": (False,)}
    caps = sensapex.capabilities(_stub(sensapex, nAxes=4, config={"capabilities": override}))

    assert caps is override


def test_set_limits_accepts_everything_the_base_does(sensapex):
    from acq4.devices.Stage.Stage import Stage

    assert (
        inspect.signature(sensapex.setLimits).parameters
        == inspect.signature(Stage.setLimits).parameters
    ), "the override must not narrow the base signature; callers pass x/y/z/d positionally"


def test_set_limits_pushes_the_whole_set_after_the_base_has_updated_it(sensapex):
    """setLimits pushes the full limit set to the driver once, after Stage.setLimits stores it."""
    pushed = []

    class _FakeDriver:
        def set_limits(self, limits):
            pushed.append([tuple(lim) for lim in limits])

    dev = _stub(sensapex, nAxes=4)
    dev.dev = _FakeDriver()
    dev._limits = [(None, None)] * 4
    recorded = []
    dev._setHardwareLimits = lambda axis, limit: recorded.append((axis, limit))
    dev.sigLimitsChanged = type("_Sig", (), {"emit": staticmethod(lambda *a: None)})()

    sensapex.setLimits(dev, x=(0, 100), d=(-50, 50))

    assert dev._limits[0] == (0, 100)
    assert dev._limits[3] == (-50, 50)
    assert pushed == [[(0, 100), (None, None), (None, None), (-50, 50)]], (
        "the driver gets the limits as stored by Stage.setLimits"
    )
    assert recorded == [(0, (0, 100)), (3, (-50, 50))], (
        "Stage.setLimits calls _setHardwareLimits for each axis given"
    )


def test_the_per_axis_hook_is_implemented(sensapex):
    # Stage._setHardwareLimits raises NotImplementedError, and Stage.setLimits calls it
    # for each axis with the limits capability.
    dev = _stub(sensapex)
    dev.sensapexSetHardwareLimitsProbe = None
    sensapex._setHardwareLimits(dev, axis=0, limit=(0, 100))


class _FakeSignal:
    def connect(self, *args, **kwargs):
        pass


class _InterfaceDev:
    """Just enough Sensapex for SensapexInterface.__init__ to build its widgets."""

    class _Driver:
        def get_soft_start_state(self):
            return 0

        def get_soft_start_value(self):
            return 10

    def __init__(self, nAxes=4):
        self.nAxes = nAxes
        self.dev = self._Driver()
        self.config = {}
        self._limits = [(None, None)] * nAxes
        self.sigPositionChanged = _FakeSignal()
        self.sigLimitsChanged = _FakeSignal()
        self.setLimitsCalls = []

    def axes(self):
        return ("x", "y", "z", "d")[: self.nAxes]

    def capabilities(self):
        return {
            "getPos": (True,) * self.nAxes,
            "setPos": (True,) * self.nAxes,
            "limits": (True,) * self.nAxes,
        }

    def globalPosition(self):
        return [0.0] * self.nAxes

    def getPosition(self):
        return [0.0] * self.nAxes

    def getLimits(self):
        return list(self._limits)

    def setLimits(self, **kwds):
        self.setLimitsCalls.append(kwds)


def test_the_device_interface_builds_when_limits_are_a_capability(qapp):
    """SensapexInterface builds a pair of limit checkboxes per axis with the limits capability."""
    pytest.importorskip("sensapex")
    from acq4.devices.Sensapex import SensapexInterface

    dev = _InterfaceDev()
    iface = SensapexInterface(dev, win=None)

    assert sorted(iface.limitChecks) == [0, 1, 2, 3], "one pair of checkboxes per axis"


def test_ticking_a_limit_checkbox_sets_that_limit_on_the_device(qapp):
    """Clicking a limit checkbox sets that limit to the current position."""
    pytest.importorskip("sensapex")
    from acq4.devices.Sensapex import SensapexInterface

    dev = _InterfaceDev()
    dev.getPosition = lambda: [1e-3, 0.0, 0.0, 0.0]
    iface = SensapexInterface(dev, win=None)

    minCheck, _maxCheck = iface.limitChecks[0]
    minCheck.setChecked(True)
    minCheck.clicked.emit(True)

    assert dev.setLimitsCalls == [{"x": (1e-3, None)}]


def test_the_checkboxes_show_the_limits_the_device_already_has(qapp):
    """The checkboxes show limits already set on the device when the interface opens."""
    pytest.importorskip("sensapex")
    from acq4.devices.Sensapex import SensapexInterface

    dev = _InterfaceDev()
    dev._limits[2] = (-5e-3, 5e-3)
    iface = SensapexInterface(dev, win=None)

    minCheck, maxCheck = iface.limitChecks[2]
    assert minCheck.isChecked() and maxCheck.isChecked()
    assert "5" in maxCheck.text(), "the checkbox label shows its limit"
