"""Place a slice's saved tile stacks in global coordinates using the transforms
recorded with them, and measure how well overlapping tiles line up."""

import argparse
import glob
import itertools
import os
import sys
from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from MetaArray import MetaArray  # noqa: E402
from pyqtgraph.configfile import readConfigFile  # noqa: E402
from scipy.ndimage import map_coordinates  # noqa: E402
from skimage.registration import phase_cross_correlation  # noqa: E402

from acq4.util.geometry import load_transform  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from spacing_report import loadDetections  # noqa: E402

MAX_GRID = 4096
MAX_DISAGREEMENT = 1e-9
MAX_SHIFT_PIXELS = 2.0


@dataclass
class Tile:
    name: str
    mip: np.ndarray
    shape: tuple
    transform: object
    fileTransform: object


def loadTiles(sliceDir: str) -> list:
    tilesDir = os.path.join(sliceDir, "tiles")
    index = readConfigFile(os.path.join(tilesDir, ".index"), np=np)
    tiles = []
    for path in sorted(glob.glob(os.path.join(tilesDir, "*.ma"))):
        name = os.path.basename(path)
        state = index.get(name, {}).get("transform")
        if state is None:
            continue
        ma = MetaArray(file=path, mmap=True)
        fileState = ma.infoCopy()[-1].get("transform")
        tiles.append(Tile(name, np.asarray(ma.asarray().max(axis=0)), tuple(ma.shape), load_transform(state),
                          None if fileState is None else load_transform(fileState)))
    return tiles


def _corners(tile):
    nz, ny, nx = tile.shape
    return np.array(list(itertools.product((0, nx - 1), (0, ny - 1), (0, nz - 1))), dtype=float)


def transformDisagreement(tile):
    if tile.fileTransform is None:
        return None
    corners = _corners(tile)
    return float(np.max(np.linalg.norm(tile.transform.map(corners) - tile.fileTransform.map(corners), axis=1)))


def _footprint(tile):
    return tile.transform.map(_corners(tile))[:, :2]


def gridShape(tiles, pixel):
    footprints = np.concatenate([_footprint(tile) for tile in tiles])
    span = footprints.max(axis=0) - footprints.min(axis=0)
    return int(span[1] // pixel) + 1, int(span[0] // pixel) + 1


def mosaicLayers(tiles, pixel):
    """One float32 max-projection layer per tile, as (layer, (row, col) offset on the shared grid)."""
    footprints = [_footprint(tile) for tile in tiles]
    allPoints = np.concatenate(footprints)
    x0, y0 = allPoints.min(axis=0)
    x1, y1 = allPoints.max(axis=0)
    layers = []
    for tile, points in zip(tiles, footprints):
        col0, row0 = np.floor((points.min(axis=0) - (x0, y0)) / pixel + 1e-6).astype(int)
        col1, row1 = np.ceil((points.max(axis=0) - (x0, y0)) / pixel - 1e-6).astype(int)
        gx, gy = np.meshgrid(x0 + np.arange(col0, col1 + 1) * pixel, y0 + np.arange(row0, row1 + 1) * pixel)
        z = (tile.shape[0] - 1) / 2
        midDepth = tile.transform.map([[0, 0, z]])[0][2]
        world = np.stack([gx.ravel(), gy.ravel(), np.full(gx.size, midDepth)], axis=1)
        voxel = tile.transform.inverse.map(world)
        sampled = map_coordinates(tile.mip.astype(np.float32), [voxel[:, 1], voxel[:, 0]], order=1,
                                  cval=np.nan, output=np.float32)
        layers.append((sampled.reshape(gx.shape), (int(row0), int(col0))))
    return layers, (x0, x1, y0, y1)


def _overlap(first, second):
    """The grid rectangle both layers span, as (row slice, col slice) into each layer, or None."""
    (a, (aRow, aCol)), (b, (bRow, bCol)) = first, second
    row0, row1 = max(aRow, bRow), min(aRow + a.shape[0], bRow + b.shape[0])
    col0, col1 = max(aCol, bCol), min(aCol + a.shape[1], bCol + b.shape[1])
    if row1 <= row0 or col1 <= col0:
        return None
    return (slice(row0 - aRow, row1 - aRow), slice(col0 - aCol, col1 - aCol)), \
           (slice(row0 - bRow, row1 - bRow), slice(col0 - bCol, col1 - bCol))


def overlapShifts(layers, minPixels=32):
    """(i, j, (dy, dx)): the grid-pixel shift that moves tile j onto tile i."""
    shifts = []
    for i, j in itertools.combinations(range(len(layers)), 2):
        window = _overlap(layers[i], layers[j])
        if window is None:
            continue
        a, b = layers[i][0][window[0]], layers[j][0][window[1]]
        both = np.isfinite(a) & np.isfinite(b)
        rows, cols = np.nonzero(both)
        if len(rows) == 0 or np.ptp(rows) + 1 < minPixels or np.ptp(cols) + 1 < minPixels:
            continue
        crop = (slice(rows.min(), rows.max() + 1), slice(cols.min(), cols.max() + 1))
        mask = both[crop]
        shift, _error, _phase = phase_cross_correlation(a[crop], b[crop], reference_mask=mask, moving_mask=mask,
                                                        normalization=None)
        shifts.append((i, j, (float(shift[0]), float(shift[1]))))
    return shifts


def plotMosaic(layers, extent, tiles, detections, path):
    rows = max(row + layer.shape[0] for layer, (row, _col) in layers)
    cols = max(col + layer.shape[1] for layer, (_row, col) in layers)
    total = np.zeros((rows, cols), dtype=np.float32)
    covered = np.zeros((rows, cols), dtype=np.int32)
    for layer, (row, col) in layers:
        window = (slice(row, row + layer.shape[0]), slice(col, col + layer.shape[1]))
        valid = np.isfinite(layer)
        total[window] += np.where(valid, layer, 0)
        covered[window] += valid
    mosaic = np.where(covered > 0, total / np.maximum(covered, 1), np.nan)
    x0, x1, y0, y1 = (v * 1e6 for v in extent)
    fig, ax = plt.subplots(figsize=(10, 10))
    ax.imshow(mosaic, origin="lower", extent=(x0, x1, y0, y1), cmap="gray")
    for tile in tiles:
        c = tile.transform.map(_corners(tile))[:, :2] * 1e6
        ax.add_patch(plt.Rectangle((c[:, 0].min(), c[:, 1].min()), np.ptp(c[:, 0]), np.ptp(c[:, 1]),
                                   fill=False, color="yellow", lw=0.8))
    if detections:
        pts = np.array([d["position"][:2] for d in detections]) * 1e6
        ax.scatter(pts[:, 0], pts[:, 1], s=10, c="red")
    ax.set_xlabel("x (µm)")
    ax.set_ylabel("y (µm)")
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slice_dir")
    parser.add_argument("--pixel", type=float, default=1e-6)
    parser.add_argument("--out", default="mosaic.png")
    args = parser.parse_args(argv)
    if not os.path.isdir(args.slice_dir):
        print(f"{args.slice_dir} is not a directory", file=sys.stderr)
        return 2
    if not os.path.isfile(os.path.join(args.slice_dir, "tiles", ".index")):
        print(f"{args.slice_dir} has no tiles index", file=sys.stderr)
        return 2

    tiles = loadTiles(args.slice_dir)
    if not tiles:
        print(f"{args.slice_dir} has no tiles with a recorded transform", file=sys.stderr)
        return 2
    rows, cols = gridShape(tiles, args.pixel)
    if max(rows, cols) > MAX_GRID:
        print(f"a {rows}x{cols} grid is too large to mosaic; raise --pixel", file=sys.stderr)
        return 2
    print(f"{len(tiles)} tiles with a recorded transform")
    failed = False
    for tile in tiles:
        d = transformDisagreement(tile)
        if d is None:
            print(f"  {tile.name}: index vs file transform (no file transform)")
            continue
        failed |= d > MAX_DISAGREEMENT
        print(f"  {tile.name}: index vs file transform {d * 1e6:.3f} µm apart")
    layers, extent = mosaicLayers(tiles, args.pixel)
    shifts = overlapShifts(layers)
    worst = 0.0
    for i, j, (dy, dx) in shifts:
        worst = max(worst, abs(dy), abs(dx))
        print(f"  {tiles[i].name} / {tiles[j].name}: overlap shift {dy:+.1f}, {dx:+.1f} px")
    plotMosaic(layers, extent, tiles, loadDetections(args.slice_dir), args.out)
    if not shifts:
        print(f"no overlaps measured; mosaic written to {args.out}")
        return 1
    limit = MAX_SHIFT_PIXELS * args.pixel * 1e6
    print(f"mosaic written to {args.out}; worst overlap shift {worst:.1f} px ({worst * args.pixel * 1e6:.1f} µm)"
          f" (expect < {MAX_SHIFT_PIXELS:.1f} px ({limit:.1f} µm))")
    return 1 if failed or worst >= MAX_SHIFT_PIXELS else 0


if __name__ == "__main__":
    sys.exit(main())
