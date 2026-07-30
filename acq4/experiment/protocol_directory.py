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
    new, that previously failed to load, or whose file's mtime has moved on
    since it was last loaded -- an already-loaded ProtocolFile whose file is
    otherwise untouched is left alone, so a rescan never clobbers a live,
    edited param tree still held by an in-progress run, while an operator's
    on-disk edit is still picked up (design doc §2.6). `reload_all()` is the
    explicit force-reload path: it re-`load()`s every discovered file
    regardless of its current state or mtime, resetting any edited param
    tree back to the file's defaults.
    """

    def __init__(self, path: str):
        self.path = path
        self.protocols: dict[str, ProtocolFile] = {}
        self._mtimes: dict[str, float] = {}

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
            full_path = os.path.join(self.path, entry)
            protocol = self.protocols.get(name)
            if protocol is None:
                protocol = ProtocolFile(full_path)
                self.protocols[name] = protocol
                self._load_quietly(protocol)
                self._mtimes[name] = self._mtime(full_path)
            elif force or not protocol.is_loaded or self._mtime(full_path) != self._mtimes.get(name):
                self._load_quietly(protocol)
                self._mtimes[name] = self._mtime(full_path)

        for name in list(self.protocols):
            if name not in found_names:
                del self.protocols[name]
                self._mtimes.pop(name, None)

    def reload(self, name: str) -> None:
        protocol = self.get(name)
        self._load_quietly(protocol)
        self._mtimes[name] = self._mtime(protocol.path)

    def get(self, name: str) -> ProtocolFile:
        return self.protocols[name]

    @staticmethod
    def _mtime(path: str) -> float:
        try:
            return os.stat(path).st_mtime
        except OSError:
            return 0.0

    @staticmethod
    def _load_quietly(protocol: ProtocolFile) -> None:
        try:
            protocol.load()
        except ProtocolLoadError:
            pass
