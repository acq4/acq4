"""Capture a cellfie, move to the approach position, then drive the patch FSM.
Any pipette problem prompts the operator and aborts the run."""
from acq4.experiment.actions import abort, cellfie, go_approach, next_cell, patch, prompt
from acq4.experiment.exceptions import OrchestrationError

PARAMS = [{"name": "speed", "type": "str", "default": "fast"}]


def run(ctx, speed="fast"):
    try:
        cellfie(ctx)
        go_approach(ctx, speed=speed)
        outcome = patch(ctx)
        ctx.log(f"patch outcome: {outcome}")
        next_cell(ctx)
    except OrchestrationError as exc:
        prompt(ctx, message=f"Pipette problem — intervene: {exc}")
        abort(ctx)
