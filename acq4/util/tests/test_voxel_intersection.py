import numpy as np
import pytest
from coorx import TTransform

from acq4.util.geometry import Volume, find_intersected_voxels_axial, line_intersects_voxel

CONTAINED_SEGMENTS = [
    pytest.param([0.2, 0.3, 0.4], [0.4, 0.5, 0.6], id='short'),
    pytest.param([0.1, 0.1, 0.1], [0.9, 0.9, 0.9], id='long-diagonal'),
    pytest.param([0.2, 0.3, 0.4], [0.2, 0.3, 0.4], id='point'),
]


@pytest.mark.parametrize('start, end', CONTAINED_SEGMENTS)
@pytest.mark.parametrize('voxel', [(0, 0, 0), (2, 4, 6), (-3, -5, -7)])
def test_segment_wholly_inside_voxel(start, end, voxel):
    voxel = np.array(voxel)
    start = voxel + start
    end = voxel + end

    assert line_intersects_voxel(start, end, voxel)
    assert line_intersects_voxel(end, start, voxel)
    assert not line_intersects_voxel(start, end, voxel + [1, 0, 0])


@pytest.mark.parametrize('start, end', CONTAINED_SEGMENTS)
def test_axial_search_includes_containing_voxel(start, end):
    voxel = np.array([2, 1, 3])
    space_max = np.array([4, 4, 4])

    assert set(find_intersected_voxels_axial(voxel + start, voxel + end, space_max)) == {(2, 1, 3)}


@pytest.mark.parametrize('start, end', CONTAINED_SEGMENTS)
def test_volume_intersects_contained_segment_in_parent_coordinates(start, end):
    data = np.zeros((5, 5, 5), dtype=bool)
    data[2, 1, 3] = True
    offset = np.array([10.0, 20.0, 30.0])
    volume = Volume(data, TTransform(offset=offset))
    start = (np.array([2, 1, 3]) + start)[::-1] + offset
    end = (np.array([2, 1, 3]) + end)[::-1] + offset

    assert volume.contains_point(start)
    assert volume.contains_point(end)
    assert volume.intersects_line(start, end)
    assert volume.intersects_line(end, start)
    assert not volume.intersects_line(start + [1, 0, 0], end + [1, 0, 0])
    assert not volume.intersects_line(start + [10, 0, 0], end + [10, 0, 0])


@pytest.mark.parametrize(
    'start, end, expected',
    [
        ([-1.0, 0.5, 0.5], [2.0, 0.5, 0.5], True),
        ([-1.0, 0.5, 0.5], [-0.1, 0.5, 0.5], False),
        ([-1.0, 1.5, 0.5], [2.0, 1.5, 0.5], False),
        ([-0.1, 0.5, 0.5], [-0.1, 0.5, 0.5], False),
    ],
)
def test_crossing_and_disjoint_segments(start, end, expected):
    voxel = np.array([0, 0, 0])
    assert line_intersects_voxel(np.array(start), np.array(end), voxel) == expected
    assert line_intersects_voxel(np.array(end), np.array(start), voxel) == expected
