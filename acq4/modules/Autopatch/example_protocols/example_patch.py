"""Capture a cellfie, move to the approach position, then drive the patch FSM.
On a successful patch (whole cell), runs the sequence already loaded in an
open TaskRunner module -- have one open, with a sequence loaded, before
running this protocol. Any other outcome prompts the operator to intervene.

`cellfie_preset` and `patch_preset` name configured microscope imaging
presets (e.g. "GFP", "brightfield") to load before the cellfie and before the
patch attempt, respectively; leave either empty to skip it.

The run opens with a pipette clean, which is skipped when the pipette reports
its tip is still clean; `force_clean` runs the cycle regardless."""

from acq4.experiment.actions import (
    cellfie,
    clean,
    go_approach,
    load_preset,
    patch,
    prompt,
    run_task,
    go_above_target,
    find_tip,
)

PARAMS = [
    {
        "name": "cellfie_preset",
        "type": "str",
        "default": "",
        "tip": "Configured microscope imaging preset (e.g. \"GFP\") to load "
        "before the cellfie. Leave empty to skip loading a preset.",
    },
    {
        "name": "patch_preset",
        "type": "str",
        "default": "",
        "tip": "Configured microscope imaging preset (e.g. \"brightfield\") "
        "to load before the patch attempt. Leave empty to skip loading a "
        "preset.",
    },
    {
        "name": "force_clean",
        "type": "bool",
        "default": False,
        "tip": "Run the cleaning cycle at the start of the run even when the "
        "pipette reports its tip is already clean. Off by default: a tip only "
        "reads dirty once it has been onto a cell since its last clean, so an "
        "untouched pipette skips the several minutes the cycle costs.",
    },
]


def run(ctx, cellfie_preset="", patch_preset="", force_clean=False):
    # First, ahead of everything else, and in particular ahead of find_tip and
    # go_approach: the cleaning cycle finishes by parking the pipette at home
    # and calling newPatchAttempt(), which clears the test-pulse history and
    # starts a fresh patch record. Calibration and positioning done before it --
    # find_tip's pipette-offset and tip-find, and the approach move -- would be
    # thrown away by the one and undone by the other.
    #
    # Nothing about the pipette forces it ahead of the cellfie as well; that is
    # about the tissue. The cycle takes minutes over at the clean and rinse
    # wells, and a z-stack captured before it has all of that time to go stale
    # against tissue that drifts. Imaging and patching want to be back to back.
    clean(ctx, only_if_needed=not force_clean)
    load_preset(ctx, cellfie_preset)
    cellfie(ctx)
    load_preset(ctx, patch_preset)
    go_above_target(ctx)
    find_tip(ctx)
    go_approach(ctx)
    # Stuck here with the status showing "now in 'cell attached'"? Check the
    # patch profile: "cell attached" only advances on a configured transition
    # (spontaneousBreakInState, or the optional autoBreakInDelay timer), so a
    # profile that configures neither never breaks in and patch() waits
    # indefinitely.
    #
    # patch() declares "broken"/"fouled" as its own terminal states, so it
    # returns them as an outcome rather than raising -- unlike reseal()/
    # clean(), which don't declare them and so raise BrokenPipette/Fouled
    # instead. That's why this is an outcome check, not a try/except
    # OrchestrationError around patch().
    outcome = patch(ctx)
    ctx.log(f"patch outcome: {outcome}")
    if outcome != "whole cell":
        if outcome not in ("bath", "fouled"):
            prompt(ctx, message=f"Patch ended in {outcome!r} — intervene if needed")
        return
    run_task(ctx)
