"""A stepwise Scientifica move must command its substeps in the driver's units.

The stepwise path exists for speeds below the controller's minimum: the target is walked
forward in time and each substep is commanded as slowly as the controller can go. Speeds
cross the Stage API in m/s and the driver wants um/s, so a substep handed the unconverted
minimum asks for 1e-4 um/s -- a figure that reaches the controller as a maxSpeed of zero
and leaves it running at whatever it pleases, with a pipette already in tissue.
"""

from __future__ import annotations

import numpy as np
import pytest


class _FakeDriverRequest:
    def wait(self, timeout=None):
        return None


class _FakeDriver:
    """Records the speed of every substep asked for."""

    def __init__(self):
        self.calls = []

    def moveTo(self, pos, speed=None, name=None, **kwds):
        self.calls.append((np.asarray(pos, dtype=float), speed, name))
        return _FakeDriverRequest()


class _FakeScientifica:
    """Just enough of the device for MoveFuture.__init__ and _stepwiseMove."""

    def __init__(self, startPos, minimumSpeed):
        self._pos = list(startPos)
        self.minimumSpeed = minimumSpeed
        self.driver = _FakeDriver()

    def name(self):
        return "FakeScientifica"

    def getPosition(self):
        return list(self._pos)


@pytest.fixture
def stepwise_future(qapp):
    """A ScientificaMoveFuture set up to run _stepwiseMove over a stub driver.

    Built with __new__ plus the MoveFuture base initializer, the way the Sensapex move
    tests do: ScientificaMoveFuture.__init__ would start a producer thread and talk to a
    controller.
    """

    pytest.importorskip("serial")

    from acq4.devices.Scientifica.scientifica import ScientificaMoveFuture
    from acq4.devices.Stage.Stage import MoveFuture

    def factory(start, target, speed, minimumSpeed=100e-6):
        dev = _FakeScientifica(start, minimumSpeed)
        fut = ScientificaMoveFuture.__new__(ScientificaMoveFuture)
        MoveFuture.__init__(fut, dev, pos=target, speed=speed, name="test stepwise move")
        fut._moveReq = None
        fut.doStepwise = True
        return fut

    return factory


def test_each_substep_is_commanded_in_micrometres_per_second(stepwise_future):
    # The device's minimum is 100 um/s. Asked for in m/s it is 1e-4, which the driver
    # would read as a tenth of a nanometre per second.
    fut = stepwise_future([0.0, 0.0, 0.0], [1.0, 0.0, 0.0], speed=1.0, minimumSpeed=100e-6)

    fut._stepwiseMove()

    calls = fut.dev.driver.calls
    assert calls, "the walk must issue at least one substep"
    for _, speed, _ in calls:
        assert speed == pytest.approx(100.0), (
            "substeps are commanded at the controller's minimum, in its own um/s"
        )


def test_the_substep_speed_follows_the_configured_minimum(stepwise_future):
    fut = stepwise_future([0.0, 0.0, 0.0], [1.0, 0.0, 0.0], speed=1.0, minimumSpeed=250e-6)

    fut._stepwiseMove()

    assert fut.dev.driver.calls[0][1] == pytest.approx(250.0)


def test_the_walk_ends_on_the_target(stepwise_future):
    fut = stepwise_future([0.0, 0.0, 0.0], [1.0, 2.0, 3.0], speed=1.0)

    fut._stepwiseMove()

    assert fut.dev.driver.calls[-1][0] == pytest.approx([1.0, 2.0, 3.0])
    assert fut.is_done
