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

DETECTIONS_SUFFIX = "_detections.yaml"
# Only these were judged on spacing; the health and region filters run first
# and do not depend on it.
SPACING_JUDGED = ("queued", "too_close", "over_cap")
COLOURS = {"queued": "tab:green", "too_close": "tab:red", "over_cap": "tab:orange",
           "unhealthy": "tab:gray", "out_of_region": "tab:purple"}


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
    parser.add_argument("--spacing", type=float, default=30e-6)
    parser.add_argument("--try", dest="tries", type=float, nargs="*", default=[10e-6, 20e-6, 40e-6, 50e-6])
    parser.add_argument("--out", default="spacing.png")
    args = parser.parse_args(argv)
    if not os.path.isdir(args.slice_dir):
        print(f"{args.slice_dir} is not a directory", file=sys.stderr)
        return 2

    detections = loadDetections(args.slice_dir)
    queued = [d for d in detections if d["disposition"] == "queued"]
    points = [d["position"] for d in queued]
    print(f"{len(detections)} detections, {len(queued)} queued")
    counts, edges = np.histogram(nearestNeighbourDistances(points) * 1e6, bins=np.arange(0, 105, 5))
    print("nearest-neighbour distance among queued cells (µm):")
    for lo, n in zip(edges[:-1], counts):
        print(f"  {lo:5.0f}-{lo + 5:<5.0f} {'#' * n} {n}")
    pairs = closePairs(points, args.spacing)
    print(f"{len(pairs)} queued pairs closer than {args.spacing * 1e6:.0f} µm (expect 0)")
    for i, j, d in pairs:
        print(f"  {queued[i]['candidate_id']} / {queued[j]['candidate_id']}: {d * 1e6:.1f} µm")
    for spacing in args.tries:
        print(f"at {spacing * 1e6:.0f} µm the survey would have queued {len(resimulate(detections, spacing))}")
    plot(detections, args.spacing, args.out)
    print(f"plot written to {args.out}")
    return 1 if pairs else 0


if __name__ == "__main__":
    sys.exit(main())
