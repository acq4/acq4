# Executor: walks a plan tree and issues device movement commands.
from __future__ import annotations

from acq4.util.future import future_wrap

from .plan import AtomicMove, ParallelGroup, SequentialGroup


def _move_device(device, position, speed, name):
    """Call the appropriate movement primitive on a device."""
    if hasattr(device, "moveToGlobal"):
        return device.moveToGlobal(position, speed, name=name)
    if hasattr(device, "setGlobalPosition"):
        return device.setGlobalPosition(position, speed, name=name)
    raise RuntimeError(f"Device {device!r} has no moveToGlobal or setGlobalPosition method")


@future_wrap
def execute_plan(plan, _future=None):
    """Recursively execute a plan tree, blocking until the full tree completes."""
    if isinstance(plan, AtomicMove):
        _future.waitFor(_move_device(plan.device, plan.position, plan.speed, plan.explanation))
    elif isinstance(plan, SequentialGroup):
        for step in plan.steps:
            _future.waitFor(execute_plan(step))
    elif isinstance(plan, ParallelGroup):
        # Start all branches before waiting for any of them.
        futures = [execute_plan(step) for step in plan.steps]
        for f in futures:
            _future.waitFor(f)
    else:
        raise TypeError(f"Unknown plan node type: {type(plan)}")
