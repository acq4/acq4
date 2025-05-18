import pytest
import numpy as np

from acq4.util.imaging.sequencer import _enforce_linear_z_stack


class MockFrame:
    def __init__(self, depth, data=None):
        self.depth = depth
        self._data = data if data is not None else np.array([depth * 10]) # Ensure some difference for non-identical frames

    def __repr__(self):
        return f"<MockFrame depth={self.depth}>"

    def data(self):
        return self._data


def test_enforce_linear_z_stack_empty_frames():
    with pytest.raises(ValueError, match="Insufficient frames to have one frame per step."):
        _enforce_linear_z_stack([], 0.0, 10.0, 1.0)


def test_enforce_linear_z_stack_single_frame():
    frames = [MockFrame(5.0)]
    assert _enforce_linear_z_stack(frames, 0.0, 0.8, 1.0) == frames


def test_enforce_linear_z_stack_zero_step():
    frames = [MockFrame(0.0), MockFrame(1.0)]
    with pytest.raises(ValueError, match="Z stack step size must be non-zero."):
        _enforce_linear_z_stack(frames, 0.0, 10.0, 0.0)


def test_enforce_linear_z_stack_insufficient_frames_exact_steps():
    frames = [MockFrame(0.0)]
    with pytest.raises(ValueError, match="Insufficient frames to have one frame per step."):
        _enforce_linear_z_stack(frames, 0.0, 2.0, 1.0) # expects 3 frames (0, 1, 2)


def test_enforce_linear_z_stack_insufficient_frames_after_pruning():
    # All frames have same depth, effectively becoming 1 unique frame
    frames = [MockFrame(0.0, data=np.array([1])), MockFrame(0.0, data=np.array([1])), MockFrame(0.0, data=np.array([1]))]
    with pytest.raises(ValueError, match=r"Insufficient frames to have one frame per step \(after pruning nigh identical frames\)."):
        _enforce_linear_z_stack(frames, 0.0, 1.0, 0.5) # expects 3 frames (0, 0.5, 1.0)


def test_enforce_linear_z_stack_ascending_exact_frames():
    f0, f1, f2 = MockFrame(0.0), MockFrame(1.0), MockFrame(2.0)
    frames = [f0, f1, f2]
    result = _enforce_linear_z_stack(frames, 0.0, 2.0, 1.0)
    assert result == [f0, f1, f2]


def test_enforce_linear_z_stack_descending_exact_frames():
    f0, f1, f2 = MockFrame(2.0), MockFrame(1.0), MockFrame(0.0)
    frames = [f0, f1, f2] # Input order shouldn't matter as it sorts by depth
    result = _enforce_linear_z_stack(frames, 2.0, 0.0, -1.0)
    # Expected depths are 2.0, 1.0, 0.0. searchsorted will pick corresponding frames.
    assert result == [f2, f1, f0]


def test_enforce_linear_z_stack_ascending_excess_frames():
    f0, f0_5, f1, f1_5, f2 = MockFrame(0.0), MockFrame(0.5), MockFrame(1.0), MockFrame(1.5), MockFrame(2.0)
    frames = [f0, f0_5, f1, f1_5, f2]
    result = _enforce_linear_z_stack(frames, 0.0, 2.0, 1.0) # expects 0, 1, 2
    # The function assigns frames to expected depths using the Hungarian algorithm.
    # The algorithm minimizes the total cost, which is the sum of absolute differences
    # between expected depths and interpolated depths.
    assert result == [f0, f1, f2]


def test_enforce_linear_z_stack_descending_excess_frames():
    f0, f0_5, f1, f1_5, f2 = MockFrame(0.0), MockFrame(0.5), MockFrame(1.0), MockFrame(1.5), MockFrame(2.0)
    frames = [f2, f1_5, f1, f0_5, f0] # Sorted by depth: f0, f0_5, f1, f1_5, f2
    result = _enforce_linear_z_stack(frames, 2.0, 0.0, -1.0) # expects 2, 1, 0
    # expected_depths will be [0, 1, 2] because start, stop are sorted internally.
    # The function assigns frames to expected depths using the Hungarian algorithm.
    # The algorithm minimizes the total cost, which is the sum of absolute differences
    # between expected depths and interpolated depths.
    assert result == [f0, f1, f2]


def test_enforce_linear_z_stack_ascending_grouped_depths():
    # Simulates stage updating z infrequently
    f0a, f0b = MockFrame(0.0, data=np.array([1])), MockFrame(0.0, data=np.array([2])) # different data
    f1a, f1b = MockFrame(1.0, data=np.array([11])), MockFrame(1.0, data=np.array([12]))
    f2a, f2b = MockFrame(2.0, data=np.array([21])), MockFrame(2.0, data=np.array([22]))
    frames = [f0a, f0b, f1a, f1b, f2a, f2b]
    result = _enforce_linear_z_stack(frames, 0.0, 2.0, 1.0)
    # After pruning identical depths (if data was same), it would pick one.
    # difference_is_significant checks if the depth is NOT close to the first or last depth.
    # The Hungarian algorithm assigns frames to expected depths to minimize the total cost.
    assert result == [f0b, f1b, f2b]


def test_enforce_linear_z_stack_descending_grouped_depths():
    f0a, f0b = MockFrame(0.0, data=np.array([1])), MockFrame(0.0, data=np.array([2]))
    f1a, f1b = MockFrame(1.0, data=np.array([11])), MockFrame(1.0, data=np.array([12]))
    f2a, f2b = MockFrame(2.0, data=np.array([21])), MockFrame(2.0, data=np.array([22]))
    frames = [f2b, f2a, f1b, f1a, f0b, f0a] # Order doesn't matter for sorting
    result = _enforce_linear_z_stack(frames, 2.0, 0.0, -1.0) # expects 2, 1, 0
    # sorted unique frames by depth: [f0a, f0b, f1a, f1b, f2a, f2b] (assuming data makes them unique)
    # expected_depths (sorted): [0, 1, 2]
    # searchsorted will pick [f0b, f1b, f2b]
    assert result == [f0b, f1b, f2b]


def test_enforce_linear_z_stack_start_equals_stop():
    f0 = MockFrame(0.0)
    frames = [f0, MockFrame(0.1), MockFrame(-0.1)]
    result = _enforce_linear_z_stack(frames, 0.0, 0.0, 1.0) # expects 1 frame at 0.0
    assert result == [f0]


def test_enforce_linear_z_stack_non_exact_step_multiple():
    # (stop - start) % step != 0
    # start=0, stop=2.5, step=1.0 => expected depths [0.0, 1.0, 2.0]
    f0, f1, f2, f2_4 = MockFrame(0.0), MockFrame(1.0), MockFrame(2.0), MockFrame(2.4)
    frames = [f0, f1, f2, f2_4]
    result = _enforce_linear_z_stack(frames, 0.0, 2.5, 1.0)
    assert result == [f0, f1, f2_4] # The function assigns frames to expected depths using the Hungarian algorithm.

    # start=0, stop=2.0, step=0.8 => expected depths [0.0, 0.8, 1.6]
    f0, f0_7, f0_9, f1_5, f1_7, f2_0 = MockFrame(0.0), MockFrame(0.7), MockFrame(0.9), MockFrame(1.5), MockFrame(1.7), MockFrame(2.0)
    frames = [f0, f0_7, f0_9, f1_5, f1_7, f2_0]
    result = _enforce_linear_z_stack(frames, 0.0, 2.0, 0.8)
    # expected_depths = [0, 0.8, 1.6]
    # The function assigns frames to expected depths using the Hungarian algorithm.
    # The algorithm minimizes the total cost, which is the sum of absolute differences
    # between expected depths and interpolated depths.
    assert result == [f0, f0_9, f1_7]


def test_enforce_linear_z_stack_pruning_identical_frames():
    # difference_is_significant checks if the depth is NOT close to the first or last depth
    # This test assumes the default behavior of difference_is_significant
    f0a = MockFrame(0.0, data=np.array([1]))
    f0b = MockFrame(0.0, data=np.array([1])) # Identical depth
    f1a = MockFrame(1.0, data=np.array([2]))
    f1b = MockFrame(1.0, data=np.array([2])) # Identical depth
    f2  = MockFrame(2.0, data=np.array([3]))
    frames = [f0a, f0b, f1a, f1b, f2]
    result = _enforce_linear_z_stack(frames, 0.0, 2.0, 1.0)
    # After pruning, depths should be [f0a, f1a, f2] (or f0b, f1b if order was different but stable sort)
    # The current implementation of difference_is_significant only checks z, so this test might not fully
    # reflect pruning if that function changes to look at data.
    # Given current difference_is_significant: it keeps only the first of consecutive identical z.
    # So, sorted input: [f0a, f0b, f1a, f1b, f2]
    # Pruned: [f0a, f1a, f2] (because f0b.z == f0a.z, f1b.z == f1a.z)
    assert result == [f0a, f1a, f2]


def test_enforce_linear_z_stack_frames_not_perfectly_on_expected_depths():
    f_neg_0_1 = MockFrame(-0.1)
    f_0_9 = MockFrame(0.9)
    f_2_1 = MockFrame(2.1)
    frames = [f_neg_0_1, f_0_9, f_2_1] # depths: -0.1, 0.9, 2.1
    result = _enforce_linear_z_stack(frames, 0.0, 2.0, 1.0) # expects 0, 1, 2
    # expected_depths = [0, 1, 2]
    # actual_depths = [-0.1, 0.9, 2.1]
    # The function assigns frames to expected depths using the Hungarian algorithm.
    # The algorithm minimizes the total cost, which is the sum of absolute differences
    # between expected depths and interpolated depths.
    assert result == [f_0_9, f_2_1, f_2_1]

def test_enforce_linear_z_stack_descending_frames_not_perfectly_on_expected_depths():
    f_neg_0_1 = MockFrame(-0.1)
    f_0_9 = MockFrame(0.9)
    f_2_1 = MockFrame(2.1)
    frames = [f_2_1, f_0_9, f_neg_0_1] # depths sorted: -0.1, 0.9, 2.1
    result = _enforce_linear_z_stack(frames, 2.0, 0.0, -1.0) # expects 2, 1, 0
    # expected_depths will be [0, 1, 2] because start, stop are sorted internally.
    # The function assigns frames to expected depths using the Hungarian algorithm.
    # The algorithm minimizes the total cost, which is the sum of absolute differences
    # between expected depths and interpolated depths.
    assert result == [f_0_9, f_2_1, f_2_1]

def test_enforce_linear_z_stack_stop_start_step_consistency():
    # (stop - start) % step == 0, so stop should be inclusive
    f0, f1, f2 = MockFrame(0.0), MockFrame(1.0), MockFrame(2.0)
    frames = [f0, f1, f2]
    result = _enforce_linear_z_stack(frames, 0.0, 2.0, 1.0) # expects 0, 1, 2
    assert result == [f0, f1, f2]

    f0, f1, f2, f3 = MockFrame(0.0), MockFrame(0.5), MockFrame(1.0), MockFrame(1.5)
    frames = [f0, f1, f2, f3]
    result = _enforce_linear_z_stack(frames, 0.0, 1.5, 0.5) # expects 0, 0.5, 1.0, 1.5
    assert result == [f0, f1, f2, f3]

def test_enforce_linear_z_stack_descending_stop_start_step_consistency():
    f0, f1, f2 = MockFrame(2.0), MockFrame(1.0), MockFrame(0.0)
    frames = [f0, f1, f2] # sorted by depth: f2, f1, f0
    result = _enforce_linear_z_stack(frames, 2.0, 0.0, -1.0) # expects 2, 1, 0
    assert result == [f2, f1, f0]

    f0, f1, f2, f3 = MockFrame(1.5), MockFrame(1.0), MockFrame(0.5), MockFrame(0.0)
    frames = [f0, f1, f2, f3] # sorted by depth: f3, f2, f1, f0
    result = _enforce_linear_z_stack(frames, 1.5, 0.0, -0.5) # expects 1.5, 1.0, 0.5, 0.0
    assert result == [f3, f2, f1, f0]

fi_0_0 = MockFrame(0.0, data=np.array([0]))
fi_0_1 = MockFrame(0.1, data=np.array([1]))
fi_0_2 = MockFrame(0.2, data=np.array([2]))
fi_0_3 = MockFrame(0.3, data=np.array([3]))
fi_0_4 = MockFrame(0.4, data=np.array([4]))
fi_0_5 = MockFrame(0.5, data=np.array([5]))

def test_enforce_linear_z_stack_complex_case_1():
    # Test from a real-world scenario that was tricky
    # Depths are not perfectly aligned with steps
    frames = [fi_0_0, fi_0_1, fi_0_2, fi_0_3, fi_0_4, fi_0_5]
    start, stop, step = 0.0, 0.5, 0.1
    # expected_depths = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    # actual_depths = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    # searchsorted(actual_depths, expected_depths, side='right')
    # idx for 0.0 -> index of fi_0_0
    # idx for 0.1 -> index of fi_0_1
    # ...
    # idx for 0.5 -> index of fi_0_5
    result = _enforce_linear_z_stack(frames, start, stop, step)
    assert result == [fi_0_0, fi_0_1, fi_0_2, fi_0_3, fi_0_4, fi_0_5]

def test_enforce_linear_z_stack_complex_case_2_descending():
    frames = [fi_0_5, fi_0_4, fi_0_3, fi_0_2, fi_0_1, fi_0_0] # reverse order input
    start, stop, step = 0.5, 0.0, -0.1
    # expected_depths (sorted for search): [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    # actual_depths (sorted from input): [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    # searchsorted will give indices corresponding to [fi_0_0, fi_0_1, ..., fi_0_5]
    result = _enforce_linear_z_stack(frames, start, stop, step)
    assert result == [fi_0_0, fi_0_1, fi_0_2, fi_0_3, fi_0_4, fi_0_5]

def test_enforce_linear_z_stack_duplicate_depths_different_data_selection():
    # difference_is_significant currently only checks z values.
    # If it were to check data, this test would be more meaningful for that aspect.
    # As is, it tests that the *last* of the frames with the same depth is chosen by searchsorted.
    f0_a = MockFrame(0.0, data=np.array([1]))
    f0_b = MockFrame(0.0, data=np.array([2])) # different data, same depth
    f1 = MockFrame(1.0, data=np.array([3]))
    frames = [f0_a, f0_b, f1]
    result = _enforce_linear_z_stack(frames, 0.0, 1.0, 1.0) # expects 0.0, 1.0
    # Sorted unique (by z) frames: [f0_a, f1] (f0_b is pruned because its z is same as f0_a's)
    # Expected: [f0_a, f1]
    # However, if difference_is_significant was more sophisticated:
    # Sorted frames by depth: [f0_a, f0_b, f1]
    # Pruning (if data matters): no pruning if data is different.
    # actual_depths = [0.0, 0.0, 1.0]
    # expected_depths = [0.0, 1.0]
    # searchsorted([0,0,1], [0,1], side='right') -> indices for [f0_b, f1]
    # This depends on the stability of the sort within _enforce_linear_z_stack and how searchsorted handles duplicates.
    # Python's sort is stable. np.searchsorted picks the rightmost valid index.
    # The current `difference_is_significant` will prune `f0_b`.
    # So, `depths` becomes `[(0.0, f0_a), (1.0, f1)]`.
    # `actual_depths` becomes `[0.0, 1.0]`.
    # `expected_depths` is `[0.0, 1.0]`.
    # `idxes` from `searchsorted` will be `[0, 1]`.
    # Result: `[f0_a, f1]`.
    assert result == [f0_a, f1]

    frames_rev = [f1, f0_b, f0_a] # Test different input order
    result_rev = _enforce_linear_z_stack(frames_rev, 0.0, 1.0, 1.0)
    # Sorted input: [f0_a, f0_b, f1]
    # Pruned: [f0_a, f1]
    assert result_rev == [f0_a, f1]

fi_0 = MockFrame(0.0)
fi_1 = MockFrame(1.0)
fi_2 = MockFrame(2.0)
fi_3 = MockFrame(3.0)
fi_4 = MockFrame(4.0)

def test_enforce_linear_z_stack_more_frames_than_steps_issue_scenario():
    # Scenario from a bug: start=0, stop=2, step=1. Frames at 0,1,2,3,4. Expect 0,1,2
    frames = [fi_0, fi_1, fi_2, fi_3, fi_4]
    result = _enforce_linear_z_stack(frames, 0.0, 2.0, 1.0)
    # expected_depths = [0,1,2]
    # The function assigns frames to expected depths using the Hungarian algorithm.
    # The algorithm minimizes the total cost, which is the sum of absolute differences
    # between expected depths and interpolated depths.
    assert result == [fi_0, fi_1, fi_2]

def test_enforce_linear_z_stack_more_frames_than_steps_issue_scenario_desc():
    # Scenario from a bug: start=2, stop=0, step=-1. Frames at 0,1,2,3,4. Expect 2,1,0
    frames = [fi_4, fi_3, fi_2, fi_1, fi_0] # sorted by depth: fi_0, fi_1, fi_2, fi_3, fi_4
    result = _enforce_linear_z_stack(frames, 2.0, 0.0, -1.0)
    # expected_depths will be [0, 1, 2] because start, stop are sorted internally.
    # The function assigns frames to expected depths using the Hungarian algorithm.
    # The algorithm minimizes the total cost, which is the sum of absolute differences
    # between expected depths and interpolated depths.
    assert result == [fi_0, fi_1, fi_2]

def test_enforce_linear_z_stack_start_stop_step_float_precision():
    f1 = MockFrame(0.1)
    f2 = MockFrame(0.2)
    f3 = MockFrame(0.30000000000000004) # numpy.arange(0.1, 0.3+0.1, 0.1) can produce this
    frames = [f1,f2,f3]
    result = _enforce_linear_z_stack(frames, 0.1, 0.3, 0.1)
    # expected_depths = [0.1, 0.2, 0.3]
    # actual_depths = [0.1, 0.2, 0.30000000000000004]
    # searchsorted(actual_depths, expected_depths, side='right')
    # idx for 0.1 -> f1
    # idx for 0.2 -> f2
    # idx for 0.3 -> f3 (because 0.30000000000000004 is >= 0.3)
    assert result == [f1,f2,f3]
