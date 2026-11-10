"""Patch with an adaptive seal: give up on a cell once continuing to seal it is
expected to cost more time than fetching a fresh one, rather than at a fixed
timeout.

The rule is a comparison of two durations. At any moment in the seal, the
expected remaining sealing time divided by the odds this episode pays off is the
cost of continuing; the expected wall-clock from abandoning this cell to the next
gigaseal -- cleaning, approach, and the amortized cost of finding another cell,
over the share of attempts that seal -- is the cost of starting over. Keep going
while the first is smaller.

`tune_patch_economics` is what makes those numbers real rather than guessed: it
reads every finished cell's outcome off this slice's own cell directories and
pins the result onto the patch profile for the length of the block, putting it
back afterwards. Below `min_cells` finished cells it pins the profile's own
hand-set values instead, so the rule always runs on something and the Area 5
timeline says which.

Two things bound what this can do, both deliberate:

- `autoSealTimeout` stays a hard ceiling. The rule can abandon a cell earlier
  than the configured timeout, never hold one past it, because the recorded runs
  it is tuned against can only support giving up sooner -- an episode the rig
  already abandoned says nothing about what a longer timeout would have won.
- With `early_exit` off, every input is still computed and written into the test
  pulse log, and nothing acts on it. That is the setting to run first: it records
  what the rule *would* have done, on real cells, so the parameters can be tuned
  against the log before the rule is ever allowed to stop a seal. See
  tools/autopatch_analysis -- `economic_rule_sweep` replays exactly this.

To extend this to nucleus extraction, wrap the reseal the same way:

    with tune_patch_economics(ctx):
        reseal(ctx)

A second call is worth making there rather than reusing this one: before the
patch the cell has no recording to be judged on, and only afterwards does its
clamp quality exist to set `prizeValue` -- what this cell's nucleus is worth
against a replacement's."""

from acq4.experiment.actions import (
    change_patch_profile_params,
    clean,
    find_tip,
    go_above_target,
    go_approach,
    go_park,
    go_search,
    mark_important,
    patch,
    tune_patch_economics,
)

PARAMS = [
    {
        "name": "early_exit",
        "type": "bool",
        "default": False,
        "tip": "Act on the economic stopping rule. Off by default, and worth "
        "leaving off for a session or two: the rule's inputs are recorded "
        "either way, so running it disabled produces the log the parameters "
        "are tuned from without any cell being abandoned on an untuned rule.",
    },
    {
        "name": "min_cells",
        "type": "int",
        "default": 0,
        "tip": "Finished cells this slice needs before its own measured "
        "numbers are trusted over the profile's hand-set ones. 0 takes the "
        "rig's `misc.minCellsForSliceStats`, which is where this normally "
        "belongs -- it is a property of the preparation, not of one protocol.",
    },
    {
        "name": "force_clean",
        "type": "bool",
        "default": False,
        "tip": "Run the cleaning cycle at the start even when the pipette "
        "reports its tip is already clean.",
    },
]


def run(ctx, early_exit=False, min_cells=0, force_clean=False):
    clean(ctx, only_if_needed=not force_clean)
    go_search(ctx)
    find_tip(ctx)
    go_above_target(ctx)
    # Again: the move above loses the offset solved for in the search field.
    find_tip(ctx)
    go_approach(ctx)
    try:
        # Two nested scopes rather than one call that does both, because they
        # answer different questions and an operator reading the timeline should
        # see them separately: the outer one is this protocol opting in, the
        # inner one is what this slice turned out to be worth.
        with change_patch_profile_params(ctx, {"seal": {"earlyExitEnabled": early_exit}}):
            with tune_patch_economics(ctx, min_cells=min_cells or None):
                outcome = patch(ctx)
        ctx.log(f"patch outcome: {outcome}")
        if outcome == "whole cell":
            mark_important(ctx)
    finally:
        # As in example_patch: every way out of the block above leaves the tip in
        # the tissue, so the retraction is a finally rather than a closing line.
        go_park(ctx)
