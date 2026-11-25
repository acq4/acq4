"""Tests for the survey-field sampler: the exposure model and the region-fraction field chooser."""

import numpy as np
import pytest

from acq4.experiment.search_grid import covered_fraction, footprint
from acq4.experiment.search_region import EllipseRegion, RectRegion
from acq4.experiment.survey_planner import (
    MAX_MASK_PIXELS,
    SamplerParams,
    choose_field,
    exposure_at,
    field_exposure,
    imaged_region_fraction,
    mask_pixel_count,
    rasterize_regions,
    region_fraction,
)

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


FOV = (200e-6, 200e-6)
PARAMS = SamplerParams(
    sigma=SIGMA,
    tau=TAU,
    exposure_threshold=0.1,
    min_region_fraction=0.8,
    max_resurvey=0.25,
)
BIG = RectRegion(0, 0, 1e-3, 1e-3)


def _picks(regions, footprints=(), insertions=(), now=1000.0, params=PARAMS, seeds=range(60)):
    raster = rasterize_regions(regions, FOV)
    return raster, [
        choose_field(raster, FOV, footprints, insertions, now, params, np.random.default_rng(seed))
        for seed in seeds
    ]


def test_region_fraction_is_one_inside_zero_outside_half_straddling():
    raster = rasterize_regions([BIG], FOV)
    got = region_fraction(raster, [(500e-6, 500e-6), (2e-3, 2e-3), (0.0, 500e-6)], FOV)
    assert got[0] == pytest.approx(1.0)
    assert got[1] == pytest.approx(0.0)
    assert got[2] == pytest.approx(0.5, abs=0.02)


def test_region_fraction_follows_curved_regions():
    disc = EllipseRegion(0, 0, 1e-3, 1e-3)
    raster = rasterize_regions([disc], FOV)
    inside, rim, corner = region_fraction(
        raster, [(500e-6, 500e-6), (1e-3, 500e-6), (50e-6, 50e-6)], FOV
    )
    assert inside == pytest.approx(1.0)
    assert 0.3 < rim < 0.6
    assert corner < 0.05


def test_mask_pixel_count_matches_raster_and_cap_is_ten_mm_square_at_5um():
    bounds = BIG.bounds()
    raster = rasterize_regions([BIG], FOV, pitch=5e-6)
    assert mask_pixel_count(bounds, FOV, 5e-6) == raster.mask.size
    assert MAX_MASK_PIXELS == 4_000_000
    assert mask_pixel_count((0, 0, 10e-3, 10e-3), (0.0, 0.0), 5e-6) == 2000 * 2000


def test_empty_regions_choose_nothing():
    raster = rasterize_regions([], FOV)
    rng = np.random.default_rng(0)
    assert choose_field(raster, FOV, [], [], 0.0, PARAMS, rng) is None
    assert imaged_region_fraction(raster, []) == 0.0


def test_picks_honour_the_region_fraction_rule():
    raster, picks = _picks([BIG])
    assert all(p is not None for p in picks)
    assert (region_fraction(raster, picks, FOV) >= 0.8 - 1e-9).all()
    assert len(set(picks)) > 10


def test_picks_in_a_band_narrower_than_a_field_still_work():
    band = RectRegion(0, 0, 1e-3, 60e-6)
    raster, picks = _picks([band])
    assert all(p is not None for p in picks)
    fractions = region_fraction(raster, picks, FOV)
    assert (fractions >= 0.9 * 0.3 - 0.01).all()


def test_exposure_eligibility_ignores_imaged_ground():
    raster, before = _picks([BIG], seeds=[0])
    cover = [footprint(before[0], FOV)]
    _, after = _picks([BIG], footprints=cover, seeds=range(30))
    assert (region_fraction(raster, after, FOV) >= 0.8 - 1e-9).all()


def test_below_threshold_pick_is_uniform_over_low_exposure_fields():
    insertions = [(300e-6, 500e-6, 1000.0)]
    raster, picks = _picks([BIG], insertions=insertions, seeds=range(200))
    exposure = field_exposure(picks, FOV, insertions, 1000.0, SIGMA, TAU)
    assert (exposure < PARAMS.exposure_threshold).all()
    assert len(set(picks)) > 20


def test_when_everything_is_hot_the_lowest_exposure_field_wins():
    insertions = [(100e-6, 500e-6, 1000.0)]
    hot = SamplerParams(1e-3, TAU, 0.2, 0.8, 0.25)
    raster, picks = _picks([BIG], insertions=insertions, params=hot, seeds=range(10))
    assert len(set(picks)) == 1
    x, y = picks[0]
    assert x > 700e-6
    assert region_fraction(raster, [picks[0]], FOV)[0] >= 0.8 - 1e-9


def test_resurvey_exclusion_respects_each_footprints_own_fov():
    covered = [footprint((250e-6, 500e-6), (500e-6, 1e-3))]
    other = [footprint((900e-6, 500e-6), (300e-6, 300e-6))]
    footprints = covered + other
    _, picks = _picks([BIG], footprints=footprints, seeds=range(100))
    assert all(p is not None for p in picks)
    for p in picks:
        assert covered_fraction(footprint(p, FOV), footprints) <= 0.25 + 0.02


def test_fully_imaged_region_is_exhausted():
    footprints = [footprint((500e-6, 500e-6), (1.4e-3, 1.4e-3))]
    _, picks = _picks([BIG], footprints=footprints, seeds=[0, 1])
    assert picks == [None, None]


def test_same_seed_gives_same_pick_and_seeds_differ():
    raster = rasterize_regions([BIG], FOV)

    def pick(seed):
        rng = np.random.default_rng([seed, 3])
        return choose_field(raster, FOV, [], [], 0.0, PARAMS, rng)

    assert pick(7) == pick(7)
    assert len({pick(s) for s in range(20)}) > 1


def test_imaged_region_fraction_counts_only_region_pixels():
    raster = rasterize_regions([BIG], FOV)
    half = [(-300e-6, -300e-6, 500e-6, 1.3e-3)]
    assert imaged_region_fraction(raster, half) == pytest.approx(0.5, abs=0.01)
    assert imaged_region_fraction(raster, []) == 0.0
    assert imaged_region_fraction(raster, [(-1.0, -1.0, 1.0, 1.0)]) == pytest.approx(1.0)


def test_multiple_regions_are_unioned():
    a, b = RectRegion(0, 0, 400e-6, 400e-6), RectRegion(2e-3, 2e-3, 2.4e-3, 2.4e-3)
    raster = rasterize_regions([a, b], FOV)
    inside_a, inside_b, between = region_fraction(
        raster, [(200e-6, 200e-6), (2.2e-3, 2.2e-3), (1.2e-3, 1.2e-3)], FOV
    )
    assert inside_a == pytest.approx(1.0)
    assert inside_b == pytest.approx(1.0)
    assert between == 0.0
