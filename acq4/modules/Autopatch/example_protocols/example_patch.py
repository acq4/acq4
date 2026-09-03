"""Capture a cellfie, move to the approach position, then drive the patch FSM.
On a successful patch (whole cell), marks the cell's data directory important
and runs the sequence already loaded in an open TaskRunner module -- have one
open, with a sequence loaded, before running this protocol. Any other outcome
prompts the operator to intervene.

`cellfie_preset` and `patch_preset` name configured microscope imaging
presets (e.g. "GFP", "brightfield") to load before the cellfie and before the
patch attempt, respectively; leave either empty to skip it.

`initialize_tracker` seeds the cell's visual tracker from the cellfie stack.
Off by default: with a fluorescence `cellfie_preset`, that stack is no use as
a reference for tracking the cell in brightfield. Turn it on only when the
cellfie is captured under the same imaging the approach uses.

The run opens with a pipette clean, which is skipped when the pipette reports
its tip is still clean; `force_clean` runs the cycle regardless."""

from acq4.experiment.actions import (
    cellfie,
    clean,
    go_approach,
    load_preset,
    mark_important,
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
        "name": "initialize_tracker",
        "type": "bool",
        "default": False,
        "tip": "Seed the cell's visual tracker from the cellfie z-stack. Off "
        "by default: a cellfie taken under fluorescence is no use as a "
        "reference for tracking the cell in brightfield. Turn it on only when "
        "the cellfie is captured under the same imaging the approach uses.",
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


def run(ctx, cellfie_preset="", patch_preset="", initialize_tracker=False, force_clean=False):
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
    cellfie(ctx, initialize_tracker=initialize_tracker)
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
    # Before run_task, not after: reaching whole cell is what makes this cell
    # worth coming back to, and the flag should be on its directory even if the
    # recording that follows fails. mark_important never raises, so a storage
    # problem here cannot cost the recording either.
    mark_important(ctx)
    run_task(ctx)
