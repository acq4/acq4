"""Capture a cellfie, move to the approach position, then drive the patch FSM.
A broken or fouled pipette prompts the operator and aborts the run; otherwise
advances to the next cell."""
from acq4.experiment.actions import cellfie, go_approach, patch, prompt

PARAMS = [{"name": "speed", "type": "str", "default": "fast"}]


def run(ctx, speed="fast"):
    cellfie(ctx)
    go_approach(ctx, speed=speed)
    # patch() declares "broken"/"fouled" as its own terminal states, so it
    # returns them as an outcome rather than raising -- unlike reseal()/
    # clean(), which don't declare them and so raise BrokenPipette/Fouled
    # instead. That's why this is an outcome check, not a try/except
    # OrchestrationError around patch().
    outcome = patch(ctx)
    ctx.log(f"patch outcome: {outcome}")
    if outcome in ("broken", "fouled"):
        prompt(ctx, message=f"Pipette {outcome} — intervene")
        ctx.abort()
    else:
        ctx.next_cell()
