"""Tests for search-region shapes: the bounding box a survey plans its tiles over,
and the exact rect-vs-shape overlap test that decides which of those tiles to image."""

import pytest

from acq4.experiment.search_region import RectRegion, SearchRegion, tile_rect

# A 10 um tile, the size used throughout these tests.
TILE = (10e-6, 10e-6)


def test_tile_rect_is_centered_on_the_tile_center():
    # A tile is named by its center (that is what the stage is driven to), but
    # overlap tests need its extent, and getting this wrong by half a field
    # would shift every survey by half a tile.
    assert tile_rect((10.0, 20.0), (4.0, 6.0)) == (8.0, 17.0, 12.0, 23.0)


def test_the_base_class_refuses_to_answer_for_itself():
    # SearchRegion is the contract, not a usable shape: a subclass that forgets
    # to implement one of the two methods must fail loudly rather than silently
    # surveying nothing.
    region = SearchRegion()
    with pytest.raises(NotImplementedError):
        region.bounds()
    with pytest.raises(NotImplementedError):
        region.overlapsTile((0.0, 0.0), TILE)


def test_rect_bounds_are_normalized_whichever_corners_are_given():
    # An ROI dragged up-and-left produces x1 < x0; the tiler would plan an empty
    # grid from that, so the region normalizes instead of trusting the caller.
    assert RectRegion(30e-6, 30e-6, 0.0, 0.0).bounds() == (0.0, 0.0, 30e-6, 30e-6)
    assert RectRegion(0.0, 0.0, 30e-6, 30e-6).bounds() == (0.0, 0.0, 30e-6, 30e-6)


def test_rect_rejects_zero_extent_in_either_axis():
    # A degenerate region is a mis-drag, not a search: it would plan a grid of
    # tiles over a line and report progress against it.
    with pytest.raises(ValueError, match="nonzero extent"):
        RectRegion(0.0, 0.0, 0.0, 30e-6)
    with pytest.raises(ValueError, match="nonzero extent"):
        RectRegion(0.0, 0.0, 30e-6, 0.0)


def test_rect_overlaps_a_tile_inside_it():
    region = RectRegion(0.0, 0.0, 30e-6, 30e-6)
    assert region.overlapsTile((15e-6, 15e-6), TILE) is True


def test_rect_does_not_overlap_a_tile_clear_of_it():
    region = RectRegion(0.0, 0.0, 30e-6, 30e-6)
    assert region.overlapsTile((100e-6, 15e-6), TILE) is False


def test_rect_overlaps_a_tile_that_only_touches_its_edge():
    # Closed-rect semantics, and not a curiosity: plan_grid centers its grid over
    # the region so the outermost tiles deliberately overhang the edges. A
    # half-open test would drop a tile at every region border.
    region = RectRegion(0.0, 0.0, 30e-6, 30e-6)
    # This tile spans -10 um .. 0 um, touching the region's near edge exactly.
    assert region.overlapsTile((-5e-6, 15e-6), TILE) is True


def test_rect_regions_with_the_same_corners_are_equal():
    # Tests and UI code compare regions; a slice's region list is only
    # meaningfully assertable if equality is by value.
    assert RectRegion(0.0, 0.0, 30e-6, 30e-6) == RectRegion(0.0, 0.0, 30e-6, 30e-6)
    assert RectRegion(0.0, 0.0, 30e-6, 30e-6) != RectRegion(0.0, 0.0, 20e-6, 30e-6)
