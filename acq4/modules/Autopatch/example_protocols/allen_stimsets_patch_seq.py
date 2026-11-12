"""Patch-seq run with the Allen (MIES) stimsets recorded at each patching event,
in place of the TaskRunner sequence of example_patch_seq.

Stages, each one stimset run by the Allen stimset runner:

- EXTPSMOKET: rig check with the tip out of the bath, at its home position,
  before the search move takes it into the bath.
- EXTPINBATH: pipette resistance and leak at the search position, after the
  tip is found and before the approach, with `in_bath_pressure` applied.
- EXTPCllATT: the ~61 s seal recording. `seal` stops the FSM at cell attached
  and holds it there (no automatic or spontaneous transitions) for the
  recording; `break_in` then breaks in.
- EXTPBREAKN: access resistance right after break-in.
- X0NRMP through X7RampN3, then optionally the chirps, as stimset chains.
- EXTPEXPEND: a closing recording before the reseal.

The nucleus tail (reseal, image, home, deposit) and the tube gate are those of
example_patch_seq. Every stage's result is recorded in the cell's notebook and
its Area 5 entry; the `on_*_fail` params say what a failed stage does:
"continue", "next cell" (park and move on) or "abort run".
"""

from acq4.experiment.actions import (
    break_in,
    cellfie,
    clean,
    collect,
    find_tip,
    go_above_target,
    go_approach,
    go_home,
    go_park,
    go_search,
    home_with_nucleus,
    load_preset,
    mark_important,
    nucleus_sites_exhausted,
    prompt,
    reseal,
    run_stimset,
    run_stimset_chain,
    seal,
    snap,
    sonicate,
    swap_tubes,
    verify_cell,
)

SMOKE_TEST = "EXTPSMOKET180424_DA_0"
IN_BATH = "EXTPINBATH180424_DA_0"
CELL_ATTACHED = "EXTPCllATT180424_DA_0"
BREAK_IN = "EXTPBREAKN180424_DA_0"
WHOLE_CELL_CHAIN = ("X0NRMP_DA_0", "X7RampN3_DA_0")
CHIRP_CHAIN = ("C2CHIRPA180503_DA_0", "C2CHIRPB180503_DA_0")
EXPERIMENT_END = "EXTPEXPEND180424_DA_0"

FAIL_POLICIES = ["continue", "next cell", "abort run"]

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
        "cellfie taken after the whole-cell stimsets. Leave empty to skip "
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
        "pipette reports its tip is already clean.",
    },
    {
        "name": "quick_clean_protocol",
        "type": "str",
        "default": "quick clean",
        "tip": "Sonicator protocol run at the search position, before the tip "
        "finding. Must name an entry in the Sonicator device's `protocols` "
        "config. Leave empty to skip the sonication.",
    },
    {
        "name": "tube_id_format",
        "type": "str",
        "default": "PXS4_%y%m%d_{tube_count + 701}_A01",
        "tip": "Template the rack-swap dialog prefills tube ids from: strftime, "
        "then an f-string over index, row, col, well and tube_count.",
    },
    {
        "name": "smoke_test",
        "type": "bool",
        "default": True,
        "tip": "Run EXTPSMOKET at the start of the cell. The pipette is moved "
        "home (out of the bath) first; already home, the move is a no-op.",
    },
    {
        "name": "on_smoke_test_fail",
        "type": "list",
        "limits": FAIL_POLICIES,
        "default": "continue",
        "tip": "What a failed EXTPSMOKET does: continue, move to the next cell, "
        "or abort the run (a rig or headstage problem).",
    },
    {
        "name": "in_bath_pressure",
        "type": "float",
        "default": 3500.0,
        "suffix": "Pa",
        "siPrefix": True,
        "tip": "Positive pressure held from the regulator during EXTPINBATH, " "then restored.",
    },
    {
        "name": "on_in_bath_fail",
        "type": "list",
        "limits": FAIL_POLICIES,
        "default": "next cell",
        "tip": "What a failed EXTPINBATH (pipette resistance or leak out of "
        "range: a bad pipette) does. Default: park and move to the next cell.",
    },
    {
        "name": "on_cell_attached_fail",
        "type": "list",
        "limits": FAIL_POLICIES,
        "default": "continue",
        "tip": "What a failed EXTPCllATT (seal below threshold) does. Continue "
        "goes on to break in.",
    },
    {
        "name": "on_break_in_fail",
        "type": "list",
        "limits": FAIL_POLICIES,
        "default": "continue",
        "tip": "What a failed EXTPBREAKN (access resistance or leak out of "
        "range) does. Continue goes on to the whole-cell stimsets.",
    },
    {
        "name": "run_chirps",
        "type": "bool",
        "default": False,
        "tip": "After X0NRMP..X7RampN3, run the chirps C2CHIRPA then C2CHIRPB " "(human cells).",
    },
    {
        "name": "stimset_source",
        "type": "str",
        "default": "",
        "tip": "MIES NWB file to read the stimsets from. Leave empty for the "
        "production stimsets bundled with ACQ4.",
    },
]


def _onFail(ctx, policy, what):
    """Act on a failed stage per *policy* (one of FAIL_POLICIES)."""
    ctx.log(f"{what} failed; on fail: {policy}")
    if policy == "next cell":
        ctx.next_cell()
    elif policy == "abort run":
        ctx.abort()


def run(
    ctx,
    cellfie_preset="",
    post_task_cellfie_preset="GFP",
    patch_preset="",
    force_clean=False,
    quick_clean_protocol="quick clean",
    tube_id_format="PFS4_%y%m%d_{tube_count + 701}_{well}",
    smoke_test=True,
    on_smoke_test_fail="continue",
    in_bath_pressure=3500.0,
    on_in_bath_fail="next cell",
    on_cell_attached_fail="continue",
    on_break_in_fail="continue",
    run_chirps=False,
    stimset_source="",
):
    source = stimset_source or None
    if nucleus_sites_exhausted(ctx) and not swap_tubes(ctx, id_format=tube_id_format):
        ctx.abort()
    clean(ctx, only_if_needed=not force_clean)
    if smoke_test:
        go_home(ctx)
        if not run_stimset(ctx, SMOKE_TEST, source=source, pausable=True).passed:
            _onFail(ctx, on_smoke_test_fail, SMOKE_TEST)
    outcome = None
    try:
        load_preset(ctx, patch_preset)
        verify_cell(ctx)
        go_search(ctx)
        sonicate(ctx, protocol=quick_clean_protocol, pressure=50e3, settle=4.0)
        find_tip(ctx)
        if not run_stimset(ctx, IN_BATH, source=source, pressure=in_bath_pressure).passed:
            _onFail(ctx, on_in_bath_fail, IN_BATH)
        go_above_target(ctx)
        find_tip(ctx)
        load_preset(ctx, cellfie_preset)
        cellfie(ctx)
        load_preset(ctx, patch_preset)
        go_approach(ctx)

        outcome = seal(ctx)
        ctx.log(f"seal outcome: {outcome}")
        if outcome == "cell attached":
            if not run_stimset(ctx, CELL_ATTACHED, source=source).passed:
                _onFail(ctx, on_cell_attached_fail, CELL_ATTACHED)
            outcome = break_in(ctx)
            ctx.log(f"break-in outcome: {outcome}")
        if outcome == "whole cell":
            mark_important(ctx)
            if not run_stimset(ctx, BREAK_IN, source=source).passed:
                _onFail(ctx, on_break_in_fail, BREAK_IN)
            # one run, so VM's autobias target still holds for the chirps
            run_stimset_chain(
                ctx, *WHOLE_CELL_CHAIN, source=source, then=[CHIRP_CHAIN] if run_chirps else []
            )
            run_stimset(ctx, EXPERIMENT_END, source=source, clamp_mode="VC")
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
