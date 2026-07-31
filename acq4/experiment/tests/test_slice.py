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


def test_depth_range_must_span_a_nonzero_thickness():
    with pytest.raises(ValueError, match="nonzero thickness"):
        SearchConstraints(depth_range=(-40e-6, -40e-6))


def test_depth_range_accepts_either_ordering():
    # An operator may type the deeper bound first; both describe the same slab.
    shallow_first = SearchConstraints(depth_range=(-20e-6, -60e-6))
    deep_first = SearchConstraints(depth_range=(-60e-6, -20e-6))
    assert shallow_first.z_span() == deep_first.z_span()
    assert shallow_first.z_span() == pytest.approx(40e-6)


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
