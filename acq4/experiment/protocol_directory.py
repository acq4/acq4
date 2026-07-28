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

    `scan()` is the reload-all path: it re-`load()`s known files, discovers
    newly-appeared ones, and drops entries whose file no longer exists.
    """

    def __init__(self, path: str):
        self.path = path
        self.protocols: dict[str, ProtocolFile] = {}

    def scan(self) -> None:
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

        for name in list(self.protocols):
            if name not in found_names:
                del self.protocols[name]

    def reload_all(self) -> None:
        self.scan()

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
