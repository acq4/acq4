"""Tests for the survey-field sampler: the exposure model and the region-fraction field chooser."""

import numpy as np
import pytest

from acq4.experiment.survey_planner import exposure_at, field_exposure

SIGMA = 50e-6
TAU = 300.0


def test_exposure_peaks_at_one_for_a_fresh_event():
    ev = [(10e-6, 20e-6, 1000.0)]
    got = exposure_at([(10e-6, 20e-6)], ev, now=1000.0, sigma=SIGMA, tau=TAU)
    assert got == pytest.approx([1.0])


def test_exposure_decays_by_e_over_tau():
    ev = [(0.0, 0.0, 1000.0)]
    got = exposure_at([(0.0, 0.0)], ev, now=1000.0 + TAU, sigma=SIGMA, tau=TAU)
    assert got == pytest.approx([np.exp(-1.0)])


def test_exposure_falls_off_as_a_gaussian_in_distance():
    ev = [(0.0, 0.0, 0.0)]
    got = exposure_at([(SIGMA, 0.0)], ev, now=0.0, sigma=SIGMA, tau=TAU)
    assert got == pytest.approx([np.exp(-0.5)])


def test_exposure_sums_events():
    ev = [(0.0, 0.0, 0.0), (0.0, 0.0, 0.0)]
    got = exposure_at([(0.0, 0.0)], ev, now=0.0, sigma=SIGMA, tau=TAU)
    assert got == pytest.approx([2.0])


def test_events_with_negligible_weight_are_ignored():
    ev = [(0.0, 0.0, 0.0)]
    old = TAU * np.log(1e3) + 1.0
    assert exposure_at([(0.0, 0.0)], ev, now=old, sigma=SIGMA, tau=TAU) == pytest.approx([0.0])
    assert field_exposure(
        [(0.0, 0.0)], (100e-6, 100e-6), ev, now=old, sigma=SIGMA, tau=TAU
    ) == pytest.approx([0.0])


def test_no_insertions_means_zero_exposure():
    assert exposure_at([(0.0, 0.0), (1.0, 1.0)], [], 5.0, SIGMA, TAU).tolist() == [0.0, 0.0]
    fe = field_exposure([(0.0, 0.0)], (1e-4, 1e-4), [], 5.0, SIGMA, TAU)
    assert fe.tolist() == [0.0]


def test_field_exposure_matches_brute_force_mean():
    rng = np.random.default_rng(1)
    ev = [(x, y, t) for x, y, t in rng.uniform([0, 0, 0], [200e-6, 200e-6, 600], (6, 3))]
    fov = (180e-6, 120e-6)
    centres = rng.uniform(0, 200e-6, (5, 2))
    now = 700.0

    got = field_exposure(centres, fov, ev, now, SIGMA, TAU)

    expected = []
    for cx, cy in centres:
        gx = np.linspace(cx - fov[0] / 2, cx + fov[0] / 2, 801)
        gy = np.linspace(cy - fov[1] / 2, cy + fov[1] / 2, 601)
        X, Y = np.meshgrid(gx, gy)
        e = exposure_at(np.column_stack([X.ravel(), Y.ravel()]), ev, now, SIGMA, TAU)
        expected.append(e.mean())
    assert got == pytest.approx(expected, abs=1e-3)
