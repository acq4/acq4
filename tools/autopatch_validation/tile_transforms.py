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


@dataclass
class Tile:
    name: str
    data: np.ndarray
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
        ma = MetaArray(file=path)
        fileState = ma.infoCopy()[-1].get("transform")
        tiles.append(Tile(name, np.asarray(ma.asarray()), load_transform(state),
                          None if fileState is None else load_transform(fileState)))
    return tiles


def _corners(tile):
    nz, ny, nx = tile.data.shape
    return np.array(list(itertools.product((0, nx - 1), (0, ny - 1), (0, nz - 1))), dtype=float)


def transformDisagreement(tile):
    if tile.fileTransform is None:
        return None
    corners = _corners(tile)
    return float(np.max(np.linalg.norm(tile.transform.map(corners) - tile.fileTransform.map(corners), axis=1)))


def mosaicLayers(tiles, pixel):
    footprints = np.array([tile.transform.map(_corners(tile))[:, :2] for tile in tiles])
    x0, y0 = footprints[..., 0].min(), footprints[..., 1].min()
    x1, y1 = footprints[..., 0].max(), footprints[..., 1].max()
    xs = np.arange(x0, x1 + pixel / 2, pixel)
    ys = np.arange(y0, y1 + pixel / 2, pixel)
    gx, gy = np.meshgrid(xs, ys)
    layers = []
    for tile in tiles:
        mip = tile.data.max(axis=0)  # (y, x)
        z = (tile.data.shape[0] - 1) / 2
        midDepth = tile.transform.map([[0, 0, z]])[0][2]
        world = np.stack([gx.ravel(), gy.ravel(), np.full(gx.size, midDepth)], axis=1)
        voxel = tile.transform.inverse.map(world)
        sampled = map_coordinates(mip, [voxel[:, 1], voxel[:, 0]], order=1, cval=np.nan)
        layers.append(sampled.reshape(gx.shape))
    return layers, (x0, x1, y0, y1)


def _windowed(image, valid):
    """Zero-mean and Hann-taper the overlap so its edges don't pull the correlation peak to zero shift."""
    image = np.where(valid, image, 0.0)
    image = np.where(valid, image - image[valid].mean(), 0.0)
    return image * np.outer(np.hanning(image.shape[0] + 2)[1:-1], np.hanning(image.shape[1] + 2)[1:-1])


def overlapShifts(layers, minPixels=32):
    shifts = []
    for i, j in itertools.combinations(range(len(layers)), 2):
        both = np.isfinite(layers[i]) & np.isfinite(layers[j])
        rows, cols = np.nonzero(both)
        if len(rows) == 0 or np.ptp(rows) + 1 < minPixels or np.ptp(cols) + 1 < minPixels:
            continue
        crop = (slice(rows.min(), rows.max() + 1), slice(cols.min(), cols.max() + 1))
        a, b = layers[i][crop], layers[j][crop]
        a, b = _windowed(a, both[crop]), _windowed(b, both[crop])
        shift, _error, _phase = phase_cross_correlation(a, b, upsample_factor=10)
        shifts.append((i, j, (float(shift[0]), float(shift[1]))))
    return shifts


def plotMosaic(layers, extent, tiles, detections, path):
    stack = np.stack(layers)
    covered = np.isfinite(stack).sum(axis=0)
    mosaic = np.where(covered > 0, np.nansum(stack, axis=0) / np.maximum(covered, 1), np.nan)
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
    print(f"{len(tiles)} tiles with a recorded transform")
    for tile in tiles:
        d = transformDisagreement(tile)
        print(f"  {tile.name}: index vs file transform "
              + ("(no file transform)" if d is None else f"{d * 1e6:.3f} µm apart"))
    layers, extent = mosaicLayers(tiles, args.pixel)
    worst = 0.0
    for i, j, (dy, dx) in overlapShifts(layers):
        worst = max(worst, abs(dy), abs(dx))
        print(f"  {tiles[i].name} / {tiles[j].name}: overlap shift {dy:+.1f}, {dx:+.1f} px")
    plotMosaic(layers, extent, tiles, loadDetections(args.slice_dir), args.out)
    print(f"mosaic written to {args.out}; worst overlap shift {worst:.1f} px (expect < 2)")
    return 1 if worst >= 2 else 0


if __name__ == "__main__":
    sys.exit(main())
