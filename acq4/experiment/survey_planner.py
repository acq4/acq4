"""Pure-numpy survey planning: the pipette-insertion exposure model and the chooser
that picks the next survey field from the region area still to image and that exposure."""

from __future__ import annotations

import numpy as np
from scipy.special import erf

MIN_EVENT_WEIGHT = 1e-3


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
