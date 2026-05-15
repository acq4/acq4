# MotionPlanner ABC: plan() produces a pure-data tree; execute() reserves devices and runs it.
from __future__ import annotations

from typing import TYPE_CHECKING

from acq4 import getManager
from acq4.util.future import future_wrap

from .executor import execute_plan
from .plan import collect_devices

if TYPE_CHECKING:
    from .plan import SequentialGroup
    from .spec import MoveSpec


class PlanningError(Exception):
    """Raised when a spec cannot be satisfied."""


class MotionPlanner:
    def __init__(self, config=None):
        self.config = config or {}

    def plan(self, specs: list["MoveSpec"]) -> "SequentialGroup":
        """Return a plan tree without executing anything.

        May read device positions and write to internal state (e.g. scope context),
        but must not command any hardware.
        """
        raise NotImplementedError

    @future_wrap
    def execute(self, specs: list["MoveSpec"], _future=None):
        """Plan and execute, holding device locks for the duration."""
        plan = self.plan(specs)
        devices = collect_devices(plan)
        man = getManager()
        with man.reserveDevices(list(devices), reserver=type(self).__name__):
            _future.waitFor(execute_plan(plan))
