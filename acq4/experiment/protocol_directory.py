"""ProtocolDirectory: scans an operator's protocol directory for .py files and
holds a ProtocolFile per discovered file, including ones that fail to load."""
from __future__ import annotations

import os
from pathlib import Path

from .protocol_file import ProtocolFile, ProtocolLoadError


class ProtocolDirectory:
    """Scans `path` for `.py` protocol files and keeps a `ProtocolFile` per
    discovered name (the filename stem). A file that fails to import is kept
    in `protocols` with its error recorded, rather than raised or hidden, so
    the UI can list a broken protocol with an error indicator.

    `scan()` is the discovery path: it discovers newly-appeared files, drops
    entries whose file no longer exists, and `load()`s only entries that are
    new or that previously failed to load -- an already-loaded ProtocolFile is
    left untouched, so a rescan never clobbers a live, edited param tree still
    held by an in-progress run. `reload_all()` is the explicit force-reload
    path: it re-`load()`s every discovered file regardless of its current
    state, resetting any edited param tree back to the file's defaults.
    """

    def __init__(self, path: str):
        self.path = path
        self.protocols: dict[str, ProtocolFile] = {}

    def scan(self) -> None:
        self._discover(force=False)

    def reload_all(self) -> None:
        self._discover(force=True)

    def _discover(self, force: bool) -> None:
        if not os.path.isdir(self.path):
            return

        found_names = set()
        for entry in os.listdir(self.path):
            if not entry.endswith(".py") or entry.startswith("_"):
                continue
            name = Path(entry).stem
            found_names.add(name)
            protocol = self.protocols.get(name)
            if protocol is None:
                protocol = ProtocolFile(os.path.join(self.path, entry))
                self.protocols[name] = protocol
                self._load_quietly(protocol)
            elif force or not protocol.is_loaded:
                self._load_quietly(protocol)

        for name in list(self.protocols):
            if name not in found_names:
                del self.protocols[name]

    def reload(self, name: str) -> None:
        protocol = self.get(name)
        self._load_quietly(protocol)

    def get(self, name: str) -> ProtocolFile:
        return self.protocols[name]

    @staticmethod
    def _load_quietly(protocol: ProtocolFile) -> None:
        try:
            protocol.load()
        except ProtocolLoadError:
            pass
