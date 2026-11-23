"""Microscope.checkGlobalLimits: refusing a scope position its stage cannot reach, without moving."""

from __future__ import annotations

import numpy as np
import pytest

from acq4.devices.Microscope.tests.test_microscope_controls import MM, Rig
from acq4.devices.Stage import OutOfLimitsError


@pytest.fixture
def rig(monkeypatch):
    return Rig(monkeypatch)


def test_a_reachable_position_passes(rig):
    scope = rig.makeScope()
    rig.stage.setLimits(x=(-10 * MM, 10 * MM))
    scope.checkGlobalLimits(np.asarray(scope.globalPosition()) + [5 * MM, 0, 0], False)


def test_an_unreachable_position_raises_without_moving(rig):
    scope = rig.makeScope()
    rig.stage.setLimits(x=(-10 * MM, 10 * MM))
    before = np.asarray(rig.stage.getPosition())

    with pytest.raises(OutOfLimitsError):
        scope.checkGlobalLimits(
            np.asarray(scope.globalPosition()) + [50 * MM, 0, 0], False
        )

    assert np.allclose(rig.stage.getPosition(), before)
