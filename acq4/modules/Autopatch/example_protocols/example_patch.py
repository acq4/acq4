"""Capture a cellfie, move to the approach position, then drive the patch FSM.
On a successful patch (whole cell), runs the sequence already loaded in an
open TaskRunner module -- have one open, with a sequence loaded, before
running this protocol. Any other outcome prompts the operator to intervene."""
from acq4.experiment.actions import cellfie, go_approach, load_preset, patch, prompt, run_task

PARAMS = [
    {"name": "cellfie_preset", "type": "str", "default": ""},
    {"name": "patch_preset", "type": "str", "default": ""},
]


def run(ctx, cellfie_preset="", patch_preset=""):
    load_preset(ctx, cellfie_preset)
    cellfie(ctx)
    load_preset(ctx, patch_preset)
    go_approach(ctx)
    # patch() declares "broken"/"fouled" as its own terminal states, so it
    # returns them as an outcome rather than raising -- unlike reseal()/
    # clean(), which don't declare them and so raise BrokenPipette/Fouled
    # instead. That's why this is an outcome check, not a try/except
    # OrchestrationError around patch().
    outcome = patch(ctx)
    ctx.log(f"patch outcome: {outcome}")
    if outcome != "whole cell":
        prompt(ctx, message=f"Patch ended in {outcome!r} — intervene if needed")
        return
    run_task(ctx)
