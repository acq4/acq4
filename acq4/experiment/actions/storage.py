"""Storage Actions: create managed data directories for an experiment run."""
from __future__ import annotations

import time

from ..action import Action
from ..registry import register_action


@register_action(name="NewDataDir")
class NewDataDirAction(Action):
    """Create a new managed data directory of a given type ("level") under the
    current storage directory and (by default) make it current.

    Mirrors the non-GUI logic of DataManagerModule.createNewFolder: for a typed
    level the parent is chosen by walking up the tree so a directory is not nested
    inside another of the same type. The special level "Folder" makes an untyped
    "NewFolder" under the current directory.
    """

    outcomes = ("created",)
    paramSpec = (
        {"name": "level", "type": "str", "default": "Cell"},
        {"name": "setCurrent", "type": "bool", "default": True},
    )

    def run(self, ctx):
        man = ctx.manager
        cdir = man.getCurrentDir()
        if not cdir.isManaged():
            cdir.createIndex()
        level = self.paramValue("level")
        if level == "Folder":
            new_dir = cdir.mkdir("NewFolder", autoIncrement=True)
            new_dir.setInfo({})
        else:
            spec = man.folderTypesConfig()[level]
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
        if self.paramValue("setCurrent"):
            man.setCurrentDir(new_dir)
        self.results["dir"] = new_dir
        return "created"
