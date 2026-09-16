"""Bundled example Autopatch protocols.

These are listed by the protocol picker *in place*, straight out of this
package directory, rather than being copied into an operator's protocol
directory on first run. One copy on disk means an edit here is the edit every
rig runs, with no second, silently-diverging copy under a config directory to
keep in step -- see ProtocolDirectory's `extra_paths`, which is how they reach
the picker, and which lets an operator shadow one of these by name with their
own file in their own protocol directory.
"""
from __future__ import annotations

import os

#: Directory the bundled examples live in, handed to ProtocolDirectory as an
#: extra search path (see AutopatchWindow.__init__). `_`-prefixed files -- this
#: package's own `__init__.py` included -- are skipped by the scan, so the
#: package machinery is never listed as a protocol.
EXAMPLE_PROTOCOLS_DIR = os.path.dirname(os.path.abspath(__file__))
