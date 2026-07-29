"""Bundled example Autopatch protocols and the first-run install step that
seeds an operator's protocol directory with them."""
from __future__ import annotations

import os
import shutil

_HERE = os.path.dirname(__file__)


def install_example_protocols(protocol_dir: str) -> None:
    """Copy every bundled example_protocols/*.py into `protocol_dir`.

    Creates `protocol_dir` if it does not exist yet. Skips this package's own
    `__init__.py` and any `_`-prefixed helper, so the package machinery is
    never installed as a protocol. Skips any file whose name already exists
    there, so an operator's edits (or deletions) are never overwritten on a
    later run.
    """
    os.makedirs(protocol_dir, exist_ok=True)
    for name in sorted(os.listdir(_HERE)):
        if not name.endswith(".py") or name.startswith("_"):
            continue
        dest = os.path.join(protocol_dir, name)
        if os.path.exists(dest):
            continue
        shutil.copyfile(os.path.join(_HERE, name), dest)
