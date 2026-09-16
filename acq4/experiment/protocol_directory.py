"""ProtocolDirectory: scans one or more protocol directories for .py files and
holds a ProtocolFile per discovered file, including ones that fail to load."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from .protocol_file import ProtocolFile, ProtocolLoadError


class ProtocolDirectory:
    """Scans `path` for `.py` protocol files and keeps a `ProtocolFile` per
    discovered name (the filename stem). A file that fails to import is kept
    in `protocols` with its error recorded, rather than raised or hidden, so
    the UI can list a broken protocol with an error indicator.

    `extra_paths` are further directories searched *after* `path`, for
    protocols that live somewhere the operator does not own -- the examples
    bundled with the Autopatch module are the case this exists for. They are
    listed in place rather than copied in, so there is exactly one copy of a
    bundled protocol on disk and editing it is editing the file everyone
    runs. Names collide by stem and the earlier path wins, so `path` shadows
    every extra: an operator who wants their own version of a bundled
    protocol copies it into `path` under the same name, and removing that
    copy again falls back to the bundled one on the next scan.

    `scan()` is the discovery path: it discovers newly-appeared files, drops
    entries whose file no longer exists, and `load()`s only entries that are
    new, that resolve to a different file than before (a shadowing copy
    appearing or going away), that previously failed to load, or whose file's
    mtime has moved on since it was last loaded -- an already-loaded
    ProtocolFile whose file is otherwise untouched is left alone, so a rescan
    never clobbers a live, edited param tree still held by an in-progress run,
    while an operator's on-disk edit is still picked up (design doc §2.6).
    `reload_all()` is the explicit force-reload path: it re-`load()`s every
    discovered file regardless of its current state or mtime, resetting any
    edited param tree back to the file's defaults.
    """

    def __init__(self, path: str, extra_paths: Iterable[str] = ()):
        self.path = path
        self.extra_paths = list(extra_paths)
        self.protocols: dict[str, ProtocolFile] = {}
        self._mtimes: dict[str, float] = {}

    @property
    def search_paths(self) -> list[str]:
        """Every directory scanned, in precedence order: `path` first."""
        return [self.path, *self.extra_paths]

    def scan(self) -> None:
        self._discover(force=False)

    def reload_all(self) -> None:
        self._discover(force=True)

    def _discover(self, force: bool) -> None:
        # Name -> the file that name resolves to. setdefault, and search_paths
        # in precedence order, is the whole of the shadowing rule: the first
        # directory holding a given stem is the one that supplies it.
        found: dict[str, str] = {}
        for root in self.search_paths:
            if not os.path.isdir(root):
                continue
            for entry in sorted(os.listdir(root)):
                if not entry.endswith(".py") or entry.startswith("_"):
                    continue
                found.setdefault(Path(entry).stem, os.path.join(root, entry))

        for name, full_path in found.items():
            protocol = self.protocols.get(name)
            # A changed path means a different file now answers to this name --
            # a shadowing copy in `path` appeared or was deleted. The old
            # ProtocolFile points at the wrong file, so it is replaced outright
            # rather than reloaded.
            if protocol is None or protocol.path != full_path:
                protocol = ProtocolFile(full_path)
                self.protocols[name] = protocol
                self._load_quietly(protocol)
                self._mtimes[name] = self._mtime(full_path)
            elif force or not protocol.is_loaded or self._mtime(full_path) != self._mtimes.get(name):
                self._load_quietly(protocol)
                self._mtimes[name] = self._mtime(full_path)

        for name in list(self.protocols):
            if name not in found:
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
