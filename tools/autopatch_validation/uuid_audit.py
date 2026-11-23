"""Audit a Data Manager tree for identity gaps: entries with no uuid, uuids used
twice, and Cell directories whose survey ids resolve to no detection record."""

import argparse
import os
import sys

import numpy as np
import yaml
from pyqtgraph.configfile import readConfigFile

DETECTIONS_SUFFIX = "_detections.yaml"


def _entries(root):
    """(path, info) for every indexed file and directory under `root`. A
    subdirectory is described by its own index's "." entry, not its parent's."""
    for dirpath, _dirs, files in os.walk(root):
        if ".index" not in files:
            continue
        index = readConfigFile(os.path.join(dirpath, ".index"), np=np)
        for name, info in index.items():
            if not isinstance(info, dict):
                continue
            path = dirpath if name == "." else os.path.join(dirpath, name)
            if name != "." and os.path.exists(os.path.join(path, ".index")):
                continue
            yield path, info


def _surveyIds(root):
    candidates, tiles = set(), set()
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if not name.endswith(DETECTIONS_SUFFIX):
                continue
            with open(os.path.join(dirpath, name)) as fh:
                record = yaml.safe_load(fh)
            if not isinstance(record, dict):
                continue
            if record.get("tile_id"):
                tiles.add(record["tile_id"])
            candidates.update(d.get("candidate_id") for d in record.get("detections") or [])
    candidates.discard(None)
    return candidates, tiles


def auditTree(root: str) -> dict:
    missing, owners, cells, entries = [], {}, [], 0
    for path, info in _entries(root):
        entries += 1
        uid = info.get("__uuid__")
        if uid is None:
            missing.append(path)
        else:
            owners.setdefault(uid, []).append(path)
        if info.get("dirType") == "Cell":
            cells.append((path, info))
    candidates, tiles = _surveyIds(root)
    unresolved = [
        path
        for path, info in cells
        if (info.get("candidate_id") and info["candidate_id"] not in candidates)
        or (info.get("tile_id") and info["tile_id"] not in tiles)
    ]
    return {
        "entries": entries,
        "missing": missing,
        "duplicates": {uid: paths for uid, paths in owners.items() if len(paths) > 1},
        "unresolved": unresolved,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args(argv)
    if not os.path.isdir(args.root):
        print(f"{args.root} is not a directory", file=sys.stderr)
        return 2
    report = auditTree(args.root)
    print(f"{report['entries']} indexed entries")
    print(f"{len(report['missing'])} without a uuid")
    for path in report["missing"]:
        print(f"  missing  {path}")
    print(f"{len(report['duplicates'])} uuids used more than once")
    for uid, paths in report["duplicates"].items():
        print(f"  dup {uid}: {', '.join(paths)}")
    print(f"{len(report['unresolved'])} Cell dirs whose ids match no detection record")
    for path in report["unresolved"]:
        print(f"  unresolved  {path}")
    return 1 if report["missing"] or report["duplicates"] or report["unresolved"] else 0


if __name__ == "__main__":
    sys.exit(main())
