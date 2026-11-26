"""Pure-numpy survey planning: the pipette-insertion exposure model and the chooser
that picks the next survey field from the region area still to image and that exposure."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.special import erf

MIN_EVENT_WEIGHT = 1e-3
DEFAULT_PITCH = 5e-6
MAX_MASK_PIXELS = 4_000_000
LATTICE_DIVISOR = 4
THIN_BAND_SLACK = 0.9


def _live_events(insertions, now: float, tau: float):
    """The (x, y, decayed weight) columns of insertions that still matter at `now`."""
    ev = np.asarray(insertions, dtype=float).reshape(-1, 3)
    weight = np.exp(-np.maximum(now - ev[:, 2], 0.0) / tau)
    keep = weight >= MIN_EVENT_WEIGHT
    return ev[keep, 0], ev[keep, 1], weight[keep]


def exposure_at(points, insertions, now: float, sigma: float, tau: float) -> np.ndarray:
    """E(p, now) at each (x, y) in `points` (N, 2), for `insertions` of (x, y, t) rows.

    E = sum_i exp(-(now - t_i)/tau) * exp(-|p - p_i|^2 / 2 sigma^2). Events whose
    decayed weight is under 1e-3 are ignored.
    """
    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    ex, ey, w = _live_events(insertions, now, tau)
    dx = pts[:, None, 0] - ex[None, :]
    dy = pts[:, None, 1] - ey[None, :]
    return (w * np.exp(-(dx * dx + dy * dy) / (2 * sigma**2))).sum(axis=1)


def _gaussian_axis_mean(centre, half, mu, sigma):
    """Mean over [centre - half, centre + half] of exp(-(x - mu)^2 / 2 sigma^2)."""
    s2 = sigma * np.sqrt(2.0)
    lo = (centre - half - mu) / s2
    hi = (centre + half - mu) / s2
    return sigma * np.sqrt(np.pi / 2.0) * (erf(hi) - erf(lo)) / (2 * half)


def field_exposure(centres, fov, insertions, now: float, sigma: float, tau: float) -> np.ndarray:
    """Mean of E over the `fov` rectangle centred on each of `centres` (N, 2).

    Exact: each event contributes a product of per-axis erf differences.
    """
    c = np.asarray(centres, dtype=float).reshape(-1, 2)
    ex, ey, w = _live_events(insertions, now, tau)
    mx = _gaussian_axis_mean(c[:, None, 0], fov[0] / 2, ex[None, :], sigma)
    my = _gaussian_axis_mean(c[:, None, 1], fov[1] / 2, ey[None, :], sigma)
    return (w * mx * my).sum(axis=1)


@dataclass(frozen=True)
class SamplerParams:
    """The tunables `choose_field` reads; defaults mirror SearchConstraints."""

    sigma: float = 50e-6
    tau: float = 300.0
    exposure_threshold: float = 0.1
    min_region_fraction: float = 0.8
    max_resurvey: float = 0.25


@dataclass(frozen=True)
class Raster:
    """The union of some regions on a pixel grid, with its integral image.

    Pixel (j, i) spans x in [origin[0] + i*pitch, +pitch) and likewise for y.
    `bounds` is the regions' own (x0, y0, x1, y1) box, or None with no regions;
    the grid extends half a field past it on every side.
    """

    origin: tuple
    pitch: float
    mask: np.ndarray
    integral: np.ndarray
    bounds: tuple | None


def mask_pixel_count(bounds, fov, pitch: float = DEFAULT_PITCH) -> int:
    """How many pixels the padded raster of a region with `bounds` needs."""
    x0, y0, x1, y1 = bounds
    nx = math.ceil((x1 - x0 + fov[0]) / pitch)
    ny = math.ceil((y1 - y0 + fov[1]) / pitch)
    return nx * ny


def _integral(mask: np.ndarray) -> np.ndarray:
    out = np.zeros((mask.shape[0] + 1, mask.shape[1] + 1), dtype=np.int64)
    out[1:, 1:] = mask.cumsum(axis=0).cumsum(axis=1)
    return out


def _pixel_span(lo, hi, origin, pitch, n):
    """Pixel index range [i0, i1) whose centres lie in [lo, hi], clipped to [0, n]."""
    i0 = np.ceil((np.asarray(lo) - origin) / pitch - 0.5).astype(np.int64)
    i1 = np.floor((np.asarray(hi) - origin) / pitch - 0.5).astype(np.int64) + 1
    return np.clip(i0, 0, n), np.clip(np.maximum(i1, i0), 0, n)


def rasterize_regions(regions, fov, pitch: float = DEFAULT_PITCH) -> Raster:
    """Rasterize the union of `regions` over their bounding box padded by half of `fov`."""
    regions = list(regions)
    if not regions:
        return Raster((0.0, 0.0), pitch, np.zeros((0, 0), bool), _integral(np.zeros((0, 0))), None)
    boxes = np.array([r.bounds() for r in regions])
    bounds = (boxes[:, 0].min(), boxes[:, 1].min(), boxes[:, 2].max(), boxes[:, 3].max())
    origin = (bounds[0] - fov[0] / 2, bounds[1] - fov[1] / 2)
    ny = math.ceil((bounds[3] - bounds[1] + fov[1]) / pitch)
    nx = math.ceil((bounds[2] - bounds[0] + fov[0]) / pitch)
    mask = np.zeros((ny, nx), dtype=bool)
    for region, (bx0, by0, bx1, by1) in zip(regions, boxes):
        i0, i1 = _pixel_span(bx0, bx1, origin[0], pitch, nx)
        j0, j1 = _pixel_span(by0, by1, origin[1], pitch, ny)
        xs = origin[0] + (np.arange(i0, i1) + 0.5) * pitch
        ys = origin[1] + (np.arange(j0, j1) + 0.5) * pitch
        gx, gy = np.meshgrid(xs, ys)
        mask[j0:j1, i0:i1] |= region.containsArray(gx, gy)
    return Raster(origin, pitch, mask, _integral(mask), bounds)


def _rect_sums(integral, i0, i1, j0, j1):
    """Pixel sums over index rectangles [i0, i1) x [j0, j1), clipped to the grid."""
    ny, nx = integral.shape[0] - 1, integral.shape[1] - 1
    i0, i1 = np.clip(i0, 0, nx), np.clip(i1, 0, nx)
    j0, j1 = np.clip(j0, 0, ny), np.clip(j1, 0, ny)
    return integral[j1, i1] - integral[j0, i1] - integral[j1, i0] + integral[j0, i0]


def _field_pixel_ranges(raster, centres, fov):
    c = np.asarray(centres, dtype=float).reshape(-1, 2)
    ox, oy = raster.origin
    p = raster.pitch
    i0 = np.rint((c[:, 0] - fov[0] / 2 - ox) / p).astype(np.int64)
    j0 = np.rint((c[:, 1] - fov[1] / 2 - oy) / p).astype(np.int64)
    width = max(int(round(fov[0] / p)), 1)
    height = max(int(round(fov[1] / p)), 1)
    return i0, i0 + width, j0, j0 + height, width * height


def region_fraction(raster: Raster, centres, fov) -> np.ndarray:
    """Fraction of a `fov` field centred on each of `centres` (N, 2) that is region."""
    i0, i1, j0, j1, area = _field_pixel_ranges(raster, centres, fov)
    if raster.mask.size == 0:
        return np.zeros(len(i0))
    return _rect_sums(raster.integral, i0, i1, j0, j1) / area


def _footprint_mask(raster: Raster, footprints) -> np.ndarray:
    mask = np.zeros(raster.mask.shape, dtype=bool)
    ny, nx = mask.shape
    for x0, y0, x1, y1 in footprints:
        i0, i1 = _pixel_span(x0, x1, raster.origin[0], raster.pitch, nx)
        j0, j1 = _pixel_span(y0, y1, raster.origin[1], raster.pitch, ny)
        mask[j0:j1, i0:i1] = True
    return mask


def imaged_region_fraction(raster: Raster, footprints) -> float:
    """Fraction of the raster's region pixels inside the union of `footprints`."""
    region_pixels = int(raster.mask.sum())
    if region_pixels == 0:
        return 0.0
    imaged = _footprint_mask(raster, footprints) & raster.mask
    return float(imaged.sum()) / region_pixels


def _lattice(lo, hi, step):
    n = int(math.floor((hi - lo) / step + 1e-9)) + 1
    return (lo + hi) / 2 + (np.arange(n) - (n - 1) / 2) * step


def choose_field(raster: Raster, fov, footprints, insertions, now, params, rng):
    """The (x, y) centre of the next field to survey, or None when none is left.

    Candidates form a lattice at fov/4 spacing over the regions' bounding box. A
    candidate is eligible when its field is at least `min_region_fraction` region
    (relaxed to 90% of the best any candidate offers, so thin regions still
    work), judged over all candidates so it does not change as the survey
    proceeds. Candidates whose field is more than `max_resurvey` already covered
    by `footprints` ((x0, y0, x1, y1) rects, any size) are dropped. One of the
    candidates with field exposure under `exposure_threshold` is then chosen
    uniformly with `rng`; if there are none, the least exposed one is taken.
    """
    if raster.bounds is None or not raster.mask.any():
        return None
    x0, y0, x1, y1 = raster.bounds
    xs = _lattice(x0, x1, fov[0] / LATTICE_DIVISOR)
    ys = _lattice(y0, y1, fov[1] / LATTICE_DIVISOR)
    gx, gy = np.meshgrid(xs, ys)
    centres = np.column_stack([gx.ravel(), gy.ravel()])

    fractions = region_fraction(raster, centres, fov)
    best = fractions.max()
    if best <= 0:
        return None
    eligible = fractions >= min(params.min_region_fraction, THIN_BAND_SLACK * best)

    if len(footprints):
        i0, i1, j0, j1, area = _field_pixel_ranges(raster, centres, fov)
        imaged = _integral(_footprint_mask(raster, footprints))
        eligible &= _rect_sums(imaged, i0, i1, j0, j1) / area <= params.max_resurvey

    centres = centres[eligible]
    if not len(centres):
        return None
    exposure = field_exposure(centres, fov, insertions, now, params.sigma, params.tau)
    cool = np.flatnonzero(exposure < params.exposure_threshold)
    index = int(rng.choice(cool)) if len(cool) else int(exposure.argmin())
    return (float(centres[index, 0]), float(centres[index, 1]))
