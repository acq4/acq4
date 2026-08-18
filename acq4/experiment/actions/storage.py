"""Storage protocol function: create managed data directories for an experiment
run, and the manager-only helper a UI button can call without a run."""
from __future__ import annotations

import time


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
