import numpy as np
import pytest
import trimesh

from acq4.util.geometry import Geometry, truncated_cone


@pytest.mark.parametrize('close_top', [False, True])
@pytest.mark.parametrize('bottom_radius, top_radius', [(1.0, 1.0), (2.0, 0.5)])
def test_bottom_cap_faces_outward(bottom_radius, top_radius, close_top):
    vertices, faces = truncated_cone(
        bottom_radius, top_radius, 3.0, close_bottom=True, close_top=close_top, segments=16
    )
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    bottom_faces = np.all(mesh.triangles[:, :, 2] == 0.0, axis=1)

    assert bottom_faces.sum() == 16
    np.testing.assert_allclose(mesh.face_normals[bottom_faces], np.tile([0, 0, -1], (16, 1)))
    assert mesh.is_winding_consistent


@pytest.mark.parametrize('bottom_radius, top_radius', [(1.0, 1.0), (2.0, 0.5)])
def test_closed_cone_geometry_has_consistent_volume(bottom_radius, top_radius):
    segments = 16
    height = 3.0
    mesh = Geometry.make_cone(
        {
            'bottom_radius': bottom_radius,
            'top_radius': top_radius,
            'height': height,
            'close_bottom': True,
            'close_top': True,
            'segments': segments,
        }
    )

    assert mesh.is_watertight
    assert mesh.is_volume
    expected_volume = (
        segments
        * np.sin(2 * np.pi / segments)
        * height
        * (bottom_radius**2 + bottom_radius * top_radius + top_radius**2)
        / 6
    )
    mesh.apply_translation([4.0, -2.0, 5.0])
    assert mesh.volume == pytest.approx(expected_volume)
