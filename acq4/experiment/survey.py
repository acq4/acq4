"""The slice's survey: every tile record and hand seed, what has been handed out,
and the selector that picks the next cell from them under the current settings."""

from __future__ import annotations

import math
import re
import threading
import time
import uuid
from dataclasses import dataclass, replace

from acq4.experiment.search_grid import footprint
from acq4.experiment.survey_record import CELL_METADATA_FILE, DETECTIONS_SUFFIX, writeRecord
from acq4.logging_config import get_logger

logger = get_logger(__name__)

# How many cells one tile hands out. A tile is a field tens of cells deep, and
# working every one before moving on would spend the run in one field; the cap
# keeps a survey spreading over the region the operator drew.
MAX_TILE_CANDIDATES = 5
MANUAL_FILE = "survey_manual.yaml"
NEED_TILE = "need_tile"


def cellDistance(a, b) -> float:
    """3D distance between two global positions (coorx Points or 3-sequences)."""
    return math.dist((a[0], a[1], a[2]), (b[0], b[1], b[2]))


@dataclass(frozen=True)
class Pick:
    entry: dict


@dataclass(frozen=True)
class TileRecord:
    header: dict
    detections: tuple
    recordDir: object = None
    recordName: str | None = None
    superseded: bool = False


class Survey:
    """Facts about one slice's tissue, and the policy that chooses from them.

    Everything but the hand-outs is plain data rebound as immutable values under
    one lock, so the GUI thread can preview while the worker thread surveys.
    """

    def __init__(self, fov, dirHandle=None):
        self._fov = (float(fov[0]), float(fov[1]))
        self._dirHandle = dirHandle
        self._lock = threading.Lock()
        self._tiles: tuple = ()
        self._manual: tuple = ()
        self._intent: tuple = ()
        self._excluded: frozenset = frozenset()
        # candidate_id -> (Cell, entry). The entry's position, not the Cell's,
        # is what spacing measures: the Cell's moves with its tracker, on the
        # worker thread.
        self._handOuts: dict = {}

    def load(self, dirHandle) -> None:
        """Fill this fresh survey from a slice directory: its tile records, its
        manual entries and exclusions, and its Cell dirs as hand-outs. Writes
        nothing."""
        for record in _readTileRecords(dirHandle):
            self.addTile(record)
        if dirHandle.exists(MANUAL_FILE):
            saved = dirHandle[MANUAL_FILE].read() or {}
            with self._lock:
                self._manual = tuple(saved.get("manual") or ())
                self._excluded = frozenset(saved.get("excluded") or ())
        for cellDir in _cellDirs(dirHandle):
            info = cellDir.info()
            with self._lock:
                entry = self._state().entries().get(info.get("candidate_id"))
            if entry is None:
                entry = _syntheticEntry(cellDir, info)
                if entry is None:
                    logger.warning("Skipping the Cell dir %r: it records no position", cellDir.name())
                    continue
                with self._lock:
                    self._manual = self._manual + (entry,)
            cell = self.handOut(entry)
            cell.cell_dir = cellDir
            cell.disposition = info.get("disposition")
        with self._lock:
            waiting = [
                e for e in self._manual
                if e["candidate_id"] not in self._handOuts and e["candidate_id"] not in self._excluded
            ]
            waiting.sort(key=lambda e: e.get("added_at") or 0.0)
            self._intent = tuple(e["candidate_id"] for e in waiting)

    # ---- facts ----
    def addTile(self, record: TileRecord) -> None:
        with self._lock:
            self._tiles = self._tiles + (record,)

    def tiles(self) -> tuple:
        return self._tiles

    def footprints(self) -> list:
        return [
            footprint(r.header["tile_center"], r.header.get("fov", self._fov))
            for r in self._tiles
            if not r.superseded
        ]

    def supersede(self, predicate) -> int:
        """Mark live records matching `predicate` superseded; returns how many."""
        with self._lock:
            changed, tiles = [], []
            for record in self._tiles:
                if not record.superseded and predicate(record):
                    record = replace(record, superseded=True)
                    changed.append(record)
                tiles.append(record)
            self._tiles = tuple(tiles)
        for record in changed:
            writeRecord(
                record.recordDir,
                record.recordName,
                {**record.header, "superseded": True, "detections": list(record.detections)},
            )
        return len(changed)

    def addManual(self, position) -> dict:
        entry = {
            "candidate_id": uuid.uuid4().hex,
            "position": [float(position[0]), float(position[1]), float(position[2])],
            "source": "manual",
            "added_at": time.time(),
        }
        with self._lock:
            self._manual = self._manual + (entry,)
            self._intent = self._intent + (entry["candidate_id"],)
        self._saveManual()
        return entry

    def manualEntries(self) -> tuple:
        return self._manual

    # ---- operator intent ----
    def requeue(self, cell) -> None:
        cid = cell.candidate_id
        with self._lock:
            if cid in self._handOuts and cid not in self._intent:
                self._intent = self._intent + (cid,)

    def exclude(self, candidate_id) -> None:
        with self._lock:
            self._excluded = self._excluded | {candidate_id}
            self._intent = tuple(i for i in self._intent if i != candidate_id)
        self._saveManual()

    def excluded(self) -> frozenset:
        return self._excluded

    def release(self, candidate_id) -> None:
        """Forget a hand-out so it can be picked again. A manual entry goes back
        on intent: the selector reaches hand seeds through intent alone."""
        with self._lock:
            held = self._handOuts.pop(candidate_id, None)
            manual = held is not None and held[1].get("source") == "manual"
            if manual and candidate_id not in self._excluded and candidate_id not in self._intent:
                self._intent = self._intent + (candidate_id,)

    # ---- hand-outs ----
    def handOut(self, entry: dict):
        cid = entry["candidate_id"]
        with self._lock:
            held = self._handOuts.get(cid)
        # Built outside the lock: the first build imports acq4_automation, which
        # takes about a second, and the GUI thread's previews wait on this lock.
        cell = _cellFor(entry) if held is None else held[0]
        with self._lock:
            held = self._handOuts.get(cid)
            if held is not None:
                cell = held[0]
            self._handOuts[cid] = (cell, entry)
            self._intent = tuple(i for i in self._intent if i != cid)
        return cell

    def handedOut(self) -> list:
        with self._lock:
            return [cell for cell, _ in self._handOuts.values()]

    def handedOutIds(self) -> frozenset:
        with self._lock:
            return frozenset(self._handOuts)

    def requeuedIds(self) -> frozenset:
        """The handed-out ids waiting for another pass: the only handed-out ids
        `preview` can return."""
        with self._lock:
            return frozenset(i for i in self._intent if i in self._handOuts)

    # ---- the selector ----
    def next(self, constraints, contains, maxPerTile=MAX_TILE_CANDIDATES):
        with self._lock:
            state = self._state()
        return _select(state, constraints, contains, maxPerTile)

    def preview(self, constraints, contains, n, maxPerTile=MAX_TILE_CANDIDATES) -> list:
        with self._lock:
            state = self._state()
        out = []
        for _ in range(n):
            choice = _select(state, constraints, contains, maxPerTile)
            if not isinstance(choice, Pick):
                break
            out.append(choice.entry)
            state = state.withHandOut(choice.entry)
        return out

    def _state(self) -> "_State":
        return _State(
            tiles=self._tiles,
            manual=self._manual,
            intent=self._intent,
            excluded=self._excluded,
            handOuts={cid: entry for cid, (_, entry) in self._handOuts.items()},
        )

    def _saveManual(self) -> None:
        if self._dirHandle is None:
            return
        try:
            self._dirHandle.writeFile(
                {"manual": list(self._manual), "excluded": sorted(self._excluded)},
                MANUAL_FILE,
                fileType="YamlFile",
            )
        except Exception:
            logger.exception("Could not write %s", MANUAL_FILE)


@dataclass(frozen=True)
class _State:
    tiles: tuple
    manual: tuple
    intent: tuple
    excluded: frozenset
    handOuts: dict

    def withHandOut(self, entry) -> "_State":
        cid = entry["candidate_id"]
        return replace(
            self,
            intent=tuple(i for i in self.intent if i != cid),
            handOuts={**self.handOuts, cid: entry},
        )

    def entries(self) -> dict:
        found = {e["candidate_id"]: {**e, "source": "manual"} for e in self.manual}
        for index, record in enumerate(self.tiles):
            for e in record.detections:
                found[e["candidate_id"]] = _surveyEntry(e, record.header, index)
        return found


def _surveyEntry(detection, header, index) -> dict:
    return {
        **detection,
        "source": "survey",
        "tile_index": index,
        "tile_id": header.get("tile_id"),
        "tile_center": header.get("tile_center"),
        "detection_prefix": header.get("detection_prefix"),
        "detection_models": header.get("detection_models") or {},
    }


def _select(state, constraints, contains, maxPerTile):
    entries = state.entries()
    for cid in state.intent:
        if cid not in state.excluded and cid in entries:
            return Pick(entries[cid])
    spacing = constraints.min_cell_spacing
    fixed = [e["position"] for e in state.handOuts.values()]
    fixed += [e["position"] for e in state.manual]
    pool = []
    for index, record in enumerate(state.tiles):
        if record.superseded:
            continue
        for detection in record.detections:
            cid = detection["candidate_id"]
            if cid in state.handOuts or cid in state.excluded:
                continue
            score = detection.get("score")
            if score is not None and score < constraints.min_health:
                continue
            if not contains(detection["position"]):
                continue
            pool.append(_surveyEntry(detection, record.header, index))
    # Stable, so equal scores keep imaging order and, within a tile, the
    # detector's own best-first order.
    pool.sort(key=lambda e: (e.get("score") is None, -(e.get("score") or 0.0)))
    kept = []
    for entry in pool:
        position = entry["position"]
        if any(cellDistance(position, p) < spacing for p in fixed):
            continue
        if any(cellDistance(position, k["position"]) < spacing for k in kept):
            continue
        kept.append(entry)
    counts = {}
    for e in state.handOuts.values():
        if e.get("tile_index") is not None:
            counts[e["tile_index"]] = counts.get(e["tile_index"], 0) + 1
    for index in range(len(state.tiles)):
        if counts.get(index, 0) >= maxPerTile:
            continue
        for entry in kept:
            if entry["tile_index"] == index:
                return Pick(entry)
    return NEED_TILE


def _readTileRecords(dirHandle) -> list:
    if not dirHandle.exists("tiles"):
        return []
    tilesDir = dirHandle["tiles"]
    records = []
    for name in sorted(n for n in tilesDir.ls() if n.endswith(DETECTIONS_SUFFIX)):
        try:
            header = tilesDir[name].read()
        except Exception:
            logger.exception("Skipping the unreadable tile record %r", name)
            continue
        if not isinstance(header, dict):
            logger.warning("Skipping the tile record %r: it is not a mapping", name)
            continue
        detections = tuple(header.pop("detections", None) or ())
        superseded = bool(header.pop("superseded", False))
        records.append(TileRecord(header, detections, recordDir=tilesDir, recordName=name, superseded=superseded))
    return records


def _cellDirs(dirHandle) -> list:
    children = (dirHandle[name] for name in sorted(dirHandle.subDirs()))
    return [child for child in children if child.info().get("dirType") == "Cell"]


def _syntheticEntry(cellDir, info) -> dict | None:
    """A manual entry for a Cell dir no record or manual entry names: one from
    before candidate ids, or whose id was lost."""
    position = _cellDirPosition(cellDir, info)
    if position is None:
        return None
    return {
        "candidate_id": info.get("candidate_id") or uuid.uuid4().hex,
        "position": position,
        "source": info.get("source") or "manual",
    }


def _cellDirPosition(cellDir, info):
    if cellDir.exists(CELL_METADATA_FILE):
        position = (cellDir[CELL_METADATA_FILE].read() or {}).get("initial_position")
        if position is not None:
            return [float(v) for v in position]
    match = re.fullmatch(r"\(([^,]+),([^,]+),([^,]+)\)\s*um", str(info.get("location", "")).strip())
    if match is None:
        return None
    return [float(v) * 1e-6 for v in match.groups()]


def _newCell(position):
    """A Cell at `position`. Imported here, not at module scope: acq4_automation is
    an internal repository, and a top-level import would stop every test under
    acq4/experiment from collecting where it is absent."""
    from acq4_automation.feature_tracking.cell import Cell
    from coorx import Point

    return Cell(Point(position, "global"))


def _cellFor(entry):
    cell = _newCell(entry["position"])
    cell.candidate_id = entry["candidate_id"]
    cell.source = entry.get("source", "survey")
    cell.score = entry.get("score")
    cell.volume = entry.get("volume")
    cell.area = entry.get("area")
    cell.tile_id = entry.get("tile_id")
    center = entry.get("tile_center")
    cell.tile_center = None if center is None else tuple(center)
    cell.detection_prefix = entry.get("detection_prefix")
    cell.detection_models = dict(entry.get("detection_models") or {})
    return cell
