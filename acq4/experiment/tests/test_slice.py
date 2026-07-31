"""Tests for SearchConstraints validation and the Slice object's regions,
coverage, and survey statistics."""

import pytest

from acq4.experiment.slice import SearchConstraints


def test_defaults_are_a_usable_search():
    c = SearchConstraints()
    assert c.depth_range == (-20e-6, -60e-6)
    assert 0.0 <= c.min_health <= 1.0
    assert c.max_cell_density > 0
    assert c.rescans_allowed is False


def test_depth_range_offsets_must_be_at_or_below_the_surface():
    # Offsets are relative to the tissue surface and negative is deeper, so a
    # positive offset would search in the bath above the tissue.
    with pytest.raises(ValueError, match="at or below the surface"):
        SearchConstraints(depth_range=(20e-6, -60e-6))
    # The positive offset can land in either position of the pair, so both
    # must be checked.
    with pytest.raises(ValueError, match="at or below the surface"):
        SearchConstraints(depth_range=(-60e-6, 20e-6))


def test_depth_range_must_span_a_nonzero_thickness():
    with pytest.raises(ValueError, match="nonzero thickness"):
        SearchConstraints(depth_range=(-40e-6, -40e-6))


def test_depth_range_accepts_either_ordering():
    # An operator may type the deeper bound first; both describe the same slab.
    shallow_first = SearchConstraints(depth_range=(-20e-6, -60e-6))
    deep_first = SearchConstraints(depth_range=(-60e-6, -20e-6))
    assert shallow_first.z_span() == deep_first.z_span()
    assert shallow_first.z_span() == pytest.approx(40e-6)


def test_z_bounds_adds_offsets_to_the_surface_and_orders_shallow_before_deep():
    # z_bounds must return (shallower, deeper), which for negative offsets
    # means (max, min); a swapped min/max or subtracted offset would only
    # show up when the surface is nonzero, since surface=0 makes signed
    # offsets look the same as their negation.
    c = SearchConstraints(depth_range=(-20e-6, -60e-6))
    assert c.z_bounds(-500e-6) == pytest.approx((-520e-6, -560e-6))


def test_z_bounds_is_unaffected_by_depth_range_ordering():
    c = SearchConstraints(depth_range=(-60e-6, -20e-6))
    assert c.z_bounds(-500e-6) == pytest.approx((-520e-6, -560e-6))


def test_z_bounds_at_a_zero_surface():
    # surface=0.0 is the degenerate case where offsets equal their own
    # negation's magnitude, so it alone can't catch a sign error; kept as a
    # sanity check alongside the nonzero-surface cases above.
    c = SearchConstraints(depth_range=(-20e-6, -60e-6))
    assert c.z_bounds(0.0) == pytest.approx((-20e-6, -60e-6))


def test_min_health_must_be_a_probability():
    with pytest.raises(ValueError, match="between 0 and 1"):
        SearchConstraints(min_health=1.5)
    with pytest.raises(ValueError, match="between 0 and 1"):
        SearchConstraints(min_health=-0.1)


def test_max_cell_density_must_be_positive():
    with pytest.raises(ValueError, match="positive"):
        SearchConstraints(max_cell_density=0.0)


def test_constraints_are_frozen():
    c = SearchConstraints()
    with pytest.raises(Exception):
        c.min_health = 0.9
