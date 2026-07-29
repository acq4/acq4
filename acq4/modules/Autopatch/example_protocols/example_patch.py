"""Capture a cellfie, move to the approach position, then drive the patch FSM.
A broken or fouled pipette prompts the operator and aborts the run; otherwise
advances to the next cell."""
from acq4.experiment.actions import abort, cellfie, go_approach, next_cell, patch, prompt

PARAMS = [{"name": "speed", "type": "str", "default": "fast"}]


def run(ctx, speed="fast"):
    cellfie(ctx)
    go_approach(ctx, speed=speed)
    outcome = patch(ctx)
    ctx.log(f"patch outcome: {outcome}")
    if outcome in ("broken", "fouled"):
        prompt(ctx, message=f"Pipette {outcome} — intervene")
        abort(ctx)
    else:
        next_cell(ctx)
