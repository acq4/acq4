"""Site actions: notice an exhausted nucleus rack, have the operator label and
swap a fresh one, and report which cell's nucleus went into which tube."""
from __future__ import annotations

from acq4.util.TubeRackPrompt import prompt_tube_rack

from ..exceptions import OrchestrationError
from ..tube_ids import generate_tube_ids, read_tube_count, well_label, write_tube_count

_SWAP_MESSAGE = (
    "Every nucleus tube is used. Load a fresh rack, check the ids below, and "
    "confirm."
)


def nucleus_sites_exhausted(ctx) -> bool:
    """Whether this pipette has no nucleus site left to deposit into.

    Scoped to the nucleus role alone; no other role is checked. A pipette with
    nothing assigned reports exhausted, which is the same answer for a protocol
    gating on it: there is nowhere to put a nucleus either way.
    """
    return ctx.pipette.pipetteDevice.getSiteFor("nucleus") is None


def swap_tubes(
    ctx, id_format, title: str = "Swap nucleus tubes", message: str = _SWAP_MESSAGE
) -> bool:
    """Ask the operator to load and label a fresh rack; return whether they did.

    On confirm every site is cleared and relabelled, and the day's tube counter
    advances past the whole rack. On cancel nothing changes. What a protocol
    does with a False is the protocol's decision -- _example_patch_seq aborts the
    run, because continuing would patch a cell with nowhere to put its nucleus.

    `id_format` is an operator's template string (see tube_ids.format_tube_id)
    or, for a scheme a template cannot express, a callable taking the namespace
    as keywords.
    """
    with ctx.log_action("Swap Nucleus Tubes") as action_entry:
        array = _nucleus_array(ctx)
        # Before the clear, which drops the tube ids the report joins on -- and
        # before the dialog, which is where the operator reads it with the old
        # rack still in hand.
        report = build_tube_report(array, _current_dir(ctx))
        rows, cols = array.rows, array.cols

        def make_ids(start, column_major):
            return generate_tube_ids(
                id_format, rows, cols, start, column_major=column_major
            )

        action_entry.set_status("waiting for the operator to swap the rack")
        answer = prompt_tube_rack(
            title,
            message,
            rows,
            cols,
            make_ids,
            read_tube_count(array),
            extra_text=report,
        )
        lines = report.split("\n")
        if answer is None:
            action_entry.set_status("operator cancelled")
            action_entry.set_details("text", {"lines": lines + ["", "operator cancelled"]})
            return False
        ids, confirmed_start_n = answer
        array.clearUsedUp()
        write_tube_count(array, confirmed_start_n + len(array.sites))
        for index, site in enumerate(array.sites):
            site.tube_id = ids.get(index)
        action_entry.set_status(f"loaded {len(array.sites)} fresh tubes")
        action_entry.set_details("text", {"lines": lines})
        return True


def tube_report(ctx) -> str:
    """The cell-to-tube table for the rack this pipette currently has loaded,
    retained for Area 5. See build_tube_report for what a swap leaves out."""
    with ctx.log_action("Tube Report") as action_entry:
        report = build_tube_report(_nucleus_array(ctx), _current_dir(ctx))
        action_entry.set_details("text", {"lines": report.split("\n")})
        return report


def build_tube_report(array, dirHandle) -> str:
    """One row per tube: its index, its well, the cell whose nucleus is in it,
    and its id.

    Two sources, joined on the id string: the array supplies the rack as it
    stands now, including the tubes nothing went into, and a walk of the Day
    directory supplies which cell named which id. The join key is the id rather
    than the position because positions are reused by every rack.

    The table is scoped to the rack currently loaded, not to the day: a swap
    clears every tube id, so cells collected into a retired rack match no site
    and do not appear here. Their record survives on each cell's own .index,
    and swap_tubes snapshots the outgoing rack's table into its action details.

    Two cells that recorded the same id collapse to whichever the walk reaches
    last. An id format carrying the day's tube count keeps them distinct.

    Takes a device and a directory handle rather than a context, so it has
    nothing to do with a run in progress.
    """
    cells = _cells_by_tube_id(_day_dir(dirHandle))
    headers = ("tube", "position", "cell", "tube id")
    rows = []
    for index, site in enumerate(array.sites):
        tube_id = site.tube_id or ""
        rows.append(
            (
                str(index),
                well_label(index, array.cols),
                cells.get(tube_id, "--") if tube_id else "--",
                tube_id,
            )
        )
    widths = [max(len(row[i]) for row in (headers, *rows)) for i in range(len(headers))]
    return "\n".join(
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip()
        for row in (headers, *rows)
    )


def _nucleus_array(ctx):
    """This pipette's nucleus rack, or an error naming what is missing."""
    device = ctx.pipette.pipetteDevice.getSiteDeviceFor("nucleus")
    if device is None or not hasattr(device, "getFirstAvailableSite"):
        raise OrchestrationError(
            "no InteractionSiteArray is assigned to this pipette's 'nucleus' role"
        )
    return device


def _current_dir(ctx):
    manager = getattr(ctx, "manager", None)
    return None if manager is None else manager.getCurrentDir()


def _day_dir(dirHandle):
    """The Day directory at or above `dirHandle`, or None.

    A rack outlives a slice, so the cell lookup has to start here rather than at
    the slice. Bounded the same way create_data_dir's walk is, since a directory
    tree's root is its own parent.
    """
    candidate = dirHandle
    for _ in range(5):
        if candidate is None or not candidate.isManaged():
            return None
        if candidate.info().get("dirType") == "Day":
            return candidate
        candidate = candidate.parent()
    return None


def _cells_by_tube_id(dayDir) -> dict:
    """{tube id: "Slice_000/Cell_003"} from the .index entries collect wrote."""
    if dayDir is None:
        return {}
    cells = {}
    for slice_name in dayDir.ls():
        if not dayDir.isDir(slice_name):
            continue
        slice_dir = dayDir[slice_name]
        for cell_name in slice_dir.ls():
            if not slice_dir.isDir(cell_name):
                continue
            tube_id = slice_dir[cell_name].info().get("nucleus_tube_id")
            if tube_id:
                cells[tube_id] = f"{slice_name}/{cell_name}"
    return cells
