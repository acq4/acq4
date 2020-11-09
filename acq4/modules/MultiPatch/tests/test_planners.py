from unittest import TestCase

import numpy as np

from acq4.devices.Pipette.planners import _extractionWaypoint, ORIGIN


class TestExtraction(TestCase):
    def test_goes_directly_to_dest_if_aligned(self):
        dest = [-1, 0, 1]
        waypoint = _extractionWaypoint(dest, np.pi / 4)
        np.testing.assert_array_almost_equal(dest, waypoint)
        self.assert_np_array_less_or_equal(np.abs(waypoint), np.abs(dest))
        self.assert_np_array_greater_or_equal(np.abs(waypoint), ORIGIN)

    def test_goes_to_x_first_if_above_pitch(self):
        dest = [-1, 0, 2]
        waypoint = _extractionWaypoint(dest, np.pi / 4)
        self.assertAlmostEqual(dest[0], waypoint[0])
        self.assert_np_array_less_or_equal(np.abs(waypoint), np.abs(dest))
        self.assert_np_array_greater_or_equal(np.abs(waypoint), ORIGIN)

    def test_goes_to_z_first_if_below_pitch(self):
        dest = [-2, 0, 1]
        waypoint = _extractionWaypoint(dest, np.pi / 4)
        self.assertAlmostEqual(dest[2], waypoint[2])
        self.assert_np_array_less_or_equal(np.abs(waypoint), np.abs(dest))
        self.assert_np_array_greater_or_equal(np.abs(waypoint), ORIGIN)

    def test_goes_nowhere_if_dest_is_below_origin(self):
        dest = [-1, 0, -1]
        waypoint = _extractionWaypoint(dest, np.pi / 4)
        np.testing.assert_array_almost_equal(waypoint, ORIGIN)
        self.assert_np_array_less_or_equal(np.abs(waypoint), np.abs(dest))
        self.assert_np_array_greater_or_equal(np.abs(waypoint), ORIGIN)

    def test_goes_nowhere_if_dest_is_in_front_of_origin(self):
        dest = [1, 0, 1]
        waypoint = _extractionWaypoint(dest, np.pi / 4)
        np.testing.assert_array_almost_equal(waypoint, ORIGIN)
        self.assert_np_array_less_or_equal(np.abs(waypoint), np.abs(dest))
        self.assert_np_array_greater_or_equal(np.abs(waypoint), ORIGIN)

    def test_invalid_pitch_gets_a_value_error(self):
        self.assertRaises(ValueError, lambda: _extractionWaypoint([-1, 0, 1], 2))
        self.assertRaises(ValueError, lambda: _extractionWaypoint([-1, 0, 1], -1))

    def test_goes_nowhere_when_already_there(self):
        waypoint = _extractionWaypoint(ORIGIN, np.pi / 4)
        np.testing.assert_array_almost_equal(ORIGIN, waypoint)

    @staticmethod
    def assert_np_array_less_or_equal(a, b):
        assert np.alltrue(a <= b), f"{a} is not less than or equal to {b}"

    @staticmethod
    def assert_np_array_greater_or_equal(a, b):
        assert np.alltrue(a >= b), f"{a} is not greater than or equal to {b}"
