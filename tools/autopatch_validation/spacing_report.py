"""Report how far apart a slice's queued cells are, from its tiles' detection
records, and what other spacings would have queued."""

import argparse
import glob
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402

from acq4.experiment.search_region import region_from_dict  # noqa: E402
from acq4.experiment.slice import SearchConstraints  # noqa: E402
from acq4.experiment.survey import MANUAL_FILE, Survey, TileRecord  # noqa: E402

DETECTIONS_SUFFIX = "_detections.yaml"
# Only these were judged on spacing; the health and region filters run first
# and do not depend on it.
SPACING_JUDGED = ("queued", "too_close", "over_cap")
COLOURS = {"queued": "tab:green", "too_close": "tab:red", "over_cap": "tab:orange",
           "unhealthy": "tab:gray", "out_of_region": "tab:purple"}


DEFAULT_SPACING = 30e-6


def recordedConstraint(sliceDir: str, key: str):
    """The constraint `key` the newest tile record was surveyed with, or None."""
    for path in sorted(glob.glob(os.path.join(sliceDir, "tiles", f"*{DETECTIONS_SUFFIX}")), reverse=True):
        with open(path) as fh:
            record = yaml.safe_load(fh)
        if isinstance(record, dict):
            value = (record.get("constraints") or {}).get(key)
            if value is not None:
                return float(value)
    return None


def recordedSpacing(sliceDir: str):
    return recordedConstraint(sliceDir, "min_cell_spacing")


def loadDetections(sliceDir: str) -> list:
    records = []
    for path in sorted(glob.glob(os.path.join(sliceDir, "tiles", f"*{DETECTIONS_SUFFIX}"))):
        with open(path) as fh:
            record = yaml.safe_load(fh)
        if isinstance(record, dict):
            records.append(record)
    records.sort(key=lambda r: r.get("detected_at") or 0.0)
    return [
        dict(d, tile_id=r.get("tile_id"), detected_at=r.get("detected_at"))
        for r in records
        for d in r.get("detections") or []
    ]


def loadSurvey(sliceDir: str):
    """The slice's survey and regions, rebuilt from its files on disk."""
    survey = Survey(fov=(0.0, 0.0))
    tilesDir = os.path.join(sliceDir, "tiles")
    names = []
    if os.path.isdir(tilesDir):
        names = sorted(n for n in os.listdir(tilesDir) if n.endswith(DETECTIONS_SUFFIX))
    for name in names:
        with open(os.path.join(tilesDir, name)) as fh:
            record = yaml.safe_load(fh)
        if not isinstance(record, dict):
            continue
        detections = tuple(record.pop("detections", None) or [])
        superseded = bool(record.pop("superseded", False))
        survey.addTile(TileRecord(header=record, detections=detections, superseded=superseded))
    manualPath = os.path.join(sliceDir, MANUAL_FILE)
    if os.path.exists(manualPath):
        with open(manualPath) as fh:
            manual = yaml.safe_load(fh) or {}
        # No public loader exists until the survey reloads its own manual record.
        for entry in manual.get("manual") or []:
            survey._manual += (entry,)
            survey._intent += (entry["candidate_id"],)
        for cid in manual.get("excluded") or []:
            survey._excluded |= {cid}
    regions = []
    regionsPath = os.path.join(sliceDir, "regions.yaml")
    if os.path.exists(regionsPath):
        with open(regionsPath) as fh:
            regions = [region_from_dict(d) for d in yaml.safe_load(fh) or []]
    return survey, regions


def livePicks(survey, regions, constraints, n=200) -> list:
    """The order the live selector would hand cells out in."""
    contains = lambda p: not regions or any(r.contains(p) for r in regions)
    return survey.preview(constraints, contains, n)


def nearestNeighbourDistances(points) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    if len(points) < 2:
        return np.array([])
    distances, _ = cKDTree(points).query(points, k=2)
    return distances[:, 1]


def closePairs(points, radius) -> list:
    points = np.asarray(points, dtype=float)
    if len(points) < 2:
        return []
    pairs = []
    for i, j in sorted(cKDTree(points).query_pairs(radius)):
        d = float(np.linalg.norm(points[i] - points[j]))
        if d < radius:
            pairs.append((i, j, d))
    return pairs


def resimulate(detections, spacing, cap=5) -> list:
    """What the producer's spacing and cap would have queued at `spacing`, in
    survey order. Hand-seeded cells and rescans are not in the records, so they
    are not modelled."""
    queued = []
    perTile = {}
    for d in detections:
        if d["disposition"] not in SPACING_JUDGED:
            continue
        p = np.asarray(d["position"], dtype=float)
        if any(np.linalg.norm(p - np.asarray(q["position"])) < spacing for q in queued):
            continue
        if perTile.get(d["tile_id"], 0) >= cap:
            continue
        perTile[d["tile_id"]] = perTile.get(d["tile_id"], 0) + 1
        queued.append(d)
    return queued


def plot(detections, spacing, path) -> None:
    fig, ax = plt.subplots(figsize=(8, 8))
    for disposition, colour in COLOURS.items():
        pts = np.array([d["position"][:2] for d in detections if d["disposition"] == disposition]).reshape(-1, 2) * 1e6
        if not len(pts):
            continue
        ax.scatter(pts[:, 0], pts[:, 1], s=12, c=colour, label=disposition)
        if disposition == "queued":
            for x, y in pts:
                ax.add_patch(plt.Circle((x, y), spacing * 1e6, fill=False, lw=0.5, color=colour))
    ax.set_aspect("equal")
    ax.set_xlabel("x (µm)")
    ax.set_ylabel("y (µm)")
    if ax.get_legend_handles_labels()[0]:
        ax.legend(loc="upper right")
    ax.set_title(f"Detections by disposition; circles are the {spacing * 1e6:.0f} µm spacing")
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slice_dir")
    parser.add_argument("--spacing", type=float, default=None)
    parser.add_argument("--try", dest="tries", type=float, nargs="*", default=[10e-6, 20e-6, 40e-6, 50e-6])
    parser.add_argument("--out", default="spacing.png")
    parser.add_argument("--min-health", type=float, default=None)
    parser.add_argument("--live", action="store_true", help="print the live selector's picks instead")
    args = parser.parse_args(argv)
    if not os.path.isdir(args.slice_dir):
        print(f"{args.slice_dir} is not a directory", file=sys.stderr)
        return 2

    if args.spacing is not None:
        spacing, source = args.spacing, "from --spacing"
    elif (recorded := recordedSpacing(args.slice_dir)) is not None:
        spacing, source = recorded, "from the records"
    else:
        spacing, source = DEFAULT_SPACING, "default"
    print(f"spacing {spacing * 1e6:.0f} µm ({source})")

    if args.live:
        if args.min_health is not None:
            minHealth, healthSource = args.min_health, "from --min-health"
        elif (recorded := recordedConstraint(args.slice_dir, "min_health")) is not None:
            minHealth, healthSource = recorded, "from the records"
        else:
            minHealth, healthSource = SearchConstraints().min_health, "default"
        print(f"min_health {minHealth:g} ({healthSource})")
        survey, regions = loadSurvey(args.slice_dir)
        picks = livePicks(survey, regions, SearchConstraints(min_health=minHealth, min_cell_spacing=spacing))
        for i, pick in enumerate(picks):
            score = pick.get("score")
            x, y, z = (c * 1e6 for c in pick["position"][:3])
            print(f"{i} {pick['candidate_id']} {pick['source']} "
                  f"{'-' if score is None else f'{score:.2f}'} ({x:.1f}, {y:.1f}, {z:.1f}) µm")
        return 0

    detections = loadDetections(args.slice_dir)
    queued = [d for d in detections if d["disposition"] == "queued"]
    points = [d["position"] for d in queued]
    print(f"{len(detections)} detections, {len(queued)} queued")
    nearest = nearestNeighbourDistances(points) * 1e6
    counts, edges = np.histogram(nearest, bins=np.arange(0, 105, 5))
    print("nearest-neighbour distance among queued cells (µm):")
    for lo, n in zip(edges[:-1], counts):
        print(f"  {lo:5.0f}-{lo + 5:<5.0f} {'#' * n} {n}")
    beyond = int((nearest > edges[-1]).sum())
    print(f"  {edges[-1]:5.0f}+      {'#' * beyond} {beyond}")
    pairs = closePairs(points, spacing)
    print(f"{len(pairs)} queued pairs closer than {spacing * 1e6:.0f} µm (expect 0)")
    for i, j, d in pairs:
        print(f"  {queued[i]['candidate_id']} / {queued[j]['candidate_id']}: {d * 1e6:.1f} µm")
    for trial in args.tries:
        print(f"at {trial * 1e6:.0f} µm the survey would have queued {len(resimulate(detections, trial))}")
    plot(detections, spacing, args.out)
    print(f"plot written to {args.out}")
    return 1 if pairs else 0


if __name__ == "__main__":
    sys.exit(main())
