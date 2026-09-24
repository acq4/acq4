import contextlib

import pytest
import numpy as np
import pyqtgraph as pg

from acq4.util.imaging.sequencer import (
    _reduce_knots,
    _stepped_z_stack,
    estimate_swept_frame_depths,
    calculate_hysteresis,
    commanded_depths,
    enforce_linear_z_stack,
    plan_z_stack,
    select_planes,
    stamp_z_stack_planes,
)
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


# The plane count must be a function of abs(stop - start) and abs(step) and nothing
# else. One test per way that can break; two callers already carry defenses against it
# not holding (AutomationDebug/detection.py trims mismatched stacks to the shorter one,
# PipetteTraining._assertStacksAligned raises on them).

SPANS = [
    (0.0, 40e-6, 1e-6),  # whole multiple, at the origin
    (1.0334e-3, 1.0734e-3, 1e-6),  # the same span, a millimetre down
    (1.0334e-3, 1.0334e-3 + 40.6e-6, 1e-6),  # fractional leftover
    (5e-3, 5.0005e-3, 0.5e-6),  # sub-micron steps
    (2.34567e-3, 2.33567e-3, 1e-6),  # descending
]


def test_commanded_depths_count_is_independent_of_absolute_depth():
    """A whole-multiple span asks for the same planes wherever the stack sits.

    This is the one the truncating ``int()`` got wrong: over randomly placed
    whole-multiple spans it dropped the top plane about half the time, whenever the
    division landed a hair under the integer.
    """
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
    """A leftover of more than half a step is dropped, not rounded up into a plane.

    Rounding here is what used to put the stepped path's last plane 0.4 um past *stop*
    and give it one more frame than the fast path over identical bounds.
    """
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


# plan_z_stack is pure arithmetic over scalars -- the two hardware-derived rates are
# arguments -- so the mode decision and the speed budgets are testable without a rig.
# A 10 ms exposure and a 100 Hz focus controller: both budgets are then in whole
# hundreds, which keeps the expected speeds below readable by hand.
RIG = dict(exposure=10e-3, position_fps=100.0)


@pytest.mark.parametrize("mode", ["fast", "stepped"])
def test_plan_z_stack_explicit_mode_is_never_overridden(mode):
    """Only "auto" asked to be decided for; the other two are instructions.

    Both spans below would go the *other* way under "auto" -- the first is a cheap sweep,
    the second a blur-capped crawl -- so an override would show up here.
    """
    for start, stop, step, max_dz in [(0.0, 40e-6, 1e-6, 5e-6), (0.0, 1e-3, 50e-6, 1e-7)]:
        plan = plan_z_stack(start, stop, step, mode=mode, max_dz_per_frame=max_dz, **RIG)
        assert plan.mode == mode


def test_plan_z_stack_auto_prefers_fast_for_an_ordinary_stack():
    # 40 um at 1 um steps: 41 planes, ~41 s stepped, against a sweep of well under a
    # second at the 50 um/s the sampling budget allows.
    plan = plan_z_stack(0.0, 40e-6, 1e-6, **RIG)
    assert plan.mode == "fast"


def test_plan_z_stack_auto_prefers_stepped_when_the_sweep_would_crawl():
    """A large step with a small blur budget is the case that flips the decision.

    21 planes over a millimetre, but a 0.1 um blur budget holds the sweep to 10 um/s, so
    it would take 100 s where stopping at each plane takes 21.
    """
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
    # ValueError, not an assert: this is a public argument, and it is the same failure
    # mode as a zero step, which commanded_depths already reports this way.
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
    """Three frames sharing a depth fill three planes rather than being refused.

    This used to raise: a prune dropped any frame within step/10 of the first or last,
    leaving one frame for three planes. That prune existed to undo the depth staircase
    stale position reports produced, which estimate_swept_frame_depths now removes
    upstream, so all it did afterwards was reject genuinely distinct frames and send the
    stack to the stepped fallback. Its removal is what makes this the same contract
    test_enforce_linear_z_stack_interpolate_refuses_to_invent_planes already asserts for
    the ten-frame case: with no interpolation a coarsely-resolved sweep is still usable,
    one real frame per plane, and only blending refuses it.
    """
    frames = [MockFrame(0.0, data=1), MockFrame(0.0, data=1), MockFrame(0.0, data=1)]
    result = enforce_linear_z_stack(frames, 0.0, 1.0, 0.5)  # expects 3 frames (0, 0.5, 1.0)
    assert len(result) == 3
    assert len({id(f) for f in result}) == 3
    # Blending the same stack is still a fiction and still refused.
    with pytest.raises(ValueError, match="two distinct frame depths"):
        enforce_linear_z_stack(frames, 0.0, 1.0, 0.5, interpolate=True)


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
    # The function assigns frames to expected depths using the Hungarian algorithm.
    # The algorithm minimizes the total cost, which is the sum of absolute differences
    # between expected depths and interpolated depths.
    assert result == [f0, f1, f2]


def test_enforce_linear_z_stack_descending_excess_frames():
    f0, f0_5, f1, f1_5, f2 = MockFrame(0.0), MockFrame(0.5), MockFrame(1.0), MockFrame(1.5), MockFrame(2.0)
    frames = [f2, f1_5, f1, f0_5, f0] # Sorted by depth: f0, f0_5, f1, f1_5, f2
    result = enforce_linear_z_stack(frames, 2.0, 0.0, -1.0) # expects 2, 1, 0
    # expected_depths will be [0, 1, 2] because start, stop are sorted internally.
    # The function assigns frames to expected depths using the Hungarian algorithm.
    # The algorithm minimizes the total cost, which is the sum of absolute differences
    # between expected depths and interpolated depths.
    assert result == [f0, f1, f2]


def test_enforce_linear_z_stack_ascending_grouped_depths():
    # Simulates stage updating z infrequently
    f0a, f0b = MockFrame(0.0, data=1), MockFrame(0.0, data=2) # different data
    f1a, f1b = MockFrame(1.0, data=11), MockFrame(1.0, data=12)
    f2a, f2b = MockFrame(2.0, data=21), MockFrame(2.0, data=22)
    frames = [f0a, f0b, f1a, f1b, f2a, f2b]
    result = enforce_linear_z_stack(frames, 0.0, 2.0, 1.0)
    # After pruning identical depths (if data was same), it would pick one.
    # difference_is_significant checks if the depth is NOT close to the first or last depth.
    # The Hungarian algorithm assigns frames to expected depths to minimize the total cost.
    # Note: We can't guarantee which specific frame will be chosen at each depth
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
    # The function internally sorts start/stop, so depths are still [0, 1, 2]
    # The algorithm assigns frames based on these depths
    assert len(result) == 3
    assert result[0].depth == 0.0
    assert result[1].depth == 1.0
    assert result[2].depth == 2.0


def test_enforce_linear_z_stack_start_equals_stop():
    f0 = MockFrame(0.0)
    frames = [f0, MockFrame(0.1), MockFrame(-0.1)]
    result = enforce_linear_z_stack(frames, 0.0, 0.0, 1.0) # expects 1 frame at 0.0
    # The closest frame to 0.0 is selected, but the algorithm might pick any of them
    assert len(result) == 1
    assert abs(result[0].depth) <= 0.10001 # Allow some tolerance for floating point errors


def test_enforce_linear_z_stack_non_exact_step_multiple():
    # (stop - start) % step != 0
    # start=0, stop=2.5, step=1.0 => expected depths [0.0, 1.0, 2.0]
    f0, f1, f2, f2_4 = MockFrame(0.0), MockFrame(1.0), MockFrame(2.0), MockFrame(2.4)
    frames = [f0, f1, f2, f2_4]
    result = enforce_linear_z_stack(frames, 0.0, 2.5, 1.0)
    # Verify we got frames at approximately expected depths
    assert len(result) == 3
    assert abs(result[0].depth - 0.0) < 0.1
    assert abs(result[1].depth - 1.0) < 0.1
    assert abs(result[2].depth - 2.0) < 0.5  # The closest to 2.0 could be either f2 or f2_4

    # start=0, stop=2.0, step=0.8 => expected depths [0.0, 0.8, 1.6]
    f0, f0_7, f0_9, f1_5, f1_7, f2_0 = MockFrame(0.0), MockFrame(0.7), MockFrame(0.9), MockFrame(1.5), MockFrame(1.7), MockFrame(2.0)
    frames = [f0, f0_7, f0_9, f1_5, f1_7, f2_0]
    result = enforce_linear_z_stack(frames, 0.0, 2.0, 0.8)
    # Verify we got frames at approximately expected depths
    assert len(result) == 3
    assert abs(result[0].depth - 0.0) < 0.1
    assert abs(result[1].depth - 0.8) < 0.2
    assert abs(result[2].depth - 1.6) < 0.4


def test_enforce_linear_z_stack_pruning_identical_frames():
    # difference_is_significant checks if the depth is NOT close to the first or last depth
    # This test assumes the default behavior of difference_is_significant
    f0a = MockFrame(0.0, data=1)
    f0b = MockFrame(0.0, data=1) # Identical depth
    f1a = MockFrame(1.0, data=2)
    f1b = MockFrame(1.0, data=2) # Identical depth
    f2  = MockFrame(2.0, data=3)
    frames = [f0a, f0b, f1a, f1b, f2]
    result = enforce_linear_z_stack(frames, 0.0, 2.0, 1.0)
    # After pruning, we should have one frame at each depth 0.0, 1.0, 2.0
    assert len(result) == 3
    assert result[0].depth == 0.0
    assert result[1].depth == 1.0
    assert result[2].depth == 2.0


def test_enforce_linear_z_stack_frames_not_perfectly_on_expected_depths():
    """Frames that miss their expected depth but land inside [start, stop] are still accepted,
    each keeping its own measured depth. Frames outside that range (beyond the 5e-7 m end
    tolerance) are deliberately discarded as movement artifacts, so a stack whose frames all
    straddle the ends has too few usable frames and raises."""
    # near misses inside the range are accepted, one per expected depth
    f_0, f_0_95, f_2 = MockFrame(0.0), MockFrame(0.95), MockFrame(2.0)
    result = enforce_linear_z_stack([f_0, f_0_95, f_2], 0.0, 2.0, 1.0) # expects 0, 1, 2
    assert result == [f_0, f_0_95, f_2]
    assert [f.depth for f in result] == [0.0, 0.95, 2.0]

    # frames just past the ends, but within the end tolerance, still count as in-range
    f_low, f_mid, f_high = MockFrame(-4e-7), MockFrame(0.95), MockFrame(2.0 + 4e-7)
    result = enforce_linear_z_stack([f_low, f_mid, f_high], 0.0, 2.0, 1.0)
    assert result == [f_low, f_mid, f_high]

    # frames well outside the range are movement artifacts and get trimmed; only 0.9 survives,
    # which is fewer than the three expected depths
    frames = [MockFrame(-0.1), MockFrame(0.9), MockFrame(2.1)] # depths: -0.1, 0.9, 2.1
    with pytest.raises(ValueError, match="Insufficient frames to have one frame per step."):
        enforce_linear_z_stack(frames, 0.0, 2.0, 1.0)


def test_enforce_linear_z_stack_descending_frames_not_perfectly_on_expected_depths():
    """Same contract as the ascending case for a descending sweep: start/stop are sorted
    internally, near misses inside the range are kept, and frames outside the range are
    discarded as movement artifacts rather than being pulled back to an expected depth."""
    # near misses inside the range are accepted
    f_0, f_0_95, f_2 = MockFrame(0.0), MockFrame(0.95), MockFrame(2.0)
    frames = [f_2, f_0_95, f_0] # depths sorted: 0.0, 0.95, 2.0
    result = enforce_linear_z_stack(frames, 2.0, 0.0, -1.0) # expects 2, 1, 0
    # Function sorts start/stop internally, so expected depths are still [0, 1, 2]
    assert result == [f_0, f_0_95, f_2]
    assert [f.depth for f in result] == [0.0, 0.95, 2.0]

    # frames well outside the range are movement artifacts and get trimmed; only 0.9 survives,
    # which is fewer than the three expected depths
    frames = [MockFrame(2.1), MockFrame(0.9), MockFrame(-0.1)] # depths sorted: -0.1, 0.9, 2.1
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
    # Test from a real-world scenario that was tricky
    # Depths are not perfectly aligned with steps
    frames = [fi_0_0, fi_0_1, fi_0_2, fi_0_3, fi_0_4, fi_0_5]
    start, stop, step = 0.0, 0.5, 0.1
    # Five whole steps, so six planes: (0.5 - 0.0) % 0.1 is not 0 in float, which used
    # to drop the top plane.
    result = enforce_linear_z_stack(frames, start, stop, step)
    # Verify we have the correct number of frames at the expected depths
    assert len(result) == 6
    for i, frame in enumerate(result):
        assert abs(frame.depth - i*0.1) < 0.01

def test_enforce_linear_z_stack_complex_case_2_descending():
    frames = [fi_0_5, fi_0_4, fi_0_3, fi_0_2, fi_0_1, fi_0_0] # reverse order input
    start, stop, step = 0.5, 0.0, -0.1
    # Same five steps, swept downward.
    result = enforce_linear_z_stack(frames, start, stop, step)
    # Verify we have the correct number of frames at the expected depths
    assert len(result) == 6
    for i, frame in enumerate(result):
        assert abs(frame.depth - i*0.1) < 0.01

def test_enforce_linear_z_stack_duplicate_depths_different_data_selection():
    # difference_is_significant currently only checks z values.
    # If it were to check data, this test would be more meaningful for that aspect.
    f0_a = MockFrame(0.0, data=1)
    f0_b = MockFrame(0.0, data=2) # different data, same depth
    f1 = MockFrame(1.0, data=3)
    frames = [f0_a, f0_b, f1]
    result = enforce_linear_z_stack(frames, 0.0, 1.0, 1.0) # expects 0.0, 1.0
    # We expect one frame at each depth
    assert len(result) == 2
    assert result[0].depth == 0.0
    assert result[1].depth == 1.0

    frames_rev = [f1, f0_b, f0_a] # Test different input order
    result_rev = enforce_linear_z_stack(frames_rev, 0.0, 1.0, 1.0)
    # We expect one frame at each depth
    assert len(result_rev) == 2
    assert result_rev[0].depth == 0.0
    assert result_rev[1].depth == 1.0

fi_0 = MockFrame(0.0)
fi_1 = MockFrame(1.0)
fi_2 = MockFrame(2.0)
fi_3 = MockFrame(3.0)
fi_4 = MockFrame(4.0)

def test_enforce_linear_z_stack_more_frames_than_steps_issue_scenario():
    # Scenario from a bug: start=0, stop=2, step=1. Frames at 0,1,2,3,4.
    frames = [fi_0, fi_1, fi_2, fi_3, fi_4]
    result = enforce_linear_z_stack(frames, 0.0, 2.0, 1.0)
    # We should get 3 frames
    assert len(result) == 3
    # The Hungarian algorithm assigns frames based on minimizing total cost
    # which means it might not select exactly 0,1,2 but frames that optimize the overall assignment
    depths = [f.depth for f in result]
    # Verify frames are returned in ascending order of expected depths
    assert depths == sorted(depths)
    # Verify we have frames that cover the range
    assert min(depths) <= 0.1
    assert max(depths) >= 1.9

def test_enforce_linear_z_stack_more_frames_than_steps_issue_scenario_desc():
    # Scenario from a bug: start=2, stop=0, step=-1. Frames at 0,1,2,3,4.
    frames = [fi_4, fi_3, fi_2, fi_1, fi_0] # sorted by depth: fi_0, fi_1, fi_2, fi_3, fi_4
    result = enforce_linear_z_stack(frames, 2.0, 0.0, -1.0)
    # We should get 3 frames 
    assert len(result) == 3
    # The Hungarian algorithm assigns frames based on minimizing total cost
    # which means it might not select exactly 0,1,2 but frames that optimize the overall assignment
    depths = [f.depth for f in result]
    # Function stores start/stop internally, so frames are returned in ascending order
    assert depths == sorted(depths)
    # Verify we have frames that cover the range
    assert min(depths) <= 0.1
    assert max(depths) >= 1.9

def test_enforce_linear_z_stack_start_stop_step_float_precision():
    f1 = MockFrame(0.1)
    f2 = MockFrame(0.2)
    f3 = MockFrame(0.30000000000000004) # numpy.arange(0.1, 0.3+0.1, 0.1) can produce this
    frames = [f1,f2,f3]
    result = enforce_linear_z_stack(frames, 0.1, 0.3, 0.1)
    # (0.3 - 0.1) % 0.1 is 0.0999999... not 0, which used to drop the top plane.
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
    def __init__(self, depth=0.0):
        self._info = {}
        self._depth = depth

    def globalTransform(self):
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
    """One addInfo per frame: the point of folding the two stamping passes into one."""
    frame = InfoFrame()
    stamp_z_stack_planes([frame], 2e-6, -1.5e-4)
    info = frame.info()
    assert set(info) == {"transform", "surfaceDepth"}
    # the z column now measures one plane-to-plane step
    assert np.linalg.norm(info["transform"].matrix[:, 2]) == pytest.approx(2e-6)


def test_stamp_z_stack_planes_signs_the_z_step_along_travel():
    """A descending stack steps in -z, so its z column must too, or the transform
    contradicts the order its frames come back in."""
    frame = InfoFrame()
    stamp_z_stack_planes([frame], -2e-6, None)
    assert frame.info()["transform"].matrix[2, 2] == pytest.approx(-2e-6)


class MockFocusDevice:
    hysteresisCorrection = 0

    def _interpretSpeed(self, speed):
        return 1e-4


class MockImager:
    """Just enough imager to drive _stepped_z_stack."""

    def __init__(self, depth=0.0):
        self.logger = None
        self._depth = depth
        self._focusDev = MockFocusDevice()

    def getFocusDevice(self):
        return self._focusDev

    def getFocusDepth(self):
        return self._depth

    def setFocusDepth(self, depth, speed, name=None):
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
    assert np.all(np.diff(est) >= -1e-15), "estimates must stay monotonic"
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
    """No cruise to fit, and the reporting gap grows as the sweep speeds up.

    Starting from rest also makes the first segment shallow, which is why the fit caps
    how far it will extrapolate to reach the resting depth -- without that cap the
    crossing lands arbitrarily far back and drags the whole fit with it.
    """
    frames, true, gap = sweep_profile("accelerating", report_every)
    raw_err, fit_err = fit_errors(frames, true)
    assert fit_err < raw_err
    assert fit_err < 0.6 * gap


def test_estimate_swept_frame_depths_is_no_worse_when_reports_nearly_keep_up():
    """Reports every other frame leave little staleness, so the fit has little to win.

    It can come out slightly worse here; what matters is that it stays bounded by the
    reporting gap rather than degrading.
    """
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


def test_estimate_swept_frame_depths_leaves_a_constant_stack_alone():
    frames = [TimedFrame(1.0, t * 0.05) for t in range(4)]
    estimate_swept_frame_depths(frames)
    assert [f.depth for f in frames] == [1.0] * 4


def test_estimate_swept_frame_depths_ignores_out_of_order_timestamps():
    frames = [TimedFrame(0.0, 1.0), TimedFrame(1.0, 0.0), TimedFrame(2.0, 2.0)]
    estimate_swept_frame_depths(frames)
    assert [f.depth for f in frames] == [0.0, 1.0, 2.0]


def _interp_frames():
    # Deliberately off the 0.0/1.0/2.0 grid.
    return [TimedFrame(d, i * 0.05, data=i + 1) for i, d in enumerate([0.0, 0.7, 1.4, 2.1])]


def test_enforce_linear_z_stack_interpolate_lands_exactly_on_commanded_depths():
    result = enforce_linear_z_stack(_interp_frames(), 0.0, 2.0, 1.0, interpolate=True)
    assert [f.depth for f in result] == pytest.approx([0.0, 1.0, 2.0])


def test_enforce_linear_z_stack_interpolate_emits_no_duplicate_planes():
    result = enforce_linear_z_stack(_interp_frames(), 0.0, 2.0, 1.0, interpolate=True)
    datas = [f.data() for f in result]
    for i in range(len(datas)):
        for j in range(i + 1, len(datas)):
            assert not np.array_equal(datas[i], datas[j])


def test_enforce_linear_z_stack_interpolate_blends_between_neighbours():
    result = enforce_linear_z_stack(_interp_frames(), 0.0, 2.0, 1.0, interpolate=True)
    # 1.0 sits between the frames at 0.7 and 1.4. MockFrame data is 10 * seed.
    lo, hi = 20.0, 30.0
    assert lo < result[1].data().mean() < hi


def test_enforce_linear_z_stack_interpolate_refuses_when_frames_fall_far_short():
    # Frames stop at 0.5; planes are wanted out to 2.0.
    frames = [TimedFrame(d, i * 0.05, data=i + 1) for i, d in enumerate([0.0, 0.25, 0.5])]
    with pytest.raises(ValueError, match="interpolate"):
        enforce_linear_z_stack(frames, 0.0, 2.0, 1.0, interpolate=True)


# --- rigs where frames do NOT outpace position reports: depths are already per-frame,
# so estimate_swept_frame_depths must leave them alone rather than smooth them.

def test_estimate_swept_frame_depths_is_a_noop_when_every_frame_has_its_own_depth():
    """One report per frame: no staleness to undo, so nothing to do."""
    original = [0.0, 1e-6, 2e-6, 3e-6, 4e-6]
    frames = [TimedFrame(d, i * 0.05) for i, d in enumerate(original)]
    estimate_swept_frame_depths(frames)
    assert [f.depth for f in frames] == pytest.approx(original)


def test_estimate_swept_frame_depths_is_a_noop_when_reports_outpace_frames():
    """Finely polled controller, slow camera: every depth is already fresh."""
    original = [0.0, 2e-6, 4e-6, 6e-6, 8e-6]
    frames = [TimedFrame(d, i * 0.5) for i, d in enumerate(original)]
    estimate_swept_frame_depths(frames)
    assert [f.depth for f in frames] == pytest.approx(original)


def test_estimate_swept_frame_depths_preserves_non_monotonic_per_frame_depths():
    """Jittery-but-distinct depths are data, not noise to smooth away."""
    original = [0.0, 1e-6, 0.5e-6, 2e-6, 3e-6]
    frames = [TimedFrame(d, i * 0.05) for i, d in enumerate(original)]
    estimate_swept_frame_depths(frames)
    assert [f.depth for f in frames] == pytest.approx(original)


def test_estimate_swept_frame_depths_leaves_tied_timestamps_alone():
    """Tied knot times would make np.interp choose arbitrarily."""
    frames = [TimedFrame(d, 0.0) for d in (1e-6, 1e-6, 2e-6, 2e-6)]
    estimate_swept_frame_depths(frames)
    assert [f.depth for f in frames] == pytest.approx([1e-6, 1e-6, 2e-6, 2e-6])


def test_estimate_swept_frame_depths_survives_frames_without_timestamps():
    class NoTime(TimedFrame):
        @property
        def time(self):
            raise KeyError("time")

    frames = [NoTime(d, 0.0) for d in (1e-6, 1e-6, 2e-6)]
    estimate_swept_frame_depths(frames)
    assert [f.depth for f in frames] == pytest.approx([1e-6, 1e-6, 2e-6])


def test_enforce_linear_z_stack_still_selects_on_a_one_report_per_frame_rig():
    """Selection must still work when de-quantization had nothing to do."""
    frames = [TimedFrame(i * 0.1, i * 0.05, data=i + 1) for i in range(6)]
    estimate_swept_frame_depths(frames)
    result = enforce_linear_z_stack(frames, 0.0, 0.5, 0.1)
    assert [f.depth for f in result] == pytest.approx([0.0, 0.1, 0.2, 0.3, 0.4, 0.5])
    assert len({id(f) for f in result}) == 6


def test_enforce_linear_z_stack_interpolate_refuses_to_invent_planes():
    """Plenty of frames, but only three depths among them: nine planes aren't in there.

    The shape left when de-quantization declines to run on a coarsely-reporting rig.
    """
    depths = [0.0] + [1.0] * 8 + [2.0]
    frames = [TimedFrame(d, i * 0.05, data=i + 1) for i, d in enumerate(depths)]
    with pytest.raises(ValueError, match="invent planes"):
        enforce_linear_z_stack(frames, 0.0, 2.0, 0.25, interpolate=True)
    # Without interpolation the same stack is still usable, one real frame per plane.
    result = enforce_linear_z_stack(frames, 0.0, 2.0, 0.25)
    assert len(result) == 9
    assert len({id(f) for f in result}) == 9


# --- select_planes: the seam between "what depth was each frame at" and "what does the
# caller get back". It is handed the planes rather than the bounds, so len(depths) is the
# answer to how many frames come back -- structurally, not by agreement between callers.


def _swept(depths, n=None):
    """Frames evenly covering *depths*, in acquisition order, distinct and timestamped."""
    depths = np.asarray(depths, dtype=float)
    n = n or 4 * len(depths)
    return [TimedFrame(d, i * 0.05, data=i + 1) for i, d in enumerate(np.linspace(depths[0], depths[-1], n))]


@pytest.mark.parametrize("interpolate", [False, True])
@pytest.mark.parametrize("n_frames", [6, 7, 23, 60])
def test_select_planes_returns_exactly_one_frame_per_commanded_depth(interpolate, n_frames):
    """len(depths) is the returned length, whatever the sweep happened to acquire."""
    depths = commanded_depths(0.0, 5e-6, 1e-6)
    result = select_planes(_swept(depths, n_frames), depths, interpolate=interpolate)
    assert len(result) == len(depths) == 6


@pytest.mark.parametrize("interpolate", [False, True])
def test_select_planes_returns_planes_in_the_order_it_was_asked_for(interpolate):
    """A descending stack asks for its planes descending and gets them that way, so the
    fast path and the stepped fallback agree on order as well as on count."""
    depths = commanded_depths(5e-6, 0.0, 1e-6)
    assert depths[0] > depths[-1]
    result = select_planes(_swept(depths), depths, interpolate=interpolate)
    got = [f.depth for f in result]
    assert got == sorted(got, reverse=True)


@pytest.mark.parametrize("start,stop", [(0.0, 5e-6), (5e-6, 0.0)])
def test_select_planes_interpolated_lands_exactly_on_the_commanded_depths(start, stop):
    depths = commanded_depths(start, stop, 1e-6)
    result = select_planes(_swept(depths), depths, interpolate=True)
    assert [f.depth for f in result] == pytest.approx(list(depths))


def test_select_planes_nearest_keeps_the_frames_own_measured_depths():
    """The nearest-frame path returns real exposures, so it reports where they were, not
    where they were wanted. Only interpolation gets to claim the commanded depth."""
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
    """Frames from the settle into and the overshoot out of the range belong to no plane."""
    depths = commanded_depths(0.0, 2e-6, 1e-6)
    inside = [MockFrame(d) for d in (0.0, 1e-6, 2e-6)]
    frames = [MockFrame(-3e-6), *inside, MockFrame(5e-6)]
    assert select_planes(frames, depths) == inside


def test_select_planes_keeps_frames_just_past_the_ends():
    """The end tolerance absorbs reporting jitter rather than trimming honest frames."""
    depths = commanded_depths(0.0, 2e-6, 1e-6)
    frames = [MockFrame(d) for d in (-4e-7, 1e-6, 2e-6 + 4e-7)]
    assert select_planes(frames, depths) == frames


def test_select_planes_rejects_empty_depths():
    with pytest.raises(ValueError, match="no commanded depths"):
        select_planes([MockFrame(0.0)], np.array([]))


def test_select_planes_rejects_too_few_frames_in_range():
    depths = commanded_depths(0.0, 2e-6, 1e-6)
    with pytest.raises(ValueError, match="Insufficient frames to have one frame per step"):
        select_planes([MockFrame(0.0), MockFrame(1e-6)], depths)


def test_select_planes_rejects_a_sweep_that_doubles_back():
    depths = commanded_depths(0.0, 2e-6, 1e-6)
    frames = [MockFrame(d) for d in (0.0, 2e-6, 1e-6, 2e-6)]
    with pytest.raises(ValueError, match="not monotonic by depth"):
        select_planes(frames, depths)


def test_select_planes_interpolate_rejects_a_single_distinct_depth():
    depths = commanded_depths(0.0, 2e-6, 1e-6)
    frames = [TimedFrame(1e-6, i * 0.05, data=i + 1) for i in range(4)]
    with pytest.raises(ValueError, match="two distinct frame depths"):
        select_planes(frames, depths, interpolate=True)


def test_select_planes_interpolate_rejects_fewer_distinct_depths_than_planes():
    depths = commanded_depths(0.0, 2e-6, 1e-6)
    frames = [TimedFrame(d, i * 0.05, data=i + 1) for i, d in enumerate([0.0, 0.0, 2e-6, 2e-6])]
    with pytest.raises(ValueError, match="invent planes"):
        select_planes(frames, depths, interpolate=True)


def test_select_planes_interpolate_rejects_frames_that_fall_far_short():
    depths = commanded_depths(0.0, 5e-6, 1e-6)
    frames = [TimedFrame(d, i * 0.05, data=i + 1) for i, d in enumerate(np.linspace(0.0, 1e-6, 8))]
    with pytest.raises(ValueError, match="to interpolate"):
        select_planes(frames, depths, interpolate=True)


def test_select_planes_leaves_the_nearest_paths_transforms_alone():
    """Stage B stops rewriting transforms: it used to restate each chosen frame's own
    depth back onto it, one of the two or three writes a returned frame used to collect
    before stamp_z_stack_planes got the last word."""
    depths = commanded_depths(0.0, 2e-6, 1e-6)

    class Tattling(MockFrame):
        writes = 0

        def addInfo(self, transform):
            type(self).writes += 1
            super().addInfo(transform)

    frames = [Tattling(d) for d in (0.0, 1e-6, 2e-6)]
    select_planes(frames, depths)
    assert Tattling.writes == 0


# --- the frame-count invariant, end to end across the seam: plan_z_stack decides the
# planes, select_planes fills them, and nothing in between gets to change how many.


@pytest.mark.parametrize("start,stop,step", SPANS)
def test_frame_count_survives_the_seam_whatever_the_interpolation(start, stop, step):
    """The same span and step yield the same count with interpolation on and off."""
    plan = plan_z_stack(start, stop, step, exposure=0.01, position_fps=100.0, mode="fast")
    frames = _swept(plan.depths)
    nearest = select_planes(frames, plan.depths, interpolate=False)
    blended = select_planes(frames, plan.depths, interpolate=True)
    assert len(nearest) == len(blended) == len(plan.depths)


def test_frame_count_survives_a_fallback_from_fast_to_stepped():
    """A fast attempt that fails and a stepped retry are handed the same plan, so the
    stack a caller gets cannot depend on whether a ValueError happened to fire."""
    start, stop, step = 1.0334e-3, 1.0334e-3 + 40.6e-6, 1e-6
    plan = plan_z_stack(start, stop, step, exposure=0.01, position_fps=100.0, mode="fast")
    # too few frames survive the range trim for the sweep to fill every plane
    with pytest.raises(ValueError, match="Insufficient frames"):
        select_planes(_swept(plan.depths, 5), plan.depths)
    stepped = _stepped_z_stack(MockImager(depth=start), plan.depths, "test")
    assert len(stepped) == len(plan.depths) == 41
