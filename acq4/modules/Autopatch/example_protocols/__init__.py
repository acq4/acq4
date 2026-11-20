"""Bundled example Autopatch protocols, and the seeding that puts a copy of
each into an operator's protocol directory.

Every template here is named `_example_<name>.py` and is copied in as
`<name>.py` (see `seed_example_protocols`, which AutopatchWindow calls as it
opens). The prefix is the whole of the distinction between a template and the
live copy made from it: ProtocolDirectory skips `_`-prefixed files, so a
template is never listed or run where it sits, and what the picker offers is
always the operator's own copy, theirs to edit.

Seeding checks the live name and nothing else. A name already present in the
operator's directory is left untouched whatever that file contains, so an
operator's edits are never overwritten -- and a copy they delete is made again
the next time Autopatch opens.

Edit these freely. An example is a template to copy and rewrite, so what it
does is an illustration rather than a contract: no test should assert which
actions one calls, in what order, or with which params. Test the actions
themselves instead -- see acq4/modules/Autopatch/tests/test_example_protocols.py,
which covers only that these seed, load and run.
"""
from __future__ import annotations

import os
import shutil

#: Directory the templates live in, and the only thing seeding copies out of.
EXAMPLE_PROTOCOLS_DIR = os.path.dirname(os.path.abspath(__file__))

#: Marks a file here as a template rather than a protocol; stripped from the
#: filename to give the live name the copy is made under.
EXAMPLE_PREFIX = "_example_"


def seed_example_protocols(dest_dir: str) -> list[str]:
    """Copy into `dest_dir` every template whose live name is missing there,
    creating the directory if it does not exist, and return the live filenames
    copied, in the order they were made.

    Presence is decided by name alone -- see this module's docstring for why
    an existing file is never inspected, let alone replaced.
    """
    os.makedirs(dest_dir, exist_ok=True)
    copied = []
    for entry in sorted(os.listdir(EXAMPLE_PROTOCOLS_DIR)):
        if not entry.startswith(EXAMPLE_PREFIX) or not entry.endswith(".py"):
            continue
        live = entry.removeprefix(EXAMPLE_PREFIX)
        dest = os.path.join(dest_dir, live)
        if os.path.exists(dest):
            continue
        # copyfile, not copy: the destination is the operator's file from the
        # moment it exists and takes their umask, rather than inheriting
        # whatever mode the installed package directory happens to carry.
        shutil.copyfile(os.path.join(EXAMPLE_PROTOCOLS_DIR, entry), dest)
        copied.append(live)
    return copied
