# Fixtures for motion planner tests.
# Mock devices expose the position/transform APIs the planner needs without real hardware.
from __future__ import annotations

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

    def checkGlobalLimits(self, pos, linear=False):
        pass


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

    def approachDepth(self):
        return self._approach_depth

    def positionAtDepth(self, depth, start=None):
        if start is None:
            start = self._global_pos.copy()
        start = np.asarray(start, dtype=float)
        axis = self.globalDirection()
        dz = depth - start[2]
        dist = dz / axis[2]
        return start + dist * axis

    def scopeDevice(self):
        return self._scope

    @property
    def parentStage(self):
        return self._parent_stage

    def parentDevice(self):
        return self._parent_stage

    def pitchRadians(self):
        return np.pi / 4  # 45-degree approach angle; convenient for test geometry

    def globalDirection(self):
        pitch = self.pitchRadians()
        return np.array([np.cos(pitch), 0.0, -np.sin(pitch)])

    def _solveGlobalStagePosition(self, pos):
        return np.asarray(pos, dtype=float)

    def _moveToGlobalNoPlanning(self, pos, speed, name=None, **kwargs):
        self.moves.append((np.asarray(pos, dtype=float), speed, name))


class MockInteractionSite(MockDevice):
    """InteractionSite mock.

    Approach position is always the site's global origin (globalPosition()) unless
    save_approach_for() is called.  Interact positions are stored per-device via
    save_positions_for().  hasApproachPosition() returns True when 'site global' is present
    in positions for the given pipette, mirroring InteractionSite behaviour.
    """

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

    def save_positions_for(self, pip, interact_global):
        """Store the interact position (global) and its site-local equivalent."""
        interact_global = np.asarray(interact_global, dtype=float)
        interact_local = self.mapFromGlobal(interact_global)
        self.positions[pip.name()] = {
            "interact global": list(interact_global),
            "interact local": list(interact_local),
        }

    def save_approach_for(self, pip, site_global=None):
        """Store the approach position for pip (defaults to the site's current global origin)."""
        if site_global is None:
            site_global = self.globalPosition()
        self.positions.setdefault(pip.name(), {})
        self.positions[pip.name()]["site global"] = list(np.asarray(site_global, dtype=float))

    def hasApproachPosition(self, pip) -> bool:
        return "site global" in self.positions.get(pip.name(), {})

    def approachGlobal(self, pip):
        pos_config = self.positions.get(pip.name(), {})
        saved = pos_config.get("site global")
        if saved is not None:
            return np.asarray(saved, dtype=float)
        return self.globalPosition()

    def approachMoveSpec(self, pip, speed='fast'):
        """Fixed mock site — no stage repositioning needed."""
        return None

    def interactLocalFor(self, pip):
        pos_config = self.positions.get(pip.name(), {})
        if "interact local" not in pos_config:
            return None
        return np.asarray(pos_config["interact local"], dtype=float)


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
    s.save_positions_for(pip, np.array([0.0, 0.0, -1e-3]))
    s.save_approach_for(pip)  # enables strict path
    return s


@pytest.fixture
def site_with_scope_park(pip):
    park = np.array([20e-3, 0.0, 15e-3])
    s = MockInteractionSite("cleanwell", global_pos=(5e-3, 0.0, -2e-3), scope_park_pos=park)
    s.save_positions_for(pip, np.array([0.0, 0.0, -1e-3]))
    s.save_approach_for(pip)  # enables strict path
    return s


@pytest.fixture
def site_without_strict_path(pip):
    s = MockInteractionSite("recording_chamber", global_pos=(5e-3, 0.0, -2e-3))
    s.save_positions_for(pip, np.array([0.0, 0.0, -1e-3]))
    # no save_approach_for → hasApproachPosition returns False → permissive paths
    return s
