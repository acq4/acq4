"""Storage protocol functions: create managed data directories for an experiment
run, flag one as important, write custom metadata onto a cell or slice, and the
manager-only helper a UI button can call without a run."""
from __future__ import annotations

import time

from ..exceptions import OrchestrationError


def create_data_dir(manager, level: str = "Cell", set_current: bool = True):
    """Create a new managed data directory of a given type ("level") under the
    current storage directory and (by default) make it current. Returns the
    created directory.

    Mirrors the non-GUI logic of DataManagerModule.createNewFolder: for a typed
    level the parent is chosen by walking up the tree so a directory is not
    nested inside another of the same type. The special level "Folder" makes an
    untyped "NewFolder" under the current directory.

    Takes a manager rather than an ExecutionContext so that both a protocol
    action and an operator's button can call it. Autopatch's New slice is a
    click with no run in progress, and a UI button must not have to fabricate a
    context to reach engine logic.
    """
    cdir = manager.getCurrentDir()
    if not cdir.isManaged():
        cdir.createIndex()
    if level == "Folder":
        new_dir = cdir.mkdir("NewFolder", autoIncrement=True)
        new_dir.setInfo({})
    else:
        spec = manager.folderTypesConfig()[level]
        name = time.strftime(spec["name"])
        # Walk up to avoid nesting a directory inside one of the same type.
        parent = cdir
        check_dir = cdir
        for _ in range(5):
            if not check_dir.isManaged():
                break
            if check_dir.info().get("dirType") == level:
                parent = check_dir.parent()
                break
            check_dir = check_dir.parent()
        new_dir = parent.mkdir(name, autoIncrement=True)
        info = {"dirType": level}
        if spec.get("experimentalUnit", False):
            info["expUnit"] = True
        new_dir.setInfo(info)
    if set_current:
        manager.setCurrentDir(new_dir)
    return new_dir


def new_data_dir(ctx, level: str = "Cell", set_current: bool = True):
    """Create a new managed data directory for this run and report it to the UI.

    The protocol-facing wrapper around create_data_dir: same behaviour, plus the
    log_action entry that puts it in Area 5's timeline.
    """
    with ctx.log_action("New Data Directory") as action_entry:
        new_dir = create_data_dir(ctx.manager, level=level, set_current=set_current)
        action_entry.set_details("text", {"lines": [f"created {new_dir.name()}"]})
        return new_dir


def mark_important(ctx, important: bool = True):
    """Flag the current data directory as important, and report it to the UI.

    `important` is a metadata field every managed directory carries (see
    Manager.suggestedDirFields) and the Data Manager's tree bolds the
    directories whose index has it set, so this is what makes the cells worth
    coming back to stand out from the ones that failed.

    The current directory is the cell's own: the orchestrator creates it and
    enters it before the protocol runs (Orchestrator._makeCellDataDir), so a
    protocol marking a successful patch marks that cell.
    """
    with ctx.log_action("Mark Important") as action_entry:
        data_dir = ctx.manager.getCurrentDir()
        data_dir.setInfo({"important": important})
        action_entry.set_details(
            "text", {"lines": [f"marked {data_dir.name()} important"]}
        )
        return data_dir


def _dir_of_type(ctx, level: str, action_name: str):
    """The managed directory of `level` at or above the current one.

    Bounded the same way create_data_dir's walk is, since a directory tree's
    root is its own parent.
    """
    candidate = ctx.manager.getCurrentDir()
    for _ in range(5):
        if candidate is None or not candidate.isManaged():
            break
        if candidate.info().get("dirType") == level:
            return candidate
        candidate = candidate.parent()
    raise OrchestrationError(
        f"{action_name}: no {level} directory at or above "
        f"{ctx.manager.getCurrentDir().name()}"
    )


def _write_metadata(ctx, level: str, values: dict, action_name: str, overwrite: bool):
    with ctx.log_action(action_name) as action_entry:
        data_dir = _dir_of_type(ctx, level, action_name)
        info = data_dir.info()
        if not overwrite:
            taken = sorted(name for name in values if name in info)
            if taken:
                shown = ", ".join(f"{name}={info[name]!r}" for name in taken)
                raise OrchestrationError(
                    f"{action_name}: {data_dir.name()} already records {shown}"
                )
        lines = []
        for name, value in values.items():
            if name in info:
                lines.append(f"{name}: {info[name]!r} -> {value!r}")
            else:
                lines.append(f"{name} = {value!r}")
        data_dir.setInfo(dict(values))
        action_entry.set_details("text", {"lines": [data_dir.name()] + lines})
        return data_dir


def set_cell_metadata(ctx, values: dict):
    """Record metadata on this cell's data directory, failing if any of the keys
    is already recorded there. Returns the directory written to.

        set_cell_metadata(ctx, {"condition": "drug", "operator": "mc"})

    Nothing is written when a key is taken, so a rejected call leaves the index
    as it was. Use update_cell_metadata to overwrite on purpose.
    """
    return _write_metadata(ctx, "Cell", values, "Set Cell Metadata", overwrite=False)


def update_cell_metadata(ctx, values: dict):
    """Record metadata on this cell's data directory, overwriting any of the keys
    already recorded there. Returns the directory written to.
    """
    return _write_metadata(ctx, "Cell", values, "Update Cell Metadata", overwrite=True)


def set_slice_metadata(ctx, values: dict):
    """Record metadata on the Slice directory above this cell, failing if any of
    the keys is already recorded there. Returns the directory written to.

    Every cell of the slice shares it, so this is for what describes the tissue
    rather than the recording.
    """
    return _write_metadata(ctx, "Slice", values, "Set Slice Metadata", overwrite=False)


def update_slice_metadata(ctx, values: dict):
    """Record metadata on the Slice directory above this cell, overwriting any of
    the keys already recorded there. Returns the directory written to.
    """
    return _write_metadata(
        ctx, "Slice", values, "Update Slice Metadata", overwrite=True
    )
