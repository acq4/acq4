"""Patch-seq run: everything example_patch does, plus the nucleus extraction
tail and the nucleus-tube bookkeeping around it.

The run opens by asking whether this pipette has a nucleus tube left. If it does
not, the operator is called over to swap the rack and label the fresh tubes; a
cancelled swap aborts the run. The gate sits ahead of the clean deliberately --
an unattended run must not spend ten minutes patching a cell it has nowhere to
put. The cost is that the operator is called over at the start of a cell rather
than right after the deposit that emptied the rack. That is the intended trade.

After a whole-cell recording the pipette reseals toward an outside-out patch,
carries the nucleus up to its home position, takes a single image of it above
the sample, and deposits it into the next free tube. `reseal` returning "whole
cell" means it fell back and there is no nucleus to deposit, so the tail is
skipped and the pipette parks.

`tube_id_format` is the template the swap dialog prefills from. It runs through
time.strftime first (so %y%m%d expands) and then as an f-string over `index`,
`row`, `col`, `well` and `tube_count` -- the day's running tube number, which is
what the dialog's start-number box and fill-order toggle move. A scheme the
template cannot express can be a callable instead; protocols are Python.

The remaining params behave exactly as they do in example_patch.
"""

from acq4.experiment.actions import (
    cellfie,
    clean,
    collect,
    find_tip,
    go_above_target,
    go_approach,
    go_park,
    go_search,
    home_with_nucleus,
    load_preset,
    mark_important,
    nucleus_sites_exhausted,
    patch,
    prompt,
    reseal,
    run_task,
    snap,
    sonicate,
    swap_tubes,
    verify_cell,
)

PARAMS = [
    {
        "name": "cellfie_preset",
        "type": "str",
        "default": "IR",
        "tip": 'Configured microscope imaging preset (e.g. "GFP") to load '
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
        "default": "IR",
        "tip": 'Configured microscope imaging preset (e.g. "brightfield") '
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
    {
        "name": "tube_id_format",
        "type": "str",
        "default": "PXS4_%y%m%d_{tube_count + 701}_A01",
        "tip": "Template the rack-swap dialog prefills tube ids from. Run "
        "through strftime (%y%m%d and friends) and then as an f-string over "
        "index, row, col, well and tube_count -- the day's running tube "
        "number. The operator can retype any id at the dialog.",
    },
]


def run(
    ctx,
    cellfie_preset="",
    post_task_cellfie_preset="GFP",
    patch_preset="",
    force_clean=False,
    quick_clean_protocol="quick clean",
    tube_id_format="PFS4_%y%m%d_{tube_count + 701}_{well}",
):
    # Before the clean, and so before anything that costs time or touches the
    # slice: a run with nowhere to put a nucleus should stop at the operator,
    # not at the end of a patch attempt.
    if nucleus_sites_exhausted(ctx) and not swap_tubes(ctx, id_format=tube_id_format):
        ctx.abort()
    clean(ctx, only_if_needed=not force_clean)
    load_preset(ctx, patch_preset)
    verify_cell(ctx)
    go_search(ctx)
    sonicate(ctx, protocol=quick_clean_protocol, pressure=50e3, settle=4.0)
    find_tip(ctx)
    go_above_target(ctx)
    find_tip(ctx)
    load_preset(ctx, cellfie_preset)
    cellfie(ctx)
    load_preset(ctx, patch_preset)
    go_approach(ctx)
    outcome = None
    try:
        outcome = patch(ctx)
        ctx.log(f"patch outcome: {outcome}")
        if outcome == "whole cell":
            mark_important(ctx)
            run_task(ctx)
            load_preset(ctx, post_task_cellfie_preset)
            cellfie(ctx)
            load_preset(ctx, patch_preset)
            if reseal(ctx) == "outside out":
                snap(ctx, name="outside_out")
                home_with_nucleus(ctx)
                collect(ctx)
    finally:
        go_park(ctx)
    if outcome not in ("whole cell", "bath", "fouled"):
        prompt(ctx, message=f"Patch ended in {outcome!r} — intervene if needed")
