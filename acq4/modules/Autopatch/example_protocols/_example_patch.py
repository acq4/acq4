"""Capture a cellfie, move to the approach position, then drive the patch FSM.
On a successful patch (whole cell), marks the cell's data directory important
and runs the sequence already loaded in an open TaskRunner module -- have one
open, with a sequence loaded, before running this protocol. Any other outcome
prompts the operator to intervene.

`cellfie_preset` and `patch_preset` name configured microscope imaging
presets (e.g. "GFP", "brightfield"): the cellfie one for the z-stack, the patch
one for the tip finding and the patch attempt either side of it. Leave either
empty to skip loading it.

`check_cell_present` runs the cell-tracker check (verify_cell) up front: it
confirms the cell is still findable where its tracker expects it, and seeds
that reference on a cell that does not have one yet. The tracker acquires the
reference itself, under whatever imaging preset is loaded when it runs, which
is why the check sits under `patch_preset` -- the imaging the approach follows
the cell in -- rather than under `cellfie_preset`.

The run opens with a pipette clean, which is skipped when the pipette reports
its tip is still clean; `force_clean` runs the cycle regardless.

However the run ends -- patched, failed, or raising -- it closes by parking the
tip clear of the slice. Nothing below the patch attempt retracts on its own, and
a tip left down where cell detect stopped keeps leaking internal into the tissue
and shadows the cells the next pass images.

Between the clean and the cellfie the tip is parked at the search position and
given a short sonication at positive pressure, to expel anything it picked up
leaving the clean well. It then stays in the bath, finding its tip at the
search position and again over the cell, and is still there for the cellfie.
`quick_clean_protocol` names the sonicator protocol to use; leave it empty to
skip the sonication on a rig that has no such protocol."""

from acq4.experiment.actions import (
    cellfie,
    clean,
    go_approach,
    go_park,
    go_search,
    load_preset,
    mark_important,
    patch,
    prompt,
    run_task,
    sonicate,
    go_above_target,
    find_tip,
    verify_cell,
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
        "name": "post_task_cellfie_preset",
        "type": "str",
        "default": "GFP",
        "tip": "Configured microscope imaging preset to load before the "
        "cellfie taken after the TaskRunner sequence. Leave empty to skip "
        "loading a preset.",
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
        "name": "check_cell_present",
        "type": "bool",
        "default": True,
        "tip": "Run the cell-tracker check (verify_cell) before the pipette "
        "leaves home: confirms the cell is still findable where its tracker "
        "expects it, and seeds that reference on a cell that does not have "
        "one yet. Turn off to patch without tracker verification.",
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
    {
        "name": "quick_clean_protocol",
        "type": "str",
        "default": "quick clean",
        "tip": "Sonicator protocol run at the search position, before the tip "
        "finding, to expel debris the tip picked up leaving the clean well. "
        "Must name an entry in the Sonicator device's `protocols` config -- an "
        "unconfigured name fails the run and reports which names exist. Leave "
        "empty to skip the sonication (the search move still runs).",
    },
]


def run(
    ctx,
    cellfie_preset="",
    post_task_cellfie_preset="GFP",
    patch_preset="",
    check_cell_present=True,
    force_clean=False,
    quick_clean_protocol="quick clean",
):
    # First: the cycle ends at home and calls newPatchAttempt(), discarding any
    # calibration done before it, and it takes minutes -- long enough to stale a
    # cellfie taken ahead of it.
    clean(ctx, only_if_needed=not force_clean)
    # Both find_tip calls need to see the tip under this; reloaded for the
    # approach after the cellfie.
    load_preset(ctx, patch_preset)
    # Here, not next to the cellfie: verify_cell has the tracker acquire its own
    # reference stack under whatever preset is loaded, and the approach then
    # follows the cell under `patch_preset` -- so the reference has to be taken
    # under that same imaging (a fluorescence reference is no use for tracking
    # the cell in brightfield). Ahead of go_above_target/find_tip as well, so
    # the pipette is still parked at home and out of the light path while the
    # imager runs its own z-stack over the cell.
    if check_cell_present:
        verify_cell(ctx)
    # The fine search (distance 0) centers the tip in a wide field, clear of the
    # slice -- Sonicator.safeToSonicate prompts on a tip that still looks like
    # it is in a chamber, which would stall an unattended run.
    go_search(ctx)
    # Expels what the tip collected leaving the clean well. 50 kPa / 4 s are rig
    # numbers, passed here so they are visible in the protocol.
    sonicate(ctx, protocol=quick_clean_protocol, pressure=50e3, settle=4.0)
    # Here, before moving: the sonication just shook the tip, and the search
    # field is where it is easiest to see. Nothing below lifts the pipette out of
    # the bath -- crossing the meniscus is what dirties a clean tip.
    find_tip(ctx)
    # Down to 50 um over the target: the objective would reach a tip left at the
    # search height on its way down to the cell.
    go_above_target(ctx)
    # Again, because that move loses the offset solved for in the search field.
    find_tip(ctx)
    load_preset(ctx, cellfie_preset)
    # The pipette is in frame, but far enough out of focus on a high-NA
    # objective not to obscure the cell.
    cellfie(ctx)
    load_preset(ctx, patch_preset)
    go_approach(ctx)
    # From here the tip is in the tissue, and every way out of this block leaves
    # it there: a failed cell detect returns, an operator prompt returns, an
    # unexpected error raises. So the retraction is a finally rather than a line
    # at the end -- see go_park. The orchestrator parks again after this returns,
    # which costs nothing once this has (go_park skips a tip already clear); this
    # call is here so the tip comes out as soon as it is finished with, rather
    # than after whatever the rest of this function goes on to do.
    outcome = None
    try:
        # patch() returns "broken"/"fouled" as declared terminals rather than
        # raising, so this is an outcome check, not a try/except. Stuck in "cell
        # attached"? The profile configures no break-in (see autoBreakInDelay).
        outcome = patch(ctx)
        ctx.log(f"patch outcome: {outcome}")
        if outcome == "whole cell":
            # Before run_task: whole cell is what makes the cell worth coming
            # back to, so the flag lands even if the recording that follows
            # fails.
            mark_important(ctx)
            run_task(ctx)
            # Post-recording fluorescence image of the patched cell, taken
            # before the park below pulls the tip off it.
            load_preset(ctx, post_task_cellfie_preset)
            cellfie(ctx)
            load_preset(ctx, patch_preset)
    finally:
        # Deliberately inside the finally for the whole-cell path too: the
        # recording is over by the time run_task returns, and the tip has no
        # business staying on the cell until the *next* cell's clean cycle gets
        # around to pulling it off. go_park puts the pipette in "bath" before it
        # retracts, which is what ends that recording; that is the intended trade
        # (see its docstring), not an oversight.
        go_park(ctx)
    # After the park, not before it. This prompt can sit unanswered for as long
    # as the rig is unattended, and a tip waiting that out down in the tissue is
    # the exact thing the park above exists to stop. Unreachable when patch()
    # raised: the finally retracts and the exception carries straight past here.
    if outcome not in ("whole cell", "bath", "fouled"):
        prompt(ctx, message=f"Patch ended in {outcome!r} — intervene if needed")
