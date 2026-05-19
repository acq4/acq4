# Executor: walks a plan tree and issues device movement commands.
from __future__ import annotations

from acq4.util.future import future_wrap

from .plan import AtomicMove, ParallelGroup, SequentialGroup


def _move_device(device, position, speed, name):
    """Call the appropriate movement primitive on a device."""
    if hasattr(device, "moveToGlobalNoPlanning"):
        return device.moveToGlobalNoPlanning(position, speed, name=name)
    raise RuntimeError(f"Device {device!r} has no moveToGlobalNoPlanning method")


def execute_plan(plan, _future):
    """Recursively execute a plan tree, blocking until the full tree completes."""
    if isinstance(plan, AtomicMove):
        _future.waitFor(_move_device(plan.device, plan.position, plan.speed, plan.explanation))
    elif isinstance(plan, SequentialGroup):
        for step in plan.steps:
            execute_plan(step, _future)
    elif isinstance(plan, ParallelGroup):
        # Start all branches before waiting for any of them.
        futures = [future_wrap(execute_plan)(step) for step in plan.steps]
        for f in futures:
            try:
                _future.waitFor(f)
            except Exception:
                for f2 in futures:
                    if not f2.isDone():
                        f2.stop("error in parallel movements")
                raise
    else:
        raise TypeError(f"Unknown plan node type: {type(plan)}")
