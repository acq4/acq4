# MotionPlanner ABC: plan() produces a pure-data tree; execute() reserves devices and runs it.
from __future__ import annotations

import numpy as np
from gentletask import throughline

from acq4 import getManager
from acq4.util.task import asynch, asynch_with_qt_signals
from .plan import AtomicMove, MovePlanStep, ParallelGroup, SequentialGroup
from .spec import MoveSpec


class PlanningError(Exception):
    """Raised when a spec cannot be satisfied."""


class MotionPlanner:
    """Base class for global motion planners. Subclasses must either implement plan() or override
    execute() with rig-specific logic.
    """
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

    @asynch_with_qt_signals
    def execute(self, specs: list[MoveSpec], name: str = ""):
        """Validate, plan, and execute, holding device locks for the duration."""
        self._validate_specs(specs)
        plan = self.plan(specs, name=name)
        self._validate_plan(specs, plan)
        devices = self.collect_devices(plan)
        man = getManager()
        with man.reserveDevices(list(devices), reserver=type(self).__name__):
            _execute_plan(plan)

    @staticmethod
    def _is_interaction_site(device) -> bool:
        # containsPoint distinguishes a single site from an InteractionSiteArray, which shares
        # the positions/_parentStage attributes but is a container of sites, not a site itself.
        return (
            device is not None
            and hasattr(device, "positions")
            and hasattr(device, "_parentStage")
            and hasattr(device, "containsPoint")
        )

    def _validate_specs(self, specs: list[MoveSpec]) -> None:
        """Raise PlanningError if specs contain device conflicts or bad relative-to ordering."""
        seen: dict[int, int] = {}
        for i, spec in enumerate(specs):
            dev_id = id(spec.device)
            if dev_id in seen:
                raise PlanningError(
                    f"Device {spec.device.name()} appears in specs at indices "
                    f"{seen[dev_id]} and {i}; a device can only have one final position."
                )
            seen[dev_id] = i

        device_spec_index = {id(spec.device): i for i, spec in enumerate(specs)}
        for i, spec in enumerate(specs):
            if spec.relative_to is None or self._is_interaction_site(spec.relative_to):
                continue
            anchor_idx = device_spec_index.get(id(spec.relative_to))
            if anchor_idx is not None and anchor_idx > i:
                raise PlanningError(
                    f"Spec {i} positions {spec.device.name()} relative to "
                    f"{spec.relative_to.name()}, but that anchor device is moved by spec "
                    f"{anchor_idx} (which comes later). Reorder specs so the anchor moves first."
                )

    @staticmethod
    def _collect_final_positions(plan: MovePlanStep, result: dict) -> None:
        """Walk a plan tree and record the last position for each device (in-order)."""
        if isinstance(plan, AtomicMove):
            result[id(plan.device)] = (plan.device, plan.position)
        elif isinstance(plan, (SequentialGroup, ParallelGroup)):
            for step in plan.steps:
                MotionPlanner._collect_final_positions(step, result)

    def _validate_plan(self, specs: list[MoveSpec], plan: MovePlanStep) -> None:
        """Raise PlanningError if a device's last plan position differs from the spec target.

        Interaction-site specs are skipped; their correctness is verified by the
        interaction-approach and exit tests.
        """
        final: dict[int, tuple] = {}
        self._collect_final_positions(plan, final)

        for spec in specs:
            if self._is_interaction_site(spec.relative_to):
                continue
            dev_id = id(spec.device)
            if dev_id not in final:
                continue
            _, actual = final[dev_id]
            if spec.relative_to is not None:
                expected = np.asarray(spec.relative_to.mapToGlobal(spec.position), dtype=float)
            else:
                expected = np.asarray(spec.position, dtype=float)
            if not np.allclose(actual, expected, atol=1e-9):
                raise PlanningError(
                    f"Plan inconsistency: {spec.device.name()} should end at "
                    f"{expected}, but the plan ends at {actual}."
                )


def _move_device(device, position, speed, name, kwargs):
    """Call the appropriate movement primitive on a device."""
    if hasattr(device, "moveToGlobalNoPlanning"):
        with throughline(name=f"moving {device} to '{name}'"):
            device.logger.debug(f"Starting move to {position}")
            return device.moveToGlobalNoPlanning(position, speed, name=name, **kwargs)
    raise RuntimeError(f"Device {device!r} has no moveToGlobalNoPlanning method")


def _execute_plan(plan):
    """Recursively execute a plan tree, blocking until the full tree completes."""
    if isinstance(plan, AtomicMove):
        _move_device(plan.device, plan.position, plan.speed, plan.explanation, plan.kwargs).wait()
    elif isinstance(plan, SequentialGroup):
        for step in plan.steps:
            _execute_plan(step)
    elif isinstance(plan, ParallelGroup):
        tasks = [asynch(_execute_plan)(step) for step in plan.steps]
        for task in tasks:
            try:
                task.wait()
            except Exception:
                for other in tasks:
                    if not other.is_done:
                        other.stop()
                raise
    else:
        raise TypeError(f"Unknown plan node type: {type(plan)}")
