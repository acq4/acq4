import pytest
import numpy as np
from acq4.devices.OptomechDevice import Geometry


@pytest.fixture
def geometry():
    config = {"type": "box", "size": [1.0, 1.0, 1.0]}
    defaults = {}
    return Geometry(config, defaults)


def test_voxelized(geometry):
    resolution = 0.1
    template = geometry.voxelized(resolution)
    assert isinstance(template, np.ndarray)
    assert template.shape == (11, 11, 11)
    assert np.any(template)
    for axis in range(3):
        assert np.any(np.argmax(template, axis=axis) == 0)
        assert np.any(np.argmax(template[::-1], axis=axis) == 0)
    surface_area = np.sum(template) * resolution ** 2
    assert np.isclose(surface_area, 6.0, atol=0.1)


def test_voxelize_into(geometry):
    space = np.zeros((10, 10, 10), dtype=bool)
    resolution = 0.1
    xform = np.eye(4)  # Identity matrix as a placeholder for transformation

    geometry.get_geometries = lambda: [geometry]  # Mock get_geometries method
    geometry.handleTransformUpdate = lambda x: None  # Mock handleTransformUpdate method

    geometry.voxelize_into(space, resolution, xform)
    # Add assertions to verify the expected behavior
    assert False, 'todo'


def test_convolve_across(geometry):
    space = np.zeros((10, 10, 10), dtype=bool)
    geometry.convolve_across(space)
    # Add assertions to verify the expected behavior
    assert False, 'todo'


def test_get_geometries(geometry):
    geometries = geometry.get_geometries()
    assert isinstance(geometries, list)
    # Add more assertions to verify the expected behavior
    assert False, 'todo'
