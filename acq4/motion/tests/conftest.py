# Fixtures for motion planner tests.
# Mock devices expose the position/transform APIs the planner needs without real hardware.
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest


class MockDevice:
    """Minimal device mock: fixed global position, records moveToGlobalNoPlanning calls."""

    def __init__(self, name, global_pos=(0.0, 0.0, 0.0)):
        self._name = name
        self._global_pos = np.asarray(global_pos, dtype=float)
        self.moves = []  # list of (pos, speed, name)

    def name(self):
        return self._name

    def globalPosition(self):
        return self._global_pos.copy()

    def moveToGlobalNoPlanning(self, pos, speed, name=None, **kwargs):
        self.moves.append((np.asarray(pos, dtype=float), speed, name))

    def mapToGlobal(self, local_pos):
        return np.asarray(local_pos, dtype=float) + self._global_pos

    def mapFromGlobal(self, global_pos):
        return np.asarray(global_pos, dtype=float) - self._global_pos


class MockStage(MockDevice):
    """Stage mock."""

    def homePosition(self):
        return np.array([0.0, 0.0, 5e-3])


class MockScope(MockDevice):
    """Microscope/scope mock with setGlobalPosition."""

    def setGlobalPosition(self, pos, speed='fast', name=None):
        self.moves.append((np.asarray(pos, dtype=float), speed, name))


class MockPipette(MockDevice):
    """Pipette tip mock.

    approach_depth: z-value (global) above which lateral movement is safe.
    """

    def __init__(self, name, global_pos=(0.0, 0.0, 0.0), approach_depth=0.0):
        super().__init__(name, global_pos)
        self._approach_depth = approach_depth
        self._scope = MockScope("scope", global_pos=(0.0, 0.0, 10e-3))
        self._parent_stage = MockStage("manipulator")

        # Default: one-step path straight to the target; override per-test as needed.
        self.pathGenerator = MagicMock()
        self.pathGenerator.safePath.side_effect = (
            lambda start, stop, speed, explanation=None:
            [(np.asarray(stop, dtype=float), speed, False, explanation or "move")]
        )

    def approachDepth(self):
        return self._approach_depth

    def positionAtDepth(self, depth, start=None):
        pos = (start if start is not None else self._global_pos).copy()
        pos = np.asarray(pos, dtype=float).copy()
        pos[2] = depth
        return pos

    def scopeDevice(self):
        return self._scope

    @property
    def parentStage(self):
        return self._parent_stage

    def parentDevice(self):
        return self._parent_stage

    def _moveToGlobalNoPlanning(self, pos, speed, name=None, **kwargs):
        self.moves.append((np.asarray(pos, dtype=float), speed, name))


class MockInteractionSite(MockDevice):
    """InteractionSite mock with saved approach and interact positions."""

    def __init__(
        self,
        name,
        global_pos=(0.0, 0.0, 0.0),
        scope_park_pos=None,
        parent_stage=None,
    ):
        super().__init__(name, global_pos)
        self.positions = {}
        self.config = {}
        if scope_park_pos is not None:
            self.config["scopeParkPos"] = np.asarray(scope_park_pos, dtype=float)
        self._parentStage = parent_stage or MockStage(f"{name}_stage", global_pos)

    def save_positions_for(self, pip, approach_global, interact_global):
        self.positions[pip.name()] = {
            "site global": list(approach_global),
            "interact global": list(interact_global),
        }


@pytest.fixture
def pip():
    return MockPipette("pip1", global_pos=(0.0, 0.0, 0.0))


@pytest.fixture
def scope():
    return MockScope("scope", global_pos=(0.0, 0.0, 10e-3))


@pytest.fixture
def stage():
    return MockStage("stage1", global_pos=(0.0, 0.0, 0.0))


@pytest.fixture
def site(pip):
    s = MockInteractionSite("cleanwell", global_pos=(5e-3, 0.0, -2e-3))
    approach = np.array([0.0, 0.0, 0.0])
    interact = np.array([0.0, 0.0, -1e-3])
    s.save_positions_for(pip, approach, interact)
    return s


@pytest.fixture
def site_with_scope_park(pip):
    park = np.array([20e-3, 0.0, 15e-3])
    s = MockInteractionSite(
        "cleanwell", global_pos=(5e-3, 0.0, -2e-3), scope_park_pos=park
    )
    approach = np.array([0.0, 0.0, 0.0])
    interact = np.array([0.0, 0.0, -1e-3])
    s.save_positions_for(pip, approach, interact)
    return s
