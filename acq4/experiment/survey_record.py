"""The per-tile survey record: every detection a tile produced and what the
producer decided about each, written beside the tile's stack."""

from __future__ import annotations

from acq4.logging_config import get_logger

logger = get_logger(__name__)

DETECTIONS_SUFFIX = "_detections.yaml"


class TileDetections(list):
    """The cells one tile produced, plus what is needed to record them.

    A list, so it satisfies everything that already takes a detector's output.
    `header` is the tile-level half of the record; `recordDir` and `recordName`
    say where it goes, and are None when the slice has nowhere to write.
    """

    def __init__(self, cells, header, recordDir=None, recordName=None):
        super().__init__(cells)
        self.header = header
        self.recordDir = recordDir
        self.recordName = recordName


def detectionEntry(candidate, disposition) -> dict:
    """One detection as plain data, with the producer's verdict on it."""
    position = candidate.position
    entry = {
        "candidate_id": getattr(candidate, "candidate_id", None),
        "position": [float(position[0]), float(position[1]), float(position[2])],
        "score": _plainFloat(getattr(candidate, "score", None)),
        "volume": _plainFloat(getattr(candidate, "volume", None)),
        "disposition": disposition,
    }
    area = getattr(candidate, "area", None)
    if area is not None:
        entry["area"] = float(area)
    return entry


def writeTileRecord(detections, triaged) -> None:
    """Write `detections`' record, one entry per `(candidate, disposition)`.

    Logged and swallowed on failure: the tile's cells are already found and
    about to be queued, and losing their record must not stop the survey.
    """
    if detections.recordDir is None:
        return
    try:
        record = dict(detections.header)
        record["detections"] = [detectionEntry(c, d) for c, d in triaged]
        detections.recordDir.writeFile(record, detections.recordName, fileType="YamlFile")
    except Exception:
        logger.exception("Could not write the detection record %r", detections.recordName)


def _plainFloat(value):
    return None if value is None else float(value)
