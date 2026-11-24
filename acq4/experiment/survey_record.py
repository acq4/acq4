"""The per-tile survey record: every detection a tile produced and what the
producer decided about each, written beside the tile's stack."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from acq4.logging_config import get_logger

logger = get_logger(__name__)

DETECTIONS_SUFFIX = "_detections.yaml"


@dataclass(frozen=True)
class Detection:
    """One cell the detector found: where, how healthy, how big, and its id."""

    position: tuple
    score: float | None = None
    volume: float | None = None
    area: float | None = None
    candidate_id: str = field(default_factory=lambda: uuid.uuid4().hex)


class TileDetections(list):
    """The detections one tile produced, plus what is needed to record them.

    A list, so it satisfies everything that already takes a detector's output.
    `header` is the tile-level half of the record; `recordDir` and `recordName`
    say where it goes, and are None when the slice has nowhere to write.
    """

    def __init__(self, detections, header, recordDir=None, recordName=None):
        super().__init__(detections)
        self.header = header
        self.recordDir = recordDir
        self.recordName = recordName


def detectionEntry(candidate, disposition) -> dict:
    """One detection as plain data, with the producer's verdict on it."""
    position = candidate.position
    entry = {
        "candidate_id": getattr(candidate, "candidate_id", None) or uuid.uuid4().hex,
        "position": [float(position[0]), float(position[1]), float(position[2])],
        "score": _plainFloat(getattr(candidate, "score", None)),
        "volume": _plainFloat(getattr(candidate, "volume", None)),
        "disposition": disposition,
    }
    area = getattr(candidate, "area", None)
    if area is not None:
        entry["area"] = float(area)
    return entry


def writeRecord(recordDir, recordName, record: dict) -> None:
    """Write one tile record. Logged and swallowed on failure: a record is never
    worth stopping the survey for."""
    if recordDir is None:
        return
    try:
        recordDir.writeFile(record, recordName, fileType="YamlFile")
    except Exception:
        logger.exception("Could not write the detection record %r", recordName)


def tileSaveTarget(slice_dir):
    """Where this tile's detection stack and mask are to be written: a
    `(directory, base name)` pair, or `(None, None)` when there is nowhere.

    The directory is a `tiles/` subdirectory of the slice's own, so a tile's
    imagery sits beside the Cell directories that tile produced. That placement
    is the whole difference from AutomationDebug's arrangement, which writes the
    same trio into a `cell_annotations/` tree outside the managed hierarchy
    entirely: unindexed, invisible in the Data Manager, and related to the
    experiment it came from only by the clock.

    The base name is timestamped to the microsecond, and is per tile rather than
    per survey because the detector writes two files under it into a directory
    every tile of the run shares. Two tiles under one name is the second tile
    writing over the first tile's stack.

    Nowhere to write is not a failure. A slice with `dirHandle` at None is a run
    the operator started without ever pressing "New slice"; a directory that
    cannot be created is a storage problem the operator will hear about from
    everything else the run does. Neither is a reason to stop imaging tissue.
    """
    if slice_dir is None:
        return None, None
    try:
        tile_dir = slice_dir.getDir("tiles", create=True)
    except Exception:
        logger.warning(
            "Could not open a tiles directory under %r; this tile's detection "
            "stack and cellpose masks will not be saved.",
            slice_dir,
            exc_info=True,
        )
        return None, None
    return tile_dir, datetime.now().strftime("tile_%Y%m%d_%H%M%S_%f")


def _plainFloat(value):
    return None if value is None else float(value)
