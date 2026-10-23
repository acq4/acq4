import contextlib
import itertools

import pytest
import numpy as np
import pyqtgraph as pg

from acq4.util.imaging import sequencer
from acq4.util.imaging.sequencer import (
    _reduce_knots,
    _runup_bounds,
    _stepped_z_stack,
    acquire_z_stack,
    approach_depth,
    estimate_swept_frame_depths,
    calculate_hysteresis,
    commanded_depths,
    enforce_linear_z_stack,
    plan_z_stack,
    select_planes,
    stamp_z_stack_planes,
)
from acq4.devices.Stage import OutOfLimitsError, Stage
from coorx import SRT3DTransform


class MockFrame:
    def __init__(self, depth, data=None):
        self.depth = depth
        seed = depth if data is None else data
        # cast back to uint8: a fractional seed would otherwise produce a float array,
        # which ssim refuses to compare without an explicit data_range
        self._data = (np.ones((10, 10), dtype=np.uint8) * 10 * seed).astype(np.uint8)

    def globalTransform(self):
        return SRT3DTransform(offset=(0, 0, self.depth))

    def addInfo(self, transform):
        self.depth = transform.as_affine().offset[2]

    def __repr__(self):
        return f"<MockFrame depth={self.depth}>"

    def data(self):
        return self._data


# The plane count must be a function of abs(stop - start) and abs(step) and nothing else.

SPANS = [
    (0.0, 40e-6, 1e-6),  # whole multiple, at the origin
    (1.0334e-3, 1.0734e-3, 1e-6),  # the same span, a millimetre down
    (1.0334e-3, 1.0334e-3 + 40.6e-6, 1e-6),  # fractional leftover
    (5e-3, 5.0005e-3, 0.5e-6),  # sub-micron steps
    (2.34567e-3, 2.33567e-3, 1e-6),  # descending
]


def test_commanded_depths_count_is_independent_of_absolute_depth():
    """A whole-multiple span asks for the same planes wherever the stack sits."""
    rng = np.random.default_rng(20260918)
    step = 1e-6
    for _ in range(2000):
        base = rng.uniform(0, 10e-3)
        n_steps = int(rng.integers(1, 500))
        assert len(commanded_depths(base, base + n_steps * step, step)) == n_steps + 1


def test_commanded_depths_whole_multiple_survives_a_few_thousand_planes():
    """The float slack is relative to the step count, so it still covers big stacks."""
    start, step = 1.0334e-3, 1e-7
    for n_steps in (5_000, 20_000, 50_000):
        assert len(commanded_depths(start, start + n_steps * step, step)) == n_steps + 1


@pytest.mark.parametrize("start,stop,step", SPANS)
def test_commanded_depths_count_is_independent_of_direction(start, stop, step):
    down = commanded_depths(stop, start, step)
    assert len(down) == len(commanded_depths(start, stop, step))
    # ...and the reversed stack really does travel the other way
    assert down[0] == stop
    assert np.all(np.diff(down) * (start - stop) >= 0)


@pytest.mark.parametrize("start,stop,step", SPANS)
def test_commanded_depths_ignores_the_sign_of_step(start, stop, step):
    assert commanded_depths(start, stop, -step) == pytest.approx(commanded_depths(start, stop, step))


def test_commanded_depths_fractional_span_never_overshoots_stop():
    """A leftover of more than half a step is dropped, not rounded up into a plane."""
    start, step = 1.0334e-3, 1e-6
    stop = start + 40.6 * step
    depths = commanded_depths(start, stop, step)
    assert len(depths) == 41
    assert depths[-1] == pytest.approx(start + 40 * step)
    assert depths[-1] < stop
    down = commanded_depths(stop, start, step)
    assert len(down) == 41
    assert down[-1] > start


@pytest.mark.parametrize("start,stop,step", SPANS)
def test_commanded_depths_begins_at_start_and_ends_at_or_before_stop(start, stop, step):
    depths = commanded_depths(start, stop, step)
    assert depths[0] == start
    travelled = abs(depths[-1] - start)
    span = abs(stop - start)
    assert travelled <= span + abs(step) * 1e-6  # never past stop
    assert travelled > span - abs(step)  # and no further short than one partial step


def test_commanded_depths_bounds_closer_than_one_step_still_ask_for_the_start_plane():
    assert commanded_depths(1e-3, 1e-3 + 0.4e-6, 1e-6) == pytest.approx([1e-3])
    assert commanded_depths(1e-3, 1e-3, 1e-6) == pytest.approx([1e-3])


def test_commanded_depths_zero_step_raises():
    with pytest.raises(ValueError, match="Z stack step size must be non-zero."):
        commanded_depths(0.0, 1.0, 0.0)


# A 10 ms exposure and a 100 Hz focus controller: both speed budgets then land in whole
# hundreds, keeping the expected speeds below readable by hand.
RIG = dict(exposure=10e-3, position_fps=100.0)


@pytest.mark.parametrize("mode", ["fast", "stepped"])
def test_plan_z_stack_explicit_mode_is_never_overridden(mode):
    """Only "auto" is decided for. Both spans below would go the other way under "auto"."""
    for start, stop, step, max_dz in [(0.0, 40e-6, 1e-6, 5e-6), (0.0, 1e-3, 50e-6, 1e-7)]:
        plan = plan_z_stack(start, stop, step, mode=mode, max_dz_per_frame=max_dz, **RIG)
        assert plan.mode == mode


def test_plan_z_stack_auto_prefers_fast_for_an_ordinary_stack():
    # 40 um at 1 um steps: 41 planes, ~41 s stepped, against a sweep of well under a
    # second at the 50 um/s the sampling budget allows.
    plan = plan_z_stack(0.0, 40e-6, 1e-6, **RIG)
    assert plan.mode == "fast"


def test_plan_z_stack_auto_prefers_stepped_when_the_sweep_would_crawl():
    # 21 planes over a millimetre, but a 0.1 um blur budget holds the sweep to 10 um/s:
    # 100 s swept against 21 s stepped.
    plan = plan_z_stack(0.0, 1e-3, 50e-6, max_dz_per_frame=1e-7, **RIG)
    assert plan.mode == "stepped"
    # ...and raising the per-step cost past the sweep's is enough to flip it back
    assert plan_z_stack(0.0, 1e-3, 50e-6, max_dz_per_frame=1e-7, est_time_per_step=10.0, **RIG).mode == "fast"


def test_plan_z_stack_speed_is_capped_by_the_blur_budget():
    # blur: 0.2 um x 100 fps = 20 um/s. sampling: 50 um x 100 fps / 2 = 2.5 mm/s.
    plan = plan_z_stack(0.0, 1e-3, 50e-6, mode="fast", max_dz_per_frame=0.2e-6, **RIG)
    assert plan.speed == pytest.approx(0.2e-6 * 100.0)


def test_plan_z_stack_speed_is_capped_by_the_sampling_budget():
    # sampling: 1 um x 100 fps / 2 = 50 um/s. blur: 5 um x 100 fps = 500 um/s.
    plan = plan_z_stack(0.0, 40e-6, 1e-6, mode="fast", **RIG)
    assert plan.speed == pytest.approx(1e-6 * 100.0 / 2.0)
    # asking for more frames per plane is what slows it further
    slower = plan_z_stack(0.0, 40e-6, 1e-6, mode="fast", frames_per_step=4.0, **RIG)
    assert slower.speed == pytest.approx(plan.speed / 2)


def test_plan_z_stack_sampling_budget_uses_the_slower_of_the_two_rates():
    """A frame the focus controller cannot place in depth is not another sample."""
    slow_stage = plan_z_stack(0.0, 40e-6, 1e-6, mode="fast", exposure=1e-3, position_fps=50.0)
    assert slow_stage.speed == pytest.approx(1e-6 * 50.0 / 2.0)
    slow_camera = plan_z_stack(0.0, 40e-6, 1e-6, mode="fast", exposure=20e-3, position_fps=1000.0)
    assert slow_camera.speed == pytest.approx(1e-6 * 50.0 / 2.0)


def test_plan_z_stack_infinite_blur_budget_leaves_the_sampling_budget_alone():
    plan = plan_z_stack(0.0, 40e-6, 1e-6, mode="fast", max_dz_per_frame=np.inf, **RIG)
    assert plan.speed == pytest.approx(1e-6 * 100.0 / 2.0)


@pytest.mark.parametrize("mode", ["auto", "fast", "stepped"])
@pytest.mark.parametrize("start,stop,step", SPANS)
def test_plan_z_stack_depths_hold_the_frame_count_invariant(mode, start, stop, step):
    """len(plan.depths) is the stack's frame count, and depends on span and step only."""
    plan = plan_z_stack(start, stop, step, mode=mode, **RIG)
    assert np.array_equal(plan.depths, commanded_depths(start, stop, step))
    # same span and step, placed a millimetre away and swept the other direction
    offset = plan_z_stack(start + 1e-3, stop + 1e-3, step, mode=mode, **RIG)
    reversed_ = plan_z_stack(stop, start, step, mode=mode, **RIG)
    assert len(offset.depths) == len(plan.depths) == len(reversed_.depths)


def test_plan_z_stack_resolves_auto_so_nothing_downstream_has_to():
    assert plan_z_stack(0.0, 40e-6, 1e-6, **RIG).mode in ("fast", "stepped")


def test_plan_z_stack_rejects_an_unknown_mode():
    with pytest.raises(ValueError, match="Unknown acquisition mode"):
        plan_z_stack(0.0, 40e-6, 1e-6, mode="stepwise", **RIG)


def test_plan_z_stack_zero_step_raises():
    with pytest.raises(ValueError, match="Z stack step size must be non-zero."):
        plan_z_stack(0.0, 40e-6, 0.0, **RIG)


def test_enforce_linear_z_stack_empty_frames():
    with pytest.raises(ValueError, match="Insufficient frames to have one frame per step."):
        enforce_linear_z_stack([], 0.0, 10.0, 1.0)


def test_enforce_linear_z_stack_single_frame():
    # the only frame is far outside [start, stop], so nothing survives the range trim
    frames = [MockFrame(5.0)]
    with pytest.raises(ValueError, match="Insufficient frames to have one frame per step."):
        enforce_linear_z_stack(frames, 0.0, 0.8, 1.0)


def test_enforce_linear_z_stack_zero_step():
    frames = [MockFrame(0.0), MockFrame(1.0)]
    with pytest.raises(ValueError, match="Z stack step size must be non-zero."):
        enforce_linear_z_stack(frames, 0.0, 10.0, 0.0)


def test_enforce_linear_z_stack_insufficient_frames_exact_steps():
    frames = [MockFrame(0.0)]
    with pytest.raises(ValueError, match="Insufficient frames to have one frame per step."):
        enforce_linear_z_stack(frames, 0.0, 2.0, 1.0) # expects 3 frames (0, 1, 2)


def test_enforce_linear_z_stack_frames_at_one_depth_still_fill_every_plane():
    """Three frames sharing a depth fill three planes rather than being refused."""
    frames = [MockFrame(0.0, data=1), MockFrame(0.0, data=1), MockFrame(0.0, data=1)]
    result = enforce_linear_z_stack(frames, 0.0, 1.0, 0.5)  # expects 3 frames (0, 0.5, 1.0)
    assert len(result) == 3
    assert len({id(f) for f in result}) == 3


def test_enforce_linear_z_stack_ascending_exact_frames():
    f0, f1, f2 = MockFrame(0.0), MockFrame(1.0), MockFrame(2.0)
    frames = [f0, f1, f2]
    result = enforce_linear_z_stack(frames, 0.0, 2.0, 1.0)
    assert result == [f0, f1, f2]


def test_enforce_linear_z_stack_descending_exact_frames():
    f0, f1, f2 = MockFrame(2.0), MockFrame(1.0), MockFrame(0.0)
    frames = [f0, f1, f2] # Input order shouldn't matter as it sorts by depth
    result = enforce_linear_z_stack(frames, 2.0, 0.0, -1.0)
    # Expected depths are 2.0, 1.0, 0.0. searchsorted will pick corresponding frames.
    assert result == [f2, f1, f0]


def test_enforce_linear_z_stack_ascending_excess_frames():
    f0, f0_5, f1, f1_5, f2 = MockFrame(0.0), MockFrame(0.5), MockFrame(1.0), MockFrame(1.5), MockFrame(2.0)
    frames = [f0, f0_5, f1, f1_5, f2]
    result = enforce_linear_z_stack(frames, 0.0, 2.0, 1.0) # expects 0, 1, 2
    assert result == [f0, f1, f2]


def test_enforce_linear_z_stack_descending_excess_frames():
    f0, f0_5, f1, f1_5, f2 = MockFrame(0.0), MockFrame(0.5), MockFrame(1.0), MockFrame(1.5), MockFrame(2.0)
    frames = [f2, f1_5, f1, f0_5, f0] # Sorted by depth: f0, f0_5, f1, f1_5, f2
    result = enforce_linear_z_stack(frames, 2.0, 0.0, -1.0) # expects 2, 1, 0
    assert result == [f0, f1, f2]


def test_enforce_linear_z_stack_ascending_grouped_depths():
    # Simulates stage updating z infrequently
    f0a, f0b = MockFrame(0.0, data=1), MockFrame(0.0, data=2) # different data
    f1a, f1b = MockFrame(1.0, data=11), MockFrame(1.0, data=12)
    f2a, f2b = MockFrame(2.0, data=21), MockFrame(2.0, data=22)
    frames = [f0a, f0b, f1a, f1b, f2a, f2b]
    result = enforce_linear_z_stack(frames, 0.0, 2.0, 1.0)
    # Which frame fills each depth is not pinned, only the depths themselves.
    assert len(result) == 3
    assert result[0].depth == 0.0
    assert result[1].depth == 1.0
    assert result[2].depth == 2.0


def test_enforce_linear_z_stack_descending_grouped_depths():
    f0a, f0b = MockFrame(0.0, data=1), MockFrame(0.0, data=2)
    f1a, f1b = MockFrame(1.0, data=11), MockFrame(1.0, data=12)
    f2a, f2b = MockFrame(2.0, data=21), MockFrame(2.0, data=22)
    frames = [f2b, f2a, f1b, f1a, f0b, f0a] # Order doesn't matter for sorting
    result = enforce_linear_z_stack(frames, 2.0, 0.0, -1.0) # expects 2, 1, 0
    assert len(result) == 3
    assert result[0].depth == 0.0
    assert result[1].depth == 1.0
    assert result[2].depth == 2.0


def test_enforce_linear_z_stack_start_equals_stop():
    f0 = MockFrame(0.0)
    frames = [f0, MockFrame(0.1), MockFrame(-0.1)]
    result = enforce_linear_z_stack(frames, 0.0, 0.0, 1.0) # expects 1 frame at 0.0
    assert len(result) == 1
    assert abs(result[0].depth) <= 0.10001


def test_enforce_linear_z_stack_non_exact_step_multiple():
    # (stop - start) % step != 0
    # start=0, stop=2.5, step=1.0 => expected depths [0.0, 1.0, 2.0]
    f0, f1, f2, f2_4 = MockFrame(0.0), MockFrame(1.0), MockFrame(2.0), MockFrame(2.4)
    frames = [f0, f1, f2, f2_4]
    result = enforce_linear_z_stack(frames, 0.0, 2.5, 1.0)
    assert len(result) == 3
    assert abs(result[0].depth - 0.0) < 0.1
    assert abs(result[1].depth - 1.0) < 0.1
    assert abs(result[2].depth - 2.0) < 0.5  # The closest to 2.0 could be either f2 or f2_4

    # start=0, stop=2.0, step=0.8 => expected depths [0.0, 0.8, 1.6]
    f0, f0_7, f0_9, f1_5, f1_7, f2_0 = MockFrame(0.0), MockFrame(0.7), MockFrame(0.9), MockFrame(1.5), MockFrame(1.7), MockFrame(2.0)
    frames = [f0, f0_7, f0_9, f1_5, f1_7, f2_0]
    result = enforce_linear_z_stack(frames, 0.0, 2.0, 0.8)
    assert len(result) == 3
    assert abs(result[0].depth - 0.0) < 0.1
    assert abs(result[1].depth - 0.8) < 0.2
    assert abs(result[2].depth - 1.6) < 0.4


def test_enforce_linear_z_stack_pruning_identical_frames():
    f0a = MockFrame(0.0, data=1)
    f0b = MockFrame(0.0, data=1) # Identical depth
    f1a = MockFrame(1.0, data=2)
    f1b = MockFrame(1.0, data=2) # Identical depth
    f2  = MockFrame(2.0, data=3)
    frames = [f0a, f0b, f1a, f1b, f2]
    result = enforce_linear_z_stack(frames, 0.0, 2.0, 1.0)
    assert len(result) == 3
    assert result[0].depth == 0.0
    assert result[1].depth == 1.0
    assert result[2].depth == 2.0


def test_enforce_linear_z_stack_frames_not_perfectly_on_expected_depths():
    """Frames inside [start, stop] keep their own measured depth; frames outside it by more
    than the 5e-7 m end tolerance are discarded, and too few left raises."""
    # near misses inside the range are accepted, one per expected depth
    f_0, f_0_95, f_2 = MockFrame(0.0), MockFrame(0.95), MockFrame(2.0)
    result = enforce_linear_z_stack([f_0, f_0_95, f_2], 0.0, 2.0, 1.0) # expects 0, 1, 2
    assert result == [f_0, f_0_95, f_2]
    assert [f.depth for f in result] == [0.0, 0.95, 2.0]

    # frames just past the ends, but within the end tolerance, still count as in-range
    f_low, f_mid, f_high = MockFrame(-4e-7), MockFrame(0.95), MockFrame(2.0 + 4e-7)
    result = enforce_linear_z_stack([f_low, f_mid, f_high], 0.0, 2.0, 1.0)
    assert result == [f_low, f_mid, f_high]

    # well outside the range: only 0.9 survives the trim, fewer than the three depths
    frames = [MockFrame(-0.1), MockFrame(0.9), MockFrame(2.1)]
    with pytest.raises(ValueError, match="Insufficient frames to have one frame per step."):
        enforce_linear_z_stack(frames, 0.0, 2.0, 1.0)


def test_enforce_linear_z_stack_descending_frames_not_perfectly_on_expected_depths():
    """Same contract for a descending sweep: start/stop are sorted internally, so the
    result is still ascending and the range trim behaves the same."""
    # near misses inside the range are accepted
    f_0, f_0_95, f_2 = MockFrame(0.0), MockFrame(0.95), MockFrame(2.0)
    frames = [f_2, f_0_95, f_0] # depths sorted: 0.0, 0.95, 2.0
    result = enforce_linear_z_stack(frames, 2.0, 0.0, -1.0) # expects 2, 1, 0
    assert result == [f_0, f_0_95, f_2]
    assert [f.depth for f in result] == [0.0, 0.95, 2.0]

    # well outside the range: only 0.9 survives the trim, fewer than the three depths
    frames = [MockFrame(2.1), MockFrame(0.9), MockFrame(-0.1)]
    with pytest.raises(ValueError, match="Insufficient frames to have one frame per step."):
        enforce_linear_z_stack(frames, 2.0, 0.0, -1.0)

def test_enforce_linear_z_stack_stop_start_step_consistency():
    # (stop - start) % step == 0, so stop should be inclusive
    f0, f1, f2 = MockFrame(0.0), MockFrame(1.0), MockFrame(2.0)
    frames = [f0, f1, f2]
    result = enforce_linear_z_stack(frames, 0.0, 2.0, 1.0) # expects 0, 1, 2
    assert result == [f0, f1, f2]

    f0, f1, f2, f3 = MockFrame(0.0), MockFrame(0.5), MockFrame(1.0), MockFrame(1.5)
    frames = [f0, f1, f2, f3]
    result = enforce_linear_z_stack(frames, 0.0, 1.5, 0.5) # expects 0, 0.5, 1.0, 1.5
    assert result == [f0, f1, f2, f3]

def test_enforce_linear_z_stack_descending_stop_start_step_consistency():
    f0, f1, f2 = MockFrame(2.0), MockFrame(1.0), MockFrame(0.0)
    frames = [f0, f1, f2] # sorted by depth: f2, f1, f0
    result = enforce_linear_z_stack(frames, 2.0, 0.0, -1.0) # expects 2, 1, 0
    assert result == [f2, f1, f0]

    f0, f1, f2, f3 = MockFrame(1.5), MockFrame(1.0), MockFrame(0.5), MockFrame(0.0)
    frames = [f0, f1, f2, f3] # sorted by depth: f3, f2, f1, f0
    result = enforce_linear_z_stack(frames, 1.5, 0.0, -0.5) # expects 1.5, 1.0, 0.5, 0.0
    assert result == [f3, f2, f1, f0]

fi_0_0 = MockFrame(0.0, data=0)
fi_0_1 = MockFrame(0.1, data=1)
fi_0_2 = MockFrame(0.2, data=2)
fi_0_3 = MockFrame(0.3, data=3)
fi_0_4 = MockFrame(0.4, data=4)
fi_0_5 = MockFrame(0.5, data=5)

def test_enforce_linear_z_stack_complex_case_1():
    frames = [fi_0_0, fi_0_1, fi_0_2, fi_0_3, fi_0_4, fi_0_5]
    start, stop, step = 0.0, 0.5, 0.1
    # Five whole steps, so six planes, though (0.5 - 0.0) % 0.1 is not 0 in float.
    result = enforce_linear_z_stack(frames, start, stop, step)
    assert len(result) == 6
    for i, frame in enumerate(result):
        assert abs(frame.depth - i*0.1) < 0.01

def test_enforce_linear_z_stack_complex_case_2_descending():
    frames = [fi_0_5, fi_0_4, fi_0_3, fi_0_2, fi_0_1, fi_0_0] # reverse order input
    start, stop, step = 0.5, 0.0, -0.1  # same five steps, swept downward
    result = enforce_linear_z_stack(frames, start, stop, step)
    assert len(result) == 6
    for i, frame in enumerate(result):
        assert abs(frame.depth - i*0.1) < 0.01

def test_enforce_linear_z_stack_duplicate_depths_different_data_selection():
    f0_a = MockFrame(0.0, data=1)
    f0_b = MockFrame(0.0, data=2) # different data, same depth
    f1 = MockFrame(1.0, data=3)
    frames = [f0_a, f0_b, f1]
    result = enforce_linear_z_stack(frames, 0.0, 1.0, 1.0) # expects 0.0, 1.0
    assert len(result) == 2
    assert result[0].depth == 0.0
    assert result[1].depth == 1.0

    frames_rev = [f1, f0_b, f0_a] # Test different input order
    result_rev = enforce_linear_z_stack(frames_rev, 0.0, 1.0, 1.0)
    assert len(result_rev) == 2
    assert result_rev[0].depth == 0.0
    assert result_rev[1].depth == 1.0

fi_0 = MockFrame(0.0)
fi_1 = MockFrame(1.0)
fi_2 = MockFrame(2.0)
fi_3 = MockFrame(3.0)
fi_4 = MockFrame(4.0)

def test_enforce_linear_z_stack_more_frames_than_steps_issue_scenario():
    # start=0, stop=2, step=1. Frames at 0,1,2,3,4.
    frames = [fi_0, fi_1, fi_2, fi_3, fi_4]
    result = enforce_linear_z_stack(frames, 0.0, 2.0, 1.0)
    assert len(result) == 3
    # Which frames the assignment picks is not pinned, only their order and coverage.
    depths = [f.depth for f in result]
    assert depths == sorted(depths)
    assert min(depths) <= 0.1
    assert max(depths) >= 1.9

def test_enforce_linear_z_stack_more_frames_than_steps_issue_scenario_desc():
    # start=2, stop=0, step=-1. Frames at 0,1,2,3,4.
    frames = [fi_4, fi_3, fi_2, fi_1, fi_0] # sorted by depth: fi_0, fi_1, fi_2, fi_3, fi_4
    result = enforce_linear_z_stack(frames, 2.0, 0.0, -1.0)
    assert len(result) == 3
    depths = [f.depth for f in result]
    assert depths == sorted(depths)  # sorted internally, so still ascending
    assert min(depths) <= 0.1
    assert max(depths) >= 1.9

def test_enforce_linear_z_stack_start_stop_step_float_precision():
    f1 = MockFrame(0.1)
    f2 = MockFrame(0.2)
    f3 = MockFrame(0.30000000000000004) # numpy.arange(0.1, 0.3+0.1, 0.1) can produce this
    frames = [f1,f2,f3]
    # (0.3 - 0.1) % 0.1 is 0.0999999..., not 0.
    result = enforce_linear_z_stack(frames, 0.1, 0.3, 0.1)
    assert len(result) == 3
    assert abs(result[0].depth - 0.1) < 0.01
    assert abs(result[1].depth - 0.2) < 0.01
    assert abs(result[2].depth - 0.3) < 0.01


def test_calculate_hysteresis_forward():
    stack = [fi_0_0, fi_0_1, fi_0_2, fi_0_3, fi_0_4]
    center = fi_0_1
    assert np.allclose(calculate_hysteresis(stack, center), -0.1)


def test_calculate_hysteresis_backwards():
    stack = [fi_0_4, fi_0_3, fi_0_2, fi_0_1, fi_0_0]
    center = fi_0_3
    assert np.allclose(calculate_hysteresis(stack, center), 0.1)


def test_negative_hysteresis_forward():
    stack = [fi_0_0, fi_0_1, fi_0_2, fi_0_3, fi_0_4]
    center = fi_0_3
    assert np.allclose(calculate_hysteresis(stack, center), 0.1)


def test_negative_hysteresis_backwards():
    stack = [fi_0_4, fi_0_3, fi_0_2, fi_0_1, fi_0_0]
    center = fi_0_1
    assert np.allclose(calculate_hysteresis(stack, center), -0.1)


def test_calculate_hysteresis_no_hysteresis():
    stack = [fi_0_0, fi_0_1, fi_0_2, fi_0_3, fi_0_4]
    center = fi_0_2
    assert np.allclose(calculate_hysteresis(stack, center), 0.0)


def test_calculate_hysteresis_nearby_frames():
    stack = [fi_0_0, fi_0_1, fi_0_2, fi_0_3, fi_0_4]
    center = MockFrame(1, data=1.1)
    assert np.allclose(calculate_hysteresis(stack, center, 0.5), -0.1)

    stack = [fi_0_4, fi_0_3, fi_0_2, fi_0_1, fi_0_0]
    center = MockFrame(1, data=0.9)
    assert np.allclose(calculate_hysteresis(stack, center, 0.5), -0.1)


def test_calculate_hysteresis_empty_stack():
    stack = []
    center = MockFrame(1, data=0)
    with pytest.raises(ValueError, match="Stack is empty"):
        calculate_hysteresis(stack, center)


def test_calculate_hysteresis_unreasonable_data():
    stack = [fi_0_0, fi_0_1, fi_0_2, fi_0_3, fi_0_4]
    center = MockFrame(2, data=100)
    with pytest.raises(ValueError, match="Center frame does not match any frame in the stack"):
        calculate_hysteresis(stack, center)


class InfoFrame:
    """Minimal frame stand-in that records info written via addInfo."""
    def __init__(self, depth=0.0, xform=None):
        self._info = {}
        self._depth = depth
        self._xform = xform

    def globalTransform(self):
        if self._xform is not None:
            return self._xform
        return SRT3DTransform(offset=(0, 0, self._depth))

    def addInfo(self, info=None, **kwargs):
        if info is not None:
            self._info.update(info)
        self._info.update(kwargs)

    def info(self):
        return self._info


def test_stamp_z_stack_planes_records_surface_depth_on_all_frames():
    frames = [InfoFrame(), InfoFrame(), InfoFrame()]
    stamp_z_stack_planes(frames, 1e-6, -1.5e-4)
    for f in frames:
        assert f.info()["surfaceDepth"] == -1.5e-4


def test_stamp_z_stack_planes_stores_none_surface_depth_when_unset():
    frames = [InfoFrame()]
    stamp_z_stack_planes(frames, 1e-6, None)
    assert frames[0].info()["surfaceDepth"] is None


def test_stamp_z_stack_planes_empty_frames_is_noop():
    stamp_z_stack_planes([], 1e-6, -1.5e-4)  # must not raise


def test_stamp_z_stack_planes_writes_the_transform_and_metadata_together():
    """One addInfo per frame, carrying both the transform and the metadata."""
    frame = InfoFrame()
    stamp_z_stack_planes([frame], 2e-6, -1.5e-4)
    info = frame.info()
    assert set(info) == {"transform", "surfaceDepth"}
    # the z column now measures one plane-to-plane step
    assert np.linalg.norm(info["transform"].matrix[:, 2]) == pytest.approx(2e-6)


def test_stamp_z_stack_planes_signs_the_z_step_as_it_is_given():
    """A descending stack steps in -z, so its z column must too."""
    frame = InfoFrame()
    stamp_z_stack_planes([frame], -2e-6, None)
    assert frame.info()["transform"].matrix[2, 2] == pytest.approx(-2e-6)


def test_stamp_z_stack_planes_leaves_the_lateral_scale_alone():
    """Only the z column is rewritten: the camera's pixel size rides on x and y."""
    frame = InfoFrame(xform=SRT3DTransform(scale=(6.5e-6, 6.5e-6, 1.0)))
    stamp_z_stack_planes([frame], 2e-6, None)
    m = np.asarray(frame.info()["transform"].matrix)
    assert np.linalg.norm(m[:, 0]) == pytest.approx(6.5e-6)
    assert np.linalg.norm(m[:, 1]) == pytest.approx(6.5e-6)
    assert m[2, 2] == pytest.approx(2e-6)


def test_stamp_z_stack_planes_replaces_an_existing_z_scale_rather_than_compounding_it():
    """The z column is normalised first, so whatever scale the device carried is not a
    factor in the step that comes out."""
    frame = InfoFrame(xform=SRT3DTransform(scale=(1.0, 1.0, 1e-3)))
    stamp_z_stack_planes([frame], 2e-6, None)
    assert frame.info()["transform"].matrix[2, 2] == pytest.approx(2e-6)


def test_stamp_z_stack_planes_is_idempotent():
    """acquire_z_stack stamps once, but the step must not compound if it ever stamps twice."""
    frame = InfoFrame()
    stamp_z_stack_planes([frame], 2e-6, None)
    once = np.asarray(frame.info()["transform"].matrix)[:, 2].copy()
    stamp_z_stack_planes([InfoFrame(xform=frame.info()["transform"])], 2e-6, None)
    stamp_z_stack_planes([frame], 2e-6, None)
    assert np.asarray(frame.info()["transform"].matrix)[:, 2] == pytest.approx(once)


def test_stamp_z_stack_planes_keeps_the_transforms_z_direction():
    """The magnitude comes from z_step; the direction is the device's own.

    They are the same axis for an untilted objective, which is the case the stack's
    'frame i sits i steps along the first transform' contract assumes.
    """
    frame = InfoFrame(xform=SRT3DTransform(angle=30, axis=(1, 0, 0)))
    stamp_z_stack_planes([frame], 2e-6, None)
    z = np.asarray(frame.info()["transform"].matrix)[:, 2].ravel()[:3]
    assert np.linalg.norm(z) == pytest.approx(2e-6), "the step is 2 um along the device's z"
    assert z[2] == pytest.approx(2e-6 * np.cos(np.radians(30))), "which is not 2 um of global z"


class MockFocusDevice:
    hysteresisCorrection = 0

    #: m/s^2, the order of magnitude of a real piezo focus axis.
    acceleration = 0.05

    #: Device z, in metres, for the run-up limit check. Deliberately not the imager's
    #: focus depth: acquire_z_stack offsets the stage position by the change in focus
    #: depth, and equal values would not exercise that mapping.
    stage_z = -0.4e-3

    #: Device-coordinate z limits, or None for no limit.
    limits = (None, None)

    def _interpretSpeed(self, speed):
        return 1e-4

    # Borrowed, not reimplemented, so the timeouts under test are the real ones.
    expectedMoveDuration = Stage.expectedMoveDuration

    def globalPosition(self):
        return 0.0, 0.0, self.stage_z

    def checkGlobalLimits(self, globalPos, linear):
        lo, hi = self.limits
        z = globalPos[2]
        if (lo is not None and z < lo) or (hi is not None and z > hi):
            raise OutOfLimitsError(f"{z} outside {self.limits}")


class MockImager:
    """Just enough imager to drive _stepped_z_stack."""

    def __init__(self, depth=0.0):
        self.logger = None
        self._depth = depth
        self._focusDev = MockFocusDevice()
        #: (depth, speed, name) of every focus move commanded, in order.
        self.moves = []

    def getFocusDevice(self):
        return self._focusDev

    def getFocusDepth(self):
        return self._depth

    def setFocusDepth(self, depth, speed, name=None):
        self.moves.append((depth, speed, name))
        self._depth = depth
        return _DoneMove()

    def ensureRunning(self, ensureFreshFrames=False):
        return contextlib.nullcontext()

    def acquireFrames(self, n=1):
        return _DoneFrames([MockFrame(self._depth) for _ in range(n)])


class _DoneMove:
    def wait(self, timeout=None):
        return None


class _DoneFrames:
    def __init__(self, frames):
        self._frames = frames

    def wait(self, timeout=None):
        return self._frames


@pytest.mark.parametrize("below,above,step", [(10e-6, 30e-6, 1e-6), (5e-6, 5e-6, 0.5e-6)])
def test_stepped_z_stack_spans_commanded_range_exactly(below, above, step):
    # On millimetre-scale depths with micron steps, an arange endpoint rounds up and
    # appends a frame past *stop*.
    tip = 1.0334e-3
    start, stop = tip - below, tip + above
    frames = _stepped_z_stack(MockImager(depth=start), commanded_depths(start, stop, step), "test")
    assert len(frames) == round((stop - start) / step) + 1
    assert frames[0].depth == pytest.approx(start, abs=1e-12)
    assert frames[-1].depth == pytest.approx(stop, abs=1e-12)


def test_stepped_z_stack_descending_spans_commanded_range_exactly():
    tip = 2.34567e-3
    start, stop, step = tip + 30e-6, tip - 10e-6, 1e-6
    frames = _stepped_z_stack(MockImager(depth=start), commanded_depths(start, stop, step), "test")
    assert len(frames) == 41
    assert frames[0].depth == pytest.approx(start, abs=1e-12)
    assert frames[-1].depth == pytest.approx(stop, abs=1e-12)


def test_stepped_z_stack_matches_fast_path_frame_count():
    # The stepped path is the fast path's fallback: same arguments, same frame count.
    tip = 0.99927e-3
    start, stop, step = tip - 10e-6, tip + 30e-6, 1e-6
    stepped = _stepped_z_stack(MockImager(depth=start), commanded_depths(start, stop, step), "test")
    swept = enforce_linear_z_stack(
        [MockFrame(d) for d in np.linspace(start, stop, 87)], start, stop, step
    )
    assert len(stepped) == len(swept)


# --- the one-shot hysteresis approach. These pin the whole move sequence: how many
# moves, to which depths, in which order.

HYST = 20e-6  # the Stage class default


def _hysteretic_imager(depth):
    imager = MockImager(depth=depth)
    imager.getFocusDevice().hysteresisCorrection = HYST
    return imager


def test_approach_depth_overshoots_a_downward_stack_approached_from_below():
    """Approached from below for a downward stack: go past the plane and come back down."""
    start, stop = 1.02e-3, 1.0e-3  # downward
    imager = _hysteretic_imager(depth=start - 5e-6)  # sitting below the first plane
    approach_depth(imager, start, stop - start, "fast", name="test")
    assert [m[0] for m in imager.moves] == pytest.approx([start + HYST, start])
    assert [m[2] for m in imager.moves] == ["test hysteresis correction", "test"]


def test_approach_depth_overshoots_an_upward_stack_approached_from_above():
    """The same the other way up: undershoot below the first plane, then rise onto it."""
    start, stop = 1.0e-3, 1.02e-3  # upward
    imager = _hysteretic_imager(depth=start + 5e-6)  # sitting above the first plane
    approach_depth(imager, start, stop - start, "fast", name="test")
    assert [m[0] for m in imager.moves] == pytest.approx([start - HYST, start])
    assert [m[2] for m in imager.moves] == ["test hysteresis correction", "test"]


@pytest.mark.parametrize(
    "start,stop,from_depth",
    [
        (1.02e-3, 1.0e-3, 1.02e-3 + 5e-6),  # downward, already above the first plane
        (1.0e-3, 1.02e-3, 1.0e-3 - 5e-6),  # upward, already below it
    ],
)
def test_approach_depth_makes_one_move_when_it_already_arrives_the_right_way(start, stop, from_depth):
    """No correction leg when the approach already arrives in the stack's direction."""
    imager = _hysteretic_imager(depth=from_depth)
    approach_depth(imager, start, stop - start, "fast", name="test")
    assert [m[0] for m in imager.moves] == pytest.approx([start])
    assert [m[2] for m in imager.moves] == ["test"]


@pytest.mark.parametrize("correction,requested", [(HYST, False), (0.0, True)])
def test_approach_depth_makes_one_move_when_there_is_no_correction_to_make(correction, requested):
    """Either the caller declined the correction or the device reports none."""
    start, stop = 1.02e-3, 1.0e-3
    imager = _hysteretic_imager(depth=start - 5e-6)
    imager.getFocusDevice().hysteresisCorrection = correction
    approach_depth(imager, start, stop - start, "fast", hysteresis_correction=requested, name="test")
    assert [m[0] for m in imager.moves] == pytest.approx([start])


def test_approach_depth_is_a_noop_for_a_depth_of_none():
    imager = _hysteretic_imager(depth=1.0e-3)
    approach_depth(imager, None, -1.0, "fast", name="test")
    assert imager.moves == []


def test_stepped_z_stack_makes_exactly_one_move_per_plane():
    """One move per plane and no hysteresis correction: the approach is the caller's."""
    start, stop, step = 1.02e-3, 1.0e-3, 1e-6  # downward
    depths = commanded_depths(start, stop, step)
    imager = _hysteretic_imager(depth=start)
    _stepped_z_stack(imager, depths, "test")
    assert [m[0] for m in imager.moves] == pytest.approx(list(depths))
    assert not any("hysteresis" in m[2] for m in imager.moves)


# --- run-up: parking v^2/2a short of the stack and running the same distance past its
# far end puts both acceleration ramps outside [start, stop].


def test_plan_z_stack_runup_is_the_kinematic_distance_for_the_sweep_speed():
    # sampling budget: 100 um x 100 fps / 2 = 5 mm/s, with the blur budget waived.
    plan = plan_z_stack(0.0, 2e-3, 100e-6, mode="fast", max_dz_per_frame=np.inf, acceleration=0.05, **RIG)
    assert plan.speed == pytest.approx(5e-3)
    assert plan.runup == pytest.approx(sequencer._RUNUP_MARGIN * 5e-3**2 / (2 * 0.05))


def test_plan_z_stack_runup_is_at_least_two_plane_steps():
    plan = plan_z_stack(0.0, 40e-6, 1e-6, mode="fast", acceleration=0.05, exposure=10e-3, position_fps=20.0)
    assert plan.runup == pytest.approx(2e-6)


def test_plan_z_stack_has_no_runup_in_stepped_mode():
    assert plan_z_stack(0.0, 40e-6, 1e-6, mode="stepped", **RIG).runup == 0.0


@pytest.mark.parametrize("acceleration", [0.0, np.inf])
def test_plan_z_stack_runup_without_an_acceleration_is_the_frame_floor(acceleration):
    plan = plan_z_stack(0.0, 40e-6, 1e-6, mode="fast", acceleration=acceleration, **RIG)
    assert plan.runup == pytest.approx(2e-6)


@pytest.mark.parametrize("start,stop", [(1.0e-3, 1.2e-3), (1.2e-3, 1.0e-3)])
def test_runup_bounds_extends_both_ends_along_the_direction_of_travel(start, stop):
    park, overrun = _runup_bounds(MockImager(depth=start), start, stop, 10e-6)
    sign = np.sign(stop - start)
    assert (park, overrun) == pytest.approx((start - sign * 10e-6, stop + sign * 10e-6))


def test_runup_bounds_declines_a_zero_runup_or_a_zero_length_stack():
    assert _runup_bounds(MockImager(depth=0.0), 1.0e-3, 1.2e-3, 0.0) == (1.0e-3, 1.2e-3)
    assert _runup_bounds(MockImager(depth=0.0), 1.0e-3, 1.0e-3, 10e-6) == (1.0e-3, 1.0e-3)


@pytest.mark.parametrize("end", ["park", "overrun"])
def test_runup_bounds_gives_up_both_ends_when_either_would_leave_the_limits(end):
    """Both ends are given up together; running up at one end only would leave the sweep
    asymmetric."""
    start, stop, runup = 1.0e-3, 1.2e-3, 10e-6
    imager = MockImager(depth=start)
    dev = imager.getFocusDevice()
    # Device z runs from stage_z at *start* to stage_z + (stop - start) at *stop*.
    base = dev.stage_z
    if end == "park":
        dev.limits = (base - runup / 2, None)
    else:
        dev.limits = (None, base + (stop - start) + runup / 2)
    assert _runup_bounds(imager, start, stop, runup) == (start, stop)


def test_acquire_z_stack_parks_short_of_the_stack_and_sweeps_past_its_far_end(null_manager):
    start, stop, step = 1.0e-3, 1.2e-3, 50e-6
    imager = SweepingMockImager(start, stop)
    frames = acquire_z_stack(imager, start, stop, step, mode="fast", max_dz_per_frame=np.inf)
    plan = plan_z_stack(
        start, stop, step, mode="fast", max_dz_per_frame=np.inf,
        exposure=0.01, position_fps=100.0, acceleration=MockFocusDevice.acceleration,
    )
    assert plan.runup > 1e-6  # big enough for this to be measuring something
    assert [m[0] for m in imager.moves] == pytest.approx([start - plan.runup, stop + plan.runup])
    # ...and the overshoot changes nothing about what comes back
    assert len(frames) == len(plan.depths) == 5


class TimedFrame(MockFrame):
    """MockFrame with a timestamp and a mutable info dict."""

    def __init__(self, depth, time, data=None):
        super().__init__(depth, data)
        self._time = time
        self._info = {}

    @property
    def time(self):
        return self._time

    def info(self):
        return self._info

    def addInfo(self, transform, time=None):
        super().addInfo(transform)
        if time is not None:
            self._time = time

    def data(self):
        return self._data


def sweep_profile(kind, report_every, rest=6, ramp=40, dt=0.05, v=20e-6, accel_frac=0.25):
    """A sweep the controller only reports every Nth frame, sampled and held.

    Parameters
    ----------
    kind: str
        Velocity profile: "constant", "trapezoid" (accelerate, cruise, decelerate), or
        "accelerating" (constant acceleration throughout, so there is no cruise to fit).
    report_every: int
        Frames per position report. 1 means the controller keeps up with the camera.
    rest: int
        Frames held at rest before and after the move.
    ramp: int
        Frames spent moving.
    dt: float
        Frame interval, seconds.
    v: float
        Cruise velocity, m/s. For "accelerating" this is the velocity reached at the end.
    accel_frac: float
        Share of a trapezoidal move spent accelerating, and the same again decelerating.
        Ignored by the other profiles.

    Returns
    -------
    tuple[list[TimedFrame], np.ndarray, float]
        The frames, their true depths, and the largest gap between reported depths.
    """
    n = 2 * rest + ramp
    times = np.arange(n) * dt
    elapsed = np.clip(times - rest * dt, 0, ramp * dt)
    if kind == "constant":
        true = v * elapsed
    elif kind == "accelerating":
        true = 0.5 * (v / (ramp * dt)) * elapsed ** 2 * 2
    else:
        total = ramp * dt
        up = accel_frac * total
        vel = np.where(elapsed < up, v * elapsed / up,
                       np.where(elapsed > total - up, v * (total - elapsed) / up, v))
        true = np.concatenate(([0.0], np.cumsum(vel[1:] * np.diff(times))))
    held = true[(np.arange(n) // report_every) * report_every]
    frames = [TimedFrame(z, t) for z, t in zip(held, times)]
    return frames, true, float(np.diff(np.unique(held)).max())


def fit_errors(frames, true):
    """Worst error before and after the fit. Asserts monotonicity on the way through."""
    raw = np.array([f.depth for f in frames])
    estimate_swept_frame_depths(frames)
    est = np.array([f.depth for f in frames])
    # solver noise scales with the depths fitted, so the backward-step allowance is relative
    assert np.all(np.diff(est) >= -1e-9 * np.ptp(est)), "estimates must stay monotonic"
    return np.abs(raw - true).max(), np.abs(est - true).max()


@pytest.mark.parametrize("report_every", [3, 5])
def test_estimate_swept_frame_depths_halves_stale_error_at_constant_velocity(report_every):
    frames, true, gap = sweep_profile("constant", report_every)
    raw_err, fit_err = fit_errors(frames, true)
    assert fit_err < raw_err / 2
    assert fit_err < 0.5 * gap


@pytest.mark.parametrize("accel_frac", [0.1, 0.15, 0.25, 0.4])
def test_estimate_swept_frame_depths_handles_a_trapezoidal_sweep(accel_frac):
    """Knots land where the speed changes, so accelerating ends are not assumed away."""
    frames, true, gap = sweep_profile("trapezoid", 3, accel_frac=accel_frac)
    raw_err, fit_err = fit_errors(frames, true)
    assert fit_err < raw_err
    assert fit_err < 0.6 * gap


@pytest.mark.parametrize("report_every", [2, 3, 5])
def test_estimate_swept_frame_depths_handles_acceleration_throughout(report_every):
    """No cruise to fit, a shallow first segment, and a reporting gap that grows."""
    frames, true, gap = sweep_profile("accelerating", report_every)
    raw_err, fit_err = fit_errors(frames, true)
    assert fit_err < raw_err
    assert fit_err < 0.6 * gap


def test_estimate_swept_frame_depths_is_no_worse_when_reports_nearly_keep_up():
    """Reports every other frame leave little staleness. The fit may come out slightly
    worse, but stays bounded by the reporting gap."""
    frames, true, gap = sweep_profile("trapezoid", 2, accel_frac=0.15)
    raw_err, fit_err = fit_errors(frames, true)
    assert fit_err < 1.5 * raw_err
    assert fit_err < 0.75 * gap


def test_estimate_swept_frame_depths_spreads_frames_across_a_plateau():
    """Frames sharing one reported depth must not all come back on that depth."""
    frames, _, _ = sweep_profile("constant", 3)
    estimate_swept_frame_depths(frames)
    est = [f.depth for f in frames]
    reported = len({f for f in est})
    assert reported > len(frames) // 2, "most frames should get their own depth"


def report_aged_sweep(n=120, rest=12, dt=0.02, v=10e-6, seed=1):
    """Return frames of a constant-velocity sweep, and the true depths.

    Each frame's reported depth was issued at a uniformly random time within the
    preceding frame interval."""
    rng = np.random.default_rng(seed)
    times = np.arange(n) * dt
    travel = (n - 2 * rest) * dt
    true = v * np.clip(times - rest * dt, 0, travel)
    issued = np.clip(times - rng.uniform(0.0, dt, n) - rest * dt, 0, travel)
    return [TimedFrame(z, t) for z, t in zip(v * issued, times)], true


def test_estimate_swept_frame_depths_corrects_for_the_age_of_a_report():
    """Fitted depths carry no bias from reports being issued, on average, half a frame
    before the frame that carries them."""
    v, dt = 10e-6, 0.02
    bias = []
    for seed in range(20):
        frames, true = report_aged_sweep(dt=dt, v=v, seed=seed)
        estimate_swept_frame_depths(frames)
        est = np.array([f.depth for f in frames])
        bias.append(np.mean(est[20:-20] - true[20:-20]))
    assert abs(np.mean(bias)) < 0.2 * v * dt / 2


def test_reduce_knots_is_parsimonious_on_a_straight_line():
    t = np.linspace(0, 1, 50)
    z = 3.0 * t
    assert len(_reduce_knots(t, z, 0.01)) == 2


def test_reduce_knots_adds_knots_where_the_curve_bends():
    t = np.linspace(0, 1, 50)
    straight = _reduce_knots(t, 3.0 * t, 0.01)
    bent = _reduce_knots(t, 3.0 * t + 2.0 * t ** 2, 0.01)
    assert len(bent) > len(straight)
    # ...but still far fewer knots than observations.
    assert len(bent) < len(t) // 2


def test_estimate_swept_frame_depths_refuses_a_stack_that_never_moved():
    frames = [TimedFrame(1.0, t * 0.05) for t in range(4)]
    with pytest.raises(ValueError, match="observation"):
        estimate_swept_frame_depths(frames)


def test_estimate_swept_frame_depths_ignores_frames_delivered_late():
    """A late frame and the one bunched behind it are left out of both fits, so neither
    the time line nor the depth curve bends toward them."""
    frames, true, _ = sweep_profile("constant", 1)
    clean = [f.time for f in frames]
    frames[25]._time += 0.04  # delivered 40 ms late...
    frames[26]._time += 0.02  # ...and the next one bunched behind it
    frames[25].depth += 0.8e-6  # stamped with the depth at delivery
    report = {}
    estimate_swept_frame_depths(frames, report=report)
    assert {25, 26} <= set(report["irregular_frames"])
    assert [f.time for f in frames] == pytest.approx(clean, abs=1e-9)
    est = np.array([f.depth for f in frames])
    assert np.abs(est - true).max() < 0.6e-6


def test_estimate_swept_frame_depths_refuses_frame_times_that_do_not_advance():
    frames = [TimedFrame(0.0, 2.0), TimedFrame(1.0, 1.0), TimedFrame(2.0, 0.0)]
    with pytest.raises(ValueError, match="do not advance"):
        estimate_swept_frame_depths(frames)


def test_estimate_swept_frame_depths_fits_frame_times_to_the_frame_index():
    """Corrected times lie on a line of time against list index: close to the raw times
    where the camera kept pace, and smoothing out a batched delivery."""
    frames, _, _ = sweep_profile("constant", 3)
    raw = np.array([f.time for f in frames])
    raw[20:22] = raw[22] - [1e-3, 0.5e-3]  # two frames delivered in a batch with frame 22
    for f, r in zip(frames, raw):
        f._time = r
    report = {}
    fit = estimate_swept_frame_depths(frames, report=report)
    times = np.array([f.time for f in frames])
    index = np.arange(len(frames))
    assert fit["frame_times"] == pytest.approx(times)
    assert np.polyfit(index, times, 1)[0] == pytest.approx(report["frame_interval"])
    assert times == pytest.approx(np.polyval(np.polyfit(index, times, 1), index))
    assert np.abs(np.delete(times - raw, [20, 21])).max() < 5e-3
    assert report["max_time_correction"] > 0.02


def _depths_with_ids(ids):
    """Fitted depths of one standard sweep, with *ids* stamped on the frames (or none)."""
    frames, _, _ = sweep_profile("constant", 3)
    if ids is not None:
        for f, i in zip(frames, ids):
            f.info()["id"] = int(i)
    estimate_swept_frame_depths(frames)
    return np.array([f.depth for f in frames])


def test_estimate_swept_frame_depths_ignores_camera_frame_ids():
    """Frame ids, whether sequential, gapped, tied or absent, do not change the fitted depths."""
    n = len(sweep_profile("constant", 3)[0])
    index = np.arange(n)
    absent = _depths_with_ids(None)
    assert _depths_with_ids(index) == pytest.approx(absent)
    assert _depths_with_ids(index + 7 * (index >= 30)) == pytest.approx(absent)
    assert _depths_with_ids(index // 2) == pytest.approx(absent)


def test_estimate_swept_frame_depths_accepts_tied_frame_ids():
    """A sweep still fits when frames share ids, as MockCamera stamps a batch when its
    acquisition poll falls behind the frame rate."""
    frames, true, gap = sweep_profile("constant", 3)
    for i, f in enumerate(frames):
        f.info()["id"] = i // 2
    raw_err, fit_err = fit_errors(frames, true)
    assert fit_err < raw_err / 2

# --- frames that keep pace with position reports: each report's age at exposure varies,
# so the reported depths jitter about the true motion and are still linearized.

def jittered_sweep(n=80, dt=0.03, v=15e-6, report_dt=0.028, seed=0):
    """A constant-velocity sweep whose controller reports about once per frame, at
    irregular times, so each frame carries a report of random age."""
    rng = np.random.default_rng(seed)
    times = np.arange(n) * dt
    report_t = np.cumsum(rng.uniform(0.5, 1.5, int(n * dt / report_dt) + 10) * report_dt) - report_dt
    true = v * times
    latest = np.searchsorted(report_t, times, side="right") - 1
    reported = v * report_t[np.clip(latest, 0, None)]
    return [TimedFrame(z, t) for z, t in zip(reported, times)], true


def test_estimate_swept_frame_depths_linearizes_when_reports_keep_pace():
    frames, true = jittered_sweep()
    raw = np.array([f.depth for f in frames])
    report = {}
    estimate_swept_frame_depths(frames, report=report)
    est = np.array([f.depth for f in frames])
    assert report["median_frames_per_report"] == 1
    assert report["n_knots"] <= 4
    # Away from the ends, the fit is a straight line at the sweep speed.
    steps = np.diff(est[5:-5])
    assert steps == pytest.approx(steps.mean(), rel=1e-6)
    assert np.abs(est - true)[5:-5].max() < 0.5 * np.abs(raw - true)[5:-5].max()


def test_estimate_swept_frame_depths_refuses_tied_timestamps():
    frames = [TimedFrame(d, 0.0) for d in (1e-6, 1e-6, 2e-6, 2e-6)]
    with pytest.raises(ValueError):
        estimate_swept_frame_depths(frames)


def test_estimate_swept_frame_depths_refuses_frames_without_timestamps():
    class NoTime(TimedFrame):
        @property
        def time(self):
            raise KeyError("time")

    frames = [NoTime(d, 0.0) for d in (1e-6, 1e-6, 2e-6)]
    with pytest.raises(ValueError, match="timestamps"):
        estimate_swept_frame_depths(frames)


def test_enforce_linear_z_stack_still_selects_on_a_one_report_per_frame_rig():
    frames = [TimedFrame(i * 0.1, i * 0.05, data=i + 1) for i in range(6)]
    estimate_swept_frame_depths(frames)
    result = enforce_linear_z_stack(frames, 0.0, 0.5, 0.1)
    assert len({id(f) for f in result}) == 6


def test_enforce_linear_z_stack_fills_every_plane_from_three_resolved_depths():
    """Frames at only three distinct depths still fill all nine planes, each with a
    different acquired frame."""
    depths = [0.0] + [1.0] * 8 + [2.0]
    frames = [TimedFrame(d, i * 0.05, data=i + 1) for i, d in enumerate(depths)]
    result = enforce_linear_z_stack(frames, 0.0, 2.0, 0.25)
    assert len(result) == 9
    assert len({id(f) for f in result}) == 9


# --- select_planes is handed the planes rather than the bounds, so len(depths) is how
# many frames come back.


def _swept(depths, n=None):
    """Frames evenly covering *depths*, in acquisition order, distinct and timestamped."""
    depths = np.asarray(depths, dtype=float)
    n = n or 4 * len(depths)
    return [TimedFrame(d, i * 0.05, data=i + 1) for i, d in enumerate(np.linspace(depths[0], depths[-1], n))]


@pytest.mark.parametrize("n_frames", [6, 7, 23, 60])
def test_select_planes_returns_exactly_one_frame_per_commanded_depth(n_frames):
    """len(depths) is the returned length, whatever the sweep happened to acquire."""
    depths = commanded_depths(0.0, 5e-6, 1e-6)
    result = select_planes(_swept(depths, n_frames), depths)
    assert len(result) == len(depths) == 6


def test_select_planes_returns_planes_in_the_order_it_was_asked_for():
    """Planes come back in the order *depths* gave them, here descending."""
    depths = commanded_depths(5e-6, 0.0, 1e-6)
    assert depths[0] > depths[-1]
    result = select_planes(_swept(depths), depths)
    got = [f.depth for f in result]
    assert got == sorted(got, reverse=True)


def test_select_planes_nearest_keeps_the_frames_own_measured_depths():
    """The nearest-frame path reports where frames were, not where they were wanted."""
    depths = commanded_depths(0.0, 2e-6, 1e-6)
    frames = [MockFrame(d) for d in (0.0, 0.9e-6, 2.0e-6)]
    result = select_planes(frames, depths)
    assert result == frames
    assert [f.depth for f in result] == pytest.approx([0.0, 0.9e-6, 2.0e-6])


def test_select_planes_nearest_never_uses_one_frame_twice():
    """Two planes closest to the same frame: assignment is over the whole stack, so the
    second plane takes the next frame along rather than a duplicate."""
    depths = commanded_depths(0.0, 2e-6, 1e-6)
    frames = [MockFrame(d) for d in (0.95e-6, 1.0e-6, 1.05e-6)]
    result = select_planes(frames, depths)
    assert len({id(f) for f in result}) == 3


def test_select_planes_trims_frames_outside_the_commanded_range():
    """Frames from the settle in and the overshoot out belong to no plane."""
    depths = commanded_depths(0.0, 2e-6, 1e-6)
    inside = [MockFrame(d) for d in (0.0, 1e-6, 2e-6)]
    frames = [MockFrame(-3e-6), *inside, MockFrame(5e-6)]
    assert select_planes(frames, depths) == inside


def test_select_planes_keeps_frames_just_past_the_ends():
    """The end tolerance absorbs reporting jitter rather than trimming honest frames."""
    depths = commanded_depths(0.0, 2e-6, 1e-6)
    frames = [MockFrame(d) for d in (-4e-7, 1e-6, 2e-6 + 4e-7)]
    assert select_planes(frames, depths) == frames


def test_select_planes_trims_a_frame_a_hair_outside_the_end_tolerance():
    """A frame more than ``_RANGE_TOL`` outside the range is dropped, leaving too few
    frames, so selection raises."""
    depths = commanded_depths(0.0, 2e-6, 1e-6)
    # test_select_planes_keeps_frames_just_past_the_ends keeps a frame at -4e-7
    frames = [MockFrame(d) for d in (-6e-7, 1e-6, 2e-6)]
    with pytest.raises(ValueError, match="Insufficient frames"):
        select_planes(frames, depths)


def test_select_planes_rejects_empty_depths():
    with pytest.raises(ValueError, match="no commanded depths"):
        select_planes([MockFrame(0.0)], np.array([]))


def test_select_planes_rejects_too_few_frames_in_range():
    depths = commanded_depths(0.0, 2e-6, 1e-6)
    with pytest.raises(ValueError, match="Insufficient frames to have one frame per step"):
        select_planes([MockFrame(0.0), MockFrame(1e-6)], depths)


def test_select_planes_nearest_fills_deeper_planes_with_deeper_frames():
    """Frames bunched below the stack, which give the assignment ties, still fill the
    planes in depth order."""
    depths = commanded_depths(0.0, 3e-6, 1e-6)
    frames = [MockFrame(d) for d in (-0.4e-6, -0.3e-6, -0.2e-6, 0.5e-6, 2.0e-6)]
    got = [f.depth for f in select_planes(frames, depths)]
    assert got == sorted(got)


def test_select_planes_nearest_ordering_is_free():
    """Depth-ordering the picks costs no accuracy: the total depth error equals the
    minimum over all assignments of those frames."""
    depths = commanded_depths(0.0, 3e-6, 1e-6)
    have = [-0.4e-6, -0.3e-6, -0.2e-6, 0.5e-6, 2.0e-6]
    got = [f.depth for f in select_planes([MockFrame(d) for d in have], depths)]
    best = min(
        sum(abs(d - have[j]) for d, j in zip(depths, pick))
        for pick in itertools.permutations(range(len(have)), len(depths))
    )
    assert sum(abs(d - g) for d, g in zip(depths, got)) == pytest.approx(best)


@pytest.mark.parametrize("descending", [False, True])
def test_select_planes_nearest_is_ascending_over_bursty_frame_spacing(descending):
    """Randomly spaced in-range frames fill the planes monotonically, ascending or descending."""
    rng = np.random.default_rng(20261019)
    base = 70e-6
    depths = base + commanded_depths(0.0, 1.5e-6, 0.5e-6)
    if descending:
        depths = depths[::-1]
    lo, hi = depths.min() - 4e-7, depths.max() + 4e-7
    for _ in range(3000):
        have = np.sort(rng.uniform(lo, hi, len(depths) + rng.integers(0, 4)))
        got = [f.depth for f in select_planes([MockFrame(float(d)) for d in have], depths)]
        assert got == (sorted(got, reverse=True) if descending else sorted(got))


def test_select_planes_rejects_a_sweep_that_doubles_back():
    depths = commanded_depths(0.0, 2e-6, 1e-6)
    frames = [MockFrame(d) for d in (0.0, 2e-6, 1e-6)]
    with pytest.raises(ValueError, match="not in acquisition order"):
        select_planes(frames, depths)


def test_select_planes_ignores_reversals_among_frames_it_does_not_use():
    """Rounding-noise reversals at rest, as the depth fit can leave them."""
    base = 1.05e-3
    depths = base + commanded_depths(0.0, 2e-6, 1e-6)
    noise = [0.0, -1e-16, 1e-16, 0.0]
    moving = (0.5e-6, 1e-6, 1.5e-6, 2e-6)
    frames = [TimedFrame(base + z, 0.05 * i) for i, z in enumerate(list(noise) + list(moving))]
    assert len(select_planes(frames, depths)) == 3


def test_select_planes_accepts_ties_on_a_descending_sweep():
    depths = commanded_depths(2e-6, 0.0, 1e-6)
    frames = [MockFrame(d) for d in (2e-6, 1e-6, 1e-6, 0.0)]
    assert [f.depth for f in select_planes(frames, depths)] == pytest.approx([2e-6, 1e-6, 0.0])


def test_select_planes_leaves_the_nearest_paths_transforms_alone():
    """The nearest-frame path writes nothing onto the frames it picks."""
    depths = commanded_depths(0.0, 2e-6, 1e-6)

    class Tattling(MockFrame):
        writes = 0

        def addInfo(self, transform):
            type(self).writes += 1
            super().addInfo(transform)

    frames = [Tattling(d) for d in (0.0, 1e-6, 2e-6)]
    select_planes(frames, depths)
    assert Tattling.writes == 0


# --- the frame-count invariant end to end: plan_z_stack decides the planes,
# select_planes fills them, and nothing in between changes how many.


@pytest.mark.parametrize("start,stop,step", SPANS)
def test_frame_count_survives_the_seam(start, stop, step):
    """select_planes returns one frame per depth in the plan's ``depths``."""
    plan = plan_z_stack(start, stop, step, exposure=0.01, position_fps=100.0, mode="fast")
    assert len(select_planes(_swept(plan.depths), plan.depths)) == len(plan.depths)


def test_frame_count_survives_a_fallback_from_fast_to_stepped():
    """A failed fast attempt and the stepped retry are handed the same plan."""
    start, stop, step = 1.0334e-3, 1.0334e-3 + 40.6e-6, 1e-6
    plan = plan_z_stack(start, stop, step, exposure=0.01, position_fps=100.0, mode="fast")
    # too few frames survive the range trim for the sweep to fill every plane
    with pytest.raises(ValueError, match="Insufficient frames"):
        select_planes(_swept(plan.depths, 5), plan.depths)
    stepped = _stepped_z_stack(MockImager(depth=start), plan.depths, "test")
    assert len(stepped) == len(plan.depths) == 41


# --- the ascending-output contract: acquire_z_stack sweeps from start toward stop, but
# always hands back frames ordered low-z to high-z.


class StampableFrame(TimedFrame):
    """TimedFrame that keeps the transform and metadata stamp_z_stack_planes writes."""

    def __init__(self, depth, time=0.0, data=None):
        super().__init__(depth, time, data)
        self.surfaceDepth = "unstamped"
        self._xform = None

    def globalTransform(self):
        return super().globalTransform() if self._xform is None else self._xform

    def addInfo(self, transform=None, surfaceDepth="unstamped", time=None):
        if transform is not None:
            self._xform = transform
            self.depth = transform.as_affine().offset[2]
        if time is not None:
            self._time = time
        self.surfaceDepth = surfaceDepth


class MockScope:
    def __init__(self, focus_dev, surface=-1.5e-4):
        self._focus = focus_dev
        self._surface = surface

    def getFocusDevice(self):
        return self._focus

    def getSurfaceDepth(self):
        return self._surface


class SweepingMockImager(MockImager):
    """MockImager that can also serve the fast path: a continuous sweep of the range.

    The sweep runs from the park position before the first plane to the overrun past the
    last, so select_planes receives out-of-range frames to trim.
    """

    def __init__(self, start, stop, n_swept=200, position_fps=100.0):
        super().__init__(depth=start)
        self._focusDev.positionUpdatesPerSecond = position_fps
        self.scopeDev = MockScope(self._focusDev)
        self._n_swept = n_swept
        #: How many frames each fixed-size acquisition asked for, in order.
        self.rest_requests = []

    def getParam(self, name):
        assert name == "exposure"
        return 0.01

    def devicesToReserve(self):
        return []

    def acquireFrames(self, n=None):
        if n is None:
            return _SweepFuture(self)
        self.rest_requests.append(n)
        return _DoneFrames([StampableFrame(self._depth) for _ in range(n)])

    def sweptFrames(self):
        """Return the sweep frames, from the park position to the overrun position (the
        last two commanded moves)."""
        park, overrun = self.moves[-2][0], self.moves[-1][0]
        return [
            StampableFrame(d, time=i * 0.01)
            for i, d in enumerate(np.linspace(park, overrun, self._n_swept))
        ]


class RampingMockImager(SweepingMockImager):
    """SweepingMockImager whose focus accelerates and decelerates inside the commanded range.

    The ramps space frames unevenly in depth, which gives the plane assignment ties.
    """

    #: Share of the sweep spent accelerating, and the same again decelerating.
    ramp = 0.25

    def sweptFrames(self):
        park, overrun = self.moves[-2][0], self.moves[-1][0]
        t = np.linspace(0.0, 1.0, self._n_swept)
        speed = np.where(
            t < self.ramp, t / self.ramp, np.where(t > 1 - self.ramp, (1 - t) / self.ramp, 1.0)
        )
        travelled = np.concatenate(([0.0], np.cumsum(speed[1:] * np.diff(t))))
        travelled /= travelled[-1]
        return [
            StampableFrame(park + (overrun - park) * f, time=i * 0.01)
            for i, f in enumerate(travelled)
        ]


class _SweepFuture:
    def __init__(self, imager):
        self._imager = imager

    def stop(self):
        pass

    def wait(self, timeout=None):
        return self._imager.sweptFrames()


class _NullManager:
    @staticmethod
    def reserveDevices(devices, timeout=None, reserver=None):
        return contextlib.nullcontext()


@pytest.fixture
def null_manager(monkeypatch):
    monkeypatch.setattr(sequencer.Manager, "getManager", lambda: _NullManager())


@pytest.mark.parametrize("mode", ["fast", "stepped"])
def test_acquire_z_stack_returns_ascending_for_a_descending_sweep(null_manager, mode):
    """Swept downward, returned low-z to high-z, in both modes."""
    tip = 1.0334e-3
    start, stop, step = tip + 20e-6, tip - 20e-6, 1e-6
    frames = acquire_z_stack(SweepingMockImager(start, stop), start, stop, step, mode=mode)
    depths = [f.depth for f in frames]
    assert len(depths) == 41
    assert depths == sorted(depths)
    assert depths[0] == pytest.approx(stop, abs=0.25e-6)
    assert depths[-1] == pytest.approx(start, abs=0.25e-6)


@pytest.mark.parametrize("mode", ["fast", "stepped"])
def test_acquire_z_stack_returns_ascending_for_an_ascending_sweep(null_manager, mode):
    """The same order the other way round: direction of travel changes nothing here."""
    tip = 1.0334e-3
    start, stop, step = tip - 20e-6, tip + 20e-6, 1e-6
    frames = acquire_z_stack(SweepingMockImager(start, stop), start, stop, step, mode=mode)
    depths = [f.depth for f in frames]
    assert len(depths) == 41
    assert depths == sorted(depths)


def test_acquire_z_stack_agrees_on_order_between_the_two_modes(null_manager):
    """The order a caller gets does not depend on which path ran."""
    tip = 1.0334e-3
    start, stop, step = tip + 20e-6, tip - 20e-6, 1e-6
    fast = acquire_z_stack(SweepingMockImager(start, stop), start, stop, step, mode="fast")
    stepped = acquire_z_stack(SweepingMockImager(start, stop), start, stop, step, mode="stepped")
    assert [f.depth for f in fast] == pytest.approx([f.depth for f in stepped], abs=0.25e-6)


@pytest.mark.parametrize("start,stop,step", SPANS)
def test_two_stacks_over_identical_bounds_have_the_same_plane_count(null_manager, start, stop, step):
    """Two stacks over the same bounds, forced down different paths, match plane for
    plane."""
    detection = acquire_z_stack(SweepingMockImager(start, stop), start, stop, step, mode="fast")
    classification = acquire_z_stack(SweepingMockImager(start, stop), start, stop, step, mode="stepped")
    assert len(detection) == len(classification) == len(commanded_depths(start, stop, step))


@pytest.mark.parametrize("start,stop", [(1.0354e-3, 1.0314e-3), (1.0314e-3, 1.0354e-3)])
def test_acquire_z_stack_z_scale_points_the_way_the_frames_are_ordered(null_manager, start, stop):
    """The returned list is ascending, so the saved z column is positive whichever way
    the focus travelled."""
    frames = acquire_z_stack(SweepingMockImager(start, stop), start, stop, 1e-6, mode="stepped")
    z_column = frames[0].globalTransform().as_affine().matrix[:, 2]
    assert z_column[2] == pytest.approx(1e-6)


def test_acquire_z_stack_stamps_the_surface_depth_on_every_plane(null_manager):
    start, stop = 1.0354e-3, 1.0314e-3
    frames = acquire_z_stack(SweepingMockImager(start, stop), start, stop, 1e-6, mode="fast")
    assert all(f.surfaceDepth == -1.5e-4 for f in frames)


@pytest.mark.parametrize("mode", ["fast", "stepped"])
def test_acquire_z_stack_debug_records_the_sweep(null_manager, mode):
    start, stop, step = 100e-6, 110e-6, 1e-6
    frames = acquire_z_stack(SweepingMockImager(start, stop), start, stop, step, mode=mode, debug=True)
    debug = frames.debug
    assert debug.mode == mode
    assert len(debug.frame_times) == len(debug.reported_depths) == len(debug.linear_depths)
    assert len(debug.selected_indices) == len(frames)
    assert debug.linear_depths[debug.selected_indices] == pytest.approx([f.depth for f in frames])


@pytest.mark.parametrize("mode", ["fast", "stepped"])
def test_acquire_z_stack_records_its_decisions(null_manager, mode):
    start, stop, step = 100e-6, 110e-6, 1e-6
    frames = acquire_z_stack(SweepingMockImager(start, stop), start, stop, step, mode=mode)
    d = frames.decisions
    assert d["request"]["mode"] == mode
    assert d["plan"]["mode"] == mode
    assert d["plan"]["n_planes"] == len(frames)
    assert d["plan"]["speed"] == min(d["plan"]["blur_speed"], d["plan"]["sampling_speed"])
    assert d["result"]["n_frames"] == len(frames)
    assert ("fast" in d) == (mode == "fast")
    if mode == "fast":
        assert d["fast"]["linearization"]["n_knots"] >= 2
        assert d["fast"]["error"] is None


def test_acquire_z_stack_is_ascending_when_the_sweep_ramps_inside_the_stack(null_manager):
    """The stack is ascending when ramps space the frames unevenly, down to barely more
    swept frames than planes."""
    start, stop, step = 70e-6, 110e-6, 0.5e-6  # 81 planes
    for n_swept in range(97, 210, 7):
        imager = RampingMockImager(start, stop, n_swept=n_swept)
        frames = acquire_z_stack(imager, start, stop, step, mode="fast", fallback_to_stepped=False)
        depths = [f.depth for f in frames]
        assert depths == sorted(depths), f"inverted with {n_swept} swept frames"


def test_acquire_z_stack_trims_the_run_up_and_overrun_frames(null_manager):
    """Frames from the run-up and overrun, outside the commanded range, fill no plane."""
    start, stop, step = 1.0e-3, 1.2e-3, 50e-6
    imager = SweepingMockImager(start, stop)
    frames = acquire_z_stack(imager, start, stop, step, mode="fast", max_dz_per_frame=np.inf)
    acquired = [f.depth for f in imager.sweptFrames()]
    assert min(acquired) < start - sequencer._RANGE_TOL  # the sweep really did overshoot
    assert max(acquired) > stop + sequencer._RANGE_TOL
    depths = [f.depth for f in frames]
    assert min(depths) >= start - sequencer._RANGE_TOL
    assert max(depths) <= stop + sequencer._RANGE_TOL


@pytest.mark.parametrize("position_fps,rest", [(100.0, 3), (40.0, 9), (20.0, 15)])
def test_acquire_z_stack_rests_for_three_report_periods_at_each_end(null_manager, position_fps, rest):
    """Fast mode acquires three position-report periods of resting frames at each end of
    the sweep, not three frames."""
    start, stop, step = 1.0e-3, 1.04e-3, 1e-6
    imager = SweepingMockImager(start, stop, position_fps=position_fps)
    acquire_z_stack(imager, start, stop, step, mode="fast")
    assert imager.rest_requests == [rest, rest]


def test_acquire_z_stack_has_no_debug_unless_asked(null_manager):
    start, stop = 100e-6, 105e-6
    frames = acquire_z_stack(SweepingMockImager(start, stop), start, stop, 1e-6, mode="stepped")
    assert frames.debug is None
