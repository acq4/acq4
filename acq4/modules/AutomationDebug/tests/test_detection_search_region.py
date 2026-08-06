# Tests for restricting detected cells to the survey region: the camera may image
# past the region, but only cells found inside it are candidates to patch.
from unittest.mock import MagicMock

import pytest

from acq4.modules.AutomationDebug.detection import MAX_DETECTION_CANDIDATES, CellDetector
from acq4.modules.AutomationDebug.survey import SurveyRegion


class _Vec:
    """Stand-in for the point objects pg.RectROI's pos()/size() return."""

    def __init__(self, x, y):
        self._x, self._y = x, y

    def x(self):
        return self._x

    def y(self):
        return self._y


def _region(pos=(0.0, 0.0), size=(10.0, 10.0)):
    region = SurveyRegion(MagicMock())
    roi = MagicMock()
    roi.pos.return_value = _Vec(*pos)
    roi.size.return_value = _Vec(*size)
    region._roi = roi
    return region


class TestContains:
    def test_inside(self):
        assert _region().contains((5.0, 5.0, -1.0))

    @pytest.mark.parametrize("pos", [(-1.0, 5.0), (11.0, 5.0), (5.0, -1.0), (5.0, 11.0)])
    def test_outside(self, pos):
        assert not _region().contains(pos)

    def test_on_the_boundary_counts_as_inside(self):
        region = _region()
        assert region.contains((0.0, 0.0))
        assert region.contains((10.0, 10.0))

    def test_handles_a_roi_dragged_to_negative_size(self):
        """A RectROI resized past its own origin reports a negative size; the
        rectangle it describes is the same one either way."""
        region = _region(pos=(10.0, 10.0), size=(-10.0, -10.0))
        assert region.contains((5.0, 5.0))
        assert not region.contains((11.0, 5.0))

    def test_no_region_contains_nothing(self):
        assert not SurveyRegion(MagicMock()).contains((0.0, 0.0))


class TestSelectCandidates:
    @staticmethod
    def _detector(region):
        win = MagicMock()
        win._surveyRegion = region
        return CellDetector(win)

    @staticmethod
    def _detection(x, y, score=1.0):
        return ((x, y, -50e-6), score)

    def test_drops_detections_outside_the_region(self):
        detector = self._detector(_region())
        inside = self._detection(5.0, 5.0)
        outside = self._detection(50.0, 5.0)
        assert detector._selectCandidates([inside, outside]) == [inside]

    def test_filters_before_truncating(self):
        """An edge tile must not spend its whole quota on out-of-region cells while
        usable ones sit just below the cut."""
        detector = self._detector(_region())
        outside = [self._detection(50.0, 5.0) for _ in range(MAX_DETECTION_CANDIDATES)]
        inside = [self._detection(1.0 + i, 5.0) for i in range(3)]
        assert detector._selectCandidates(outside + inside) == inside

    def test_keeps_the_best_detections_when_more_are_in_region_than_wanted(self):
        detector = self._detector(_region())
        detections = [self._detection(1.0, 1.0 + i) for i in range(MAX_DETECTION_CANDIDATES + 4)]
        selected = detector._selectCandidates(detections)
        assert selected == detections[:MAX_DETECTION_CANDIDATES]

    def test_keeps_everything_when_no_region_is_set(self):
        """Manual detection with no survey region has nothing to be outside of."""
        detector = self._detector(SurveyRegion(MagicMock()))
        detections = [self._detection(500.0, 500.0), self._detection(5.0, 5.0)]
        assert detector._selectCandidates(detections) == detections
