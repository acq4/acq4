# MotionPlanner ABC: plan() produces a pure-data tree; execute() reserves devices and runs it.
from __future__ import annotations

from acq4 import getManager
from acq4.util.future import future_wrap
from .executor import execute_plan
from .plan import AtomicMove, MovePlanStep, ParallelGroup, SequentialGroup
from .spec import MoveSpec


class PlanningError(Exception):
    """Raised when a spec cannot be satisfied."""


class MotionPlanner:
    def __init__(self, config=None):
        self.config = config or {}

    def plan(self, specs: list[MoveSpec], name: str = "") -> MovePlanStep:
        """Return a plan tree without executing anything.

        May read device positions and write to internal state (e.g. scope context),
        but must not command any hardware.
        """
        raise NotImplementedError

    def collect_devices(self, plan: MovePlanStep) -> set:
        """Return the set of all devices that should be reserved during plan execution.

        The default implementation walks the plan tree.  Subclasses may extend this
        to add devices that are not moved but must be held stable during execution
        (e.g. a scope whose position must not change while a pipette path is being
        computed around it).
        """
        if isinstance(plan, AtomicMove):
            return {plan.device}
        if isinstance(plan, (SequentialGroup, ParallelGroup)):
            devices: set = set()
            for step in plan.steps:
                devices |= self.collect_devices(step)
            return devices
        return set()

    @future_wrap
    def execute(self, specs: list[MoveSpec], name: str = "", _future=None):
        """Plan and execute, holding device locks for the duration."""
        plan = self.plan(specs, name=name)
        devices = self.collect_devices(plan)
        man = getManager()
        with man.reserveDevices(list(devices), reserver=type(self).__name__):
            _future.waitFor(execute_plan(plan))
